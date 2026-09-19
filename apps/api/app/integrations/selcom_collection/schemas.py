"""Response/payload shapes for Selcom Mobile Checkout —
https://developers.selcommobile.com/#checkout-api.

Selcom's own docs note (and this codebase has independently observed the
same on the Business API) that `data` shapes vary — sometimes a
single-item array, sometimes empty, never assumed to be one shape without
validation. Every model here parses defensively: an unexpected/missing
field becomes None, never a hard failure that could mask a real payment
signal, and — critically — never assumed to mean success.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


def money_from_provider(value: Decimal | float | int | str | None) -> Decimal | None:
    """Converts a provider-returned numeric into a Decimal at this
    integration boundary — the only place a float is allowed to touch a
    monetary value, and only long enough to re-quantize via str() rather
    than Decimal(float) (which would capture float binary imprecision)."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid monetary value from Selcom: {value!r}") from exc


def _normalize_data_list(value: Any) -> list[dict[str, Any]]:
    """Selcom's own documented examples show `data` as a single-item
    array on success and an empty array `[]` when there's nothing to
    report — but never assume that shape holds; a bare object or None
    must parse just as safely."""
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


class CreateOrderData(BaseModel):
    gateway_buyer_uuid: str | None = None
    payment_token: str | None = None
    qr: str | None = None
    # Base64-encoded per Selcom's docs ("All urls in the request and
    # response are base64 encoded") — decoded only where actually
    # displayed to an operator/tenant, never assumed to be plaintext.
    payment_gateway_url: str | None = None


class CreateOrderMinimalResponse(BaseModel):
    reference: str | None = None
    resultcode: str | None = None
    result: str | None = None
    message: str | None = None
    data: list[CreateOrderData] = Field(default_factory=list)

    _normalize_data = field_validator("data", mode="before")(_normalize_data_list)

    @property
    def first(self) -> CreateOrderData | None:
        return self.data[0] if self.data else None


class WalletPaymentResponse(BaseModel):
    reference: str | None = None
    resultcode: str | None = None
    result: str | None = None
    message: str | None = None
    data: list[dict[str, Any]] = Field(default_factory=list)

    _normalize_data = field_validator("data", mode="before")(_normalize_data_list)


class OrderStatusData(BaseModel):
    order_id: str | None = None
    creation_date: str | None = None
    amount: Decimal | None = None
    payment_status: str | None = None
    # "Available on COMPLETED payments only" per Selcom's docs.
    transid: str | None = None
    channel: str | None = None
    reference: str | None = None
    # Documentation conflict (see docs/architecture.md): the worked JSON
    # example calls this field "phone", but the field-description table
    # directly below it calls the same concept "msisdn" — both keys are
    # accepted defensively via the validator below; neither is invented.
    phone: str | None = None
    # NOT part of Selcom's documented order-status response (its documented
    # data fields are order_id/creation_date/amount/payment_status/transid/
    # channel/reference/msisdn — re-confirmed 2026-09-19). Parsed only so
    # that IF a response ever does carry it, app/services/collections.py can
    # verify it against the transaction's own currency before crediting,
    # rather than ignoring a mismatch. Inert while Selcom omits it.
    currency: str | None = None

    _normalize_amount = field_validator("amount", mode="before")(
        lambda v: money_from_provider(v) if v is not None else None
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_msisdn_alias(cls, data: object) -> object:
        if isinstance(data, dict) and not data.get("phone") and data.get("msisdn"):
            data = {**data, "phone": data["msisdn"]}
        return data


class OrderStatusResponse(BaseModel):
    reference: str | None = None
    resultcode: str | None = None
    result: str | None = None
    message: str | None = None
    data: list[OrderStatusData] = Field(default_factory=list)

    _normalize_data = field_validator("data", mode="before")(_normalize_data_list)

    @property
    def first(self) -> OrderStatusData | None:
        return self.data[0] if self.data else None


class WebhookPayload(BaseModel):
    """The inbound webhook body — https://developers.selcommobile.com/#webhook-callback.
    Only transid/order_id/reference/result/resultcode/payment_status are
    ever part of Signed-Fields per the docs; channel/amount/phone appear
    in the sample payload but are NOT signed, so they are parsed here for
    logging/context only and must never be trusted for amount validation
    or crediting a wallet — see app/services/collections.py, which always
    re-queries order-status (a request WE sign) before crediting."""

    transid: str | None = None
    order_id: str | None = None
    reference: str | None = None
    result: str | None = None
    resultcode: str | None = None
    payment_status: str | None = None
    # Unsigned — context only, never trusted for financial decisions.
    channel: str | None = None
    amount: Decimal | None = None
    phone: str | None = None

    _normalize_amount = field_validator("amount", mode="before")(
        lambda v: money_from_provider(v) if v is not None else None
    )
