# Architecture

## Services

- **`apps/web`** — Next.js (App Router) frontend on Vercel. Public marketing
  shell, `/login`, `/super-admin/*`, `/dashboard/*`, `/portal/*`,
  `/captive-portal/*`. Authenticates via Supabase Auth (cookie-based
  sessions through `@supabase/ssr`).
- **`apps/api`** — FastAPI on Railway. The only writer to the primary
  Supabase Postgres database via SQLAlchemy 2 (async) + Alembic. Verifies
  Supabase-issued JWTs on every request and enforces tenant/RBAC checks.
- **`apps/worker`** — Celery worker + beat on Railway. Background/async jobs
  (billing runs, RADIUS sync, expirations, reconciliation) against Redis.
- **`apps/network-agent`** — FastAPI service on a separate, dedicated
  Network VPS (not Railway). The only component that speaks to MikroTik
  routers, over a WireGuard tunnel. Reached from `apps/api` over HTTPS with
  a shared API key.

## Data stores

- **Supabase Postgres** — primary application database (tenants, users,
  billing, wallets, etc.), governed by Row Level Security policies plus
  FastAPI-side tenant validation as a second layer.
- **RADIUS Postgres** — separate database on the Network VPS, owned by
  FreeRADIUS (`radcheck`, `radacct`, `nas`, ...). Kept independent because
  of very different write volume/access patterns.
- **Redis** — Celery broker/result backend on Railway.

## Local RADIUS development database

`app/services/radius_sync.py` talks to `RADIUS_DATABASE_URL` directly with
raw SQL against the stock FreeRADIUS schema — it's a genuinely separate
Postgres database from `DATABASE_URL` (real Supabase), never a schema
inside it, because production points them at two different machines (the
primary app database on Supabase; RADIUS on the Network VPS, owned by
FreeRADIUS itself). Locally, both need to exist, but there's no VPS yet —
so the RADIUS schema lives in its own database (`radius`) on the same
local Postgres instance already used for the primary app's test database
(`infinity_radius`).

**One-time setup** (from `apps/api`):

```bash
python -m scripts.setup_local_radius_db
```

This is idempotent — safe to re-run any time. It:

1. Creates the `radius` database on local Postgres if it doesn't exist.
2. Creates a dedicated, least-privilege `radius_app` role (generating a
   real local password) — the API never connects to this database as the
   Postgres superuser, matching how production should also never let
   FreeRADIUS's Postgres role be a superuser.
