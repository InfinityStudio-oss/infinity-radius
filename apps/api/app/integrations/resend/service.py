"""Public entry point for sending Infinity Radius transactional email.
Never touches the database — callers (OnboardingService,
AdminTenantService) are responsible for writing the matching email_events
row from the EmailSendResult this returns. Every method fails soft: a
ResendNotConfiguredError or ResendSendError is caught here and turned into
an EmailSendResult(sent=False, ...), never raised past this class, so a
missing/broken email provider never blocks account creation or an admin
action that already succeeded in the database.
"""

from datetime import datetime
from uuid import UUID

import structlog

from app.core.config import get_settings
from app.integrations.resend.client import ResendClient
from app.integrations.resend.config import ResendConfig
from app.integrations.resend.exceptions import ResendError
from app.integrations.resend.schemas import EmailSendResult
from app.integrations.resend.templates import onboarding as templates

logger = structlog.get_logger("app.integrations.resend")


def _config() -> ResendConfig:
    settings = get_settings()
    return ResendConfig(
        api_key=settings.resend_api_key,
        from_email=settings.resend_from_email,
        from_name=settings.resend_from_name,
        super_admin_review_email=settings.super_admin_review_email,
        app_url=settings.app_url,
    )


class ResendEmailService:
    def __init__(self) -> None:
        self._config = _config()
        self._client = ResendClient(self._config)

    async def _send(self, *, to: str, subject: str, html: str, log_context: str) -> EmailSendResult:
        try:
            return await self._client.send(to=to, subject=subject, html=html)
        except ResendError as exc:
            logger.warning("resend.send_failed", context=log_context, error=str(exc))
            return EmailSendResult(sent=False, provider_message_id=None, error_message=str(exc))

    async def send_verification_email(
        self, *, to: str, first_name: str, verify_url: str
    ) -> EmailSendResult:
        subject, html = templates.verification_email(
            app_url=self._config.app_url, first_name=first_name, verify_url=verify_url
        )
        return await self._send(to=to, subject=subject, html=html, log_context="verification")

    async def send_admin_new_tenant_email(
        self,
        *,
        tenant_id: UUID,
        business_name: str,
        legal_name: str | None,
        business_type: str | None,
        owner_name: str,
        owner_email: str,
        owner_phone: str,
        business_email: str,
        business_phone: str,
        tin: str | None,
        business_license_number: str | None,
        region: str | None,
        district: str | None,
        ward: str | None,
        submitted_at: datetime,
    ) -> EmailSendResult:
        if not self._config.super_admin_review_email:
            return EmailSendResult(
                sent=False,
                provider_message_id=None,
                error_message="SUPER_ADMIN_REVIEW_EMAIL is not configured",
            )
        subject, html = templates.admin_new_tenant_email(
            app_url=self._config.app_url,
            tenant_id=tenant_id,
            business_name=business_name,
            legal_name=legal_name,
            business_type=business_type,
            owner_name=owner_name,
            owner_email=owner_email,
            owner_phone=owner_phone,
            business_email=business_email,
            business_phone=business_phone,
            tin=tin,
            business_license_number=business_license_number,
            region=region,
            district=district,
            ward=ward,
            submitted_at=submitted_at,
        )
        return await self._send(
            to=self._config.super_admin_review_email,
            subject=subject,
            html=html,
            log_context="admin_new_tenant",
        )

    async def send_tenant_approved_email(self, *, to: str, first_name: str) -> EmailSendResult:
        subject, html = templates.tenant_approved_email(
            app_url=self._config.app_url, first_name=first_name
        )
        return await self._send(to=to, subject=subject, html=html, log_context="tenant_approved")

    async def send_tenant_rejected_email(
        self, *, to: str, first_name: str, reason: str
    ) -> EmailSendResult:
        subject, html = templates.tenant_rejected_email(
            app_url=self._config.app_url, first_name=first_name, reason=reason
        )
        return await self._send(to=to, subject=subject, html=html, log_context="tenant_rejected")

    async def send_more_information_required_email(
        self, *, to: str, first_name: str, message: str
    ) -> EmailSendResult:
        subject, html = templates.more_information_required_email(
            app_url=self._config.app_url, first_name=first_name, message=message
        )
        return await self._send(
            to=to, subject=subject, html=html, log_context="more_information_required"
        )

    async def send_tenant_suspended_email(
        self, *, to: str, first_name: str, reason: str | None
    ) -> EmailSendResult:
        subject, html = templates.tenant_suspended_email(
            app_url=self._config.app_url, first_name=first_name, reason=reason
        )
        return await self._send(to=to, subject=subject, html=html, log_context="tenant_suspended")

    async def send_tenant_reactivated_email(self, *, to: str, first_name: str) -> EmailSendResult:
        subject, html = templates.tenant_reactivated_email(
            app_url=self._config.app_url, first_name=first_name
        )
        return await self._send(
            to=to, subject=subject, html=html, log_context="tenant_reactivated"
        )
