"""Public (unauthenticated) captive-portal response shapes. Deliberately
thin — no tenant_id, no router_id, nothing beyond what an anonymous
hotspot client needs to render a login/payment page. The client only ever
carries `router` (a signed token), `mac`, and `dst` — see
app/core/router_token.py and app/api/v1/public.py."""

from datetime import datetime
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


class CaptivePortalSessionRequest(BaseModel):
    """Starts a payment session from an already-signed router token."""

    router: str
    # Correlation/troubleshooting only. NEVER authentication: a MAC is
    # trivially spoofable and is frequently absent (randomized MACs, or a
    # redirect that did not carry one).
    mac_address: str | None = None


class CaptivePortalSessionResult(BaseModel):
    """The short-lived credential authorizing ONE payment attempt.

    Carries no tenant id, no router id and no nonce — everything that
    matters is read server-side from the captive_sessions row the token
    resolves to.
    """

    intent_token: str
    expires_at: datetime


class CaptivePortalPaymentInitiateRequest(BaseModel):
    """Everything a browser may say about a payment.

    Note what is ABSENT and cannot be added by a client: tenant_id, amount,
    price, currency, commission, payment_provider. Those are not optional
    fields that default server-side — they are not fields at all, so a
    tampered request cannot carry them. A TZS 10,000 package is therefore
    not payable as TZS 1 by any request shape this model accepts.
    """

    intent_token: str
    package_id: UUID
    phone: str


PaymentInitiateStatus = Literal[
    "pending",  # STK requested, awaiting the customer
    "duplicate",  # an identical attempt was already live — reusing it
    "provider_not_configured",
    "unavailable",  # production gate closed
    "rate_limited",
]


class CaptivePortalPaymentInitiateResult(BaseModel):
    transaction_token: str | None = None
    status: PaymentInitiateStatus
    amount: Money | None = None
    currency: str | None = None
    # Customer-safe copy. Never an operator diagnostic, never a provider
    # error, never anything that helps someone tune around a control.
    message: str | None = None


PaymentStatus = Literal["pending", "completed", "failed", "not_found"]
# The customer-facing fulfillment state, kept separate from payment status
# for the same reason the database columns are: "paid" and "online" are
# different facts, and conflating them is how a paying customer gets told
# their payment failed.
ActivationPublicStatus = Literal["pending", "activating", "active", "failed"]


class CaptivePortalPaymentStatusResult(BaseModel):
    status: PaymentStatus
    # True only while the payment is genuinely still being verified
    # (REQUIRES_REVIEW / AMBIGUOUS). The portal uses this to tell the
    # customer NOT to pay again — the one message that prevents a double
    # charge on a payment that may yet settle.
    under_review: bool = False
    activation_status: ActivationPublicStatus | None = None
    package_name: str | None = None
    amount: Money | None = None
    currency: str | None = None
    # 2557*****101 — never the raw msisdn.
    payer_phone_masked: str | None = None
    # The payment channel's own receipt id, which the customer also sees on
    # their mobile-money SMS. Available on COMPLETED payments only.
    provider_reference: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    activated_at: datetime | None = None
    # Plain-language copy for the portal to render directly.
    message: str | None = None
    # Present only once activation_status == "active" — this customer's own
    # RADIUS credentials, needed to submit the router's hotspot login form.
    # Withheld while access does not yet exist, so the portal can never
    # hand over credentials FreeRADIUS would reject.
    login_username: str | None = None
    login_password: str | None = None
