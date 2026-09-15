"""Environment-validated application settings.

Pydantic Settings fails fast at process startup if a required variable is
missing or malformed, rather than surfacing as an obscure error mid-request.
"""

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
