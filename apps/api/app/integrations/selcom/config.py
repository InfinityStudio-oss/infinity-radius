"""Selcom configuration interface.

DELIBERATELY MINIMAL: Selcom's Collection API (customer payments) and
Disbursement API (payouts) have real, documented authentication headers,
request signing, and callback schemas that Anthropic has not verified here.
Do not guess them. This module only defines the shape of the configuration
Infinity Radius will need — fill in real values once Selcom's official
integration guide and merchant credentials are available.
"""

from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True)
class SelcomConfig:
    api_base_url: str | None
    api_key: str | None
    api_secret: str | None
    merchant_id: str | None

    @property
    def is_configured(self) -> bool:
        return all([self.api_base_url, self.api_key, self.api_secret, self.merchant_id])


def selcom_config_from_settings() -> SelcomConfig:
    """Builds the legacy Selcom config from environment settings.

    Used only by the Disbursement callback routes, whose signing scheme
    is still a documented TODO. The Mobile Checkout Collection flow has
    its own, fully-implemented config — see
    app/integrations/selcom_collection/config.py — and never uses this.
    """
    settings = get_settings()
    return SelcomConfig(
        api_base_url=settings.selcom_api_base_url,
        api_key=settings.selcom_api_key,
        api_secret=settings.selcom_api_secret,
        merchant_id=settings.selcom_merchant_id,
    )
