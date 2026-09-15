"""Unit-level coverage of app.core.security's DB-backed tenant/role
resolution — the piece that makes "tenant_id is never trusted from the
client" true on the FastAPI side, mirroring what tests/fixtures/
rls_isolation_test.sql proves at the database level.

Test bodies stay synchronous (matching the rest of the suite) and use
`asyncio.run` for the one or two awaits each needs — see
tests/db_fixtures.py for why fixtures avoid pytest-asyncio's own loop.
"""

import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import AsyncSessionLocal
from tests.auth_helpers import make_token
from tests.db_fixtures import SeededContext


async def _resolve(user_id: UUID) -> AuthenticatedUser:
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=make_token(user_id=user_id)
    )
    async with AsyncSessionLocal() as db:
        return await get_current_user(credentials=credentials, db=db)


def test_tenant_id_is_resolved_from_profile_not_jwt() -> None:
    """A forged JWT cannot claim a tenant_id — there is nowhere on the
    token for one to even go; get_current_user only ever reads `sub`."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        user = asyncio.run(_resolve(user_id))

    assert user.id == user_id
    assert user.tenant_id == tenant_id
    assert user.roles == frozenset({"TENANT_ADMIN"})
    assert not user.is_super_admin


def test_two_tenants_resolve_to_different_tenant_ids() -> None:
    # SeededContext tracks one tenant_id each for cleanup, so use two
    # separate contexts to ensure both tenants get torn down.
    with SeededContext() as ctx_a, SeededContext() as ctx_b:
        tenant_a = ctx_a.new_tenant(name="Tenant A")
        tenant_b = ctx_b.new_tenant(name="Tenant B")
        user_a = ctx_a.new_user(role_code="TENANT_OWNER", tenant_id=tenant_a)
        user_b = ctx_b.new_user(role_code="TENANT_OWNER", tenant_id=tenant_b)

        resolved_a = asyncio.run(_resolve(user_a))
        resolved_b = asyncio.run(_resolve(user_b))

    assert resolved_a.tenant_id == tenant_a
    assert resolved_b.tenant_id == tenant_b
    assert resolved_a.tenant_id != resolved_b.tenant_id


def test_super_admin_has_no_tenant_id() -> None:
    with SeededContext() as ctx:
        user_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        user = asyncio.run(_resolve(user_id))

    assert user.tenant_id is None
    assert user.is_super_admin


def test_profile_less_token_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_resolve(uuid4()))

    assert exc_info.value.status_code == 403
