"""scripts/integrity_check.py — read-only diagnostics. Each test seeds the
exact drift the diagnostic is meant to catch, confirms it's found, and
confirms nothing else (well-formed rows) is flagged as a false positive.
"""

from uuid import uuid4

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.tenancy import ProfileRole
from app.models.tenancy import Role as RoleModel
from scripts.integrity_check import (
    find_active_tenants_without_owner,
    find_mismatched_owner_tenants,
    find_orphaned_tenant_scoped_roles,
    find_tenants_with_multiple_owners,
)
from tests.db_fixtures import SeededContext


async def test_finds_orphaned_tenant_scoped_role() -> None:
    with SeededContext() as ctx_admin, SeededContext() as ctx_tenant:
        tenant_id = ctx_tenant.new_tenant()
        # Mirrors the real bug: a profile with tenant_id NULL (platform
        # account) that still holds a tenant-scoped profile_roles row.
        admin_id = ctx_admin.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        async with AsyncSessionLocal() as db:
            owner_role_id = await db.scalar(
                select(RoleModel.id).where(RoleModel.code == "TENANT_OWNER")
            )
            db.add(ProfileRole(profile_id=admin_id, role_id=owner_role_id, tenant_id=tenant_id))
            await db.commit()

            findings = await find_orphaned_tenant_scoped_roles(db)
            assert any(f.profile_id == admin_id and f.role_code == "TENANT_OWNER" for f in findings)


async def test_clean_super_admin_is_not_flagged() -> None:
    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        async with AsyncSessionLocal() as db:
            findings = await find_orphaned_tenant_scoped_roles(db)
            assert not any(f.profile_id == admin_id for f in findings)


async def test_finds_active_tenant_without_owner() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant(name="Ownerless Active Co", status="ACTIVE")
        async with AsyncSessionLocal() as db:
            findings = await find_active_tenants_without_owner(db)
            assert any(f.tenant_id == tenant_id for f in findings)


async def test_active_tenant_with_owner_is_not_flagged() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant(name="Owned Active Co", status="ACTIVE")
        ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        async with AsyncSessionLocal() as db:
            findings = await find_active_tenants_without_owner(db)
            assert not any(f.tenant_id == tenant_id for f in findings)


async def test_pending_tenant_without_owner_is_not_flagged() -> None:
    """Only ACTIVE tenants are expected to have an owner by this point —
    a still-PENDING_VERIFICATION tenant with no owner isn't a real finding."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant(name="Pending Co", status="PENDING_VERIFICATION")
        async with AsyncSessionLocal() as db:
            findings = await find_active_tenants_without_owner(db)
            assert not any(f.tenant_id == tenant_id for f in findings)


async def test_mismatched_owner_tenant_is_flagged() -> None:
    with SeededContext() as ctx_a, SeededContext() as ctx_b:
        tenant_a = ctx_a.new_tenant()
        tenant_b = ctx_b.new_tenant()
        # Profile belongs to tenant_a, but its TENANT_OWNER role row is
        # (incorrectly) scoped to tenant_b.
        owner_id = ctx_a.new_user(role_code=None, tenant_id=tenant_a)
        async with AsyncSessionLocal() as db:
            owner_role_id = await db.scalar(
                select(RoleModel.id).where(RoleModel.code == "TENANT_OWNER")
            )
            db.add(ProfileRole(profile_id=owner_id, role_id=owner_role_id, tenant_id=tenant_b))
            await db.commit()

            findings = await find_mismatched_owner_tenants(db)
            assert any(
                f.profile_id == owner_id
                and f.profile_tenant_id == tenant_a
                and f.role_tenant_id == tenant_b
                for f in findings
            )


async def test_consistent_owner_is_not_flagged() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        async with AsyncSessionLocal() as db:
            findings = await find_mismatched_owner_tenants(db)
            assert not any(f.profile_id == owner_id for f in findings)


async def test_finds_tenant_with_multiple_owners() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        async with AsyncSessionLocal() as db:
            findings = await find_tenants_with_multiple_owners(db)
            match = next((f for f in findings if f.tenant_id == tenant_id), None)
            assert match is not None
            assert match.owner_count == 2


async def test_single_owner_tenant_is_not_flagged() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        async with AsyncSessionLocal() as db:
            findings = await find_tenants_with_multiple_owners(db)
            assert not any(f.tenant_id == tenant_id for f in findings)


async def test_unrelated_random_tenant_id_produces_no_findings() -> None:
    """Sanity check that the queries don't false-positive on unrelated data."""
    async with AsyncSessionLocal() as db:
        random_id = uuid4()
        findings = await find_active_tenants_without_owner(db)
        assert not any(f.tenant_id == random_id for f in findings)
