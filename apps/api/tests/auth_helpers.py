"""Test-only helpers for minting Supabase-shaped JWTs.

Real Supabase projects sign access tokens asymmetrically (ES256/RS256)
against keys published at SUPABASE_JWKS_URL — there is no shared secret
to sign test tokens with anymore. So this module generates its own EC
keypair once per test run and signs with that; tests/conftest.py's
autouse `_stub_jwks` fixture makes app.core.security resolve every
token's signing key from TEST_PUBLIC_KEY instead of a real network call,
so the exact same verification code path (signature/issuer/audience/
expiry) runs in tests as in production — only the key source is faked.

Only `sub` (and `email`, for convenience) matter for resolving a caller —
tenant_id and role are resolved from the database by
app.core.security.get_current_user, not from token claims. Pair these
with tests/db_fixtures.py to seed the profile/role rows a token's `sub`
needs to resolve to something real.
"""

import time
from uuid import UUID

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

TEST_SUPABASE_URL = "https://test.supabase.co"
TEST_ISSUER = f"{TEST_SUPABASE_URL}/auth/v1"
TEST_KID = "test-signing-key"

# Generated once per test process — never written to disk, never the same
# key material a real Supabase project uses.
_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
TEST_PUBLIC_KEY = _PRIVATE_KEY.public_key()

# A second, unrelated keypair — used only to prove a token signed by an
# untrusted key is rejected (see tests/test_jwks_auth.py).
_OTHER_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())


def make_token(
    *,
    user_id: UUID,
    email: str = "test@example.test",
    expires_in_seconds: int = 3600,
    issuer: str = TEST_ISSUER,
    audience: str = "authenticated",
    signing_key: ec.EllipticCurvePrivateKey | None = None,
) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "aud": audience,
        "iss": issuer,
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    return jwt.encode(
        payload,
        signing_key or _PRIVATE_KEY,
        algorithm="ES256",
        headers={"kid": TEST_KID},
    )


def make_token_signed_by_untrusted_key(*, user_id: UUID) -> str:
    """A syntactically valid, well-formed token that nothing in this test
    process's trusted key set could have issued — must be rejected."""
    return make_token(user_id=user_id, signing_key=_OTHER_PRIVATE_KEY)


def auth_header(*, user_id: UUID, email: str = "test@example.test") -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user_id=user_id, email=email)}"}
