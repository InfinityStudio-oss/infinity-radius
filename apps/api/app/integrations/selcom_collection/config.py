"""Selcom Mobile Checkout Collection configuration interface.

Real values come only from Railway environment variables
(SELCOM_COLLECTION_BASE_URL / SELCOM_COLLECTION_API_KEY /
SELCOM_COLLECTION_API_SECRET / SELCOM_COLLECTION_PRIVATE_KEY_B64 /
SELCOM_COLLECTION_DIGEST_METHOD / SELCOM_COLLECTION_VENDOR — see
app/core/config.py) — never hardcoded, never shipped to the frontend, and
never any of the SELCOM_BUSINESS_* Disbursement variables.

Deliberately NO startup-crash validation (unlike Disbursement's
validate_selcom_startup_config — see app/main.py): a real incident
(2026-09-19, docs/architecture.md) showed a malformed Disbursement
credential crashing the entire web service at import time. Collection
credential validation instead happens lazily, the first time
require_configured() is actually called (create-order/wallet-payment
time) — a bad Collection credential can never take down the whole
platform, only Collection requests, and only once SELCOM_COLLECTION_ENABLED
is even turned on.
"""

import base64
from dataclasses import dataclass

from app.core.config import get_settings
from app.integrations.selcom_collection.errors import SelcomCollectionNotConfiguredError

SUPPORTED_DIGEST_METHODS = frozenset({"HS256", "RS256"})


@dataclass(frozen=True)
class SelcomCollectionConfig:
    base_url: str | None
    api_key: str | None
    api_secret: str | None  # HS256 only
    private_key_pem: str | None  # RS256 only — decoded PEM text, never the raw base64
    digest_method: str | None  # "HS256" | "RS256"
    vendor: str | None
    enabled: bool  # SELCOM_COLLECTION_ENABLED — the general feature kill switch
    production_enabled: bool  # SELCOM_COLLECTION_PRODUCTION_ENABLED — the second, live-STK gate

    @property
    def is_configured(self) -> bool:
        if not all([self.base_url, self.api_key, self.vendor, self.digest_method]):
            return False
        if self.digest_method not in SUPPORTED_DIGEST_METHODS:
            return False
        if self.digest_method == "HS256":
            return bool(self.api_secret)
        return bool(self.private_key_pem)  # RS256

    def require_configured(self) -> None:
        if self.digest_method is not None and self.digest_method not in SUPPORTED_DIGEST_METHODS:
            raise SelcomCollectionNotConfiguredError(
                f"SELCOM_COLLECTION_DIGEST_METHOD={self.digest_method!r} is not supported — "
                "must be HS256 or RS256."
            )
        if not self.is_configured:
            raise SelcomCollectionNotConfiguredError(
                "Selcom Collection is not configured. Set SELCOM_COLLECTION_BASE_URL, "
                "SELCOM_COLLECTION_API_KEY, SELCOM_COLLECTION_VENDOR, "
                "SELCOM_COLLECTION_DIGEST_METHOD, and exactly one of "
                "SELCOM_COLLECTION_API_SECRET (HS256) / "
                "SELCOM_COLLECTION_PRIVATE_KEY_B64 (RS256) on Railway."
            )


def _decode_private_key(raw_b64: str | None) -> str | None:
    if not raw_b64:
        return None
    try:
        return base64.b64decode(raw_b64).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise SelcomCollectionNotConfiguredError(
            "SELCOM_COLLECTION_PRIVATE_KEY_B64 is not valid base64-encoded PEM text"
        ) from exc


def selcom_collection_config_from_settings() -> SelcomCollectionConfig:
    settings = get_settings()
    return SelcomCollectionConfig(
        base_url=settings.selcom_collection_base_url,
        api_key=settings.selcom_collection_api_key,
        api_secret=settings.selcom_collection_api_secret,
        private_key_pem=_decode_private_key(settings.selcom_collection_private_key_b64),
        digest_method=settings.selcom_collection_digest_method,
        vendor=settings.selcom_collection_vendor,
        enabled=settings.selcom_collection_enabled,
        production_enabled=settings.selcom_collection_production_enabled,
    )