3. Applies `infrastructure/freeradius/schema/0001_radius_schema.sql`
   (`radcheck`/`radreply`/`radgroupcheck`/`radgroupreply`/`radusergroup`/
   `radacct`/`radpostauth`/`nas` — the same file a real FreeRADIUS instance
   uses, so there's exactly one schema source of truth).
4. Grants `radius_app` exactly the privileges the app needs on those
   tables — nothing more.
5. Writes the resulting `RADIUS_DATABASE_URL` into `apps/api/.env`
   directly, so the local password is never printed to a terminal or
   pasted anywhere.
6. Verifies the connection *as `radius_app`* (not the superuser) and
   confirms every expected table is reachable.

`app/core/config.py` also fails fast at startup if `RADIUS_DATABASE_URL`
and `DATABASE_URL` are ever accidentally set to the same database —
catching a copy/paste mistake before the two schemas could collide.

**Verify the connection** without running the full test suite:

```bash
python -c "from app.core.config import get_settings; s = get_settings(); \
print('radius db configured:', s.radius_database_url is not None)"
```

**Run the RADIUS-dependent tests** (a real integration suite — no
database calls are mocked):

```bash
pytest tests/test_radius_sync.py tests/test_captive_portal_payments.py tests/test_selcom_webhook.py
```

**Reset only the local RADIUS database** (never touches Supabase or
`infinity_radius`) if it ever gets into a bad state:

```bash
psql -U postgres -h localhost -c "DROP DATABASE radius;"
psql -U postgres -h localhost -c "DROP ROLE IF EXISTS radius_app;"
python -m scripts.setup_local_radius_db
```

## Router communication path

```
FastAPI (Railway) --HTTPS--> Network Agent (VPS) --WireGuard--> MikroTik RouterOS 7
```

Railway never opens a connection directly to a router's IP address. This
keeps router-facing credentials and the RouterOS API surface confined to a
single, purpose-built service.

`apps/api` sends the Network Agent only a router UUID (`app/integrations/network_agent/client.py`);
the agent alone resolves that UUID to a real WireGuard tunnel address and
RouterOS credentials (`apps/network-agent/app/core/router_registry.py`) —
there is no code path on either side that accepts an arbitrary caller-
supplied host. Every request between the two is HMAC-SHA256 signed over
method+path+timestamp+nonce+body (`app/integrations/network_agent/signing.py`
/ `apps/network-agent/app/core/security.py`), rejected outside a small
clock-skew window, and checked against an in-memory nonce cache for replay
protection; the signing key supports zero-downtime rotation (current +
previous secret both accepted). A Caddy reverse proxy
(`infrastructure/caddy/Caddyfile`) terminates TLS in front of the agent and
an IP allowlist (`apps/network-agent/app/core/ip_allowlist.py`) restricts
callers to Railway's static outbound IPs — both are defense in depth on
top of, never instead of, the request signature. `verify=False` is not a
parameter either side's HTTP client accepts.

MikroTik routers authenticate hotspot customers against FreeRADIUS
(`infrastructure/freeradius`) over the same WireGuard tunnel — 1812/UDP
for authentication, 1813/UDP for accounting — never over the public
internet (FreeRADIUS binds only to the WireGuard interface).

## Captive portal

A hotspot's walled-garden login redirect (generated by the Add Router
Wizard, `apps/web/app/dashboard/network/routers/add`) carries: `router=
<signed-token>`, `mac=<client-mac>`, `dst=<destination>`, and `login=
<router's-own-local-login-url>` — never a tenant id, never a raw router
id. The token (`app/core/router_token.py`) is Fernet-encrypted +
authenticated, so `apps/web`'s public `/captive-portal` page and
`apps/api`'s unauthenticated `/api/v1/public/captive-portal/*` endpoints
can resolve router -> tenant server-side without the client ever holding —
or being able to forge — that mapping. The walled garden itself allows
only two tenant-agnostic platform domains (`PUBLIC_CAPTIVE_PORTAL_DOMAIN`,
`PUBLIC_API_DOMAIN`) — never a wildcard like `*.supabase.co` — so an
unauthenticated hotspot client can reach the login page and pay/check
status, and nothing else.

The full flow: the portal loads the tenant's real branding and ACTIVE
packages, a customer picks one and enters a Tanzanian phone number
(`+255`), which creates a real `Transaction` + `PENDING` `Subscription`
and returns a second, independently-keyed signed token
(`app/core/transaction_token.py`) — the *only* thing the payment-waiting
screen holds, polled every 2-5s, so a client can never read or enumerate
anyone else's transaction row. On completion,
`CaptivePortalService.mark_transaction_completed` activates the
subscription and provisions real RADIUS credentials
(`app/services/radius_sync.py` — a dedicated engine against
`RADIUS_DATABASE_URL`, syncing the package's `Mikrotik-Rate-Limit`/
`Session-Timeout`/`Simultaneous-Use` into its `radgroupreply`/
`radgroupcheck` group), and the browser auto-submits a hidden form to the
router's own `login` URL to complete hotspot re-authentication — the
router then redirects the browser to `dst` itself.

## Payments

Selcom Collection (customer payments) and Disbursement (provider payouts)
are integrated behind `apps/api/app/integrations/selcom/`:

```
client.py          # SelcomClient facade — .collection / .disbursement
collection.py      # initiate_collection / query_collection / verify_callback / process_callback
disbursement.py    # create_disbursement / query_disbursement (thin, mirrors collection.py)
authentication.py  # outbound request auth — TODO(selcom-docs)
signatures.py      # outbound request signing + inbound webhook verification — TODO(selcom-docs)
schemas.py         # Infinity Radius's own field names, not Selcom's wire format
exceptions.py      # SelcomNotConfiguredError vs SelcomNotImplementedError, etc.
config.py          # SelcomConfig — api_base_url/api_key/api_secret/merchant_id
```

No endpoint path, auth header, signature format, or webhook field name is
invented anywhere in this package — every place Selcom's official
documentation needs to be mapped in is a `TODO(selcom-docs)` that raises
`SelcomNotImplementedError` (distinct from `SelcomNotConfiguredError`,
which just means credentials are unset) until it's filled in for real.

