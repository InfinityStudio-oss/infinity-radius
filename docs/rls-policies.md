# Row Level Security

Every tenant-scoped table has RLS enabled. This document is the reference
for what each policy allows and why — the policies themselves live in
`apps/api/alembic/versions/41619a38de4a_rls_policies.py`, and the schema
they protect in `78bb02eec08a_initial_schema.py`.

## The trust chain

```
auth.users (Supabase Auth)
   -> public.profiles.id            (1:1, same UUID — not a surrogate key)
   -> public.profiles.tenant_id     (nullable: NULL = platform-wide staff)
   -> public.tenants.id
```

`profiles.tenant_id` is the **only** source of truth for "which tenant does
this signed-in user belong to." It is never read from a JWT claim, and a
client can never set it directly — see [Provisioning](#provisioning) and
[Never trust the client](#never-trust-the-client) below.

## Helper functions

Both are `SECURITY DEFINER` (so they can read `profiles`/`profile_roles`
regardless of the caller's own RLS visibility into those tables) with an
explicit `SET search_path = public` (the standard defense against
search-path-hijacking on `SECURITY DEFINER` functions).

- **`public.current_tenant_id() returns uuid`** — `SELECT tenant_id FROM
public.profiles WHERE id = auth.uid()`. Returns `NULL` for a
  platform-wide account (or an unrecognized `auth.uid()`), which correctly
  makes every `tenant_id = current_tenant_id()` comparison evaluate to
  `NULL`/false — fails closed.
- **`public.is_super_admin() returns boolean`** — true if the caller has a
  `profile_roles` row for the `SUPER_ADMIN` role. Super admins bypass
  tenant scoping (see every policy below: `... OR public.is_super_admin()`).

## Provisioning (invitation-ready)

`public.handle_new_auth_user()`, triggered `AFTER INSERT ON auth.users`,
creates the matching `profiles` row (`status = 'invited'`, `tenant_id =
NULL`) automatically. This fires for **both** self-signup and
`supabase.auth.admin.inviteUserByEmail` — both insert into `auth.users` —
so invitations need no separate table: a tenant admin (or super admin)
invites someone, then assigns `tenant_id` and a `profile_roles` row
afterward via the `profiles_update` / `profile_roles_insert` policies below.

## Access pattern per table group

| Group                 | Tables                                                                                                                                                 | authenticated can...                                                                                            |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| Reference (immutable) | `roles`, `permissions`, `role_permissions`                                                                                                             | SELECT only (`true`) — no write policy at all; only this migration writes them                                  |
| `tenants`             | —                                                                                                                                                      | SELECT/UPDATE own tenant; INSERT/DELETE super-admin only                                                        |
| `profiles`            | —                                                                                                                                                      | SELECT self + own tenant + super-admin; UPDATE self + own tenant + super-admin; no INSERT policy (trigger-only) |
| `profile_roles`       | —                                                                                                                                                      | SELECT own assignment + own tenant + super-admin; INSERT/UPDATE/DELETE own tenant or super-admin                |
| Full CRUD             | `locations`, `routers`, `packages`, `customers`, `customer_devices`, `subscriptions`, `voucher_batches`, `offline_vouchers`, `withdrawal_destinations` | SELECT/INSERT/UPDATE/DELETE, all scoped to `tenant_id = current_tenant_id()`                                    |
| No delete             | `transactions`, `withdrawals`                                                                                                                          | SELECT/INSERT/UPDATE, scoped; no DELETE policy — a financial trail is corrected with new rows, never erased     |
| Backend-only write    | `user_sessions`, `payment_webhooks`, `tenant_wallets`, `ledger_entries`, `settlement_logs`, `audit_logs`                                               | SELECT only, scoped; writes happen exclusively through the trusted backend connection (see below)               |

Every scoped policy follows the same shape:

```sql
USING (tenant_id = public.current_tenant_id() OR public.is_super_admin())
```

with `WITH CHECK` repeating the same expression on INSERT/UPDATE, so a
tenant member can never read, write, or even _attempt_ to write a row
tagged with someone else's `tenant_id` — see the [Verification](#verification)
section for a live test of exactly that.

## Never trust the client

Two independent layers enforce tenant isolation, deliberately overlapping:

1. **RLS**, as above — applies to any connection using the `authenticated`
   Postgres role (i.e. Supabase's own client libraries, PostgREST,
   Realtime).
2. **FastAPI** (`apps/api/app/core/security.py`) connects to Postgres with
   a privileged, RLS-bypassing role and does its **own** tenant filtering
   in Python — `AuthenticatedUser.tenant_id` is resolved by querying
   `profiles`/`profile_roles` fresh on every request, keyed only by the
   JWT's verified `sub` claim. A JWT's `app_metadata`/`user_metadata` is
   never read for tenant_id or role, and a request body/query param
   claiming a `tenant_id` is never accepted as authoritative.

Both layers read the same source of truth (`profiles.tenant_id`), so they
can't disagree — but neither depends on the other being correctly wired
everywhere, which is the point of defense in depth.

## Verification

Two scripts exercise this for real, against a real Postgres (not a
mock) — see `apps/api/tests/fixtures/`:

- **`rls_isolation_test.sql`** — connects as `authenticated`/`anon` with
  `request.jwt.claims` set per scenario (the same mechanism PostgREST
  uses) and asserts real query results: tenant A cannot see, insert into,
  or update tenant B's rows; a profile-less token sees nothing; a super
  admin sees across tenants; reference tables are read-only;
  `audit_logs`/etc. reject client writes entirely. Run it with `psql -f`
  against a migrated database — every scenario `RAISE EXCEPTION`s loudly
  on failure. All 8 scenarios pass as of this migration.
- **`supabase_auth_stub.sql`** — local-only bootstrap (`auth` schema,
  `auth.users`, `auth.uid()`, and the `anon`/`authenticated`/`service_role`
  Postgres roles) so the above can run against a plain local Postgres
  instead of a provisioned Supabase project. Never run this against a real
  Supabase database — it already has all of this.
- **`apps/api/tests/test_security.py`** and **`test_tenant.py`** /
  **`test_super_admin.py`** — pytest integration tests seeding real
  tenants/profiles/roles (via `tests/db_fixtures.py`, cleaned up after
  every test) and asserting `get_current_user` resolves tenant_id/roles
  from the database, two tenants resolve to different tenant_ids, and
  cross-role access is rejected end-to-end through the FastAPI app.

## Adding a new tenant-owned table

1. Add `tenant_id uuid not null references tenants(id)` to the table.
2. Add it to the right list in `41619a38de4a`'s Python constants
   (`FULL_CRUD_TABLES`, `NO_DELETE_TABLES`, or `SELECT_ONLY_TABLES`) in a
   new migration — don't edit the historical one.
3. `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` plus the matching policies,
   following the existing loop's pattern.
4. Add a scenario to `rls_isolation_test.sql` proving cross-tenant access
   is denied for the new table.
