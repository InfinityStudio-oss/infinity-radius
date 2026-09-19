"""Environment-validated application settings.

Pydantic Settings fails fast at process startup if a required variable is
missing or malformed, rather than surfacing as an obscure error mid-request.
"""

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "Infinity Radius API"
    environment: Literal["development", "staging", "production"] = "development"
    api_v1_prefix: str = "/api/v1"
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # --- Localization (Tanzania is the initial market; see docs/localization.md) ---
    default_country_code: str = "TZ"
    default_currency: str = "TZS"
    default_timezone: str = "Africa/Dar_es_Salaam"
    default_locale: str = "en-TZ"

    # --- Primary database (Supabase Postgres) ---
    database_url: PostgresDsn

    # --- Migration safety (see app/core/migration_safety.py, alembic/env.py) ---
    # A bare `alembic upgrade head` has twice resolved this DATABASE_URL to
    # the real production Supabase database from a developer's local .env
    # (whose ENVIRONMENT was "development" — proof ENVIRONMENT alone isn't
    # a reliable signal). Both migrations happened to be additive/harmless,
    # but nothing stopped a destructive one. Default False: any
    # non-localhost DATABASE_URL is refused until this is explicitly set,
    # only for the one migration command, then unset again.
    allow_production_migrations: bool = False
    # Explicit operator override for the rare case the hostname heuristic
    # in app/core/migration_safety.py gets a database target wrong (e.g. a
    # future staging host that isn't "localhost" but is genuinely safe).
    # Never required for normal local/production use.
    database_migration_target: Literal["local", "test", "staging", "production"] | None = None

    # --- RADIUS database (separate Postgres on the Network VPS, FreeRADIUS schema) ---
    radius_database_url: PostgresDsn | None = None

    # --- Supabase (JWT verification for incoming requests) ---
    supabase_url: str
    # Modern Supabase JWT Signing Keys system — the backend verifies every
    # incoming Authorization: Bearer token against the project's published
    # public signing keys (app/core/security.py), never a shared symmetric
    # secret. Typically
    # "https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json".
    supabase_jwks_url: str = Field(
        description="Supabase project JWKS endpoint, used to verify Authorization: Bearer tokens.",
    )
    # Secret/server key (the modern replacement for the legacy
    # service_role key) — needed only by OnboardingService to create the
    # Supabase Auth user server-side (app/core/supabase_admin.py). Left
    # unset until a real Supabase project is connected: never printed,
    # never sent to the frontend, and onboarding fails closed with a clear
    # "not configured" error rather than the app refusing to boot.
    supabase_secret_key: str | None = None

    # --- Public application URL (used to build email links) ---
    app_url: str = "http://localhost:3000"

    # --- Resend (transactional email — client/admin onboarding notices).
    # Left unset until a real API key is supplied; ResendEmailService fails
    # closed the same way the Selcom client does — see
    # app/integrations/resend/exceptions.py. ---
    resend_api_key: str | None = None
    resend_from_email: str | None = None
    resend_from_name: str = "Infinity Radius"
    # Recipient for "new tenant awaiting approval" notifications.
    super_admin_review_email: str | None = None

    # --- Redis / Celery ---
    redis_url: RedisDsn

    # --- Rate limiting (fixed window, per client IP; see app.middleware.rate_limit) ---
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    # --- Network Agent (Railway -> HTTPS -> Network Agent VPS -> WireGuard -> MikroTik) ---
    network_agent_base_url: str | None = None
    network_agent_api_key: str | None = None

    # --- Secrets at rest (router RADIUS secrets, WireGuard private keys) and
    # the signed public router token (captive-portal redirects) — two
    # distinct Fernet keys, generated with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Deliberately separate: the token key protects a value handed to
    # semi-public router infrastructure; the secrets key never leaves the
    # server. Never share, and never derive one from the other.
    secrets_encryption_key: str
    router_token_signing_key: str
    transaction_token_signing_key: str

    # --- Walled garden (see app/services/router_provisioning.py) ---
    # The tenant-agnostic platform domains a hotspot's walled garden must
    # allow so the captive portal and its payment/status calls work before
    # the customer is authenticated. Never a wildcard (e.g. "*.supabase.co")
    # — only the exact domains actually needed.
    public_captive_portal_domain: str | None = None
    public_api_domain: str | None = None

    # --- WireGuard server (the Network VPS's own wg0.conf — see
    # infrastructure/wireguard/wg0.conf.example) — needed to generate a
    # complete router-side WireGuard config in the Add Router Wizard.
    wireguard_server_public_key: str | None = None
    wireguard_server_endpoint: str | None = None  # "<public-ip-or-host>:<port>"
    wireguard_server_subnet: str = "10.90.0.0/24"

    # --- Selcom (Collection + Disbursement). Left unset until official
    # credentials/spec are supplied — see app/integrations/selcom/. ---
    selcom_api_base_url: str | None = None
    selcom_api_key: str | None = None
    selcom_api_secret: str | None = None
    selcom_merchant_id: str | None = None

    # Disbursement is a separate, explicit gate from having credentials
    # configured: even with SELCOM_API_KEY etc. set, no withdrawal may be
    # requested or submitted until Infinity has explicit business/legal
    # approval for the disbursement model and flips this on. Defaults to
    # off — see app/services/payouts.py and docs/architecture.md.
    selcom_disbursement_enabled: bool = False

    # --- Selcom Business API (real disbursement transport) ---
    # developer.selcom.business — RSA-SHA256 signed, distinct from the
    # older selcom_api_key/selcom_api_secret HMAC-style config above (which
    # remains for the still-unimplemented Collection API only). See
    # app/integrations/selcom_business/. "sandbox" or "production" —
    # sandbox until real credentials/access are confirmed working end to
    # end (account lookup, transaction process, transaction query,
    # callback/reconciliation) — never production by accident.
    selcom_business_environment: Literal["sandbox", "production"] = "sandbox"
    # Origin only, e.g. "https://sandbox.selcom.business" or
    # "https://api.selcom.business" — never include a trailing "/v1": the
    # client always appends the full "/v1/..." path itself, and defensively
    # strips one if present (the public docs display the production base
    # AS "https://api.selcom.business/v1", which would double up otherwise
    # — see app/integrations/selcom_business/client.py).
    selcom_business_base_url: str | None = None
    selcom_business_api_key: str | None = None
    # PEM-encoded RSA private key, base64-encoded once more so a multiline
    # PEM block survives being pasted into a single-line env var. Decode
    # with base64.b64decode(...).decode() to recover the real PEM. Never
    # logged, never returned in any API response, never sent to Vercel.
    selcom_business_private_key_b64: str | None = None
    # Only needed if the Balance endpoint is used (Super Admin provider-
    # health visibility) — never the tenant wallet balance.
    selcom_business_account_number: str | None = None

    # --- Production payout kill switch (see app/services/payouts.py._submit_to_selcom) ---
    # A THIRD, independent gate on top of selcom_business_environment and
    # selcom_disbursement_enabled — a real production disbursement requires
    # ALL THREE: environment=production AND disbursement_enabled=true AND
    # this. Defaults False so flipping environment to "production" alone
    # (or even that plus disbursement_enabled) is never, by itself, enough
    # to move real money — this must be turned on deliberately, separately,
    # only when an operator is actually ready for the first real payout.
    selcom_production_payouts_enabled: bool = False

    # --- Withdrawal approval threshold (see app/services/payouts.py) ---
    # amount <= this: no Super Admin approval, proceeds straight to Selcom
    # once 2FA confirms. amount > this: PENDING_APPROVAL until a SUPER_ADMIN
    # approves or rejects it. Server-side only — never a frontend control.
    selcom_withdrawal_approval_threshold_tzs: Decimal = Decimal("100000")

    # --- Withdrawal safety limits (see app/services/payouts.py) ---
    # No product/business policy has been decided on these yet — every
    # limit defaults to None (disabled/unenforced) so this platform's
    # actual behavior doesn't silently change until an operator makes a
    # real decision and sets a value. The enforcement code exists and is
    # tested now so activating a limit later needs only a Railway
    # variable, not a deploy.
    withdrawal_min_amount_tzs: Decimal | None = None
    withdrawal_max_single_amount_tzs: Decimal | None = None
    withdrawal_daily_limit_tzs: Decimal | None = None
    withdrawal_daily_count_limit: int | None = None

    # --- Stale withdrawal alerting (see app/tasks/reconciliation.py) ---
    # A withdrawal that's been PROCESSING or AMBIGUOUS for longer than
    # this is almost certainly stuck waiting on a human, not the next
    # Beat sweep — alert once, then respect the cooldown rather than
    # re-alerting every 120s while it stays unresolved.
    withdrawal_processing_alert_minutes: int = 30
    withdrawal_ambiguous_alert_minutes: int = 15
    withdrawal_stale_alert_cooldown_minutes: int = 60

    # --- Withdrawal OTP (see app/services/two_factor.py) ---
    # HMAC key for hashing withdrawal OTPs — a small (6-digit) keyspace
    # means an unsalted/unkeyed hash would be brute-forceable offline if
    # the DB ever leaked, so this key is required before any OTP can be
    # issued or verified. Left unset until a real value is generated
    # (`python -c "import secrets; print(secrets.token_hex(32))"`) and set
    # in Railway Variables only — never committed, never sent to Vercel,
    # and only the web service needs it (OTP verification is synchronous,
    # never done from the Celery worker/beat).
    otp_verification_secret: str | None = None
    withdrawal_otp_ttl_seconds: int = 600
    withdrawal_otp_max_attempts: int = 5
    withdrawal_otp_resend_cooldown_seconds: int = 60
    withdrawal_otp_max_sends: int = 5

    # --- Internal worker->web disbursement-reconciliation auth (see
    # app/core/internal_auth.py, app/api/v1/internal_disbursements.py,
    # app/integrations/internal_web/client.py) ---
    # Dedicated HMAC secret for the worker to call web's internal
    # reconciliation endpoint over Railway private networking, so the
    # Celery worker never needs Selcom Business credentials/egress itself
    # (only web's Static Outbound IPs need Selcom whitelisting). Deliberately
    # separate from otp_verification_secret and the Network Agent key —
    # never shared across trust boundaries. Required on web (to verify) and
    # worker (to sign); generate with
    # `python -c "import secrets; print(secrets.token_hex(32))"`.
    internal_worker_web_hmac_key: str | None = None
    # Replay-protection timestamp tolerance for internal HMAC requests.
    internal_request_max_skew_seconds: int = 90
    # Worker-only: base URL of the web service reached over Railway private
    # networking (e.g. "http://<RAILWAY_PRIVATE_DOMAIN>:8000"). Unset on web.
    internal_web_base_url: str | None = None

    # --- Selcom Mobile Checkout Collection (customer -> platform payments,
    # STK/wallet-pull push) — see app/integrations/selcom_collection/.
    # developer.selcommobile.com — a DIFFERENT Selcom product from Business
    # Disbursement above: different credentials, different signing scheme,
    # never shared. Web-only, same least-privilege rule as Disbursement —
    # never on the worker/beat. The operator has stated no separate test
    # environment exists for these credentials, so there is no
    # "SELCOM_COLLECTION_ENVIRONMENT" — only the two kill switches below.
    selcom_collection_base_url: str | None = None
    selcom_collection_api_key: str | None = None
    # HS256 only — exactly one of this or the private key below is set,
    # matching selcom_collection_digest_method.
    selcom_collection_api_secret: str | None = None
    # RS256 only — base64-encoded PEM, same convention as
    # SELCOM_BUSINESS_PRIVATE_KEY_B64 (decode with base64.b64decode(...)).
    selcom_collection_private_key_b64: str | None = None
    # "HS256" | "RS256" — whichever Selcom actually issued; never guessed.
    selcom_collection_digest_method: str | None = None
    # Vendor/Merchant ID allocated by Selcom for Checkout (distinct from
    # any Disbursement account number).
    selcom_collection_vendor: str | None = None
    # First gate: the general feature kill switch. False until the
    # integration is implemented, tested, and credentials are configured.
    selcom_collection_enabled: bool = False
    # Second, independent gate: because there is no sandbox for these
    # credentials, a real STK/wallet-pull is only ever sent when BOTH this
    # AND selcom_collection_enabled are true — mirrors
    # selcom_production_payouts_enabled's role for Disbursement. Query-only
    # reconciliation of an already-created order is allowed while this is
    # false; only NEW payment initiation (create-order/wallet-payment) is
    # blocked.
    selcom_collection_production_enabled: bool = False
    # Infinity Radius's OWN operational review threshold — NOT a Selcom-
    # documented timeout (Selcom's docs state no expiry/timeout for how
    # long order-status may report PENDING/INPROGRESS; see
    # docs/architecture.md's Collection section). Purely advisory: past
    # this many minutes since stk_requested_at, a still-PENDING/INPROGRESS
    # order is flagged CollectionStatus.REQUIRES_REVIEW for Super Admin/
    # support visibility — never terminal, never blocks a later genuine
    # provider result, never affects any wallet. <= 0 disables the flag
    # entirely (falls back to the old PENDING/INPROGRESS-forever behavior).
    selcom_collection_pending_review_minutes: int = 30

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _radius_database_must_be_separate(self) -> "Settings":
        """RADIUS_DATABASE_URL is a different Postgres instance from
        DATABASE_URL (real Supabase) — see infrastructure/freeradius/
        schema/0001_radius_schema.sql. Catching an accidental copy/paste
        that points both at the same database here, at startup, is much
        safer than the two schemas silently colliding at request time."""
        if self.radius_database_url is not None and str(self.radius_database_url) == str(
            self.database_url
        ):
            raise ValueError(
                "RADIUS_DATABASE_URL must not be the same database as DATABASE_URL — "
                "the RADIUS schema (radcheck/radacct/...) and the primary app schema "
                "must never share a database."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
