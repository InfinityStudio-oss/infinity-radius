"""Selcom integration error hierarchy. Every Selcom-related failure raised
anywhere in this codebase is one of these — callers can catch
`SelcomError` to handle "anything Selcom-related went wrong" without
depending on which specific stage failed.
"""


class SelcomError(Exception):
    """Base class for all Selcom integration errors."""


class SelcomNotConfiguredError(SelcomError):
    """Raised when SELCOM_API_BASE_URL/API_KEY/API_SECRET/MERCHANT_ID are
    not set. Distinct from SelcomNotImplementedError: this means the
    operator hasn't supplied credentials yet, not that the code mapping
    Selcom's real API is unwritten."""


class SelcomNotImplementedError(SelcomError):
    """Raised by any Selcom operation whose real request/response/signing
    format Anthropic has not been given official documentation for — even
    with valid credentials configured. Distinct from
    SelcomNotConfiguredError: filling in credentials alone can never clear
    this one, only supplying the official integration guide can."""


class SelcomAuthenticationError(SelcomError):
    """Raised when Selcom rejects this app's credentials/auth on an
    outbound request (once a real authentication scheme exists)."""


class SelcomSignatureError(SelcomError):
    """Raised when an outbound request's signature can't be computed, or
    Selcom reports it as invalid (once a real signing scheme exists)."""


class SelcomAPIError(SelcomError):
    """Raised when Selcom's API returns an explicit error response, or
    when a webhook's claims don't match our own records (amount/reference
    mismatch). Carries whatever raw detail is available — never
    fabricated."""

    def __init__(
        self, message: str, *, status_code: int | None = None, raw_response: object = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response


class SelcomWebhookVerificationError(SelcomError):
    """Raised when an inbound Selcom webhook fails authenticity
    verification. A request that raises this is never processed as a real
    payment event — see app/integrations/selcom/collection.py."""
