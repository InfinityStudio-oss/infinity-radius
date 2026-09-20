"""Network Agent settings.

This process is deployed on the Network VPS, not Railway. It is reachable
only over HTTPS (TLS terminated by Caddy — see infrastructure/caddy) from
the FastAPI backend, never directly by arbitrary clients, and reaches
MikroTik routers only over the WireGuard tunnel (private, non-routable
addresses) — never over the public internet.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class NetworkAgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "staging", "production"] = "development"
    host: str = "0.0.0.0"
    port: int = 8100

    # --- Request signing (see app.core.security) ---
    # The FastAPI backend signs every request with HMAC-SHA256 over
    # method+path+timestamp+nonce+body, keyed by one of these two secrets.
    # `previous` stays valid for a rotation grace period after the backend
    # switches to a newly-generated `current` key — remove it once every
    # caller has picked up the new key.
    agent_api_key_current: str
    agent_api_key_previous: str | None = None

    # Signed requests older/newer than this (clock skew) are rejected.
    request_max_skew_seconds: int = 300
    # Nonces are remembered for at least this long to reject replays — must
    # be >= 2x request_max_skew_seconds to cover both directions of skew.
    nonce_cache_ttl_seconds: int = 600

    # --- Source IP allowlist (Railway static outbound IPs) ---
    # Comma-separated IPs/CIDRs. Empty means "allow any source" — every
    # request must still pass HMAC verification, but this is meaningfully
    # weaker defense-in-depth, so an empty list is only tolerated outside
    # production (see app.core.ip_allowlist).
    allowed_source_ips: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # --- Router registry (UUID -> real connection details) ---
    # The FastAPI backend only ever sends a router UUID; this agent alone
    # resolves it to a host/credentials — see app.core.router_registry.
    # Never a caller-supplied IP. Real file is git-ignored; see
    # routers.yaml.example.
    router_registry_path: Path = Path("routers.yaml")

    # --- MikroTik RouterOS API connection defaults ---
    # RouterOS API-SSL (port 8729) with certificate verification is the
    # default; verify=False (mikrotik_ssl_verify=false) is refused outside
    # development — see app.services.mikrotik_client.
    mikrotik_use_ssl: bool = True
    mikrotik_ssl_verify: bool = True
    mikrotik_connect_timeout_seconds: int = 5

    # Name of the local WireGuard interface used to reach router private IPs.
    wireguard_interface: str = "wg0"

    # Name of the local Postgres systemd service backing the RADIUS
    # database on this VPS — checked the same lightweight, credential-free
    # way as freeradius itself (systemctl is-active), so /health never
    # needs a second set of DB credentials on top of FreeRADIUS's own.
    radius_db_service_name: str = "postgresql"
    # Connection string for the LOCAL FreeRADIUS PostgreSQL on this VPS.
    # Always a localhost/unix-socket DSN — this value is what makes it
    # unnecessary to expose the database to the internet, so pointing it
    # at a public host would defeat its entire purpose.
    radius_database_dsn: str | None = None

    @field_validator("allowed_source_ips", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [ip.strip() for ip in value.split(",") if ip.strip()]
        return value

    @model_validator(mode="after")
    def _forbid_insecure_mikrotik_tls_in_production(self) -> "NetworkAgentSettings":
        if self.environment == "production" and not self.mikrotik_ssl_verify:
            raise ValueError(
                "mikrotik_ssl_verify=false is refused in production — "
                "a MikroTik RouterOS API-SSL connection must always verify "
                "the router's certificate outside development."
            )
        return self

    @property
    def active_signing_keys(self) -> tuple[str, ...]:
        keys = [self.agent_api_key_current]
        if self.agent_api_key_previous:
            keys.append(self.agent_api_key_previous)
        return tuple(keys)


@lru_cache
def get_network_agent_settings() -> NetworkAgentSettings:
    return NetworkAgentSettings()
