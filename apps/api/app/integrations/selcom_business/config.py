"""Selcom Business API configuration interface.

Real values come only from Railway environment variables
(SELCOM_BUSINESS_BASE_URL / SELCOM_BUSINESS_API_KEY /
SELCOM_BUSINESS_PRIVATE_KEY_B64 / SELCOM_BUSINESS_ACCOUNT_NUMBER — see
app/core/config.py) — never hardcoded, never shipped to the frontend.
"""

import base64
from dataclasses import dataclass

from app.core.config import get_settings
from app.integrations.selcom_business.errors import SelcomBusinessNotConfiguredError


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

    def require_configured(self) -> None:
        if not self.is_configured:
            raise SelcomBusinessNotConfiguredError(
                "Selcom Business API is not configured. Set SELCOM_BUSINESS_BASE_URL, "
                "SELCOM_BUSINESS_API_KEY, and SELCOM_BUSINESS_PRIVATE_KEY_B64 on Railway."
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
