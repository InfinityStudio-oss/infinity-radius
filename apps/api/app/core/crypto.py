"""Encryption at rest for MikroTik/RADIUS secrets (router credentials,
RADIUS shared secrets, WireGuard private keys) — Fernet (AES-128-CBC +
HMAC-SHA256, authenticated) keyed by SECRETS_ENCRYPTION_KEY.

Deliberately a *different* key from app.core.router_token's signing key:
that token is handed to semi-public infrastructure (baked into a router's
hotspot config); this key must never leave the server. Reusing one key for
both would let a leak of one compromise the other.

Generate a real key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

__all__ = ["SecretDecryptionError", "decrypt_secret", "encrypt_secret"]


class SecretDecryptionError(ValueError):
    """Raised when ciphertext fails to decrypt — wrong key, or tampered/corrupt data."""


@lru_cache
def _fernet() -> Fernet:
    return Fernet(get_settings().secrets_encryption_key.encode("utf-8"))


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretDecryptionError("Could not decrypt secret") from exc
