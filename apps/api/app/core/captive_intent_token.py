"""The short-lived credential that authorizes ONE captive-portal payment
attempt.

Deliberately a third key, separate from both existing token keys:

    ROUTER_TOKEN_SIGNING_KEY       permanent site identifier. Lives inside
                                   every router's hotspot configuration and
                                   is handed to every customer who
                                   associates with that AP. Long-lived by
                                   design.
    TRANSACTION_TOKEN_SIGNING_KEY  read-only status polling for one
                                   already-created transaction.
    CAPTIVE_INTENT_TOKEN_SIGNING_KEY   authorizes CREATING a payment.

Reusing the router key here would make an intercepted, effectively
permanent site identifier sufficient to start payments forever. This key
is never in a router's config, never reaches a browser as a secret, and
the token it signs expires.

The token carries only a captive_sessions row id. Everything that matters
— tenant, router, nonce, expiry, consumed state — is read server-side from
that row, so a client cannot influence any of it by editing the token.
Fernet gives authentication and encryption (the session id is not even
visible) plus a verifiable embedded timestamp, which is what `ttl` below
enforces.

Two independent expiries on purpose: the cryptographic TTL here, and
`captive_sessions.expires_at` checked in the database. A token that
survives one must still fail the other, and only the database row can
record single-use consumption.
"""

from functools import lru_cache
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class CaptiveIntentNotConfiguredError(RuntimeError):
    """CAPTIVE_INTENT_TOKEN_SIGNING_KEY is not set.

    Raised lazily, only when a captive payment session is actually
    requested — the app must never fail to boot over it, matching how
    Selcom credentials are handled.
    """


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().captive_intent_token_signing_key
    if not key:
        raise CaptiveIntentNotConfiguredError(
            "CAPTIVE_INTENT_TOKEN_SIGNING_KEY is not set — captive payment "
            "sessions cannot be issued."
        )
    return Fernet(key.encode("utf-8"))


def create_captive_intent_token(captive_session_id: UUID) -> str:
    return _fernet().encrypt(str(captive_session_id).encode("utf-8")).decode("utf-8")


def resolve_captive_intent_token(token: str) -> UUID | None:
    """Returns the captive_sessions id this token was issued for, or None
    if it is invalid, tampered with, or older than
    CAPTIVE_INTENT_TOKEN_TTL_SECONDS.

    Never raises on bad input — this is called on fully untrusted public
    data, and every failure mode must be indistinguishable to the caller
    so a client cannot probe which part of a forged token was wrong.
    """
    settings = get_settings()
    try:
        raw = _fernet().decrypt(
            token.encode("utf-8"), ttl=settings.captive_intent_token_ttl_seconds
        )
        return UUID(raw.decode("utf-8"))
    except (InvalidToken, ValueError, CaptiveIntentNotConfiguredError):
        return None
