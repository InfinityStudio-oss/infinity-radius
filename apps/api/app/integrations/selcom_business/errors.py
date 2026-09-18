"""Selcom Business API error hierarchy — every failure raised anywhere in
app.integrations.selcom_business is one of these.
"""

from dataclasses import dataclass
from enum import StrEnum


class SelcomBusinessError(Exception):
    """Base class for all Selcom Business API errors."""


class SelcomBusinessNotConfiguredError(SelcomBusinessError):
    """SELCOM_BUSINESS_BASE_URL/API_KEY/PRIVATE_KEY_B64 not set."""


class SelcomBusinessMisconfiguredError(SelcomBusinessError):
    """SELCOM_BUSINESS_BASE_URL doesn't match SELCOM_BUSINESS_ENVIRONMENT
    (e.g. a sandbox base URL with environment=production, or vice versa) —
    distinct from simply not being configured at all. Never proceeds with
    a request under this condition: sandbox credentials must never reach
    a production URL, and production credentials must never accidentally
    stay pointed at sandbox."""


class SelcomBusinessTransportError(SelcomBusinessError):
    """The HTTP request itself failed (timeout, connection error, DNS,
    TLS) — distinct from a request that reached Selcom and got an error
    response. This is the case app.services.payouts must treat as
    "unknown outcome — query before ever retrying", never as FAIL."""


class SelcomBusinessAPIError(SelcomBusinessError):
    """Selcom's API responded, but with success=false / a non-2xx status
    unrelated to the documented transaction result-code vocabulary (e.g.
    a malformed request, auth rejected). Carries whatever raw detail is
    available — never fabricated."""

    def __init__(
        self, message: str, *, status_code: int | None = None, raw_response: object = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response


class SelcomResultOutcome(StrEnum):
    """The four documented resultcode buckets from developer.selcom.business
    Transaction Process — see app.integrations.selcom_business.schemas for
    the exact code -> outcome mapping. Never invent a fifth bucket."""

    SUCCESS = "SUCCESS"  # resultcode 000
    INPROGRESS = "INPROGRESS"  # resultcode 111 or 927 — query, never retry
    AMBIGUOUS = "AMBIGUOUS"  # resultcode 999 — query until resolved, never retry
    FAIL = "FAIL"  # any other documented failure code


@dataclass(frozen=True)
class SelcomResultCode:
    """A parsed provider result — never just a raw HTTP status. See
    SelcomResultOutcome for what each `outcome` means for whether it's
    safe to release reserved funds, finalize a debit, or retry."""

    outcome: SelcomResultOutcome
    resultcode: str
    message: str | None
