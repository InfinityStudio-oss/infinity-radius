"""Return shape for every send_* call — never the raw Resend SDK response,
so callers (OnboardingService, AdminTenantService) depend on a stable
shape regardless of which SDK version is installed."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EmailSendResult:
    sent: bool
    provider_message_id: str | None
    error_message: str | None = None
