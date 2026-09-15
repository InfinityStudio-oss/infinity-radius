"""Direct coverage of app.core.security's JWKS-based JWT verification —
signature, issuer, audience, and expiry are all genuinely checked here
(only the signing-key *source* is stubbed to a local test keypair, see
tests/conftest.py's autouse `_stub_jwks` fixture). Proves the backend
never accepts a token it didn't actually verify.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.security import _decode_token
from tests.auth_helpers import (
    TEST_ISSUER,
    make_token,
    make_token_signed_by_untrusted_key,
)


def test_valid_token_is_accepted() -> None:
    user_id = uuid4()
    token = make_token(user_id=user_id)
    claims = _decode_token(token)
    assert claims["sub"] == str(user_id)
    assert claims["iss"] == TEST_ISSUER
    assert claims["aud"] == "authenticated"


def test_expired_token_is_rejected() -> None:
    token = make_token(user_id=uuid4(), expires_in_seconds=-60)
    with pytest.raises(HTTPException) as exc_info:
        _decode_token(token)
    assert exc_info.value.status_code == 401


def test_token_with_wrong_issuer_is_rejected() -> None:
    token = make_token(user_id=uuid4(), issuer="https://not-our-project.supabase.co/auth/v1")
    with pytest.raises(HTTPException) as exc_info:
        _decode_token(token)
    assert exc_info.value.status_code == 401


def test_token_with_wrong_audience_is_rejected() -> None:
    token = make_token(user_id=uuid4(), audience="some-other-audience")
    with pytest.raises(HTTPException) as exc_info:
        _decode_token(token)
    assert exc_info.value.status_code == 401


def test_token_signed_by_untrusted_key_is_rejected() -> None:
    """A well-formed token that isn't signed by anything in our trusted
    key set — the exact shape an attacker who doesn't have Supabase's
    private signing key would produce."""
    token = make_token_signed_by_untrusted_key(user_id=uuid4())
    with pytest.raises(HTTPException) as exc_info:
        _decode_token(token)
    assert exc_info.value.status_code == 401


def test_malformed_token_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _decode_token("this-is-not-a-jwt")
    assert exc_info.value.status_code == 401


def test_empty_token_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _decode_token("")
    assert exc_info.value.status_code == 401
