"""Unit tests for the internal worker->web HMAC scheme
(app/core/internal_auth.py) — the dedicated auth for
app/api/v1/internal_disbursements.py. Covers the algorithm itself
(cross-checked against an independently recomputed HMAC, same technique
as test_network_agent_signing.py) and the async verify path's replay
protection against a real local Redis (REDIS_URL is pinned to
localhost in tests/conftest.py)."""

import hashlib
import hmac
import time
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import redis.asyncio as redis_asyncio

from app.core.internal_auth import (
    InternalAuthError,
    sign_internal_request,
    verify_internal_request,
)


def test_signature_matches_independent_recomputation() -> None:
    headers = sign_internal_request(secret="k", method="post", path="/x", body=b"body")

    body_hash = hashlib.sha256(b"body").hexdigest()
    message = f"{headers.timestamp}\n{headers.nonce}\nPOST\n/x\n{body_hash}".encode()
    expected = hmac.new(b"k", message, hashlib.sha256).hexdigest()

    assert headers.signature == expected


def test_empty_body_hashes_to_the_well_known_sha256_of_empty_string() -> None:
    headers = sign_internal_request(secret="k", method="GET", path="/y")

    message = (
        f"{headers.timestamp}\n{headers.nonce}\nGET\n/y\n"
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855".encode()
    )
    expected = hmac.new(b"k", message, hashlib.sha256).hexdigest()

    assert headers.signature == expected


def test_each_call_generates_a_fresh_nonce_and_therefore_a_fresh_signature() -> None:
    first = sign_internal_request(secret="k", method="GET", path="/x")
    second = sign_internal_request(secret="k", method="GET", path="/x")

    assert first.nonce != second.nonce
    assert first.signature != second.signature


def test_as_dict_exposes_exactly_the_three_signing_headers() -> None:
    headers = sign_internal_request(secret="k", method="GET", path="/x").as_dict()

    assert set(headers) == {
        "X-Internal-Timestamp",
        "X-Internal-Nonce",
        "X-Internal-Signature",
    }


@pytest.fixture
async def redis_client() -> AsyncIterator[redis_asyncio.Redis]:
    """A fresh connection per test, not the process-wide cached client
    (get_internal_auth_redis_client) — each async test here runs in its
    own event loop (pytest-asyncio's default function-scoped loop), and
    redis.asyncio connections, like asyncpg's, are bound to the loop that
    created them (see app/db/session.py's docstring for the same issue).
    The cached singleton is exactly right for the real app (one event
    loop for the whole process) but wrong to reuse across independent
    test event loops."""
    conn = redis_asyncio.from_url("redis://localhost:6379/0")  # type: ignore[no-untyped-call]
    yield conn
    await conn.aclose()


async def test_valid_signature_is_accepted(redis_client: redis_asyncio.Redis) -> None:
    headers = sign_internal_request(secret="k", method="POST", path="/p", body=b"{}")

    await verify_internal_request(
        secret="k",
        method="POST",
        path="/p",
        body=b"{}",
        timestamp=headers.timestamp,
        nonce=headers.nonce,
        signature=headers.signature,
        redis_client=redis_client,
    )


async def test_missing_headers_are_rejected(redis_client: redis_asyncio.Redis) -> None:
    with pytest.raises(InternalAuthError):
        await verify_internal_request(
            secret="k",
            method="POST",
            path="/p",
            body=b"{}",
            timestamp=None,
            nonce=None,
            signature=None,
            redis_client=redis_client,
        )


async def test_bad_signature_is_rejected(redis_client: redis_asyncio.Redis) -> None:
    headers = sign_internal_request(secret="k", method="POST", path="/p", body=b"{}")

    with pytest.raises(InternalAuthError):
        await verify_internal_request(
            secret="k",
            method="POST",
            path="/p",
            body=b"{}",
            timestamp=headers.timestamp,
            nonce=headers.nonce,
            signature="0" * 64,
            redis_client=redis_client,
        )


async def test_signature_signed_with_wrong_secret_is_rejected(
    redis_client: redis_asyncio.Redis,
) -> None:
    headers = sign_internal_request(secret="wrong-secret", method="POST", path="/p", body=b"{}")

    with pytest.raises(InternalAuthError):
        await verify_internal_request(
            secret="k",
            method="POST",
            path="/p",
            body=b"{}",
            timestamp=headers.timestamp,
            nonce=headers.nonce,
            signature=headers.signature,
            redis_client=redis_client,
        )


async def test_tampered_body_is_rejected(redis_client: redis_asyncio.Redis) -> None:
    headers = sign_internal_request(secret="k", method="POST", path="/p", body=b"{}")

    with pytest.raises(InternalAuthError):
        await verify_internal_request(
            secret="k",
            method="POST",
            path="/p",
            body=b'{"tampered": true}',
            timestamp=headers.timestamp,
            nonce=headers.nonce,
            signature=headers.signature,
            redis_client=redis_client,
        )


async def test_expired_timestamp_is_rejected(redis_client: redis_asyncio.Redis) -> None:
    stale_timestamp = str(int(time.time()) - 300)
    message = f"{stale_timestamp}\nn\nPOST\n/p\n{hashlib.sha256(b'{}').hexdigest()}".encode()
    signature = hmac.new(b"k", message, hashlib.sha256).hexdigest()

    with pytest.raises(InternalAuthError):
        await verify_internal_request(
            secret="k",
            method="POST",
            path="/p",
            body=b"{}",
            timestamp=stale_timestamp,
            nonce="n",
            signature=signature,
            redis_client=redis_client,
            max_skew_seconds=90,
        )


async def test_future_skewed_timestamp_is_rejected(redis_client: redis_asyncio.Redis) -> None:
    future_timestamp = str(int(time.time()) + 300)
    message = f"{future_timestamp}\nn\nPOST\n/p\n{hashlib.sha256(b'{}').hexdigest()}".encode()
    signature = hmac.new(b"k", message, hashlib.sha256).hexdigest()

    with pytest.raises(InternalAuthError):
        await verify_internal_request(
            secret="k",
            method="POST",
            path="/p",
            body=b"{}",
            timestamp=future_timestamp,
            nonce="n",
            signature=signature,
            redis_client=redis_client,
            max_skew_seconds=90,
        )


async def test_reused_nonce_is_rejected(redis_client: redis_asyncio.Redis) -> None:
    """A second request replaying the exact same (valid) timestamp/nonce/
    signature must be rejected even though the signature itself is
    genuine — this is what distinguishes replay protection from mere
    signature verification."""
    path = f"/replay/{uuid4()}"
    headers = sign_internal_request(secret="k", method="POST", path=path, body=b"{}")

    await verify_internal_request(
        secret="k",
        method="POST",
        path=path,
        body=b"{}",
        timestamp=headers.timestamp,
        nonce=headers.nonce,
        signature=headers.signature,
        redis_client=redis_client,
    )  # first use: accepted

    with pytest.raises(InternalAuthError):
        await verify_internal_request(
            secret="k",
            method="POST",
            path=path,
            body=b"{}",
            timestamp=headers.timestamp,
            nonce=headers.nonce,
            signature=headers.signature,
            redis_client=redis_client,
        )  # replay: rejected
