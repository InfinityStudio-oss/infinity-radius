"""Resend integration error hierarchy — mirrors app/integrations/selcom's
shape so both external-provider integrations fail the same way."""


class ResendError(Exception):
    """Base class for all Resend integration errors."""


class ResendNotConfiguredError(ResendError):
    """Raised when RESEND_API_KEY/RESEND_FROM_EMAIL are not set. Onboarding
    never fails registration because of this — it records the email as
    FAILED in email_events and continues; only the send itself is skipped.
    """


class ResendSendError(ResendError):
    """Raised when Resend's API rejects or fails to deliver a send request."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
