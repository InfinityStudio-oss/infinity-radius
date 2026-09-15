"""Signed public transaction token — the only thing the captive portal's
payment-waiting screen ever holds to poll a transaction's status. Never
the transaction's raw database id: a client polling with a guessed/
incremented UUID must not be able to enumerate or read anyone else's
private transaction row.

Same Fernet-based scheme as app.core.router_token, with its own key
(TRANSACTION_TOKEN_SIGNING_KEY) — kept separate so leaking one token
type's key never affects the other.
"""

from functools import lru_cache
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    return Fernet(get_settings().transaction_token_signing_key.encode("utf-8"))


def create_transaction_token(transaction_id: UUID) -> str:
    return _fernet().encrypt(str(transaction_id).encode("utf-8")).decode("utf-8")


def resolve_transaction_token(token: str) -> UUID | None:
    """Returns the transaction UUID the token was issued for, or None if
    invalid/tampered — never raises, since this is called on fully
    untrusted public input."""
    try:
        raw = _fernet().decrypt(token.encode("utf-8"))
        return UUID(raw.decode("utf-8"))
    except (InvalidToken, ValueError):
        return None
