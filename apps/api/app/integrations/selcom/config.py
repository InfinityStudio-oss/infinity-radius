"""Selcom configuration interface.

DELIBERATELY MINIMAL: Selcom's Collection API (customer payments) and
Disbursement API (payouts) have real, documented authentication headers,
request signing, and callback schemas that Anthropic has not verified here.
Do not guess them. This module only defines the shape of the configuration
Infinity Radius will need — fill in real values once Selcom's official
integration guide and merchant credentials are available.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SelcomConfig:
    api_base_url: str | None
    api_key: str | None
    api_secret: str | None
    merchant_id: str | None

    @property
    def is_configured(self) -> bool:
        return all([self.api_base_url, self.api_key, self.api_secret, self.merchant_id])
