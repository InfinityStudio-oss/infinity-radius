"""Authentication and tenant-context resolution.

Supabase Auth issues the JWT; we verify its signature — using the
project's real published public signing keys, fetched from
SUPABASE_JWKS_URL, never a shared secret — to know WHO is calling
(`sub`). Everything else — tenant_id and role(s) — is looked up fresh
from `public.profiles` / `public.profile_roles` on every request, never
trusted from the token's claims. This mirrors the RLS design (see
`public.current_tenant_id()` in the rls_policies migration): a tenant_id
supplied by the client, even inside a signed JWT's app_metadata, is never
treated as authoritative on its own — the database row is.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.roles import Role
from app.db.session import get_db
from app.models.tenancy import Profile, ProfileRole, Tenant
from app.models.tenancy import Role as RoleModel

bearer_scheme = HTTPBearer(auto_error=False)

# Supabase's asymmetric JWT Signing Keys use ES256 (its current default)
# or RS256 (its earlier asymmetric option) — never a symmetric HS* alg,
# which would let anyone who can read this list forge a token. The actual
# key used is whichever one the JWKS entry matching the token's `kid`
# publishes; jwt.decode still checks the token's own `alg` header is in
# this list before trusting it.
_ALLOWED_ALGORITHMS = ["ES256", "RS256"]

_jwk_client: PyJWKClient | None = None


def _get_jwk_client() -> PyJWKClient:
    """Lazily-constructed, process-wide singleton. PyJWKClient caches the
    fetched key set in memory (cache_jwk_set=True, the default) and
    re-fetches automatically whenever a token's `kid` isn't found in the
    cache — the standard way signing-key rotation is handled without a
    manual TTL loop. `lifespan` additionally forces a refresh after 10
    minutes even if no unknown `kid` shows up, so a revoked key can't
    stay trusted indefinitely from a stale cache.

    Tests never construct a real one — see tests/conftest.py's autouse
    `_stub_jwks` fixture, which replaces this function entirely so no
    test depends on network access or a real Supabase project.
    """
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(
            get_settings().supabase_jwks_url,
            cache_keys=True,
            lifespan=600,
        )
    return _jwk_client


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    email: str | None
    tenant_id: UUID | None
    # None for a platform-wide account (tenant_id is None) or, in the rare
    # case, a tenant_id that no longer resolves to a row. Populated
    # alongside tenant_id in get_current_user — see app.core.context's
    # get_tenant_context for where this actually gates access.
    tenant_status: str | None
    roles: frozenset[str]

    def has_role(self, *allowed: str) -> bool:
        return bool(self.roles.intersection(allowed))

    @property
    def is_super_admin(self) -> bool:
        return Role.SUPER_ADMIN in self.roles


def _decode_token(token: str) -> dict[str, Any]:
    """Verifies the JWT's signature against Supabase's real published
    public keys (never a shared secret, never `verify_signature=False`)
    and returns its claims. The claims are used only to identify WHO the
    caller is (`sub`/`email`) — tenant_id and role are never read from
    here; see get_current_user.

    jwt.decode, given no `options` override, verifies signature +
    expiry + not-before by default; audience and issuer are checked
    explicitly below. A malformed token, an expired one, one signed by an
    unknown key, or one with the wrong audience/issuer all raise
    PyJWTError/PyJWKClientError here and come back as 401 — never treated
    as valid.
    """
    settings = get_settings()
    try:
        signing_key = _get_jwk_client().get_signing_key_from_jwt(token)
    except jwt.PyJWKClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        ) from exc

    try:
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=_ALLOWED_ALGORITHMS,
            audience="authenticated",
            issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        ) from exc


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    claims = _decode_token(credentials.credentials)
    user_id = UUID(claims["sub"])

    profile = await db.get(Profile, user_id)
    if profile is None:
        # A verified Supabase session with no matching profiles row — either
        # the provisioning trigger hasn't run yet, or the account was removed.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No profile found for this account",
        )

    role_rows = await db.execute(
        select(RoleModel.code)
        .join(ProfileRole, ProfileRole.role_id == RoleModel.id)
        .where(ProfileRole.profile_id == user_id)
    )
    roles = frozenset(role_rows.scalars().all())

    tenant_status: str | None = None
    if profile.tenant_id is not None:
        tenant_status = await db.scalar(
            select(Tenant.status).where(Tenant.id == profile.tenant_id)
        )

    return AuthenticatedUser(
        id=user_id,
        email=profile.email or claims.get("email"),
        tenant_id=profile.tenant_id,
        tenant_status=tenant_status,
        roles=roles,
    )


def require_role(*allowed_roles: str) -> Callable[..., Awaitable[AuthenticatedUser]]:
    """Dependency factory enforcing RBAC on top of a verified Supabase session
    and its database-resolved role(s)."""

    async def _check(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not user.has_role(*allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _check
