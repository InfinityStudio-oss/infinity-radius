"""Access activation for a captive-portal payment — deliberately SEPARATE
from the payment itself.

PAYMENT VERIFIED and ACCESS ACTIVATED are different facts, and this module
exists so a failure in the second can never undo the first. The customer's
money has already moved by the time anything here runs; rolling the payment
back because FreeRADIUS was unreachable would mean they were charged and
then told they were not.

That guarantee is STRUCTURAL, not a convention: activation runs in its own
database transaction, opened after the payment transaction has already
committed. `run_activation()` is the only supported entry point for that
reason — it commits a successful activation, and on failure it rolls the
partial work back and then records ACTIVATION FAILED in a second, clean
transaction. The payment row's status, wallet and ledger are never inside
either of those transactions.

Everything here is idempotent. A retry after a failure re-runs only what
is still missing: a subscription already ACTIVE is left alone, RADIUS
provisioning is an upsert by design (see app/services/radius_sync.py), and
a transaction already ACTIVE returns immediately without touching anything.
Retrying can therefore only ever grant access — it can never create a
second payment, credit the wallet again, or charge the customer twice.

NOT WIRED TO A LIVE FLOW YET. No captive payment can reach a provider, so
nothing calls this in production — see app/services/captive_portal.py.
"""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ActivationStatus, CollectionStatus, SubscriptionStatus
from app.core.errors import DomainValidationError, NotFoundError
from app.db.session import AsyncSessionLocal
from app.models.network import Customer, Package, Subscription
from app.repositories.finance import TransactionRepository
from app.services.audit import write_audit_log
from app.services.radius_provisioning import describe_transport, provision_access
from app.services.radius_sync import derive_radius_password
from app.services.subscriptions import SubscriptionService

logger = structlog.get_logger("services.captive_activation")


