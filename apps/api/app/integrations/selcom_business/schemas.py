"""Selcom Business API request/response shapes — field names exactly as
documented at developer.selcom.business. Provider JSON numbers are always
converted to Decimal at this boundary — see money_from_provider — never
left as float past this module.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.integrations.selcom_business.errors import SelcomResultCode, SelcomResultOutcome


def _empty_list_to_none(value: Any) -> Any:
    """Selcom's sandbox returns `"data": []` (an empty array, not `null` or
    `{}`) when a lookup/query has nothing to report — observed directly
    against the real sandbox, not assumed. Every Response.data field below
    treats that the same as "no data", never a schema validation failure."""
    if isinstance(value, list) and not value:
        return None
    return value

# --- Account Lookup (GET /v1/account/lookup) -------------------------------


class AccountLookupRequest(BaseModel):
    bank: str  # DestinationCode value
    account: str
    trans_id: str
    amount: Decimal | None = None


class AccountLookupData(BaseModel):
    bank: str | None = None
    account: str | None = None
    account_name: str | None = Field(default=None, alias="accountName")
    operator: str | None = None
    charges: list[Any] = Field(default_factory=list)
    total_charges: Decimal | None = Field(default=None, alias="totalCharges")
    category_code: str | None = Field(default=None, alias="categoryCode")

    model_config = {"populate_by_name": True}


class AccountLookupResponse(BaseModel):
    success: bool
    result: str | None = None
    resultcode: str | None = None
    trans_id: str | None = Field(default=None, alias="transId")
    message: str | None = None
    data: AccountLookupData | None = None

    model_config = {"populate_by_name": True}

    _normalize_data = field_validator("data", mode="before")(_empty_list_to_none)


# --- Transaction Process (POST /v1/transaction/process) --------------------


class TransactionProcessRequest(BaseModel):
    trans_id: str = Field(alias="transId")
    recipient_fi_code: str = Field(alias="recipientFiCode")
    recipient_account: str = Field(alias="recipientAccount")
    recipient_name: str = Field(alias="recipientName")
    amount: Decimal
    purpose: str = "FT"
    remarks: str | None = None

    model_config = {"populate_by_name": True}


class TransactionProcessData(BaseModel):
    trans_id: str | None = Field(default=None, alias="trans_id")
    selcom_receipt: str | None = None
    status: str | None = None  # "ACCEPTED" | "COMPLETED"
    amount: Decimal | None = None
    currency: str | None = None

    model_config = {"populate_by_name": True}


class TransactionProcessResponse(BaseModel):
    success: bool
    result: str | None = None
    resultcode: str | None = None
    message: str | None = None
    data: TransactionProcessData | None = None

    model_config = {"populate_by_name": True}

    _normalize_data = field_validator("data", mode="before")(_empty_list_to_none)


# --- Transaction Query (GET /v1/transaction/query) --------------------------


class TransactionQueryData(BaseModel):
    trans_id: str | None = Field(default=None, alias="transId")
    status: str | None = None  # "ACCEPTED" | "COMPLETED" | "FAILED"
    amount: Decimal | None = None
    currency: str | None = None
    selcom_receipt: str | None = Field(default=None, alias="selcomReceipt")
    trans_datetime: str | None = Field(default=None, alias="transDatetime")
    sender_account: str | None = Field(default=None, alias="senderAccount")
    sender_name: str | None = Field(default=None, alias="senderName")

    model_config = {"populate_by_name": True}


class TransactionQueryResponse(BaseModel):
    success: bool
    result: str | None = None
    resultcode: str | None = None
    message: str | None = None
    data: TransactionQueryData | None = None

    model_config = {"populate_by_name": True}

    _normalize_data = field_validator("data", mode="before")(_empty_list_to_none)


# --- Balance (POST /v1/balance) --------------------------------------------


class BalanceData(BaseModel):
    account_number: str | None = None
    currency: str | None = None
    available_balance: Decimal | None = None
    active: bool | None = None


class BalanceResponse(BaseModel):
    success: bool
    result: str | None = None
    resultcode: str | None = None
    message: str | None = None
    data: BalanceData | None = None

    _normalize_data = field_validator("data", mode="before")(_empty_list_to_none)


# --- Disbursement callback (POST our /webhooks/selcom-business/disbursement)


class DisbursementCallbackPayload(BaseModel):
    """Always-present fields per the public docs are reference_id +
    status; everything else is only sent if selected in the Selcom portal
    callback configuration — see docs section on manual portal setup."""

    reference_id: str
    status: str  # documented as always "SUCCESS" when Selcom sends this at all
    sender_account_name: str | None = None
    sender_account_number: str | None = None
    recipient_name: str | None = None
    recipient_account_number: str | None = None
    amount: Decimal | None = None
    charges: Decimal | None = None
    selcom_receipt: str | None = None


# --- Result-code interpretation --------------------------------------------

_SUCCESS_CODES = frozenset({"000"})
_INPROGRESS_CODES = frozenset({"111", "927"})
_AMBIGUOUS_CODES = frozenset({"999"})


def interpret_resultcode(*, resultcode: str | None, message: str | None) -> SelcomResultCode:
    """Never treats a missing/unrecognized code as SUCCESS — an unmapped
    code always falls through to FAIL, the conservative choice: money
    should never be treated as delivered just because we didn't recognize
    the response as a failure."""
    code = (resultcode or "").strip()
    if code in _SUCCESS_CODES:
        outcome = SelcomResultOutcome.SUCCESS
    elif code in _INPROGRESS_CODES:
        outcome = SelcomResultOutcome.INPROGRESS
    elif code in _AMBIGUOUS_CODES:
        outcome = SelcomResultOutcome.AMBIGUOUS
    else:
        outcome = SelcomResultOutcome.FAIL
    return SelcomResultCode(outcome=outcome, resultcode=code, message=message)


def money_from_provider(value: Decimal | float | int | str | None) -> Decimal | None:
    """Converts a provider-returned numeric (Selcom's JSON uses plain
    floats for amounts/charges) into a Decimal at this integration
    boundary — the only place a float is ever allowed to touch a monetary
    value in this codebase, and only long enough to re-quantize it safely
    via str() rather than Decimal(float) (which would capture the float's
    binary imprecision)."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid monetary value from Selcom: {value!r}") from exc
