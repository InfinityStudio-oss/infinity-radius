# Infinity Radius

Multi-Tenant ISP Billing & WiFi Management Platform. Initial market: Tanzania
(currency **TZS**, timezone `Africa/Dar_es_Salaam`, locale `en-TZ`).

This repository currently contains the **foundational scaffold only** — no
billing, RADIUS, router, wallet, or payment business logic has been built
yet. See [Remaining work](#remaining-work).

## Monorepo layout

```
infinity-radius/
  apps/
    web/             Next.js (App Router) frontend — Vercel
    api/              FastAPI backend — Railway
    worker/           Celery worker + beat — Railway
    network-agent/    MikroTik/WireGuard bridge — dedicated Network VPS
  packages/
    ui/               Shared React components + design tokens
    types/            Shared TypeScript types
    config/            Shared tsconfig/eslint/Tailwind design tokens
  infrastructure/
    freeradius/         FreeRADIUS config + RADIUS Postgres schema
    wireguard/          WireGuard server/peer config templates
    caddy/              Reverse proxy in front of the Network Agent
    fail2ban/           Jail/filter config for the Network VPS
    systemd/            Network Agent systemd unit
    railway/            Railway per-service deploy configs
    scripts/            VPS provisioning + WireGuard peer onboarding scripts
  docs/
    architecture.md
    deployment.md
    rls-policies.md
```

See `docs/architecture.md` for how these pieces talk to each other.

## Prerequisites

- Node.js >= 20, [pnpm](https://pnpm.io) >= 9 (`corepack enable && corepack prepare pnpm@9.15.0 --activate`)
- Python 3.12
- PostgreSQL (for local Supabase-equivalent + RADIUS databases)
- Redis (for Celery)

## Local setup

```bash
# JavaScript workspace
pnpm install

# Python apps (repeat per app)
cd apps/api && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
cd apps/worker && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
cd apps/network-agent && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

Copy every `.env.example` to `.env` in the same directory and fill in real
values:

```bash
cp apps/web/.env.example apps/web/.env.local
cp apps/api/.env.example apps/api/.env
cp apps/worker/.env.example apps/worker/.env
cp apps/network-agent/.env.example apps/network-agent/.env
```

## Running locally

```bash
# Frontend
pnpm --filter @infinity-radius/web dev        # http://localhost:3000

# API
cd apps/api && uvicorn app.main:app --reload    # http://localhost:8000/docs

# Worker / beat
cd apps/worker && celery -A app.celery_app worker --loglevel=info
cd apps/worker && celery -A app.celery_app beat --loglevel=info

# Network Agent (Network VPS in production; runnable locally for development)
cd apps/network-agent && uvicorn app.main:app --reload --port 8100

# Database migrations
cd apps/api && alembic upgrade head
cd apps/api && alembic revision --autogenerate -m "description"
```

`apps/api`'s test suite (`test_security.py`, `test_tenant.py`,
`test_super_admin.py`) is a real integration suite against Postgres — it
seeds and tears down real tenant/profile/role rows for every test. Against
a fresh local Postgres (not Supabase), run
`psql -f apps/api/tests/fixtures/supabase_auth_stub.sql` once first (see
`docs/rls-policies.md`) to provide the `auth` schema/roles Supabase already
has in production; then `alembic upgrade head`.

The RADIUS-dependent tests (`test_radius_sync.py`, and the RADIUS-sync
paths in `test_captive_portal_payments.py`/`test_selcom_webhook.py`) need
a second, separate local database — run `python -m scripts.setup_local_radius_db`
(from `apps/api`) once to create it, apply the FreeRADIUS schema, and
write a working `RADIUS_DATABASE_URL` into `.env`; see
`docs/architecture.md#local-radius-development-database` for details.

## Verifying the build

```bash
pnpm type-check
pnpm lint
pnpm build

cd apps/api && ruff check . && mypy app && pytest
cd apps/worker && ruff check . && pytest
cd apps/network-agent && ruff check . && pytest

# RLS tenant-isolation/cross-tenant-denial scenarios (see docs/rls-policies.md)
psql -h localhost -U postgres -d infinity_radius -f apps/api/tests/fixtures/rls_isolation_test.sql
```

## Environment variables

| App           | Variable                                                                              | Purpose                                                              |
| ------------- | ------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| web           | `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`                          | Supabase Auth + client                                               |
| web           | `NEXT_PUBLIC_API_BASE_URL`                                                            | FastAPI base URL                                                     |
| web           | `SUPABASE_SERVICE_ROLE_KEY`                                                           | Server-only elevated Supabase access                                 |
| api           | `DATABASE_URL`                                                                        | Supabase Postgres (async, `postgresql+asyncpg://`)                   |
| api           | `RADIUS_DATABASE_URL`                                                                 | RADIUS Postgres on the Network VPS                                   |
| api           | `SUPABASE_URL` / `SUPABASE_JWT_SECRET`                                                | Verify incoming Supabase session tokens                              |
| api           | `REDIS_URL`                                                                           | Celery broker/backend                                                |
| api           | `NETWORK_AGENT_BASE_URL` / `NETWORK_AGENT_API_KEY`                                    | Reach the Network Agent                                              |
| api           | `SECRETS_ENCRYPTION_KEY` / `ROUTER_TOKEN_SIGNING_KEY` / `TRANSACTION_TOKEN_SIGNING_KEY` | Fernet keys — router credentials at rest, the signed public router token, and the signed public transaction token (three separate keys — see `app/core/crypto.py`, `app/core/router_token.py`, `app/core/transaction_token.py`) |
| api           | `PUBLIC_CAPTIVE_PORTAL_DOMAIN` / `PUBLIC_API_DOMAIN`                                  | Walled garden domains — exact hosts only, never a wildcard            |
| api           | `WIREGUARD_SERVER_PUBLIC_KEY` / `WIREGUARD_SERVER_ENDPOINT` / `WIREGUARD_SERVER_SUBNET` | The Network VPS's own wg0.conf values, needed by the Add Router Wizard |
| api           | `SELCOM_API_BASE_URL` / `SELCOM_API_KEY` / `SELCOM_API_SECRET` / `SELCOM_MERCHANT_ID` | Selcom Collection API (unset until official credentials/spec are supplied — not used for disbursement) |
| api           | `SELCOM_DISBURSEMENT_ENABLED`                                                         | Platform-wide disbursement gate — defaults `false`; a separate, explicit approval switch from having credentials configured |
| api           | `SELCOM_BUSINESS_ENVIRONMENT` / `SELCOM_BUSINESS_BASE_URL` / `SELCOM_BUSINESS_API_KEY` / `SELCOM_BUSINESS_PRIVATE_KEY_B64` / `SELCOM_BUSINESS_ACCOUNT_NUMBER` | Real disbursement transport (developer.selcom.business, RSA-SHA256 signed) — see `app/integrations/selcom_business/` |
| api           | `SELCOM_WITHDRAWAL_APPROVAL_THRESHOLD_TZS`                                            | Amount above which a withdrawal needs SUPER_ADMIN approval — defaults `100000`, server-side only |
| worker        | `REDIS_URL`                                                                           | Celery broker/backend                                                |
| network-agent | `AGENT_API_KEY_CURRENT` / `AGENT_API_KEY_PREVIOUS`                                    | HMAC signing keys required from the API (rotation-capable)            |
| network-agent | `ALLOWED_SOURCE_IPS`                                                                  | Railway static outbound IPs allowed to reach this agent                |
| network-agent | `ROUTER_REGISTRY_PATH`                                                                | Router UUID -> connection details (see `routers.yaml.example`)        |
| network-agent | `WIREGUARD_INTERFACE`                                                                 | Local WireGuard interface name                                       |

Full detail and defaults are in each app's `.env.example`.

## Implementation rules (see project instructions)

- No mock/seeded/fake data anywhere — dashboards and lists render honest
  empty states (`EmptyState` component in `@infinity-radius/ui`) until real
  data exists.
- No fabricated fallback metrics — unavailable services report
  `not_configured` / `unavailable` / `error`, never a fake "ok".
- Money is `NUMERIC`/`Decimal` end-to-end, never `float`; wire format is a
  decimal string (`packages/types/src/money.ts`).
- Currency is TZS; locale is `en-TZ`; timezone is `Africa/Dar_es_Salaam`
  (`packages/types/src/locale.ts`, `apps/api/app/core/config.py`).

## Remaining work

Done: the full database schema (23 tables, UUID PKs, tenant_id on every
tenant-owned table), Row Level Security on all of them, the
`current_tenant_id()`/`is_super_admin()` trust chain, RBAC seed data, and
Supabase Auth login/logout/password-reset — see `docs/rls-policies.md`.

Done since then: customers/locations/packages/subscriptions/vouchers
business logic (server-generated customer numbers, voucher redemption as
one locked transaction, subscription activation via
`SubscriptionService.activate()`); the network infrastructure layer —
FreeRADIUS config + RADIUS Postgres schema (`infrastructure/freeradius`),
WireGuard peer provisioning (`infrastructure/scripts/add-router-peer.sh`),
and the Network Agent (`apps/network-agent`) with HMAC+timestamp+nonce
request signing, key rotation, an IP allowlist, and a router UUID ->
connection registry that never accepts a caller-supplied host; and the
Add Router Wizard (`apps/web/app/dashboard/network/routers/add`) — a
9-step MikroTik RouterOS 7 onboarding flow generating real WireGuard/
RADIUS/hotspot/walled-garden RouterOS config, backed by
`RouterProvisioningService` (`apps/api/app/services/router_provisioning.py`).
RADIUS secrets and WireGuard private keys are encrypted at rest (Fernet,
`app/core/crypto.py`) and returned in plaintext exactly once, at
generation time. The captive portal is scoped by a signed, encrypted
router token (`app/core/router_token.py`) — a redirect carries only
`router=<token>&mac=<mac>&dst=<dst>&login=<router-local-login-url>`, never
a tenant id or raw router id; the backend resolves token -> router ->
tenant itself.

The captive portal flow (`apps/web/app/captive-portal`,
`apps/api/app/services/captive_portal.py`) is real end-to-end: branding
and ACTIVE packages load for the resolved tenant, a customer's phone
number and package choice create a real `Transaction` + `PENDING`
`Subscription`, a safe Fernet-signed *transaction* token
(`app/core/transaction_token.py`, a separate key from the router token)
is polled every 3s for status — never a database id — and on completion
the subscription activates, RADIUS credentials are provisioned for real
in the RADIUS Postgres (`app/services/radius_sync.py`, a package's
`Mikrotik-Rate-Limit`/`Session-Timeout`/`Simultaneous-Use` synced into its
`radgroupreply`/`radgroupcheck` group), and the browser auto-submits the
router's own local login form to complete re-authentication.

The Selcom Collection integration *architecture* (`apps/api/app/
integrations/selcom/`) — restructured into `client`/`collection`/
`disbursement`/`authentication`/`signatures`/`schemas`/`exceptions`, plus a
real, reachable `POST /api/v1/webhooks/selcom/collection` — see
`docs/architecture.md#payments` and the "Not yet built" note below for
exactly what still can't move real money. A payment's charged amount is
always server-derived from `package.price_tzs`, never accepted from the
client.

Production-grade tenant finance accounting (`apps/api/app/services/
wallet.py`, `commercial_terms.py`): `ledger_entries` is the financial
source of truth, `tenant_wallets` only a summarized cache with five
independent buckets (available/pending/reserved/frozen/total_disbursed),
every balance change row-locked and ledger-justified. Platform commission
is never hard-coded — each tenant has its own versioned commercial terms
(`tenant_commercial_terms`), managed only by a super admin; a completed
collection fails closed if none are configured. On a completed payment,
`WalletService.process_collection` splits the gross amount into a
`PLATFORM_FEE` and a `TENANT_SHARE` entry (the two always sum exactly to
the gross, by subtraction) and credits the tenant's pending balance. No
endpoint ever accepts a raw new wallet balance — the only manual
correction path is an immutable, reason-and-actor-tracked `ADJUSTMENT`
entry. See `docs/architecture.md#tenant-finance-accounting`.

Selcom Disbursement architecture (`apps/api/app/services/payouts.py`,
`two_factor.py`, `settlement_config.py`): a full maker-checker withdrawal
lifecycle (`withdrawals`/`withdrawal_destinations`/`withdrawal_events`,
9-state status machine, row-locked at every step) gated behind two
independent switches — never assumed on — because Infinity Radius must
never assume it legally/commercially holds a tenant's funds. Per-tenant
`settlement_mode` (`direct_merchant_settlement`, the default meaning
Infinity holds nothing, vs `platform_managed_wallet`) plus a platform-wide
`SELCOM_DISBURSEMENT_ENABLED` flag (defaults `false`) both have to allow it
before a withdrawal can even be requested. A `TENANT_OWNER` requests
(reserving the balance and issuing a real, hashed, rate-limited 2FA code —
delivery is an honest interim gap, see below), confirms 2FA, and a
different `TENANT_OWNER`/`TENANT_ADMIN` approves or rejects — the service
layer refuses a reviewer who is also the requester regardless of role.
Submission is idempotency-keyed and never re-entrant ("never retry payout
submission blindly"). See `docs/architecture.md#selcom-disbursement-architecture`.

The tenant dashboard landing page (`apps/web/app/dashboard/page.tsx`) is
fully real-data-bound: 6 KPI cards, a collections/session trend chart pair,
a network health panel, recent transactions/sessions tables, and a
package-performance ranking, all backed by real aggregation queries
(`apps/api/app/services/dashboard.py`, `GET /api/v1/dashboard/*` +
`GET /api/v1/routers/health`) — tenant-isolated, zero on an empty
database rather than a placeholder, and an honest `EmptyChartState`
instead of a fabricated trend line whenever a chart has nothing to plot.
Router telemetry that has no real integration yet (active users, latency,
CPU, uptime) renders "Unavailable", never a guessed number. See
`docs/architecture.md#tenant-dashboard`.

The super-admin landing page (`apps/web/app/super-admin/page.tsx`) mirrors
that same contract platform-wide: 9 KPI cards (active/suspended tenants,
router fleet/online, RADIUS active sessions, today's collections, pending
payouts, failed webhooks, reconciliation exceptions), a collections/
tenant-growth trend pair, a cross-tenant pending-payouts queue, and a
platform-wide activity feed — all real aggregations
(`apps/api/app/services/super_admin_dashboard.py`,
`GET /api/v1/super-admin/{dashboard-summary,collections-trend,
tenant-growth-trend,pending-payouts,audit-logs}`), added alongside (never
replacing) the earlier-phase `/overview`/`/system-health` stubs the same
file already had. `reconciliation_exceptions` has no backing table
anywhere in this codebase yet, so it's reported `not_configured`, never a
fabricated 0. See `docs/architecture.md#super-admin-dashboard`.

Not yet built:

- Most MikroTik dashboard actions beyond "test connection" — the Network
  Agent implements identity/resource/hotspot-sessions/disconnect/
  interfaces/RADIUS-status and `apps/api` has a signed client ready to call
  them, but only `POST /routers/{id}/test-connection` is wired to a
  dashboard-facing endpoint so far.
- The Add Router Wizard's WireGuard step assumes the operator manually
  applies the generated `[Peer]` block to the Network VPS's `wg0.conf` and
  the NAS client block to FreeRADIUS's `clients.conf` — there's no Network
  Agent endpoint yet to do either automatically.
- Selcom Collection/Disbursement implementation itself (blocked on
  official docs + credentials, and — for Disbursement specifically —
  `SELCOM_DISBURSEMENT_ENABLED` staying deliberately `false` until Infinity
  has explicit business/legal approval for the disbursement model). The
  *architecture* is real and in place —
  `apps/api/app/integrations/selcom/{client,collection,disbursement,
  authentication,signatures,schemas,exceptions}.py`, plus real, reachable
  `POST /api/v1/webhooks/selcom/{collection,disbursement}`
  (`app/api/v1/webhooks.py`) that always save the raw callback — but
  `verify_webhook_signature` always raises `SelcomNotImplementedError`
  today, so no callback can be marked SUCCESS yet: every webhook currently
  comes back `{"status": "unverified"}`. Once verification is real, the
  whole downstream pipeline for both sides already works and is tested —
  collection: reference/amount/state validation, idempotency, subscription
  activation, the gross -> platform fee / tenant share wallet split, RADIUS
  sync, audit log (`apps/api/tests/test_selcom_webhook.py`); disbursement:
  the full maker-checker withdrawal lifecycle end to end, simulated by
  monkeypatching only the same verification/extraction/initiate boundary
  (`apps/api/tests/test_disbursement_webhook.py`, `test_payouts.py`,
  `test_wallet.py`, `test_settlement_config.py`).
- A real SMS/email provider for delivering a withdrawal's 2FA code. The
  code-generation/hashing/expiry/rate-limiting mechanism is real
  (`apps/api/app/services/two_factor.py`), but delivery is an honest
  interim gap: until a provider is wired in, the one-time code is recorded
  only in the audit trail, not sent anywhere — see
  `docs/architecture.md#2fa--an-honest-interim-design`.
- Voucher redemption from the captive-portal UI (the staff-side voucher
  redemption transaction already exists — see `VoucherService.redeem`).
- Staff invitation UI (the trigger/table architecture is invitation-ready —
  see `docs/rls-policies.md#provisioning` — but there's no "invite a
  teammate" screen yet)
- Customer-portal authentication (the `CUSTOMER` role is seeded and
  prepared, not yet wired to a login flow)
- Full public marketing site (hero, pricing, docs) — only the header/footer
  shell exists today, per the current phase's scope
- CI pipeline
