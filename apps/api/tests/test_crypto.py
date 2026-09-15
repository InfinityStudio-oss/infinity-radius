import pytest
from cryptography.fernet import Fernet

from app.core.crypto import SecretDecryptionError, decrypt_secret, encrypt_secret


def test_encrypt_then_decrypt_round_trips() -> None:
    ciphertext = encrypt_secret("a-real-radius-secret")
    assert decrypt_secret(ciphertext) == "a-real-radius-secret"


def test_ciphertext_is_never_the_plaintext() -> None:
    ciphertext = encrypt_secret("super-secret-value")
    assert "super-secret-value" not in ciphertext


def test_two_encryptions_of_the_same_plaintext_differ() -> None:
    """Fernet includes a random IV — encrypting the same value twice must
    not produce identical ciphertext (otherwise equal secrets would be
    distinguishable by comparing ciphertext, a real information leak)."""
    first = encrypt_secret("same-value")
    second = encrypt_secret("same-value")
    assert first != second


def test_tampered_ciphertext_fails_to_decrypt() -> None:
    ciphertext = encrypt_secret("a-real-secret")
    tampered = ciphertext[:-4] + ("A" if ciphertext[-4] != "A" else "B") + ciphertext[-3:]
    with pytest.raises(SecretDecryptionError):
        decrypt_secret(tampered)


def test_decrypting_with_the_wrong_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    ciphertext = encrypt_secret("a-real-secret")

    from app.core import crypto

    crypto._fernet.cache_clear()
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    from app.core.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(SecretDecryptionError):
        decrypt_secret(ciphertext)

    # Restore caches so later tests in this process see the real test key again.
    get_settings.cache_clear()
    crypto._fernet.cache_clear()
