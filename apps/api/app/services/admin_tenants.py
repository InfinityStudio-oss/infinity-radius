"""Super Admin tenant review actions — approve/reject/request-more-info/
suspend/reactivate. The ONLY place tenants.status and
tenant_feature_flags ever change after onboarding. Every transition is
audit-logged and (best-effort) emailed via Resend; never deletes the auth
user, tenant, or any history.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EmailEventStatus, EmailEventType, TenantStatus, TenantVerificationStatus
from app.core.errors import DomainValidationError, NotFoundError
from app.integrations.resend.schemas import EmailSendResult
from app.integrations.resend.service import ResendEmailService
from app.models.audit import AuditLog
from app.models.onboarding import EmailEvent, TenantFeatureFlags, TenantVerification
from app.models.tenancy import Profile, Tenant
from app.repositories.tenancy import TenantRepository
from app.schemas.onboarding import (
    AdminTenantDetailRead,
    AdminTenantQueueRow,
    TenantVerificationRead,
)
from app.schemas.tenancy import TenantRead
from app.services.audit import write_audit_log

# Financial access policy: business approval (tenant.status -> ACTIVE)
# never implies live financial processing. collection_enabled/
# payout_enabled on tenant_feature_flags are independently controlled by
# a Super Admin via set_collection_enabled/set_payout_enabled below, each
# its own explicit, audited decision — see docs/architecture.md.


class AdminTenantService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.tenant_repo = TenantRepository(db)
        self._resend = ResendEmailService()

    async def _get_tenant_and_owner(
        self, tenant_id: uuid.UUID
    ) -> tuple[Tenant, TenantVerification, Profile | None]:
        tenant = await self.tenant_repo.get_by_id(tenant_id=None, id=tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found")

        verification_result = await self.db.execute(
            select(TenantVerification).where(TenantVerification.tenant_id == tenant_id)
        )
        verification = verification_result.scalar_one_or_none()
        if verification is None:
            raise DomainValidationError("Tenant has no verification record")

        # Plain Profile.tenant_id match — no ProfileRole join. A join there
        # would incorrectly report "no owner" for a profile that exists
        # but (through some other integrity gap) currently holds no role
        # row; this query's only job is "does a profile still claim this
        # tenant", which owner_missing below reports honestly either way.
        owner_result = await self.db.execute(
            select(Profile)
            .where(Profile.tenant_id == tenant_id)
            .order_by(Profile.created_at.asc())
            .limit(1)
        )
        owner = owner_result.scalars().first()
        return tenant, verification, owner

    async def approve(self, *, tenant_id: uuid.UUID, actor_id: uuid.UUID) -> Tenant:
        tenant, verification, owner = await self._get_tenant_and_owner(tenant_id)
        now = datetime.now(UTC)

        tenant.status = TenantStatus.ACTIVE.value
        verification.status = TenantVerificationStatus.APPROVED.value
        verification.reviewed_at = now
        verification.reviewed_by = actor_id
        verification.approved_at = now

        # Deliberately does NOT touch collection_enabled/payout_enabled —
        # business approval and financial access are two separate Super
        # Admin decisions. See set_collection_enabled/set_payout_enabled.

        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="TENANT_REVIEWED",
            target_type="tenant",
            target_id=tenant_id,
            metadata={"decision": "APPROVED"},
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="TENANT_APPROVED",
            target_type="tenant",
            target_id=tenant_id,
        )
        await self.db.commit()
        await self.db.refresh(tenant)

        if owner is not None and owner.email:
            result = await self._resend.send_tenant_approved_email(
                to=owner.email, first_name=owner.first_name or "there"
            )
            await self._record_email_event(
                tenant_id=tenant_id,
                recipient=owner.email,
                email_type=EmailEventType.TENANT_APPROVED.value,
                result=result,
            )
            await self.db.commit()

        return tenant

    async def reject(
        self, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, reason: str
    ) -> Tenant:
        tenant, verification, owner = await self._get_tenant_and_owner(tenant_id)
        now = datetime.now(UTC)

        tenant.status = TenantStatus.REJECTED.value
        verification.status = TenantVerificationStatus.REJECTED.value
        verification.reviewed_at = now
        verification.reviewed_by = actor_id
        verification.rejected_at = now
        verification.rejection_reason = reason

        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="TENANT_REVIEWED",
            target_type="tenant",
            target_id=tenant_id,
            metadata={"decision": "REJECTED", "reason": reason},
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="TENANT_REJECTED",
            target_type="tenant",
            target_id=tenant_id,
            metadata={"reason": reason},
        )
        await self.db.commit()
        await self.db.refresh(tenant)

        if owner is not None and owner.email:
            result = await self._resend.send_tenant_rejected_email(
                to=owner.email, first_name=owner.first_name or "there", reason=reason
            )
            await self._record_email_event(
                tenant_id=tenant_id,
                recipient=owner.email,
                email_type=EmailEventType.TENANT_REJECTED.value,
                result=result,
            )
            await self.db.commit()

        return tenant

    async def request_more_information(
        self, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, message: str
    ) -> Tenant:
        tenant, verification, owner = await self._get_tenant_and_owner(tenant_id)
        now = datetime.now(UTC)

        tenant.status = TenantStatus.MORE_INFORMATION_REQUIRED.value
        verification.status = TenantVerificationStatus.MORE_INFORMATION_REQUIRED.value
        verification.reviewed_at = now
        verification.reviewed_by = actor_id
        verification.more_information_message = message

        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="MORE_INFORMATION_REQUESTED",
            target_type="tenant",
            target_id=tenant_id,
            metadata={"message": message},
        )
        await self.db.commit()
        await self.db.refresh(tenant)

        if owner is not None and owner.email:
            result = await self._resend.send_more_information_required_email(
                to=owner.email, first_name=owner.first_name or "there", message=message
            )
            await self._record_email_event(
                tenant_id=tenant_id,
                recipient=owner.email,
                email_type=EmailEventType.MORE_INFORMATION_REQUIRED.value,
                result=result,
            )
            await self.db.commit()

        return tenant

    async def suspend(
        self, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, reason: str | None
    ) -> Tenant:
        tenant = await self.tenant_repo.get_by_id(tenant_id=None, id=tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found")

        tenant.status = TenantStatus.SUSPENDED.value
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="TENANT_SUSPENDED",
            target_type="tenant",
            target_id=tenant_id,
            metadata={"reason": reason} if reason else None,
        )
        await self.db.commit()
        await self.db.refresh(tenant)

        _, _, owner = await self._get_tenant_and_owner(tenant_id)
        if owner is not None and owner.email:
            result = await self._resend.send_tenant_suspended_email(
                to=owner.email, first_name=owner.first_name or "there", reason=reason
            )
            await self._record_email_event(
                tenant_id=tenant_id,
                recipient=owner.email,
                email_type=EmailEventType.TENANT_SUSPENDED.value,
                result=result,
            )
            await self.db.commit()

        return tenant

    async def reactivate(self, *, tenant_id: uuid.UUID, actor_id: uuid.UUID) -> Tenant:
        tenant = await self.tenant_repo.get_by_id(tenant_id=None, id=tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found")

        tenant.status = TenantStatus.ACTIVE.value
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="TENANT_REACTIVATED",
            target_type="tenant",
            target_id=tenant_id,
        )
        await self.db.commit()
        await self.db.refresh(tenant)

        _, _, owner = await self._get_tenant_and_owner(tenant_id)
        if owner is not None and owner.email:
            result = await self._resend.send_tenant_reactivated_email(
                to=owner.email, first_name=owner.first_name or "there"
            )
            await self._record_email_event(
                tenant_id=tenant_id,
                recipient=owner.email,
                email_type=EmailEventType.TENANT_REACTIVATED.value,
                result=result,
            )
            await self.db.commit()

        return tenant

    async def _get_flags(self, tenant_id: uuid.UUID) -> TenantFeatureFlags:
        flags = await self.db.scalar(
            select(TenantFeatureFlags).where(TenantFeatureFlags.tenant_id == tenant_id)
        )
        if flags is None:
            raise DomainValidationError("Tenant has no feature flags record")
        return flags

    async def set_collection_enabled(
        self, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, enabled: bool
    ) -> TenantFeatureFlags:
        """Independent of tenant.status — a Super Admin can enable/disable
        Collections access for an ACTIVE tenant at any time, separate from
        the approval decision. Never touches wallet balances or ledger
        entries; this only gates whether the captive portal's payment
        flow is allowed to run for this tenant."""
        flags = await self._get_flags(tenant_id)
        flags.collection_enabled = enabled
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="TENANT_COLLECTION_ENABLED" if enabled else "TENANT_COLLECTION_DISABLED",
            target_type="tenant",
            target_id=tenant_id,
        )
        await self.db.commit()
        await self.db.refresh(flags)
        return flags

    async def set_payout_enabled(
        self, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, enabled: bool
    ) -> TenantFeatureFlags:
        """Same independence as set_collection_enabled — gates whether a
        tenant may request a payout at all; never edits a wallet balance
        or approves/rejects an individual withdrawal itself (see
        app/services/payouts.py for that, unrelated, maker-checker flow)."""
        flags = await self._get_flags(tenant_id)
        flags.payout_enabled = enabled
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="TENANT_PAYOUT_ENABLED" if enabled else "TENANT_PAYOUT_DISABLED",
            target_type="tenant",
            target_id=tenant_id,
        )
        await self.db.commit()
        await self.db.refresh(flags)
        return flags

    async def list_queue(self, *, status_filter: str | None) -> list[AdminTenantQueueRow]:
        """Powers /super-admin/tenants. `email_verified` reflects the last
        time tenant_verifications.email_verified_at was synced (see
        OnboardingService.get_account_status) — a cached signal, not a
        live per-row Supabase call, so listing many tenants stays cheap.

        Both joins are LEFT OUTER: a tenant whose owner profile is missing
        (e.g. that profile was later converted to a platform SUPER_ADMIN
        account, or the verification row is somehow absent) must still
        appear here for a Super Admin to see and investigate — never
        silently dropped from the queue. See owner_missing on the result.
        """
        stmt = (
            select(
                Tenant.id,
                Tenant.name,
                Tenant.business_type,
                Tenant.region,
                Tenant.status,
                Profile.full_name,
                Profile.email,
                TenantVerification.submitted_at,
                TenantVerification.email_verified_at,
            )
            .outerjoin(Profile, Profile.tenant_id == Tenant.id)
            .outerjoin(TenantVerification, TenantVerification.tenant_id == Tenant.id)
            .order_by(desc(TenantVerification.submitted_at))
        )
        if status_filter and status_filter != "all":
            stmt = stmt.where(Tenant.status == status_filter)

        result = await self.db.execute(stmt)
        rows = result.all()

        seen: set[uuid.UUID] = set()
        queue: list[AdminTenantQueueRow] = []
        for row in rows:
            if row.id in seen:
                continue
            seen.add(row.id)
            queue.append(
                AdminTenantQueueRow(
                    id=row.id,
                    business_name=row.name,
                    owner_name=row.full_name,
                    owner_email=row.email,
                    owner_missing=row.email is None,
                    business_type=row.business_type,
                    region=row.region,
                    email_verified=row.email_verified_at is not None,
                    submitted_at=row.submitted_at,
                    status=row.status,
                )
            )
        return queue

    async def get_detail(self, *, tenant_id: uuid.UUID) -> AdminTenantDetailRead:
        tenant, verification, owner = await self._get_tenant_and_owner(tenant_id)

        flags = await self.db.scalar(
            select(TenantFeatureFlags).where(TenantFeatureFlags.tenant_id == tenant_id)
        )

        audit_result = await self.db.execute(
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant_id)
            .order_by(desc(AuditLog.created_at))
            .limit(20)
        )
        audit_logs = audit_result.scalars().all()

        return AdminTenantDetailRead(
            tenant=TenantRead.model_validate(tenant),
            owner_name=owner.full_name if owner is not None else None,
            owner_email=owner.email if owner is not None else None,
            owner_phone=owner.phone if owner is not None else None,
            owner_missing=owner is None,
            authorized_contact_name=tenant.authorized_contact_name
            or (owner.full_name if owner is not None else None),
            email_verified=verification.email_verified_at is not None,
            verification=TenantVerificationRead.model_validate(verification),
            collection_enabled=flags.collection_enabled if flags is not None else False,
            payout_enabled=flags.payout_enabled if flags is not None else False,
            recent_audit_logs=[
                {
                    "action": log.action,
                    "created_at": log.created_at.isoformat(),
                    "actor_id": str(log.actor_id) if log.actor_id else None,
                    "metadata": log.log_metadata,
                }
                for log in audit_logs
            ],
        )

    async def _record_email_event(
        self,
        *,
        tenant_id: uuid.UUID,
        recipient: str,
        email_type: str,
        result: EmailSendResult,
    ) -> None:
        now = datetime.now(UTC)
        self.db.add(
            EmailEvent(
                tenant_id=tenant_id,
                recipient=recipient,
                email_type=email_type,
                provider_message_id=result.provider_message_id,
                status=(
                    EmailEventStatus.SENT.value if result.sent else EmailEventStatus.FAILED.value
                ),
                sent_at=now if result.sent else None,
                failed_at=None if result.sent else now,
                error_message=result.error_message,
            )
        )
        await self.db.flush()
