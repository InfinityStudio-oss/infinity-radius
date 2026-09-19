"""Selcom Mobile Checkout HTTP client —
https://developers.selcommobile.com/#checkout-api.

URL composition strips a trailing "/v1" from the configured base URL (if
present) before joining with a path that always starts with "/v1/" —
same defensive convention as app/integrations/selcom_business/client.py,
so SELCOM_COLLECTION_BASE_URL can be pasted with or without a trailing
"/v1" without ever doubling it up (see build_url + its tests).
"""

from collections import OrderedDict
from decimal import Decimal
from typing import Any

import httpx2 as httpx
import structlog

from app.integrations.selcom_collection.config import SelcomCollectionConfig
from app.integrations.selcom_collection.constants import (
    CREATE_ORDER_MINIMAL_PATH,
    ORDER_STATUS_PATH,
    WALLET_PAYMENT_PATH,
)
from app.integrations.selcom_collection.errors import (
    SelcomCollectionAPIError,
    SelcomCollectionTransportError,
)
from app.integrations.selcom_collection.schemas import (
    CreateOrderMinimalResponse,
    OrderStatusResponse,
    WalletPaymentResponse,
)
from app.integrations.selcom_collection.signing import sign_request

logger = structlog.get_logger("integrations.selcom_collection.client")


def build_url(base_url: str, path: str) -> str:
    if not path.startswith("/v1/"):
        raise ValueError(f"Selcom Collection endpoint paths must start with '/v1/', got: {path!r}")
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[: -len("/v1")]
    return f"{normalized}{path}"


def whole_tzs_amount(amount: Decimal) -> str:
    """Selcom's Checkout docs show `amount` as a bare integer (e.g.
    `"amount": 8000`), never a decimal string — unlike this platform's
    internal Numeric(14,2) amounts. Fails closed on a fractional TZS
    amount rather than silently rounding money; TZS has no conventional
    subunit in everyday use."""
    if amount != amount.to_integral_value():
        raise ValueError(f"Selcom Collection amount must be a whole number of TZS, got {amount}")
    return str(int(amount))


class SelcomCollectionClient:
    def __init__(self, config: SelcomCollectionConfig) -> None:
        config.require_configured()
        self._config = config

    def _headers(self, *, fields: "OrderedDict[str, str]") -> dict[str, str]:
        assert self._config.api_key is not None
        assert self._config.digest_method is not None
        signed = sign_request(
            api_key=self._config.api_key,
            digest_method=self._config.digest_method,
            api_secret=self._config.api_secret,
            private_key_pem=self._config.private_key_pem,
            fields=fields,
        )
        headers = signed.as_dict()
        headers["Accept"] = "application/json"
        headers["Content-Type"] = "application/json"
        return headers

    async def _post(self, path: str, *, fields: "OrderedDict[str, str]") -> dict[str, Any]:
        assert self._config.base_url is not None
        url = build_url(self._config.base_url, path)
        headers = self._headers(fields=fields)
        # Every field is sent as a JSON string, including amount/no_of_items
        # (Selcom's own examples show these as bare JSON numbers) — this
        # keeps the request body byte-for-byte consistent with the values
        # actually signed (the signing string always stringifies), which
        # matters far more than the JSON type: a signature mismatch fails
        # 100% of requests, while a string-typed numeric field is commonly
        # tolerated by payment-gateway JSON parsers. Worth re-checking
        # against a real response during the first live connectivity test
        # (see docs/architecture.md) — never assumed without one.
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=dict(fields), headers=headers)
        except httpx.HTTPError as exc:
            raise SelcomCollectionTransportError(
                f"Selcom Collection request failed: {exc}"
            ) from exc
        return self._parse(response)

    async def _get(self, path: str, *, fields: "OrderedDict[str, str]") -> dict[str, Any]:
        assert self._config.base_url is not None
        url = build_url(self._config.base_url, path)
        headers = self._headers(fields=fields)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=dict(fields), headers=headers)
        except httpx.HTTPError as exc:
            raise SelcomCollectionTransportError(
                f"Selcom Collection request failed: {exc}"
            ) from exc
        return self._parse(response)

    def _parse(self, response: httpx.Response) -> dict[str, Any]:
        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            raise SelcomCollectionAPIError(
                "Selcom Collection returned a non-JSON response",
                status_code=response.status_code,
                raw_response=response.text,
            ) from exc
        if response.status_code >= 400:
            # Unlike selcom_business's client, Collection treats ANY 4xx
            # or 5xx as a real error — a real production incident
            # (2026-09-19, Disbursement side, see docs/architecture.md)
            # showed a client that only raised on 5xx silently treating a
            # 400 as "success with empty data", masking a genuine
            # provider rejection.
            raise SelcomCollectionAPIError(
                f"Selcom Collection returned {response.status_code}",
                status_code=response.status_code,
                raw_response=body,
            )
        return body

    # ------------------------------------------------------------ endpoints

    async def create_order_minimal(
        self,
        *,
        order_id: str,
        buyer_email: str,
        buyer_name: str,
        buyer_phone: str,
        amount: Decimal,
        currency: str,
        no_of_items: int,
        webhook_url_b64: str | None = None,
        buyer_remarks: str | None = None,
        merchant_remarks: str | None = None,
    ) -> CreateOrderMinimalResponse:
        assert self._config.vendor is not None
        fields: OrderedDict[str, str] = OrderedDict(
            [
                ("vendor", self._config.vendor),
                ("order_id", order_id),
                ("buyer_email", buyer_email),
                ("buyer_name", buyer_name),
                ("buyer_phone", buyer_phone),
                ("amount", whole_tzs_amount(amount)),
                ("currency", currency),
                ("no_of_items", str(no_of_items)),
            ]
        )
        if webhook_url_b64 is not None:
            fields["webhook"] = webhook_url_b64
        if buyer_remarks is not None:
            fields["buyer_remarks"] = buyer_remarks
        if merchant_remarks is not None:
            fields["merchant_remarks"] = merchant_remarks
        body = await self._post(CREATE_ORDER_MINIMAL_PATH, fields=fields)
        return CreateOrderMinimalResponse.model_validate(body)

    async def wallet_payment(
        self, *, transid: str, order_id: str, msisdn: str
    ) -> WalletPaymentResponse:
        fields: OrderedDict[str, str] = OrderedDict(
            [("transid", transid), ("order_id", order_id), ("msisdn", msisdn)]
        )
        body = await self._post(WALLET_PAYMENT_PATH, fields=fields)
        return WalletPaymentResponse.model_validate(body)

    async def order_status(self, *, order_id: str) -> OrderStatusResponse:
        fields: OrderedDict[str, str] = OrderedDict([("order_id", order_id)])
        body = await self._get(ORDER_STATUS_PATH, fields=fields)
        return OrderStatusResponse.model_validate(body)