`POST /api/v1/webhooks/selcom/collection` (`apps/api/app/api/v1/webhooks.py`)
is real and reachable, and always saves the raw callback (`PaymentWebhook`)
regardless of outcome — but `verify_webhook_signature` always raises
today, so nothing can be marked SUCCESS through it yet: every webhook
currently comes back `{"status": "unverified"}`. Once verification is
real, `CollectionService.process_callback` validates the claimed
reference/amount/state against the stored `Transaction`, applies
idempotency (a transaction not still `pending` is a no-op "duplicate",
never re-applied), and — only then — calls
`CaptivePortalService.mark_transaction_completed`, which activates the
subscription, splits the gross amount into the tenant's `PLATFORM_FEE` and
`TENANT_SHARE` ledger entries and credits its pending balance
(`WalletService.process_collection`, row-locked against concurrent
collections — see "Tenant finance accounting" below), syncs RADIUS, and
writes the audit trail. All of that downstream logic is real
and tested today (`apps/api/tests/test_selcom_webhook.py` simulates a
verified callback by monkeypatching only the verification/field-extraction
boundary, never touching runtime code) — it's specifically the
authenticity check that awaits Selcom's official documentation.

The captive portal never sends an authoritative payment amount — the
charged amount always comes from the server-resolved `package.price_tzs`,
looked up from `package_id` after the router token resolves the tenant;
see `CaptivePortalService.initiate_payment`.

## Authorization model

Two layers, defense in depth — see `docs/rls-policies.md` for the full
reference:

1. **Supabase RLS** — row-level policies on every tenant-scoped table,
   keyed by `public.current_tenant_id()`, which reads `public.profiles`
   (never a JWT claim).
2. **FastAPI tenant validation** — `apps/api/app/core/security.py` verifies
   the JWT signature to learn WHO is calling (`sub`), then resolves
   `tenant_id` and role(s) fresh from `profiles`/`profile_roles` on every
   request. A `tenant_id` supplied by the client — in a request body, query
   param, or even inside a signed JWT's `app_metadata` — is never accepted
   as authoritative on its own; the database row is.

RBAC role checks (`SUPER_ADMIN`, `TENANT_OWNER`, `TENANT_ADMIN`,
`ACCOUNTANT`, `NETWORK_TECHNICIAN`, `CUSTOMER_CARE`, `CASHIER`, and
`CUSTOMER` prepared for the customer-portal auth phase — see
`apps/api/app/core/roles.py`) sit on top of both layers.

## Money

All monetary values are `NUMERIC` in Postgres and `Decimal` in Python —
never `float`. Over the wire (API <-> frontend), amounts are decimal
strings, not JSON numbers, so no precision is lost to floating-point
rounding. See `packages/types/src/money.ts`.

## Tenant finance accounting

