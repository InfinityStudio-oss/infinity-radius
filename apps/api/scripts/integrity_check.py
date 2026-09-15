"""Read-only operator diagnostic for profile/tenant role integrity.

Reports (never modifies) four known ways profiles/profile_roles/tenants
can drift out of sync — see docs/architecture.md. Safe to run at any time
against any environment; issues nothing but SELECT statements.

Usage:
    python -m scripts.integrity_check

Exit code is 0 whether or not findings are reported — this is a report,
not a gate. Pipe/grep the output, or import find_* functions directly
for programmatic use (e.g. from a test).
"""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal


@dataclass(frozen=True)
class OrphanedTenantScopedRole:
    """A profile with tenant_id NULL (i.e. not a tenant member — usually a
    SUPER_ADMIN) that nonetheless still holds a tenant-scoped profile_roles
    row. Exactly the class of bug scripts.assign_super_admin now prevents
    going forward; this finds any that predate that fix."""

    profile_id: UUID
    email: str | None
    role_code: str
    role_tenant_id: UUID


@dataclass(frozen=True)
class MismatchedOwnerTenant:
    """A TENANT_OWNER profile_roles row whose tenant_id disagrees with
    that same profile's own profiles.tenant_id — the two are supposed to
    always agree for tenant-scoped roles."""

    profile_id: UUID
    email: str | None
    profile_tenant_id: UUID | None
    role_tenant_id: UUID | None


@dataclass(frozen=True)
class ActiveTenantWithoutOwner:
    tenant_id: UUID
    name: str


@dataclass(frozen=True)
class TenantWithMultipleOwners:
    tenant_id: UUID
    owner_count: int


async def find_orphaned_tenant_scoped_roles(db: AsyncSession) -> list[OrphanedTenantScopedRole]:
    rows = (
        await db.execute(
            text(
                """
                SELECT p.id, p.email, r.code, pr.tenant_id
                FROM profiles p
                JOIN profile_roles pr ON pr.profile_id = p.id
                JOIN roles r ON r.id = pr.role_id
                WHERE p.tenant_id IS NULL AND pr.tenant_id IS NOT NULL
                ORDER BY p.id
                """
            )
        )
    ).all()
    return [
        OrphanedTenantScopedRole(profile_id=r[0], email=r[1], role_code=r[2], role_tenant_id=r[3])
        for r in rows
    ]


async def find_mismatched_owner_tenants(db: AsyncSession) -> list[MismatchedOwnerTenant]:
    rows = (
        await db.execute(
            text(
                """
                SELECT p.id, p.email, p.tenant_id, pr.tenant_id
                FROM profiles p
                JOIN profile_roles pr ON pr.profile_id = p.id
                JOIN roles r ON r.id = pr.role_id
                WHERE r.code = 'TENANT_OWNER'
                  AND pr.tenant_id IS DISTINCT FROM p.tenant_id
                ORDER BY p.id
                """
            )
        )
    ).all()
    return [
        MismatchedOwnerTenant(
            profile_id=r[0], email=r[1], profile_tenant_id=r[2], role_tenant_id=r[3]
        )
        for r in rows
    ]


async def find_active_tenants_without_owner(db: AsyncSession) -> list[ActiveTenantWithoutOwner]:
    rows = (
        await db.execute(
            text(
                """
                SELECT t.id, t.name
                FROM tenants t
                WHERE t.status = 'ACTIVE'
                  AND NOT EXISTS (
                    SELECT 1 FROM profile_roles pr
                    JOIN roles r ON r.id = pr.role_id
                    WHERE pr.tenant_id = t.id AND r.code = 'TENANT_OWNER'
                  )
                ORDER BY t.id
                """
            )
        )
    ).all()
    return [ActiveTenantWithoutOwner(tenant_id=r[0], name=r[1]) for r in rows]


async def find_tenants_with_multiple_owners(db: AsyncSession) -> list[TenantWithMultipleOwners]:
    rows = (
        await db.execute(
            text(
                """
                SELECT pr.tenant_id, COUNT(*)
                FROM profile_roles pr
                JOIN roles r ON r.id = pr.role_id
                WHERE r.code = 'TENANT_OWNER' AND pr.tenant_id IS NOT NULL
                GROUP BY pr.tenant_id
                HAVING COUNT(*) > 1
                ORDER BY pr.tenant_id
                """
            )
        )
    ).all()
    return [TenantWithMultipleOwners(tenant_id=r[0], owner_count=r[1]) for r in rows]


async def _report() -> None:
    async with AsyncSessionLocal() as db:
        orphaned = await find_orphaned_tenant_scoped_roles(db)
        mismatched = await find_mismatched_owner_tenants(db)
        ownerless_active = await find_active_tenants_without_owner(db)
        multi_owner = await find_tenants_with_multiple_owners(db)

    print("=== Profile / tenant role integrity report ===")

    print(f"\n1. Platform profiles holding a stale tenant-scoped role: {len(orphaned)}")
    for orphan in orphaned:
        print(
            f"   profile={orphan.profile_id} email={orphan.email!r} "
            f"role={orphan.role_code} tenant={orphan.role_tenant_id}"
        )

    print(f"\n2. TENANT_OWNER role tenant_id mismatched with profiles.tenant_id: {len(mismatched)}")
    for mismatch in mismatched:
        print(
            f"   profile={mismatch.profile_id} email={mismatch.email!r} "
            f"profiles.tenant_id={mismatch.profile_tenant_id} "
            f"role.tenant_id={mismatch.role_tenant_id}"
        )

    print(f"\n3. ACTIVE tenants with no TENANT_OWNER: {len(ownerless_active)}")
    for tenant in ownerless_active:
        print(f"   tenant={tenant.tenant_id} name={tenant.name!r}")

    print(f"\n4. Tenants with more than one TENANT_OWNER: {len(multi_owner)}")
    for dup in multi_owner:
        print(f"   tenant={dup.tenant_id} owner_count={dup.owner_count}")

    total = len(orphaned) + len(mismatched) + len(ownerless_active) + len(multi_owner)
    print(f"\nTotal findings: {total}")
    print("This is a report only — no records were modified.")


def main() -> None:
    asyncio.run(_report())


if __name__ == "__main__":
    main()
