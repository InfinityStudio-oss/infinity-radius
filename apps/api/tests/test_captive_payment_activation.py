"""Payment finalization and access activation are separate, and a failure
in the second must never undo the first.

The guarantee under test: once Selcom has verified a payment COMPLETED,
the customer's money has moved. If FreeRADIUS is then unreachable, they
must still be recorded as paid — with access owed and retryable — rather
than told their payment failed. Getting this wrong means charging someone
and then denying it, which is the worst outcome this system can produce.

These tests drive the real services against the real database. RADIUS
failure is simulated by pointing the provisioning call at a raising stub,
which is how the production failure actually surfaces (see
app/services/radius_sync.py, which talks to a separate Postgres instance).
"""

import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.core.enums import ActivationStatus, CollectionStatus, TransactionType
from app.core.errors import DomainValidationError
from app.db.session import AsyncSessionLocal
from app.models.network import Customer, Package, Subscription
from app.repositories.finance import TransactionRepository
from app.services import captive_activation as activation_module
from app.services.captive_activation import (
    CaptivePortalActivationService,
    run_activation,
)
from app.services.captive_portal import CaptivePortalService
from tests.db_fixtures import SeededContext

_PRICE = Decimal("1500.00")


async def _seed_payable(tenant_id: UUID) -> UUID:
    """Creates the customer/package/subscription/transaction shape that
    captive initiation produces, without contacting any provider."""
    async with AsyncSessionLocal() as db:
        customer = Customer(
            tenant_id=tenant_id,
            customer_number=f"C{uuid4().hex[:10]}",
            phone=f"2557{uuid4().int % 10**8:08d}",
        )
        package = Package(
            tenant_id=tenant_id,
            name="Test Package",
            price_tzs=str(_PRICE),
            duration_minutes=60,
            download_speed_kbps=2048,
            upload_speed_kbps=1024,
        )
        db.add_all([customer, package])
        await db.flush()
        subscription = Subscription(
            tenant_id=tenant_id, customer_id=customer.id, package_id=package.id, status="PENDING"
        )
        db.add(subscription)
        await db.flush()
        transaction = await TransactionRepository(db).create(
            tenant_id=tenant_id,
            customer_id=customer.id,
            subscription_id=subscription.id,
            transaction_type=TransactionType.CAPTIVE_PORTAL.value,
            reference=f"CP-{uuid4().hex[:16].upper()}",
            channel="captive_portal",
            amount=str(_PRICE),
            currency="TZS",
            status=CollectionStatus.CREATED.value,
        )
        await db.commit()
        return transaction.id


async def _finalize(transaction_id: UUID) -> None:
    async with AsyncSessionLocal() as db:
        await CaptivePortalService(db).finalize_payment(transaction_id=transaction_id)
        await db.commit()


async def _row(transaction_id: UUID) -> tuple[str, str | None, object]:
    async with AsyncSessionLocal() as db:
        t = await TransactionRepository(db).get_by_id(tenant_id=None, id=transaction_id)
        assert t is not None
        return t.status, t.activation_status, t.activated_at


async def _ledger_rows(tenant_id: UUID) -> list[tuple[str, str]]:
    from sqlalchemy import select

    from app.models.finance import LedgerEntry

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(LedgerEntry.entry_type, LedgerEntry.amount).where(
                LedgerEntry.tenant_id == tenant_id
            )
        )
        return [(r[0], str(r[1])) for r in result.all()]


def _break_radius(monkeypatch: pytest.MonkeyPatch, message: str = "RADIUS is down") -> None:
    """Simulates the real production failure: FreeRADIUS unreachable."""

    async def _boom(**_kwargs: object) -> None:
        raise RuntimeError(message)

    monkeypatch.setattr(activation_module, "sync_package_radius_group", _boom)
    monkeypatch.setattr(activation_module, "provision_customer_radius_access", _boom)


# ----------------------------------------------------- status vocabulary


