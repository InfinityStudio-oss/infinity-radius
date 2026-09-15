"""Unit tests for the Network Agent request-signing scheme. Cross-checks
against an independently recomputed HMAC (the exact algorithm
apps/network-agent/app/core/security.py verifies against) rather than just
asserting internal self-consistency."""

import hashlib
import hmac

from app.integrations.network_agent.signing import sign_request


def test_signature_matches_independent_recomputation() -> None:
    headers = sign_request(api_key="k", method="post", path="/x", body=b"body")

    body_hash = hashlib.sha256(b"body").hexdigest()
    message = f"{headers.timestamp}\n{headers.nonce}\nPOST\n/x\n{body_hash}".encode()
    expected = hmac.new(b"k", message, hashlib.sha256).hexdigest()

    assert headers.signature == expected


def test_empty_body_hashes_to_the_well_known_sha256_of_empty_string() -> None:
    headers = sign_request(api_key="k", method="GET", path="/y")

    message = (
        f"{headers.timestamp}\n{headers.nonce}\nGET\n/y\n"
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855".encode()
    )
    expected = hmac.new(b"k", message, hashlib.sha256).hexdigest()

    assert headers.signature == expected


def test_each_call_generates_a_fresh_nonce_and_therefore_a_fresh_signature() -> None:
    first = sign_request(api_key="k", method="GET", path="/x")
    second = sign_request(api_key="k", method="GET", path="/x")

    assert first.nonce != second.nonce
    assert first.signature != second.signature


def test_as_dict_exposes_exactly_the_three_signing_headers() -> None:
    headers = sign_request(api_key="k", method="GET", path="/x").as_dict()

    assert set(headers) == {"X-Agent-Timestamp", "X-Agent-Nonce", "X-Agent-Signature"}
