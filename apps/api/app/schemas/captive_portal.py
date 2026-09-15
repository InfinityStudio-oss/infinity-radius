"""Public (unauthenticated) captive-portal response shapes. Deliberately
thin — no tenant_id, no router_id, nothing beyond what an anonymous
hotspot client needs to render a login/payment page. The client only ever
carries `router` (a signed token), `mac`, and `dst` — see
app/core/router_token.py and app/api/v1/public.py."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.core.money import Money

ResolveStatus = Literal["ok", "invalid_token", "router_not_found"]


class CaptivePortalResolveResult(BaseModel):
    status: ResolveStatus
    router_name: str | None = None
    site_name: str | None = None
    mac: str | None = None
    dst: str | None = None
    # The router's own local login endpoint ($(link-login-only)) — not
    # sensitive (it's on the same LAN the client is already connected to),
    # and required for the browser to submit the final hotspot login form
    # cross-origin once payment completes. Present only when the router
    # actually passed it (real MikroTik redirects do; local/dev testing
    # without a router won't).
    login_url: str | None = None


class CaptivePortalBrandingRead(BaseModel):
    """Tenant-supplied branding only — no fabricated logo/color. Absent
    fields mean the portal falls back to Infinity Radius's own branding."""

    tenant_name: str
    logo_url: str | None
    brand_color: str | None


class CaptivePortalPackageRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    price_tzs: Money
    duration_minutes: int | None
    download_speed_kbps: int | None
    upload_speed_kbps: int | None
    device_limit: int


class CaptivePortalPaymentInitiateRequest(BaseModel):
    router: str
    package_id: UUID
    phone: str
    # Correlates the payment with the originating hotspot session for
    # audit/troubleshooting only — never used to derive the charged
    # amount, which always comes from the server-resolved package.
    mac_address: str | None = None


PaymentInitiateStatus = Literal["pending", "provider_not_configured"]


class CaptivePortalPaymentInitiateResult(BaseModel):
    transaction_token: str
    status: PaymentInitiateStatus
    amount: Money
    currency: str


PaymentStatus = Literal["pending", "completed", "failed", "not_found"]


class CaptivePortalPaymentStatusResult(BaseModel):
    status: PaymentStatus
    # Present only once status == "completed" — this customer's own RADIUS
    # credentials, needed to submit the router's hotspot login form. Never
    # a database id; never shown for anyone else's transaction (the token
    # itself is what proves this request is about this transaction).
    login_username: str | None = None
    login_password: str | None = None
