"""Selcom Business API HTTP client — developer.selcom.business.

URL composition is deliberately defensive: the public docs display the
production base URL AS "https://api.selcom.business/v1" while also
documenting endpoint paths like "/v1/transaction/process" — concatenated
naively that produces ".../v1/v1/transaction/process". `build_url` strips
a trailing "/v1" (with or without a trailing slash) from whatever base URL
is configured before joining it with a path that always starts with
"/v1/", so the correct final URL comes out the same way regardless of
which of the two documented spellings SELCOM_BUSINESS_BASE_URL was set to.
See tests/test_selcom_business_client.py for both cases.
"""

from collections import OrderedDict
from decimal import Decimal
from typing import Any

import httpx2 as httpx
import structlog

from app.integrations.selcom_business.config import SelcomBusinessConfig
from app.integrations.selcom_business.errors import (
    SelcomBusinessAPIError,
    SelcomBusinessTransportError,
)
from app.integrations.selcom_business.schemas import (
    AccountLookupResponse,
    BalanceResponse,
    TransactionProcessResponse,
    TransactionQueryResponse,
)
from app.integrations.selcom_business.signing import sign_request

logger = structlog.get_logger("integrations.selcom_business.client")

_ACCOUNT_LOOKUP_PATH = "/v1/account/lookup"
_TRANSACTION_PROCESS_PATH = "/v1/transaction/process"
_TRANSACTION_QUERY_PATH = "/v1/transaction/query"
_BALANCE_PATH = "/v1/balance"


def build_url(base_url: str, path: str) -> str:
    """`base_url` may or may not already end in "/v1" (both spellings are
    shown as "the base URL" across Selcom's own docs) — normalize away any
    trailing slash and a trailing "/v1" segment before joining, so the
    result is identical either way. `path` must always start with "/v1/"."""
    if not path.startswith("/v1/"):
        raise ValueError(f"Selcom Business endpoint paths must start with '/v1/', got: {path!r}")
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[: -len("/v1")]
    return f"{normalized}{path}"


def _str(value: Decimal | str | None) -> str:
    """Exact string form used for BOTH the outbound payload/query value and
    the value fed into the signing string — the two must always match."""
    return "" if value is None else str(value)


class SelcomBusinessClient:
    def __init__(self, config: SelcomBusinessConfig) -> None:
        self._config = config

    def _headers(
        self, *, fields: "OrderedDict[str, str]", content_type: str | None
    ) -> dict[str, str]:
        self._config.require_configured()
        assert self._config.api_key is not None
        assert self._config.private_key_pem is not None
        signed = sign_request(
            api_key=self._config.api_key,
            private_key_pem=self._config.private_key_pem,
            fields=fields,
        )
        return signed.as_dict(content_type=content_type)

    async def _get(self, path: str, *, fields: "OrderedDict[str, str]") -> dict[str, Any]:
        self._config.require_configured()
        assert self._config.base_url is not None
        url = build_url(self._config.base_url, path)
        headers = self._headers(fields=fields, content_type=None)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=dict(fields), headers=headers)
        except httpx.HTTPError as exc:
            raise SelcomBusinessTransportError(f"Selcom Business request failed: {exc}") from exc
        return self._parse(response)

    async def _post(self, path: str, *, fields: "OrderedDict[str, str]") -> dict[str, Any]:
        self._config.require_configured()
        assert self._config.base_url is not None
        url = build_url(self._config.base_url, path)
        headers = self._headers(fields=fields, content_type="application/json")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=dict(fields), headers=headers)
        except httpx.HTTPError as exc:
            raise SelcomBusinessTransportError(f"Selcom Business request failed: {exc}") from exc
        return self._parse(response)

    def _parse(self, response: httpx.Response) -> dict[str, Any]:
        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            raise SelcomBusinessAPIError(
                "Selcom Business returned a non-JSON response",
                status_code=response.status_code,
                raw_response=response.text,
            ) from exc
        if response.status_code >= 500:
            raise SelcomBusinessAPIError(
                f"Selcom Business returned {response.status_code}",
                status_code=response.status_code,
                raw_response=body,
            )
        return body

    # ------------------------------------------------------------ endpoints

    async def account_lookup(
        self, *, bank: str, account: str, trans_id: str, amount: Decimal | None = None
    ) -> AccountLookupResponse:
        fields: OrderedDict[str, str] = OrderedDict(
            [("bank", bank), ("account", account), ("transId", trans_id)]
        )
        if amount is not None:
            fields["amount"] = _str(amount)
        body = await self._get(_ACCOUNT_LOOKUP_PATH, fields=fields)
        return AccountLookupResponse.model_validate(body)

    async def transaction_process(
        self,
        *,
        trans_id: str,
        recipient_fi_code: str,
        recipient_account: str,
        recipient_name: str,
        amount: Decimal,
        purpose: str = "FT",
        remarks: str | None = None,
    ) -> TransactionProcessResponse:
        fields: OrderedDict[str, str] = OrderedDict(
            [
                ("transId", trans_id),
                ("recipientFiCode", recipient_fi_code),
                ("recipientAccount", recipient_account),
                ("recipientName", recipient_name),
                ("amount", _str(amount)),
                ("purpose", purpose),
            ]
        )
        if remarks is not None:
            fields["remarks"] = remarks
        body = await self._post(_TRANSACTION_PROCESS_PATH, fields=fields)
        return TransactionProcessResponse.model_validate(body)

    async def transaction_query(self, *, trans_id: str) -> TransactionQueryResponse:
        fields: OrderedDict[str, str] = OrderedDict([("transId", trans_id)])
        body = await self._get(_TRANSACTION_QUERY_PATH, fields=fields)
        return TransactionQueryResponse.model_validate(body)

    async def balance(self, *, account_number: str) -> BalanceResponse:
        fields: OrderedDict[str, str] = OrderedDict([("account_number", account_number)])
        body = await self._post(_BALANCE_PATH, fields=fields)
        return BalanceResponse.model_validate(body)