def test_captive_initiation_writes_the_unified_status_vocabulary() -> None:
    """No lowercase 'pending' anywhere — one vocabulary for both payment
    families, so one reconciler and one set of terminal rules cover both."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        transaction_id = asyncio.run(_seed_payable(tenant_id))
        status, activation_status, _ = asyncio.run(_row(transaction_id))
        assert status == CollectionStatus.CREATED.value
        assert status not in {"pending", "completed", "failed"}
        assert activation_status is None


def test_source_contains_no_lowercase_transaction_status_assumptions() -> None:
    """Guards the removal itself.

    Scoped to `transaction.status` comparisons and to what the writer
    persists — NOT to the public API's own `status` literal, which is a
    deliberately coarse customer-facing projection ("pending"/"completed"/
    "failed") and is meant to stay lowercase. The bug this phase removed
    was a lowercase comparison against the STORED column, which silently
    matched no row at all.
    """
    import pathlib
    import re

    for module in ("app/services/captive_portal.py", "app/services/captive_activation.py"):
        source = pathlib.Path(module).read_text(encoding="utf-8")
        offenders = re.findall(
            r'transaction\.status\s*[!=]=\s*"(pending|completed|failed)"', source
        )
        assert not offenders, f"{module} compares transaction.status to {offenders}"

    # And the writer persists the unified vocabulary, not a bare literal.
    writer = pathlib.Path("app/services/captive_portal.py").read_text(encoding="utf-8")
    assert "status=CollectionStatus.CREATED.value" in writer
    assert "status=CollectionStatus.COMPLETED.value" in writer


def test_public_status_projection_stays_lowercase_by_design() -> None:
    """The customer-facing contract is intentionally unchanged: the
    frontend reads these exact values, and they are a projection of the
    stored vocabulary, not the vocabulary itself."""
    from app.schemas.captive_portal import CaptivePortalPaymentStatusResult

    result = CaptivePortalPaymentStatusResult(status="completed")
    assert result.status == "completed"


# --------------------------------------------------- payment finalization


def test_completed_finalizes_payment_and_credits_wallet_exactly_once() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        ctx.new_commercial_terms(tenant_id=tenant_id, commission_rate_percent="10.00")
        transaction_id = asyncio.run(_seed_payable(tenant_id))

        asyncio.run(_finalize(transaction_id))

        status, activation_status, activated_at = asyncio.run(_row(transaction_id))
        assert status == CollectionStatus.COMPLETED.value
        # Paid, access not yet granted — visible to the retry sweep.
        assert activation_status == ActivationStatus.PENDING.value
        assert activated_at is None

        entries = asyncio.run(_ledger_rows(tenant_id))
        by_type = {t: a for t, a in entries}
        assert len(entries) == 3
        assert by_type["COLLECTION"] == "1500.00"
        assert by_type["PLATFORM_FEE"] == "150.00"
        assert by_type["TENANT_SHARE"] == "1350.00"


def test_duplicate_completed_does_not_double_credit() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        ctx.new_commercial_terms(tenant_id=tenant_id, commission_rate_percent="10.00")
        transaction_id = asyncio.run(_seed_payable(tenant_id))

        asyncio.run(_finalize(transaction_id))
        asyncio.run(_finalize(transaction_id))
        asyncio.run(_finalize(transaction_id))

        # Still exactly three ledger entries, not nine.
        assert len(asyncio.run(_ledger_rows(tenant_id))) == 3


def test_terminal_failure_status_can_never_be_finalized_into_a_credit() -> None:
    """A CANCELLED payment must never be resurrected into money."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        ctx.new_commercial_terms(tenant_id=tenant_id, commission_rate_percent="10.00")
        transaction_id = asyncio.run(_seed_payable(tenant_id))

        async def _cancel() -> None:
            async with AsyncSessionLocal() as db:
                repo = TransactionRepository(db)
                t = await repo.get_by_id(tenant_id=None, id=transaction_id)
                assert t is not None
                await repo.update(t, status=CollectionStatus.CANCELLED.value)
                await db.commit()

        asyncio.run(_cancel())
        with pytest.raises(DomainValidationError):
            asyncio.run(_finalize(transaction_id))
        assert asyncio.run(_ledger_rows(tenant_id)) == []


