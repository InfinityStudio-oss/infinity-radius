"""Client signup + business onboarding orchestration.

`register()` is the ONLY place a Tenant, its owning Profile, and every
related first-run row (wallet, settings, feature flags, verification
record) come into existence together. The frontend never creates any of
this state itself — see app/api/v1/onboarding.py.

Ordering matters: the Supabase Auth user is created FIRST, before any
local DB writes, specifically so that if the local DB transaction fails
afterward, we can compensate by deleting the just-created auth user
(never leaving an orphaned account with no tenant). Email delivery is
deliberately NOT part of that same atomic unit — once the DB transaction
commits, the account genuinely exists; a Resend outage after that point
is recorded as a FAILED email_events row, never a reason to undo
already-successful account creation.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import EmailEventStatus, EmailEventType, TenantStatus, TenantVerificationStatus
from app.core.errors import ConflictError, DomainValidationError
from app.core.phone import normalize_tz_phone
from app.core.roles import Role
from app.core.supabase_admin import SupabaseAdminClient, SupabaseAdminError
from app.integrations.resend.schemas import EmailSendResult
from app.integrations.resend.service import ResendEmailService
from app.models.onboarding import EmailEvent, TenantFeatureFlags, TenantSettings, TenantVerification
from app.models.tenancy import Profile, ProfileRole, Tenant
from app.models.tenancy import Role as RoleModel
from app.repositories.tenancy import ProfileRepository, TenantRepository
from app.schemas.onboarding import OnboardingRegisterRequest
from app.services.audit import write_audit_log
from app.services.wallet import WalletService

logger = structlog.get_logger("app.services.onboarding")

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    base = _SLUG_INVALID_CHARS.sub("-", name.strip().lower()).strip("-") or "tenant"
    return f"{base[:40]}-{uuid.uuid4().hex[:6]}"


@dataclass(frozen=True)
class OnboardingResult:
    tenant_id: uuid.UUID
    owner_id: uuid.UUID


class OnboardingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.tenant_repo = TenantRepository(db)
        self.profile_repo = ProfileRepository(db)
        self._supabase = SupabaseAdminClient()
        self._resend = ResendEmailService()

    async def _email_in_use(self, email: str) -> bool:
        result = await self.db.execute(select(Profile.id).where(Profile.email == email))
        return result.scalar_one_or_none() is not None

    async def register(self, payload: OnboardingRegisterRequest) -> OnboardingResult:
        # --- Validation not already covered by Pydantic field/model validators ---
        if await self._email_in_use(payload.work_email):
            raise ConflictError("An account with this email already exists")

        try:
            owner_phone = normalize_tz_phone(payload.phone)
            business_phone = normalize_tz_phone(payload.business_phone)
            authorized_phone = (
                normalize_tz_phone(payload.authorized_contact_phone)
                if payload.authorized_contact_phone
                else None
            )
        except ValueError as exc:
            raise DomainValidationError(str(exc)) from exc

        full_name = f"{payload.first_name} {payload.last_name}".strip()

        # --- External step FIRST: if this fails, nothing local was written. ---
        try:
            auth_user = await self._supabase.create_user(
                email=payload.work_email,
                password=payload.password,
                phone=f"+{owner_phone}",
                user_metadata={"full_name": full_name},
            )
        except SupabaseAdminError as exc:
            message = str(exc).lower()
            if "already" in message or "exists" in message:
                raise ConflictError("An account with this email already exists") from exc
            raise DomainValidationError(f"Could not create account: {exc}") from exc

        try:
            result = await self._create_local_records(
                payload=payload,
                owner_id=auth_user.id,
                full_name=full_name,
                owner_phone=owner_phone,
                business_phone=business_phone,
                authorized_phone=authorized_phone,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            logger.error("onboarding.local_write_failed", owner_id=str(auth_user.id))
            # Compensating action — never leave an auth user with no tenant.
            try:
                await self._supabase.delete_user(auth_user.id)
            except SupabaseAdminError as cleanup_exc:
                logger.error(
                    "onboarding.compensating_delete_failed",
                    owner_id=str(auth_user.id),
                    error=str(cleanup_exc),
                )
            raise

        # --- Best-effort from here: emails never unwind a committed account. ---
        await self._send_onboarding_emails(
            payload=payload, result=result, full_name=payload.first_name
        )

        return result

    async def _create_local_records(
        self,
        *,
        payload: OnboardingRegisterRequest,
        owner_id: uuid.UUID,
        full_name: str,
        owner_phone: str,
        business_phone: str,
        authorized_phone: str | None,
    ) -> OnboardingResult:
        now = datetime.now(UTC)

        tenant = Tenant(
            name=payload.trading_name,
            legal_name=payload.legal_name,
            slug=_slugify(payload.trading_name),
            business_type=payload.business_type.value,
            business_email=payload.business_email,
            business_phone=business_phone,
            tin=payload.tin,
            business_license_number=payload.business_license_number,
            region=payload.region,
            district=payload.district,
            ward=payload.ward,
            street_area=payload.street_area,
            address=payload.business_address,
            authorized_contact_name=payload.authorized_contact_name,
            authorized_contact_position=payload.authorized_contact_position,
            authorized_contact_phone=authorized_phone,
            authorized_contact_email=payload.authorized_contact_email,
            status=TenantStatus.PENDING_VERIFICATION.value,
            accepted_terms_at=now,
            accepted_privacy_at=now,
        )
        self.db.add(tenant)
        await self.db.flush()

        # The handle_new_auth_user trigger already inserted a `profiles` row
        # (tenant_id=NULL, status='invited') the moment create_user() ran.
        # This is the ONE place that row is claimed for a tenant.
        profile = await self.db.get(Profile, owner_id)
        if profile is None:
            # Should be unreachable (the trigger is unconditional on Supabase),
            # but never silently create a second, inconsistent profile row.
            raise DomainValidationError(
                "Account provisioning did not complete — please contact support"
            )
        profile.tenant_id = tenant.id
        profile.first_name = payload.first_name
        profile.last_name = payload.last_name
        profile.full_name = full_name
        profile.phone = owner_phone
        profile.status = "active"

        owner_role_id = await self.db.scalar(
            select(RoleModel.id).where(RoleModel.code == Role.TENANT_OWNER.value)
        )
        if owner_role_id is None:
            raise DomainValidationError("TENANT_OWNER role is not seeded — contact support")
        self.db.add(
            ProfileRole(profile_id=owner_id, role_id=owner_role_id, tenant_id=tenant.id)
        )

        self.db.add(
            TenantVerification(
                tenant_id=tenant.id,
                status=TenantVerificationStatus.PENDING_VERIFICATION.value,
                submitted_at=now,
            )
        )
        self.db.add(TenantSettings(tenant_id=tenant.id))
        self.db.add(TenantFeatureFlags(tenant_id=tenant.id))

        await WalletService(self.db).get_or_create_wallet(tenant_id=tenant.id)

        await write_audit_log(
            self.db,
            tenant_id=tenant.id,
            actor_id=owner_id,
            action="TENANT_REGISTERED",
            target_type="tenant",
            target_id=tenant.id,
            metadata={
                "business_type": payload.business_type.value,
                "region": payload.region,
                "district": payload.district,
            },
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant.id,
            actor_id=owner_id,
            action="PROFILE_CREATED",
            target_type="profile",
            target_id=owner_id,
        )

        return OnboardingResult(tenant_id=tenant.id, owner_id=owner_id)

    async def _send_onboarding_emails(
        self, *, payload: OnboardingRegisterRequest, result: OnboardingResult, full_name: str
    ) -> None:
        await self.send_verification_email(
            tenant_id=result.tenant_id,
            owner_id=result.owner_id,
            email=payload.work_email,
            first_name=full_name,
        )

        admin_result = await self._resend.send_admin_new_tenant_email(
            tenant_id=result.tenant_id,
            business_name=payload.trading_name,
            legal_name=payload.legal_name,
            business_type=payload.business_type.value,
            owner_name=f"{payload.first_name} {payload.last_name}",
            owner_email=payload.work_email,
            owner_phone=f"+{normalize_tz_phone(payload.phone)}",
            business_email=payload.business_email,
            business_phone=f"+{normalize_tz_phone(payload.business_phone)}",
            tin=payload.tin,
            business_license_number=payload.business_license_number,
            region=payload.region,
            district=payload.district,
            ward=payload.ward,
            submitted_at=datetime.now(UTC),
        )
        await self._record_email_event(
            tenant_id=result.tenant_id,
            recipient="super-admin-review",
            email_type=EmailEventType.NEW_TENANT_ADMIN_ALERT.value,
            result=admin_result,
        )
        await self.db.commit()

    async def send_verification_email(
        self, *, tenant_id: uuid.UUID, owner_id: uuid.UUID, email: str, first_name: str
    ) -> bool:
        """Shared by registration and the rate-limited "resend verification
        email" action. Always generates a fresh, real Supabase link —
        never reuses/invents one."""
        settings = get_settings()
        try:
            action_link = await self._supabase.generate_link(
                link_type="signup",
                email=email,
                password=None,
                redirect_to=f"{settings.app_url}/account/verify-email",
            )
        except SupabaseAdminError as exc:
            logger.error("onboarding.generate_link_failed", error=str(exc))
            await self._record_email_event(
                tenant_id=tenant_id,
                recipient=email,
                email_type=EmailEventType.VERIFY_EMAIL.value,
                result=None,
                error_message=str(exc),
            )
            await self.db.commit()
            return False

        send_result = await self._resend.send_verification_email(
            to=email, first_name=first_name, verify_url=action_link
        )
        await self._record_email_event(
            tenant_id=tenant_id,
            recipient=email,
            email_type=EmailEventType.VERIFY_EMAIL.value,
            result=send_result,
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=owner_id,
            action="EMAIL_VERIFICATION_SENT",
            target_type="tenant",
            target_id=tenant_id,
        )
        await self.db.commit()
        return send_result.sent

    async def resend_verification_by_email(self, *, email: str) -> bool:
        """Powers the rate-limited "Resend verification email" action on
        /account/verify-email — reached before the user necessarily has a
        session (Supabase requires email confirmation before login by
        default), so this is looked up by email, not an authenticated
        context."""
        result = await self.db.execute(
            select(Profile.id, Profile.tenant_id, Profile.first_name).where(
                Profile.email == email
            )
        )
        row = result.first()
        if row is None:
            # Never confirm/deny account existence to an unauthenticated caller.
            return True
        owner_id, tenant_id, first_name = row
        if tenant_id is None:
            return True
        return await self.send_verification_email(
            tenant_id=tenant_id,
            owner_id=owner_id,
            email=email,
            first_name=first_name or "there",
        )

    async def get_account_status(
        self, *, tenant_id: uuid.UUID, owner_id: uuid.UUID
    ) -> tuple[str, bool, TenantVerification | None]:
        """Returns (tenant_status, email_verified, verification_record) —
        exactly what /account/pending-review and friends render. Email
        verification is asked of Supabase directly (the source of truth),
        never inferred from local state."""
        tenant = await self.tenant_repo.get_by_id(tenant_id=None, id=tenant_id)
        tenant_status = (
            tenant.status if tenant is not None else TenantStatus.PENDING_VERIFICATION.value
        )

        email_verified = False
        try:
            detail = await self._supabase.get_user(owner_id)
            email_verified = detail.email_confirmed
        except SupabaseAdminError as exc:
            logger.warning("onboarding.get_user_failed", error=str(exc))

        verification_result = await self.db.execute(
            select(TenantVerification).where(TenantVerification.tenant_id == tenant_id)
        )
        verification = verification_result.scalar_one_or_none()

        if email_verified and verification is not None and verification.email_verified_at is None:
            verification.email_verified_at = datetime.now(UTC)
            await write_audit_log(
                self.db,
                tenant_id=tenant_id,
                actor_id=owner_id,
                action="EMAIL_VERIFIED",
                target_type="tenant",
                target_id=tenant_id,
            )
            await self.db.commit()

        return tenant_status, email_verified, verification

    async def _record_email_event(
        self,
        *,
        tenant_id: uuid.UUID | None,
        recipient: str,
        email_type: str,
        result: object,
        error_message: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        if isinstance(result, EmailSendResult):
            self.db.add(
                EmailEvent(
                    tenant_id=tenant_id,
                    recipient=recipient,
                    email_type=email_type,
                    provider_message_id=result.provider_message_id,
                    status=(
                        EmailEventStatus.SENT.value
                        if result.sent
                        else EmailEventStatus.FAILED.value
                    ),
                    sent_at=now if result.sent else None,
                    failed_at=None if result.sent else now,
                    error_message=result.error_message,
                )
            )
        else:
            self.db.add(
                EmailEvent(
                    tenant_id=tenant_id,
                    recipient=recipient,
                    email_type=email_type,
                    status=EmailEventStatus.FAILED.value,
                    failed_at=now,
                    error_message=error_message,
                )
            )
        await self.db.flush()
