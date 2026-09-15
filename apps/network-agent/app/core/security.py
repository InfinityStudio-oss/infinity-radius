"""Verifies every request the FastAPI backend makes to this agent.

Scheme (must match apps/api/app/integrations/network_agent/signing.py
exactly on the caller's side):

    signature = HMAC-SHA256(
        key = shared secret,
        message = f"{timestamp}\\n{nonce}\\n{METHOD}\\n{path}\\n{sha256(body).hexdigest()}",
    )

sent as three headers alongside the request:

    X-Agent-Timestamp: unix epoch seconds
    X-Agent-Nonce:     random per-request token, never reused
    X-Agent-Signature: hex HMAC digest

A request is accepted only if:
  1. the signature verifies against the current OR previous active key
     (supports zero-downtime key rotation — see NetworkAgentSettings),
  2. the timestamp is within `request_max_skew_seconds` of server time, and
  3. the nonce has not been seen before within `nonce_cache_ttl_seconds`
     (replay protection).

This is the ONLY authentication this agent has — there is no session,
cookie, or bearer token. A plain shared-secret header (the previous scheme)
is vulnerable to replay if ever intercepted; signing the method+path+body
and binding it to a timestamp+nonce closes that gap.
"""

import hashlib
import hmac
import time
from functools import lru_cache

from fastapi import Header, HTTPException, Request, status

from app.core.config import get_network_agent_settings
from app.core.nonce_cache import NonceCache


@lru_cache
def get_nonce_cache() -> NonceCache:
    settings = get_network_agent_settings()
    return NonceCache(ttl_seconds=settings.nonce_cache_ttl_seconds)


def _canonical_message(*, timestamp: str, nonce: str, method: str, path: str, body: bytes) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    message = f"{timestamp}\n{nonce}\n{method.upper()}\n{path}\n{body_hash}"
    return message.encode("utf-8")


def _signature_is_valid(
    message: bytes, *, provided_signature: str, active_keys: tuple[str, ...]
) -> bool:
    for key in active_keys:
        expected = hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, provided_signature):
            return True
    return False


async def verify_agent_signature(
    request: Request,
    x_agent_timestamp: str | None = Header(default=None),
    x_agent_nonce: str | None = Header(default=None),
    x_agent_signature: str | None = Header(default=None),
) -> None:
    settings = get_network_agent_settings()

    if not x_agent_timestamp or not x_agent_nonce or not x_agent_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing request signature headers",
        )

    try:
        request_time = int(x_agent_timestamp)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid timestamp"
        ) from exc

    skew = abs(int(time.time()) - request_time)
    if skew > settings.request_max_skew_seconds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Request timestamp outside allowed skew",
        )

    body = await request.body()
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"
    message = _canonical_message(
        timestamp=x_agent_timestamp,
        nonce=x_agent_nonce,
        method=request.method,
        path=path,
        body=body,
    )

    if not _signature_is_valid(
        message, provided_signature=x_agent_signature, active_keys=settings.active_signing_keys
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    # Only recorded once the signature is confirmed valid — an attacker
    # spamming garbage signatures with reused nonces shouldn't be able to
    # burn through legitimate future nonces (there aren't any to burn,
    # since nonces are random per-request, but this ordering is the
    # correct general principle: never let unauthenticated input consume
    # a security-relevant resource).
    nonce_cache = get_nonce_cache()
    if await nonce_cache.seen_before(x_agent_nonce):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Nonce already used (replay)"
        )