class ActivationFailedError(Exception):
    """Access provisioning failed for a payment that is, and stays,
    COMPLETED. Carries the reason so it can be recorded and shown to
    support — never surfaced to the customer as a payment failure."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class CaptivePortalActivationService:
    """Grants the access a verified payment paid for.

    Takes a session like every other service, but callers MUST NOT reuse
    the session that finalized the payment — see this module's docstring
    and `run_activation`, which enforces the separation.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.transaction_repo = TransactionRepository(db)

    async def activate(self, *, transaction_id: UUID) -> ActivationStatus:
        """Activates the subscription and provisions RADIUS for an
        already-COMPLETED payment. Row-locks the transaction so two
        concurrent retries cannot both provision.

        Raises ActivationFailedError if access provisioning fails — the
        caller is responsible for rolling back and recording that, which
        is what `run_activation` does.
        """
        transaction = await self.transaction_repo.get_by_id_for_update(
            tenant_id=None, id=transaction_id
        )
        if transaction is None:
            raise NotFoundError("Transaction not found")

        # Access is only ever granted for a payment THIS system verified as
        # COMPLETED. Any other status — including a non-terminal one still
        # being reconciled — must never provision anything.
        if transaction.status != CollectionStatus.COMPLETED.value:
            raise DomainValidationError(
                f"Cannot activate access for a payment in status {transaction.status}"
            )

        if transaction.activation_status == ActivationStatus.ACTIVE.value:
            return ActivationStatus.ACTIVE  # already granted — idempotent no-op

        if transaction.subscription_id is None or transaction.customer_id is None:
            raise DomainValidationError("Transaction has no associated subscription/customer")

        subscription = (
            await self.db.execute(
                select(Subscription).where(Subscription.id == transaction.subscription_id)
            )
        ).scalar_one_or_none()
        if subscription is None:
            raise NotFoundError("Subscription not found")

        customer = (
            await self.db.execute(
                select(Customer).where(Customer.id == transaction.customer_id)
            )
        ).scalar_one()
        package = (
            await self.db.execute(select(Package).where(Package.id == subscription.package_id))
        ).scalar_one()

        await self.transaction_repo.update(
            transaction, activation_status=ActivationStatus.ACTIVATING.value
        )

        # Idempotent: a retry after a RADIUS failure finds the subscription
        # already ACTIVE from the previous attempt and must not try to
        # re-activate it (SubscriptionService.activate only accepts PENDING).
        if subscription.status == SubscriptionStatus.PENDING:
            subscription = await SubscriptionService(self.db).activate(
                tenant_id=transaction.tenant_id,
                actor_id=None,
                subscription_id=subscription.id,
            )

        # The step that genuinely fails in production. Provisioning is an
        # upsert through whichever transport is configured (Network Agent
        # in production, direct database locally — see
        # app/services/radius_provisioning.py), so re-running it is safe.
        # NOTE: it writes to a SEPARATE system entirely and is not covered
        # by this transaction either way — another reason activation must
        # never share the payment's.
        try:
            transport = await provision_access(
                customer_phone=customer.phone,
                package_id=package.id,
                radius_password=derive_radius_password(subscription.id),
                download_speed_kbps=package.download_speed_kbps,
                upload_speed_kbps=package.upload_speed_kbps,
                session_timeout_seconds=(
                    package.duration_minutes * 60 if package.duration_minutes else None
                ),
                simultaneous_sessions=package.simultaneous_sessions,
            )
        except Exception as exc:  # noqa: BLE001 — any provisioning failure is recoverable
            logger.warning(
                "captive_activation.radius_provisioning_failed",
                transaction_id=str(transaction_id),
                transport=describe_transport(),
                error=str(exc),
            )
            raise ActivationFailedError(f"RADIUS provisioning failed: {exc}") from exc

        await self.transaction_repo.update(
            transaction,
            activation_status=ActivationStatus.ACTIVE.value,
            activated_at=datetime.now(UTC),
        )
        await write_audit_log(
            self.db,
            tenant_id=transaction.tenant_id,
            actor_id=None,
            action="captive_portal.access_activated",
            target_type="transaction",
            target_id=transaction.id,
            metadata={
                "subscription_id": str(subscription.id),
                # Which path actually granted access — the first thing to
                # check when access works in one environment and not another.
                "transport": transport,
            },
        )
        return ActivationStatus.ACTIVE

    async def record_failure(self, *, transaction_id: UUID, reason: str) -> ActivationStatus:
        """Marks activation FAILED on a payment that remains COMPLETED.

        Called in a CLEAN transaction after the failed attempt was rolled
        back, so this marker survives even though the partial subscription
        work did not. Never touches status, amount, wallet or ledger.
        """
        transaction = await self.transaction_repo.get_by_id_for_update(
            tenant_id=None, id=transaction_id
        )
        if transaction is None:
            raise NotFoundError("Transaction not found")

        await self.transaction_repo.update(
            transaction, activation_status=ActivationStatus.FAILED.value
        )
        await write_audit_log(
            self.db,
            tenant_id=transaction.tenant_id,
            actor_id=None,
            action="captive_portal.access_activation_failed",
            target_type="transaction",
            target_id=transaction.id,
            # The payment state is restated here on purpose: whoever reads
            # this audit entry must see immediately that the money is fine
            # and only access is outstanding.
            metadata={
                "reason": reason,
                "payment_status": transaction.status,
                "retryable": True,
            },
        )
        return ActivationStatus.FAILED

    async def list_retryable(self, *, limit: int = 100) -> list[UUID]:
        """Payments that are paid but not yet activated — the work list for
        the retry sweep. Deliberately includes PENDING (activation never
        started, e.g. the process died between the two transactions) as
        well as FAILED."""
        stmt = (
            select(TransactionRepository.model.id)
            .where(
                TransactionRepository.model.status == CollectionStatus.COMPLETED.value,
                TransactionRepository.model.activation_status.in_(
                    [ActivationStatus.PENDING.value, ActivationStatus.FAILED.value]
                ),
            )
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


async def run_activation(*, transaction_id: UUID) -> ActivationStatus:
    """The ONLY supported way to activate access.

    Opens its own session so activation can never share the transaction
    that finalized the payment. On failure it rolls the partial work back
    and records ACTIVATION FAILED in a second, clean transaction — so the
    outcome is always durable, and the payment is never in scope of either.
    """
    async with AsyncSessionLocal() as db:
        service = CaptivePortalActivationService(db)
        try:
            result = await service.activate(transaction_id=transaction_id)
            await db.commit()
            return result
        except ActivationFailedError as exc:
            await db.rollback()
            reason = exc.reason

    async with AsyncSessionLocal() as db:
        await CaptivePortalActivationService(db).record_failure(
            transaction_id=transaction_id, reason=reason
        )
        await db.commit()
    return ActivationStatus.FAILED