`ledger_entries` is the financial source of truth. `tenant_wallets` is only
ever a summarized current-state cache derived from it — five independently
moving buckets (`available_balance_tzs`, `pending_balance_tzs`,
`reserved_balance_tzs`, `frozen_balance_tzs`, `total_disbursed_tzs`), never
edited directly. Every method that changes a wallet balance
(`app/services/wallet.py`'s `WalletService`) takes a `SELECT ... FOR UPDATE`
row lock on the wallet before reading it, so concurrent operations on the
same tenant's wallet serialize instead of racing into a lost update, and
writes an immutable `LedgerEntry` justifying exactly what changed.

`ledger_entries.entry_type` is one of eight values, enforced by a Postgres
CHECK constraint and mirrored in `app.core.enums.LedgerEntryType`:
`COLLECTION`, `TENANT_SHARE`, `PLATFORM_FEE`, `REFUND`, `REVERSAL`,
`DISBURSEMENT`, `DISBURSEMENT_REVERSAL`, `ADJUSTMENT`. Each entry also
carries a `direction` (`credit`/`debit`, explicit — never inferred from
`entry_type`) and a `wallet_bucket` (which of the five wallet columns
moved, `NULL` for entries that don't move a tenant-owned bucket at all,
like the informational `COLLECTION` record and `PLATFORM_FEE`).

Platform commission is never hard-coded. Each tenant has its own
commercial terms row (`tenant_commercial_terms` — commission rate,
versioned: changing a rate deactivates the old row and inserts a new one,
so history is never overwritten; a partial unique index enforces exactly
one active row per tenant), managed only by a super admin via
`POST /api/v1/tenants/{tenant_id}/commercial-terms`
(`app/services/commercial_terms.py`). `WalletService.process_collection`
fails closed with a `DomainValidationError` if a tenant has no active
commercial terms configured, rather than assuming a default rate.

On a completed customer payment, `WalletService.process_collection` splits
the gross amount using the tenant's own active commercial terms: the
platform fee is quantized to 2dp (`ROUND_HALF_UP`, `app.core.money.
quantize_tzs`) and the tenant share is the remainder by subtraction, so the
two always sum exactly to the gross amount. Three ledger entries are
written in the same locked transaction — an informational `COLLECTION`
record of the gross amount, a `PLATFORM_FEE` record of what the platform
keeps, and the `TENANT_SHARE` entry that actually credits the tenant's
`pending` balance. `CaptivePortalService.mark_transaction_completed` calls
this on every completed payment.

Money moves through the buckets like this:

```
COLLECTION (gross) -> split -> PLATFORM_FEE (kept) + TENANT_SHARE -> pending
pending  -> settle_pending ------------------------------------> available
available -> reserve_for_withdrawal -----------------------------> reserved
reserved -> complete_disbursement (DISBURSEMENT entry) ----> total_disbursed
total_disbursed -> reverse_disbursement (DISBURSEMENT_REVERSAL) --> available
```

`settle_pending` (pending -> available) and `reserve_for_withdrawal`
(available -> reserved, held for an in-flight `Withdrawal`) don't get their
own ledger entry type — `settlement_logs` and `withdrawals.status` are the
source of truth for those two specific moves, the same way the 8-type
vocabulary doesn't include "settlement" or "reserve". `record_refund` and
`record_reversal` are the tested (but not yet externally triggered — no
refund provider integration exists yet) primitives for a `REFUND` (debits
`available`) and a `REVERSAL` (debits `pending`, for a collection later
found bad before it settled). `complete_disbursement`/`reverse_disbursement`
are real and driven end to end by the withdrawal lifecycle below.

No frontend ever computes a balance, and no endpoint ever accepts a raw new
balance value. The only way to manually correct a wallet is
`POST /api/v1/tenants/{tenant_id}/wallet/adjustments` (super admin only) —
a signed delta against one named bucket with a mandatory reason, recorded
as an immutable `ADJUSTMENT` ledger entry attributed to the acting admin.

## Selcom Disbursement architecture

Whether — and how — Infinity Radius ever disburses a tenant's funds is
gated by two independent switches, because the platform must never assume
it legally or commercially holds tenant money:

1. **Settlement mode** (`app.core.enums.SettlementMode`, per tenant,
   versioned exactly like commercial terms — `tenant_settlement_config`,
   `app/services/settlement_config.py`, managed only by a super admin via
   `/api/v1/tenants/{tenant_id}/settlement-config`). A tenant with no
   explicit row is **`direct_merchant_settlement`** — the safe default:
   Selcom settles directly with the tenant's own merchant account, and
   Infinity Radius's wallet is informational only.
   `PayoutService.request_withdrawal` refuses to run for any tenant not
   explicitly switched to **`platform_managed_wallet`**.
2. **`Settings.selcom_disbursement_enabled`** (`app/core/config.py`,
   platform-wide, defaults to `False`) — an explicit business/legal
   approval gate, independent of whether Selcom credentials happen to be
   configured (`SelcomConfig.is_configured`). Checked both when a
   withdrawal is requested and again immediately before submission, so
   flipping it off mid-flight can't be raced.

### Withdrawal lifecycle (threshold-gated Super Admin approval)

Three tables: `withdrawals` (the request itself), `withdrawal_destinations`
(mobile money/bank/Selcom targets a tenant configured, each carrying a
canonical `destination_code` — `app.core.enums.DestinationCode`, the one
source of Selcom FI codes), `withdrawal_events` (an immutable, ordered log
of every status transition — distinct from `ledger_entries`, which only
records money movement).

`withdrawals.status` is one of ten values (`app.core.enums.WithdrawalStatus`),
enforced by a Postgres CHECK constraint:

```
DRAFT -> APPROVED -> PROCESSING -> SUCCESS                 (<= threshold, auto)
                                 -> AMBIGUOUS -> SUCCESS/FAILED  (resultcode 999, query-resolved)
                                 -> FAILED
DRAFT -> PENDING_APPROVAL -> APPROVED -> PROCESSING -> ...  (> threshold, SUPER_ADMIN)
                           -> REJECTED                      (SUPER_ADMIN declines)
DRAFT -> CANCELLED                     (2FA exhausted/expired, or requester cancels)
SUCCESS -> REVERSED                    (super admin only, exceptional)
```

**Approval is a pure amount threshold**
(`Settings.selcom_withdrawal_approval_threshold_tzs`, default `100000`,
server-side only — never a frontend control): `amount <= threshold` skips
human approval entirely; `amount > threshold` requires a `SUPER_ADMIN` —
**never** a tenant user, and never the requester. `approval_required` is
computed once, at request time, and persisted on the row so a later
threshold change never rewrites a past withdrawal's history. 2FA
(`app/services/two_factor.py`) is unrelated to approval and unchanged —
it confirms the *requester's own* identity, independent of who (if anyone)
later reviews the amount.

The full flow (`app/services/payouts.py`'s `PayoutService`), every step
row-locked (`WithdrawalRepository.get_by_id_for_update`) and every
transition written as a `WithdrawalEvent` + an `audit_logs` entry:

1. **`request_withdrawal`** (`TENANT_OWNER` only) — verifies settlement
   mode, the disbursement flag, and the tenant's `payout_enabled` feature
   flag (`tenant_feature_flags` — approval status never overrides this),
   then row-locks and reserves the amount (`WalletService.
   reserve_for_withdrawal`, `available -> reserved`) *before* anything
   else, computes and stores `approval_required`, and issues a one-time
   2FA challenge. A server-generated `idempotency_key` (never
   client-supplied) is stamped on the row once, here, and never
   regenerated — it becomes Selcom's own `transId`.
2. **`confirm_two_factor`** (requester only) — verifies the code. On
   success: `approval_required` withdrawals move to `PENDING_APPROVAL`
   and a Super Admin review email goes out (Resend,
   `send_admin_withdrawal_review_email`); everything else moves straight
   to `APPROVED` and calls `_submit_to_selcom` immediately — no human step
   at all. A wrong code's attempt-increment is committed even though the
   HTTP response is a 422 — only a genuinely exhausted/expired challenge
   auto-cancels the withdrawal and releases the reservation.
3. **`approve_withdrawal` / `reject_withdrawal`** (`SUPER_ADMIN` only —
   `app/api/v1/admin_withdrawals.py`, cross-tenant lookup) — reject
   releases the reservation; approve immediately attempts submission.
4. **`_submit_to_selcom`** — never re-entrant (same "never retry payout
   submission blindly" guarantee as before). Re-verifies the destination
   via `GET /v1/account/lookup` (a fresh `transId`) immediately before
   transferring — the resulting `accountName` is the *only* source of
   `verified_recipient_name`, never a client-supplied value — then moves
   to `PROCESSING` and calls `POST /v1/transaction/process` exactly once
   with `purpose="FT"`. A transport-level failure (timeout/connection
   error) never marks the row FAILED and never resubmits — it queries
   Selcom with the same `transId` instead (`_reconcile_locked`).
5. **`_apply_provider_result`** — interprets a Selcom resultcode
   (`000`=SUCCESS, `111`/`927`=INPROGRESS, `999`=AMBIGUOUS, anything else
   =FAIL — `interpret_resultcode`) from any of three sources: the direct
   `transaction/process` response, a reconciliation `transaction/query`,
   or a webhook-triggered query. SUCCESS calls
   `WalletService.complete_disbursement` (`reserved -> total_disbursed`,
   a `DISBURSEMENT` entry) and cross-checks the provider-reported amount
   against the withdrawal before finalizing — a mismatch becomes
   `AMBIGUOUS`, never a silent finalize. INPROGRESS leaves it `PROCESSING`.
   AMBIGUOUS is never retried — only resolved by a later query. FAIL
   releases the reservation. Idempotent throughout: only acts while
   status is `PROCESSING`/`AMBIGUOUS`.
6. **`reverse_withdrawal`** (super admin only, under
   `/api/v1/tenants/{tenant_id}/withdrawals/{withdrawal_id}/reverse`,
   unchanged) — the exceptional path for an already-`SUCCESS`'d
   disbursement that turns out to be wrong: `WalletService.
   reverse_disbursement` (`total_disbursed -> available`, a
   `DISBURSEMENT_REVERSAL` entry) and the withdrawal moves to `REVERSED`.

### Selcom Business API (`app/integrations/selcom_business/`)

The real, RSA-SHA256-signed transport (developer.selcom.business) —
distinct from `app/integrations/selcom/` (the older, still-unimplemented
Collection API module, untouched). `client.py` implements all four
documented endpoints (`account/lookup`, `transaction/process`,
`transaction/query`, `balance`); `signing.py` builds the exact canonical
string (`timestamp=<iso8601-ms>&field1=value1&...`, fields in
`signed-fields` header order) and signs it with
`cryptography`'s PKCS#1 v1.5; `schemas.py` holds the request/response
shapes and `interpret_resultcode`; `errors.py` the exception hierarchy.
`client.build_url` defensively strips a trailing `/v1` from the
configured base URL before joining a path — the public docs display the
production base AS `https://api.selcom.business/v1` while also
documenting `/v1/...` paths, which would otherwise double up.

**Callback is a signal, never authoritative** — the public docs describe
no callback signature/authentication scheme. `POST
/api/v1/webhooks/selcom-business/disbursement` only extracts
`reference_id`, looks up the matching withdrawal, and calls
`PayoutService.reconcile_withdrawal`, which re-verifies via an
authenticated `GET /v1/transaction/query` before anything is ever
finalized — the callback payload's own `status`/`amount` claims are never
trusted directly. A periodic Celery Beat task
(`app/tasks/reconciliation.py`, every 2 minutes, registered on `apps/api`'s
own `celery_app` — it needs the API's DB/service layer, unlike
`apps/worker`) sweeps every `PROCESSING`/`AMBIGUOUS` withdrawal the same
way, as a safety net for a missed or never-sent callback.

Run locally against the sandbox base URL first
(`SELCOM_BUSINESS_ENVIRONMENT=sandbox`) — no production disbursement until
signing, lookup, process, query, and callback/reconciliation are all
verified working end to end.

### 2FA — an honest interim design

There is no SMS/email provider integrated anywhere in this codebase.
`app/services/two_factor.py` implements the confirmation-code *mechanism*
for real (generate, hash, 10-minute expiry, rate-limited verification) —
only the hash is ever stored, and the raw code is returned exactly once,
at issuance, the same convention already used for RADIUS secrets and
WireGuard private keys. Delivery is the explicit gap: until a real
provider is wired in, the one-time code is recorded only in the audit
trail (`audit_logs`, itself authenticated and role-gated), as an interim,
auditable distribution path — not a public one, and not yet a true second
factor. `WithdrawalRead` never exposes the code or its hash.

## Tenant dashboard

The tenant dashboard landing page (`apps/web/app/dashboard/page.tsx`) is
backed entirely by real aggregation queries — `app/services/dashboard.py`'s
`DashboardService`, exposed via `app/api/v1/dashboard.py`:

```
GET /api/v1/dashboard/summary             -- the 6 KPI cards, one query each
GET /api/v1/dashboard/collections-trend   -- daily gross COLLECTION totals, trailing 14 days
GET /api/v1/dashboard/session-trend       -- daily session-start counts, trailing 14 days
GET /api/v1/dashboard/package-performance -- per-package subscription/revenue ranking
GET /api/v1/routers/health                -- per-router status + honestly-null telemetry
```

Every one of these is tenant-scoped via `TenantContext`/`require_tenant_role`
(`app.core.context`) — a client can never supply or influence which
tenant's numbers come back, the same trust chain every other production
endpoint uses. "Today" is computed in `Settings.default_timezone`
(Africa/Dar_es_Salaam), not UTC, so a day boundary lines up with when a
Tanzanian operator actually experiences "today".

`DashboardSummaryRead` returns plain real numbers (never a `MetricValue`
placeholder-status wrapper) — `online_users`, `today_collections_tzs`,
`active_vouchers`, `routers_online`, `routers_total`, `failed_transactions`,
`available_wallet_balance_tzs` — because these are always computable
COUNT()/SUM() queries, not integrations that can be "not configured". A
brand-new tenant legitimately gets all zeros; that is the correct answer,
not a placeholder the frontend has to special-case.

The two trend endpoints and package-performance never fabricate a data
point to make a chart "look full": `collections_trend`/`session_trend`
return `[]` when there is no real activity anywhere in the window (the
frontend renders `EmptyChartState` — "No collections recorded yet" /
"No activity recorded yet" — never a flat invented line), and only fill
zero-value days *between* two real data points once at least one real
value exists in the window. `package_performance` returns `[]` when no
subscription has ever been created against any package, even if packages
themselves exist.

`GET /api/v1/routers/health` (`RouterService.health`, registered before
`/{router_id}` — same route-ordering class of bug as payouts.py's
`/destinations`) returns each router's real `status`/`last_seen_at` (only
ever written by the not-yet-built Network Agent monitoring integration, so
realistically `"unknown"`/`null` today — never fabricated to look
otherwise) alongside `active_users`/`latency_ms`/`cpu_load_pct`/
`uptime_seconds`, which have no backing telemetry pipeline at all and are
always `null` — the frontend renders "Unavailable" for each, never a
random number.

On the frontend, `packages/ui` gained a small dashboard component family —
`DashboardMetricCard`, `DashboardSection`, `EmptyChartState`,
`RouterHealthCard`, `DashboardMetricGridSkeleton`/`DashboardChartSkeleton`/
`DashboardListSkeleton`, and a shared `formatMoney()` helper (also now used
internally by `MoneyDisplay`) that renders `"TZS 1,500"`-style amounts via
`Intl.NumberFormat("en-TZ", { currencyDisplay: "code" })` — the ISO code is
always shown, never a symbol that could be mistaken for another currency.
Every dashboard data-fetching component (`apps/web/components/dashboard/*`)
follows the same loading/error/empty/success branching already established
by `useApiQuery` (`apps/web/lib/hooks/use-api-query.ts`) — no dashboard
panel silently substitutes a fake row for a failed or empty fetch.

The tenant's real name and role (`GET /api/v1/auth/me` ->
`CurrentUserRead.tenant_name`/`.roles`, via the new
`apps/web/lib/hooks/use-current-user.ts`) now drive the dashboard shell's
top-bar title and sidebar footer role label — previously hard-coded
strings (`"Tenant Dashboard"`, `"Tenant Operator"`).

## Super-admin dashboard

The platform-wide super-admin landing page (`apps/web/app/super-admin/page.tsx`)
mirrors the tenant dashboard's contract exactly, but aggregated across
every tenant instead of one — `app/services/super_admin_dashboard.py`'s
`SuperAdminDashboardService`, exposed via new routes appended to the
existing `app/api/v1/super_admin.py`:

```
GET /api/v1/super-admin/dashboard-summary      -- the 9 KPI cards
GET /api/v1/super-admin/collections-trend      -- daily gross COLLECTION totals, all tenants, trailing 14 days
GET /api/v1/super-admin/tenant-growth-trend    -- new tenants per day, trailing 30 days
GET /api/v1/super-admin/pending-payouts        -- withdrawals in PENDING_APPROVAL/APPROVED, joined to tenant name
GET /api/v1/super-admin/audit-logs             -- platform-wide audit trail (tenant_id=None — no tenant filter)
```

These are deliberately **new** routes, not a rewrite of the existing
`/overview`/`/resources/{resource}`/`/system-health` stubs in the same
file — those three keep their exact `MetricValue`/`ResourceListResponse`
shape (`tests/test_super_admin.py` locks it in, and some earlier-phase
frontend calls still hit them), the same "add new, don't mutate the old
stub" precedent the tenant dashboard set with `/api/v1/tenant/overview`
vs. `/api/v1/dashboard/*`.

Of the 9 cards, 8 are fully real aggregations (`active_tenants`/
`suspended_tenants` — `Tenant.status`, `routers_total`/`routers_online`,
`radius_active_sessions` — `user_sessions.status = 'active'` with no
tenant filter, `collections_today_tzs`, `pending_payouts`/
`pending_payouts_amount_tzs`, `failed_webhooks` — the honest definition
given today's schema is `signature_verified = false AND processed = true`,
an attempted-and-rejected callback, not "not yet verifiable"). The 9th,
**`reconciliation_exceptions`, has no backing table anywhere in this
codebase** (confirmed: the string only exists as an allow-listed
`resource` path param in the legacy stub) — it is reported via
`MetricValue.not_configured()`, not a fabricated 0, because 0 would
falsely imply "checked, found none" rather than the truth "not tracked
yet". `SuperAdminSummaryCards` (`apps/web/components/super-admin/`)
renders that field's real `status` straight through `DashboardMetricCard`,
which already understands `MetricStatus` — no special-casing needed on
the frontend.

The two trend charts live behind a `SegmentedTabs` switcher
(`PlatformTrendsPanel`) exactly like the tenant dashboard's
Collections/Sessions tabs — `CollectionsTrendChart` gained an optional
`path` prop (default: the tenant-scoped endpoint) so the exact same chart
renders the platform-wide series without duplicating the component.


## Client Signup, Business Onboarding & Super Admin Approval

`POST /api/v1/onboarding/register` is the single unauthenticated endpoint
behind `/get-started` — a single-page signup collecting the account
owner, business details, location, and (optional) authorized contact in
one submission. The frontend never creates tenant/profile/wallet state
itself; `OnboardingService.register()` (`apps/api/app/services/onboarding.py`)
orchestrates everything server-side:

1. Validate input (Pydantic + `normalize_tz_phone` + email-uniqueness check).
2. Create the Supabase Auth user via the Admin API
   (`app/core/supabase_admin.py`, service-role key) — `email_confirm=false`.
   This runs **before** any local DB write, specifically so a later
   failure can be compensated by deleting the just-created auth user
   rather than leaving an orphaned account.
3. The `handle_new_auth_user` trigger (see `rls-policies.md`) has already
   inserted a bare `profiles` row (`tenant_id=NULL`, `status='invited'`)
   the instant the auth user was created — `_create_local_records` claims
   that same row (sets `tenant_id`, `first_name`/`last_name`, `phone`,
   `status='active'`) rather than inserting a second one.
4. In one transaction: create `tenants` (`status=PENDING_VERIFICATION`),
   assign the `TENANT_OWNER` role, create `tenant_verifications`,
   `tenant_wallets` (via the existing `WalletService.get_or_create_wallet`
   — not duplicated), `tenant_settings`, and `tenant_feature_flags`
   (`collection_enabled`/`payout_enabled`/`api_enabled` all `false`).
   Commit. If anything in this step fails, roll back and delete the auth
   user.
5. Best-effort, outside that transaction: generate a real Supabase
   `signup` action link (`SupabaseAdminClient.generate_link` — never an
   invented token) and send it via Resend
   (`app/integrations/resend/service.py`), plus a Super Admin review
   notification to `SUPER_ADMIN_REVIEW_EMAIL`. Every send attempt is
   recorded in `email_events`, success or failure — a Resend outage never
   unwinds an already-committed account.

**Tenant status is the real access gate**, not a frontend redirect alone:
`app.core.context.get_tenant_context` (the dependency underlying
`require_tenant_role` and every tenant-scoped router) rejects any request
whose `tenants.status != ACTIVE` with 403, regardless of what the
frontend does. `apps/web/lib/auth.ts`'s `requireActiveTenantUser()` /
`requireSuperAdmin()` mirror this for UX (routing to the right
`/account/*` page) but are not themselves the authorization boundary.

**Super Admin review** (`/super-admin/tenants`, `/super-admin/tenants/{id}`)
is powered by `app/services/admin_tenants.py` /
`app/api/v1/admin_tenants.py` (`POST /api/v1/admin/tenants/{id}/approve|
reject|request-more-information|suspend|reactivate`, SUPER_ADMIN only).
Approval sets `tenants.status=ACTIVE` only — it deliberately never
touches `tenant_feature_flags.collection_enabled`/`payout_enabled`.
Business approval and financial access are two independent Super Admin
decisions: `POST /api/v1/admin/tenants/{id}/collection` and `/payout`
(`AdminTenantService.set_collection_enabled`/`set_payout_enabled`), each
its own audit action (`TENANT_COLLECTION_ENABLED`/`_DISABLED`,
`TENANT_PAYOUT_ENABLED`/`_DISABLED`) and never touching a wallet balance
or ledger entry. Infinity Radius still centrally manages Collections and
Payouts once enabled — tenants are never asked for payment-provider
credentials — but "approved" and "financially live" are not the same
switch. Every transition (approval included) writes an `audit_logs`
entry and a best-effort Resend notification.

Tables added: `tenant_settings`, `tenant_feature_flags`,
`tenant_verifications`, `email_events` (migration
`11075bc476b4_onboarding_and_verification`) — RLS-enabled, read-only to
tenant clients (`tenant_id = current_tenant_id() OR is_super_admin()`),
writable only by the trusted backend, matching `tenant_wallets`/
`audit_logs`'s existing pattern.

### Assigning the First Real Super Admin

There is no seeded Super Admin account and no self-service or API path to
become one — by design. To grant the role:

1. Have the person sign in once (or be invited) through the real
   Supabase Auth project, so their `profiles` row exists (the
   `handle_new_auth_user` trigger creates it automatically).
2. Run, against the same database the API uses:
   ```
   cd apps/api
   python -m scripts.assign_super_admin owner@yourcompany.com
   ```
   This sets `profiles.tenant_id = NULL` and inserts the matching
   `profile_roles` row (`role = SUPER_ADMIN`, `tenant_id = NULL`) for
   that account. It never creates an account, sets a password, or prints
   one — it only grants a role to an account that already exists.

Every subsequent Super Admin can be granted the same way, or invited by
an existing Super Admin once a staff-invitation UI exists for platform
accounts (not built yet — out of scope here).
