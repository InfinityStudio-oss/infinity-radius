"""Selcom Business API configuration interface.

Real values come only from Railway environment variables
(SELCOM_BUSINESS_BASE_URL / SELCOM_BUSINESS_API_KEY /
SELCOM_BUSINESS_PRIVATE_KEY_B64 / SELCOM_BUSINESS_ACCOUNT_NUMBER — see
app/core/config.py) — never hardcoded, never shipped to the frontend.
"""

import base64
from dataclasses import dataclass
from urllib.parse import urlparse

from app.core.config import get_settings
from app.integrations.selcom_business.errors import (
    SelcomBusinessMisconfiguredError,
    SelcomBusinessNotConfiguredError,
)

# developer.selcom.business's own documented hostnames — sandbox always
# under this subdomain, production always under this one. Used only to
# catch a mismatched pairing (sandbox env + production URL, or the
# reverse), never to guess a URL that isn't explicitly configured.
_SANDBOX_HOST_MARKER = "sandbox"
_PRODUCTION_HOST = "api.selcom.business"


@dataclass(frozen=True)
class SelcomBusinessConfig:
    environment: str  # "sandbox" | "production"
    base_url: str | None
    api_key: str | None
    # Decoded PEM text (never the raw base64), or None if unset.
    private_key_pem: str | None
    account_number: str | None

    @property
    def is_configured(self) -> bool:
        return all([self.base_url, self.api_key, self.private_key_pem])

    @property
    def base_url_matches_environment(self) -> bool:
        """True if base_url is unset (nothing to mismatch yet) or if its
        host is consistent with `environment`. Sandbox hosts always
        contain "sandbox" (e.g. sandbox.selcom.business); the one
        documented production host never does."""
        if not self.base_url:
            return True
        host = (urlparse(self.base_url).hostname or "").lower()
        if self.environment == "sandbox":
            return _SANDBOX_HOST_MARKER in host
        return host == _PRODUCTION_HOST

    def require_configured(self) -> None:
        if not self.is_configured:
            raise SelcomBusinessNotConfiguredError(
                "Selcom Business API is not configured. Set SELCOM_BUSINESS_BASE_URL, "
                "SELCOM_BUSINESS_API_KEY, and SELCOM_BUSINESS_PRIVATE_KEY_B64 on Railway."
            )
        if not self.base_url_matches_environment:
            raise SelcomBusinessMisconfiguredError(
                f"SELCOM_BUSINESS_BASE_URL does not match "
                f"SELCOM_BUSINESS_ENVIRONMENT={self.environment!r} — refusing to send "
                "any request until this is corrected. This platform never sends "
                "sandbox credentials to a production URL or vice versa."
            )


def _decode_private_key(raw_b64: str | None) -> str | None:
    if not raw_b64:
        return None
    try:
        return base64.b64decode(raw_b64).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise SelcomBusinessNotConfiguredError(
            "SELCOM_BUSINESS_PRIVATE_KEY_B64 is not valid base64-encoded PEM text"
        ) from exc


def selcom_business_config_from_settings() -> SelcomBusinessConfig:
    settings = get_settings()
    return SelcomBusinessConfig(
        environment=settings.selcom_business_environment,
        base_url=settings.selcom_business_base_url,
        api_key=settings.selcom_business_api_key,
        private_key_pem=_decode_private_key(settings.selcom_business_private_key_b64),
        account_number=settings.selcom_business_account_number,
    )


def validate_selcom_startup_config() -> None:
    """Called once at process import (see app/main.py) — fails loud and
    immediately if SELCOM_BUSINESS_BASE_URL is set but doesn't match
    SELCOM_BUSINESS_ENVIRONMENT, rather than waiting for the first real
    withdrawal to discover it. Deliberately does NOT require
    selcom_production_payouts_enabled to be true even when environment is
    "production" — an operator configuring production credentials with
    payouts still deliberately OFF is the expected, safe state during
    setup (see docs/architecture.md's production activation runbook).
    Never logs/raises with the base_url or any credential value."""
    config = selcom_business_config_from_settings()
    if config.base_url and not config.base_url_matches_environment:
        raise SelcomBusinessMisconfiguredError(
            f"SELCOM_BUSINESS_BASE_URL does not match "
            f"SELCOM_BUSINESS_ENVIRONMENT={config.environment!r} at startup — refusing "
            "to boot with a sandbox/production credential mismatch. Fix the Railway "
            "variables and redeploy."
        )
