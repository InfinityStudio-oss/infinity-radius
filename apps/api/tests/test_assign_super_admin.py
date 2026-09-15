"""scripts/assign_super_admin.py — the tenant-role collision safety net.
Every scenario here also removes its own auth.users row via SeededContext
so nothing lingers in the local test database (see tests/db_fixtures.py).
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.roles import Role
from app.db.session import AsyncSessionLocal
from app.models.tenancy import Profile, ProfileRole
from app.models.tenancy import Role as RoleModel
from scripts.assign_super_admin import TenantAssociationConflict, _assign
from tests.db_fixtures import SeededContext


async def _profile_roles(profile_id: object) -> list[tuple[object, str]]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ProfileRole.tenant_id, RoleModel.code)
            .join(RoleModel, RoleModel.id == ProfileRole.role_id)
            .where(ProfileRole.profile_id == profile_id)
        )
        return [(tenant_id, code) for tenant_id, code in result.all()]


async def _profile_tenant_id(profile_id: object) -> object:
    async with AsyncSessionLocal() as db:
        return await db.scalar(select(Profile.tenant_id).where(Profile.id == profile_id))


async def test_fresh_assignment_grants_super_admin() -> None:
    """A just-registered account with no role at all yet — the state a
    real person is in before this script has ever touched them."""
    with SeededContext() as ctx:
        email = f"fresh-{uuid4()}@example.test"
        user_id = ctx.new_user(role_code=None, tenant_id=None, email=email)

        await _assign(email, force=False)

        assert await _profile_roles(user_id) == [(None, "SUPER_ADMIN")]
        assert await _profile_tenant_id(user_id) is None


async def test_already_super_admin_is_idempotent(capsys: pytest.CaptureFixture[str]) -> None:
    with SeededContext() as ctx:
        email = f"already-{uuid4()}@example.test"
        user_id = ctx.new_user(role_code=Role.SUPER_ADMIN.value, tenant_id=None, email=email)

        await _assign(email, force=False)
        out = capsys.readouterr().out
        assert "already a SUPER_ADMIN with no conflicting tenant roles" in out

        roles = await _profile_roles(user_id)
        assert roles == [(None, "SUPER_ADMIN")], "must not create a duplicate SUPER_ADMIN row"


async def test_tenant_owner_collision_refuses_without_force() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        email = f"owner-{uuid4()}@example.test"
        user_id = ctx.new_user(role_code=Role.TENANT_OWNER.value, tenant_id=tenant_id, email=email)

        with pytest.raises(TenantAssociationConflict) as exc_info:
            await _assign(email, force=False)
        assert exc_info.value.tenant_scoped_roles == ["TENANT_OWNER"]
        assert exc_info.value.tenant_id == tenant_id

        # Refused entirely — nothing changed.
        assert await _profile_tenant_id(user_id) == tenant_id
        roles = await _profile_roles(user_id)
        assert (tenant_id, "TENANT_OWNER") in roles
        assert not any(code == "SUPER_ADMIN" for _, code in roles)


async def test_tenant_owner_collision_cleaned_up_with_force() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        email = f"owner-force-{uuid4()}@example.test"
        user_id = ctx.new_user(role_code=Role.TENANT_OWNER.value, tenant_id=tenant_id, email=email)

        await _assign(email, force=True)

        assert await _profile_tenant_id(user_id) is None
        assert await _profile_roles(user_id) == [(None, "SUPER_ADMIN")]


async def test_tenant_staff_collision_cleaned_up_with_force() -> None:
    """Same collision, a different (non-owner) tenant-scoped role — proves
    the cleanup isn't hardcoded to TENANT_OWNER specifically."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        email = f"staff-force-{uuid4()}@example.test"
        user_id = ctx.new_user(role_code=Role.ACCOUNTANT.value, tenant_id=tenant_id, email=email)

        await _assign(email, force=True)

        assert await _profile_tenant_id(user_id) is None
        assert await _profile_roles(user_id) == [(None, "SUPER_ADMIN")]


async def test_force_run_twice_is_idempotent_and_leaves_no_duplicates() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        email = f"twice-{uuid4()}@example.test"
        user_id = ctx.new_user(role_code=Role.TENANT_OWNER.value, tenant_id=tenant_id, email=email)

        await _assign(email, force=True)
        await _assign(email, force=True)  # must be a clean no-op the second time

        assert await _profile_roles(user_id) == [(None, "SUPER_ADMIN")]


async def test_conflict_refusal_does_not_touch_auth_user() -> None:
    """A refused conversion must never delete/orphan the profile (1:1 with
    auth.users.id) — only role/tenant-membership rows are ever in scope."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        email = f"safe-{uuid4()}@example.test"
        user_id = ctx.new_user(role_code=Role.TENANT_OWNER.value, tenant_id=tenant_id, email=email)

        with pytest.raises(TenantAssociationConflict):
            await _assign(email, force=False)

        async with AsyncSessionLocal() as db:
            profile = await db.get(Profile, user_id)
            assert profile is not None  # still resolvable, nothing deleted


async def test_unknown_email_errors_without_raising_conflict() -> None:
    with pytest.raises(SystemExit):
        await _assign(f"no-such-profile-{uuid4()}@example.test", force=False)
