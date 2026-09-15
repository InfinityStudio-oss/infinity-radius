"""AuthContext / TenantContext — the only two ways a route handler learns
who is calling and which tenant they belong to. Both are resolved from the
database (see app.core.security.get_current_user), never from a client-
supplied value, so `TenantContext.tenant_id` is safe to pass straight into
a repository's tenant filter with no further validation.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status

from app.core.enums import TenantStatus
from app.core.security import AuthenticatedUser, get_current_user

# AuthContext is simply the verified, database-resolved caller — kept as an
# alias so route signatures read `AuthContext = Depends(get_auth_context)`
# rather than reaching into app.core.security directly.
AuthContext = AuthenticatedUser


async def get_auth_context(user: AuthenticatedUser = Depends(get_current_user)) -> AuthContext:
    return user


@dataclass(frozen=True)
class TenantContext:
    """A caller who is guaranteed to belong to exactly one tenant — every
    tenant-scoped route depends on this instead of AuthContext directly, so
    a platform-wide super admin calling a tenant-only route is rejected
    before any repository/service code runs.
    """

    tenant_id: UUID
    user: AuthenticatedUser


async def get_tenant_context(user: AuthenticatedUser = Depends(get_current_user)) -> TenantContext:
    if user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not scoped to a tenant",
        )
    # Backend-enforced, not just a frontend redirect: a tenant that's
    # pending review, rejected, suspended, or waiting on more information
    # gets no access to any tenant-scoped endpoint, regardless of what the
    # frontend does. A SUPER_ADMIN calling a tenant route never reaches
    # here (their own tenant_id is always None), so this check applies
    # only to actual tenant staff.
    if user.tenant_status != TenantStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant account is not active (status: {user.tenant_status})",
        )
    return TenantContext(tenant_id=user.tenant_id, user=user)


def require_tenant_role(*allowed_roles: str) -> Callable[..., Awaitable[TenantContext]]:
    """Composes tenant-scoping with an RBAC check: the resulting dependency
    rejects both platform-wide accounts (no tenant_id) and tenant members
    whose role isn't in `allowed_roles`."""

    async def _check(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if not ctx.user.has_role(*allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return ctx

    return _check
