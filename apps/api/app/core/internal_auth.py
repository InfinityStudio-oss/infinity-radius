"""Dedicated HMAC-SHA256 service-to-service authentication for the
worker -> web internal disbursement-reconciliation endpoint (see
app/api/v1/internal_disbursements.py and
app/integrations/internal_web/client.py) — never a tenant JWT, never the
Super Admin JWT, and never Railway private networking alone (a service on
the same private network could still reach this route by hostname; a
cryptographic signature is required regardless of network path).

Canonical string follows the exact convention already used for Network
Agent request signing (app/integrations/network_agent/signing.py):

    HMAC-SHA256(secret, f"{timestamp}\\n{nonce}\\n{METHOD}\\n{path}\\n{sha256(body).hexdigest()}")

Deliberately a separate module and a separate secret
(Settings.internal_worker_web_hmac_key) from Network Agent signing —
same proven pattern, different trust boundary (worker<->web, not
Railway<->VPS), never sharing a key with it.
"""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

import redis.asyncio as redis_asyncio
from fastapi import HTTPException, Request, status

from app.core.config import get_settings

DEFAULT_MAX_SKEW_SECONDS = 90
_NONCE_KEY_PREFIX = "internal-auth-nonce:"
# Comfortably longer than any sane timestamp tolerance, so a replay is
# rejected for the entire window a (still-fresh-looking) timestamp/
# signature pair would otherwise be accepted.
_NONCE_TTL_SECONDS = 300

_HEADER_TIMESTAMP = "X-Internal-Timestamp"
_HEADER_NONCE = "X-Internal-Nonce"
_HEADER_SIGNATURE = "X-Internal-Signature"


class InternalAuthError(Exception):
    """Raised for any failed verification. The HTTP layer turns every one
    of these into the same generic 401 body — missing signature, bad
    signature, stale timestamp, future-skewed timestamp, and a replayed
    nonce are all indistinguishable to the caller, on purpose."""


@dataclass(frozen=True)
class SignedRequestHeaders:
    timestamp: str
    nonce: str
    signature: str

    def as_dict(self) -> dict[str, str]:
        return {
            _HEADER_TIMESTAMP: self.timestamp,
            _HEADER_NONCE: self.nonce,
            _HEADER_SIGNATURE: self.signature,
        }


def _canonical_message(
    *, timestamp: str, nonce: str, method: str, path: str, body: bytes
) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    return f"{timestamp}\n{nonce}\n{method.upper()}\n{path}\n{body_hash}".encode()


def sign_internal_request(
    *, secret: str, method: str, path: str, body: bytes = b""
) -> SignedRequestHeaders:
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    message = _canonical_message(
        timestamp=timestamp, nonce=nonce, method=method, path=path, body=body
    )
    signature = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return SignedRequestHeaders(timestamp=timestamp, nonce=nonce, signature=signature)


async def verify_internal_request(
    *,
    secret: str,
    method: str,
    path: str,
    body: bytes,
    timestamp: str | None,
    nonce: str | None,
    signature: str | None,
    redis_client: redis_asyncio.Redis,
    max_skew_seconds: int = DEFAULT_MAX_SKEW_SECONDS,
) -> None:
    """Raises InternalAuthError on any failure; returns None (never a
    value) on success — the caller only needs to know verification
    passed. Nonce replay protection is atomic (`SET NX EX`) so two
    concurrent requests bearing the same (stolen/replayed) nonce can
    never both pass."""
    if not timestamp or not nonce or not signature:
        raise InternalAuthError("missing signature headers")

    try:
        request_time = int(timestamp)
    except ValueError as exc:
        raise InternalAuthError("invalid timestamp") from exc

    if abs(int(time.time()) - request_time) > max_skew_seconds:
        raise InternalAuthError("timestamp outside tolerance")

    expected_message = _canonical_message(
        timestamp=timestamp, nonce=nonce, method=method, path=path, body=body
    )
    expected_signature = hmac.new(
        secret.encode("utf-8"), expected_message, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        raise InternalAuthError("signature mismatch")

    nonce_key = f"{_NONCE_KEY_PREFIX}{nonce}"
    claimed = await redis_client.set(nonce_key, "1", nx=True, ex=_NONCE_TTL_SECONDS)
    if not claimed:
        raise InternalAuthError("nonce already used")


async def require_internal_auth(request: Request) -> None:
    """FastAPI dependency guarding app/api/v1/internal_disbursements.py —
    the ONLY authentication that route accepts. Deliberately never a
    tenant JWT, never the Super Admin JWT: this route is reached from the
    Celery worker, not a browser, and Railway private networking alone is
    a transport, not proof of identity, so every request still needs a
    valid signature over its exact method/path/body regardless of which
    network it arrived over. Every failure mode (missing headers, bad
    signature, stale/future timestamp, reused nonce) collapses to the
    same generic 401 — see verify_internal_request/InternalAuthError."""
    settings = get_settings()
    if not settings.internal_worker_web_hmac_key:
        # Fails closed: an unconfigured secret must never be treated as
        # "auth disabled" — the route is unusable until an operator sets
        # INTERNAL_WORKER_WEB_HMAC_KEY, not silently open.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal auth is not configured",
        )

    body = await request.body()
    # A fresh connection per request, not a cached process-wide client —
    # this path is low-frequency (Celery Beat sweeps at most every couple
    # of minutes, never a hot path like the general rate limiter in
    # app/middleware/rate_limit.py), so the connection overhead is
    # negligible, and it sidesteps redis.asyncio connections being bound
    # to the event loop that created them (see app/db/session.py's
    # docstring for the same class of issue with asyncpg).
    redis_client: redis_asyncio.Redis = redis_asyncio.from_url(  # type: ignore[no-untyped-call]
        str(settings.redis_url)
    )
    try:
        await verify_internal_request(
            secret=settings.internal_worker_web_hmac_key,
            method=request.method,
            path=request.url.path,
            body=body,
            timestamp=request.headers.get(_HEADER_TIMESTAMP),
            nonce=request.headers.get(_HEADER_NONCE),
            signature=request.headers.get(_HEADER_SIGNATURE),
            redis_client=redis_client,
            max_skew_seconds=settings.internal_request_max_skew_seconds,
        )
    except InternalAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        ) from exc
    finally:
        await redis_client.aclose()
