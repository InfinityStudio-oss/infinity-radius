"""Pydantic models at the boundary between Infinity Radius's own domain
(Decimal TZS amounts, our own reference strings) and whatever Selcom's
real wire format turns out to be.

Field NAMES here are Infinity Radius's own internal vocabulary, chosen for
clarity — they are NOT Selcom's actual JSON field names, which remain
unknown until official API documentation is supplied. The real request/
response (de)serialization against Selcom's actual schema belongs in
disbursement.py once that mapping is confirmed; nothing in
this file should be treated as "the Selcom wire format."

`DisbursementCallbackPayload` deliberately carries only the raw,
unparsed webhook body — inventing field names for it (a "reference" key,
an "amount" key, a "status" key) before official documentation confirms
them is exactly the mistake this module exists to avoid.
"""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class DisbursementOrderRequest(BaseModel):
    """What Infinity Radius needs Selcom to pay out to a tenant's
    withdrawal destination.

    TODO(selcom-docs): map these to Selcom's actual Disbursement API
    request fields (vendor/merchant id, order id, recipient account
    details, amount, currency, channel, etc.) once the official
    integration guide is available — see
    app/integrations/selcom/disbursement.py. `reference` carries this
    codebase's own `Withdrawal.idempotency_key` — whether Selcom's API
    itself supports a de-dup key, and under what field name, is also
    TODO(selcom-docs)."""

    reference: str
    amount: Decimal
    currency: str
    recipient_phone: str
    recipient_name: str | None = None


class DisbursementOrderResponse(BaseModel):
    """TODO(selcom-docs): populate from Selcom's real Disbursement order-
    creation response. `provider_reference` stands in for whatever
    Selcom's own order/transaction identifier field is actually called."""

    provider_reference: str | None = None
    raw_response: dict[str, Any] = Field(default_factory=dict)


class DisbursementStatusResponse(BaseModel):
    """TODO(selcom-docs): populate from Selcom's real disbursement-status
    query response. `result_code`/`result_message` are placeholders for
    whatever Selcom's actual status vocabulary is — do not assume any
    particular code means success/failure without the official
    specification confirming it."""

    provider_reference: str | None = None
    result_code: str | None = None
    result_message: str | None = None
    raw_response: dict[str, Any] = Field(default_factory=dict)


class DisbursementCallbackPayload(BaseModel):
    """The inbound disbursement webhook's real field names are
    TODO(selcom-docs) — this only carries the parsed-JSON payload
    verbatim, mirroring CollectionCallbackPayload."""

    raw: dict[str, Any]
