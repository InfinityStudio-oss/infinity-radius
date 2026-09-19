"""Errors for app/integrations/selcom_collection/ — deliberately its own
hierarchy, never shared with app/integrations/selcom_business/errors.py:
these are two different Selcom products (Mobile Checkout Collection vs
Business Disbursement) with different failure modes worth distinguishing
in logs/handlers."""


class SelcomCollectionError(Exception):
    """Base class for every Collection-integration failure."""


class SelcomCollectionNotConfiguredError(SelcomCollectionError):
    """SELCOM_COLLECTION_* settings are missing/incomplete."""


class SelcomCollectionTransportError(SelcomCollectionError):
    """The HTTP request itself failed (timeout, connection error, DNS) —
    never distinguishable from "maybe it actually went through", so
    callers must never treat this as a definitive failure to retry."""


class SelcomCollectionAPIError(SelcomCollectionError):
    """Selcom responded, but with a non-2xx status or a body that doesn't
    parse as the expected schema."""

    def __init__(
        self, message: str, *, status_code: int | None = None, raw_response: object = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response


class SelcomCollectionWebhookVerificationError(SelcomCollectionError):
    """An inbound webhook's Authorization/Digest/Signed-Fields didn't
    verify against SELCOM_COLLECTION_API_KEY/secret — never processed as
    a genuine payment signal."""