def test_non_completed_payment_cannot_activate_access() -> None:
    """Access is only ever granted for a payment verified COMPLETED."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        transaction_id = asyncio.run(_seed_payable(tenant_id))

        async def _try() -> None:
            async with AsyncSessionLocal() as db:
                await CaptivePortalActivationService(db).activate(transaction_id=transaction_id)

        with pytest.raises(DomainValidationError):
            asyncio.run(_try())


# ------------------------------------------------ activation independence


def test_radius_failure_never_rolls_back_the_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE core guarantee of this phase. The money stays finalized; only
    access is outstanding."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        ctx.new_commercial_terms(tenant_id=tenant_id, commission_rate_percent="10.00")
        transaction_id = asyncio.run(_seed_payable(tenant_id))

        asyncio.run(_finalize(transaction_id))
        _break_radius(monkeypatch)
        result = asyncio.run(run_activation(transaction_id=transaction_id))

        assert result is ActivationStatus.FAILED
        status, activation_status, activated_at = asyncio.run(_row(transaction_id))
        # Payment untouched.
        assert status == CollectionStatus.COMPLETED.value
        # Only activation is marked failed.
        assert activation_status == ActivationStatus.FAILED.value
        assert activated_at is None
        # Wallet/ledger remain finalized — exactly once, not rolled back.
        entries = asyncio.run(_ledger_rows(tenant_id))
        assert len(entries) == 3
        assert {t: a for t, a in entries}["TENANT_SHARE"] == "1350.00"


def test_failed_activation_is_retryable_and_succeeds_without_a_second_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        ctx.new_commercial_terms(tenant_id=tenant_id, commission_rate_percent="10.00")
        transaction_id = asyncio.run(_seed_payable(tenant_id))

        asyncio.run(_finalize(transaction_id))
        _break_radius(monkeypatch)
        assert asyncio.run(run_activation(transaction_id=transaction_id)) is ActivationStatus.FAILED

        # It is on the retry work list precisely because it failed.
        async def _retryable() -> list[UUID]:
            async with AsyncSessionLocal() as db:
                return await CaptivePortalActivationService(db).list_retryable()

        assert transaction_id in asyncio.run(_retryable())

        # RADIUS comes back.
        monkeypatch.undo()
        assert asyncio.run(run_activation(transaction_id=transaction_id)) is ActivationStatus.ACTIVE

        status, activation_status, activated_at = asyncio.run(_row(transaction_id))
        assert status == CollectionStatus.COMPLETED.value
        assert activation_status == ActivationStatus.ACTIVE.value
        assert activated_at is not None
        # No second payment, no second credit.
        assert len(asyncio.run(_ledger_rows(tenant_id))) == 3


def test_duplicate_retry_after_success_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        ctx.new_commercial_terms(tenant_id=tenant_id, commission_rate_percent="10.00")
        transaction_id = asyncio.run(_seed_payable(tenant_id))

        asyncio.run(_finalize(transaction_id))
        assert asyncio.run(run_activation(transaction_id=transaction_id)) is ActivationStatus.ACTIVE
        _, _, first_activated_at = asyncio.run(_row(transaction_id))

        # Re-running must change nothing at all.
        assert asyncio.run(run_activation(transaction_id=transaction_id)) is ActivationStatus.ACTIVE
        assert asyncio.run(run_activation(transaction_id=transaction_id)) is ActivationStatus.ACTIVE

        status, activation_status, activated_at = asyncio.run(_row(transaction_id))
        assert status == CollectionStatus.COMPLETED.value
        assert activation_status == ActivationStatus.ACTIVE.value
        assert activated_at == first_activated_at  # not re-stamped
        assert len(asyncio.run(_ledger_rows(tenant_id))) == 3

        # And it is no longer on the retry work list.
        async def _retryable() -> list[UUID]:
            async with AsyncSessionLocal() as db:
                return await CaptivePortalActivationService(db).list_retryable()

        assert transaction_id not in asyncio.run(_retryable())


def test_paid_but_unactivated_payment_is_on_the_retry_list() -> None:
    """Covers the process dying between the two transactions: activation
    was never attempted, so activation_status is PENDING and the sweep must
    still find it."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        ctx.new_commercial_terms(tenant_id=tenant_id, commission_rate_percent="10.00")
        transaction_id = asyncio.run(_seed_payable(tenant_id))
        asyncio.run(_finalize(transaction_id))

        async def _retryable() -> list[UUID]:
            async with AsyncSessionLocal() as db:
                return await CaptivePortalActivationService(db).list_retryable()

        assert transaction_id in asyncio.run(_retryable())


def test_credentials_are_withheld_until_access_is_actually_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A paid-but-not-activated customer must not be handed RADIUS
    credentials FreeRADIUS would reject."""
    from app.core.transaction_token import create_transaction_token

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        ctx.new_commercial_terms(tenant_id=tenant_id, commission_rate_percent="10.00")
        transaction_id = asyncio.run(_seed_payable(tenant_id))
        asyncio.run(_finalize(transaction_id))
        _break_radius(monkeypatch)
        asyncio.run(run_activation(transaction_id=transaction_id))

        token = create_transaction_token(transaction_id)

        async def _status() -> tuple[str, str | None]:
            async with AsyncSessionLocal() as db:
                result = await CaptivePortalService(db).get_payment_status(token=token)
                return result.status, result.login_password

        status, password = asyncio.run(_status())
        assert status == "completed"  # money is settled, and we say so
        assert password is None  # but access is not, so no credentials
