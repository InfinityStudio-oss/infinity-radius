"""One-time operator tool: grant the platform-wide SUPER_ADMIN role to a
real, already-registered Supabase Auth user.

There is no self-service or API path to become a SUPER_ADMIN — by design.
This script is meant to be run manually, once, by whoever operates the
database, against a person who already has a real account (having signed
in at least once, so their `profiles` row exists via the
`handle_new_auth_user` trigger).

Usage:
    python -m scripts.assign_super_admin owner@yourcompany.com
    python -m scripts.assign_super_admin owner@yourcompany.com --force

Requires DATABASE_URL (or the rest of app.core.config.Settings) to be set
exactly as the API itself would need it — this connects with the same
credentials, not a separate elevated one. Never stores or prints a
password; it only ever grants a role to an existing account.

--- Tenant-role collision safety ---

A SUPER_ADMIN account must have profiles.tenant_id = NULL and hold no
tenant-scoped profile_roles row (see app.core.context.get_tenant_context,
which treats a non-NULL tenant_id as "this is tenant staff"). If the
target email currently belongs to a tenant — as its owner, admin, or any
other staff role — converting them without also clearing that tenant
association leaves contradictory state: profiles.tenant_id may end up
NULL while a stale tenant-scoped profile_roles row survives underneath
it, unreachable by normal application code but still sitting in the
database.

So this script refuses to convert a tenant-associated profile unless
--force is passed. With --force, the conflicting tenant association
(profiles.tenant_id and every tenant-scoped profile_roles row for this
profile) is removed atomically in the same transaction that grants
SUPER_ADMIN — never left half-done. This never deletes the auth user or
any tenant; it only removes this one profile's tenant membership.

Running the command twice is safe: the second run finds no conflicts and
no missing SUPER_ADMIN grant, and does nothing.
"""

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import select

from app.core.roles import Role
from app.db.session import AsyncSessionLocal
from app.models.tenancy import Profile, ProfileRole
from app.models.tenancy import Role as RoleModel
from app.services.audit import write_audit_log


class TenantAssociationConflict(Exception):
    """Raised when the target profile still belongs to a tenant and
    --force was not supplied. Carries the details so main() can print a
    clear, specific warning instead of a raw stack trace."""

    def __init__(self, *, tenant_id: UUID | None, tenant_scoped_roles: list[str]) -> None:
        self.tenant_id = tenant_id
        self.tenant_scoped_roles = tenant_scoped_roles
        super().__init__("tenant association conflict")


async def _assign(email: str, *, force: bool) -> None:
    async with AsyncSessionLocal() as db:
        profile = (
            await db.execute(select(Profile).where(Profile.email == email))
        ).scalar_one_or_none()
        if profile is None:
            print(
                f"No profile found for {email!r}. The person must sign up or be invited "
                "through Supabase Auth first (their profiles row is created automatically "
                "by the handle_new_auth_user trigger on first account creation)."
            )
            raise SystemExit(1)

        super_admin_role_id: UUID | None = await db.scalar(
            select(RoleModel.id).where(RoleModel.code == Role.SUPER_ADMIN.value)
        )
        if super_admin_role_id is None:
            print("SUPER_ADMIN role is not seeded — run the rbac_seed_data migration first.")
            raise SystemExit(1)

        already_super_admin = (
            await db.execute(
                select(ProfileRole).where(
                    ProfileRole.profile_id == profile.id,
                    ProfileRole.role_id == super_admin_role_id,
                    ProfileRole.tenant_id.is_(None),
                )
            )
        ).scalar_one_or_none() is not None

        # Every tenant-scoped role this profile currently holds, regardless
        # of role type (TENANT_OWNER, TENANT_ADMIN, ACCOUNTANT, ...) — a
        # SUPER_ADMIN must hold none of these.
        tenant_scoped_roles_result = await db.execute(
            select(ProfileRole, RoleModel.code)
            .join(RoleModel, RoleModel.id == ProfileRole.role_id)
            .where(
                ProfileRole.profile_id == profile.id,
                ProfileRole.tenant_id.is_not(None),
            )
        )
        tenant_scoped_rows = tenant_scoped_roles_result.all()

        has_conflict = profile.tenant_id is not None or len(tenant_scoped_rows) > 0

        if has_conflict and not force:
            role_codes = sorted({code for _, code in tenant_scoped_rows})
            raise TenantAssociationConflict(
                tenant_id=profile.tenant_id, tenant_scoped_roles=role_codes
            )

        removed_role_codes: list[str] = []
        if has_conflict and force:
            previous_tenant_id = profile.tenant_id
            profile.tenant_id = None
            for profile_role, code in tenant_scoped_rows:
                await db.delete(profile_role)
                removed_role_codes.append(code)

            await write_audit_log(
                db,
                tenant_id=None,
                actor_id=None,
                action="SUPER_ADMIN_TENANT_ROLE_CLEANUP",
                target_type="profile",
                target_id=profile.id,
                metadata={
                    "email": email,
                    "removed_roles": removed_role_codes,
                    "previous_tenant_id": str(previous_tenant_id) if previous_tenant_id else None,
                    "reason": "conflicting tenant association removed as part of "
                    "SUPER_ADMIN conversion (assign_super_admin --force)",
                },
            )

        if not already_super_admin:
            db.add(ProfileRole(profile_id=profile.id, role_id=super_admin_role_id, tenant_id=None))
            await write_audit_log(
                db,
                tenant_id=None,
                actor_id=None,
                action="SUPER_ADMIN_GRANTED",
                target_type="profile",
                target_id=profile.id,
                metadata={"email": email},
            )

        if already_super_admin and not removed_role_codes:
            await db.commit()
            print(
                f"{email} is already a SUPER_ADMIN with no conflicting tenant roles. "
                "Nothing to do."
            )
            return

        await db.commit()

        if removed_role_codes:
            print(
                f"Removed conflicting tenant-scoped role(s) {removed_role_codes} for {email} "
                f"({profile.id}) and cleared profiles.tenant_id."
            )
        if not already_super_admin:
            print(f"Granted SUPER_ADMIN to {email} ({profile.id}).")
        else:
            print(
                f"{email} ({profile.id}) already held SUPER_ADMIN; "
                "tenant-role conflict cleaned up."
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.assign_super_admin",
        description="Grant the platform-wide SUPER_ADMIN role to an already-registered account.",
    )
    parser.add_argument("email", help="Email of the already-registered Supabase Auth account.")
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Required when the target account currently belongs to a tenant "
            "(as owner or any other tenant-scoped role). Atomically clears that "
            "tenant association as part of granting SUPER_ADMIN. Without this "
            "flag, the script refuses to proceed and makes no changes."
        ),
    )
    args = parser.parse_args()

    try:
        asyncio.run(_assign(args.email, force=args.force))
    except TenantAssociationConflict as exc:
        print(f"REFUSING: {args.email!r} currently belongs to a tenant.")
        if exc.tenant_id is not None:
            print(f"  profiles.tenant_id = {exc.tenant_id}")
        if exc.tenant_scoped_roles:
            print(f"  tenant-scoped role(s) held: {', '.join(exc.tenant_scoped_roles)}")
        print(
            "Converting this account to SUPER_ADMIN would leave contradictory role "
            "state unless that tenant association is removed first."
        )
        print(
            "Re-run with --force to atomically clear the tenant association "
            "(profiles.tenant_id and all tenant-scoped profile_roles rows for this "
            "profile) and grant SUPER_ADMIN in the same transaction. This does NOT "
            "delete the auth user, the tenant, or any tenant data — only this "
            "profile's membership in that tenant."
        )
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
