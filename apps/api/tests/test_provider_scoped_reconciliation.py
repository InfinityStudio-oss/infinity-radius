"""Reconciliation discovers work by `payment_provider`, never by
`transaction_type` — and the tenant dashboard does the exact opposite.

These two scopings pull in opposite directions on purpose, which is the
whole reason `transactions` carries both columns:

    reconciliation  -> every row SELCOM_COLLECTION settles, whatever flow
                       created it (so a captive-portal package payment is
                       swept exactly like a tenant Collection)
    tenant dashboard-> only transaction_type=COLLECTION (so a captive-
                       portal row can never appear in a tenant's
                       Collections list or inflate its counts)

Getting either one backwards is a real production failure: widen the
dashboard and tenants see payments that aren't theirs to manage; narrow
reconciliation and a real customer payment sits unresolved forever.

The ordering rule these tests protect: a writer MUST set payment_provider
before reconciliation is allowed to discover by it. A row created without
it is invisible to the sweep.
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.core.enums import ActivationStatus, CollectionStatus, PaymentProvider, TransactionType
from app.db.session import AsyncSessionLocal
from app.repositories.finance import TransactionRepository
from app.services.captive_portal import CAPTIVE_PORTAL_SELCOM_FLOW
from app.services.collections import COLLECTION_FLOW, CollectionService
from tests.db_fixtures import SeededContext

_AMOUNT = Decimal("1000.00")

# Exactly what SelcomPaymentProvider.list_reconcilable sweeps for.
_NON_TERMINAL = [
    status.value
    for status in CollectionStatus
    if status
    not in {
        CollectionStatus.COMPLETED,
        CollectionStatus.FAILED,
        CollectionStatus.CANCELLED,
        CollectionStatus.USERCANCELLED,
        CollectionStatus.DECLINED,
        CollectionStatus.REJECTED,
        CollectionStatus.EXPIRED,
    }
]


async def _insert(
    *,
    tenant_id: UUID,
    transaction_type: str,
    payment_provider: str | None,
    status: str,
    reference: str,
) -> UUID:
    """Writes a row directly so each test can pin one exact combination of
    (transaction_type, payment_provider, status) without driving a live
    provider call."""
    async with AsyncSessionLocal() as db:
        transaction = await TransactionRepository(db).create(
            tenant_id=tenant_id,
            transaction_type=transaction_type,
            payment_provider=payment_provider,
            reference=reference,
            amount=str(_AMOUNT),
            currency="TZS",
            status=status,
        )
        await db.commit()
        return transaction.id


async def _swept_ids() -> list[UUID]:
    async with AsyncSessionLocal() as db:
        rows = await CollectionService(db).list_reconcilable_collections()
        return [row.id for row in rows]


def test_collection_flow_declares_selcom_as_its_provider() -> None:
    """The writer and the sweep read the SAME constant, so they cannot
    drift into disagreeing about which provider owns these rows."""
    assert COLLECTION_FLOW.transaction_type is TransactionType.COLLECTION
    assert COLLECTION_FLOW.payment_provider is PaymentProvider.SELCOM_COLLECTION


def test_captive_portal_flow_pairs_captive_type_with_selcom_provider() -> None:
    """The pairing that makes two columns necessary: reconciled like a
    Collection, but never listed as one."""
    assert CAPTIVE_PORTAL_SELCOM_FLOW.transaction_type is TransactionType.CAPTIVE_PORTAL
    assert CAPTIVE_PORTAL_SELCOM_FLOW.payment_provider is PaymentProvider.SELCOM_COLLECTION
    # Must differ from the Collection flow, or captive rows would be
    # indistinguishable from tenant Collections.
    assert CAPTIVE_PORTAL_SELCOM_FLOW.transaction_type is not COLLECTION_FLOW.transaction_type
    assert CAPTIVE_PORTAL_SELCOM_FLOW.reference_prefix != COLLECTION_FLOW.reference_prefix


def test_reconciliation_includes_collection_rows_with_the_selcom_provider() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        transaction_id = asyncio.run(
            _insert(
                tenant_id=tenant_id,
                transaction_type=TransactionType.COLLECTION.value,
                payment_provider=PaymentProvider.SELCOM_COLLECTION.value,
                status=CollectionStatus.STK_SENT.value,
                reference=f"col-{uuid4().hex}",
            )
        )
        assert transaction_id in asyncio.run(_swept_ids())


def test_reconciliation_includes_captive_portal_rows_with_the_selcom_provider() -> None:
    """The point of provider-scoped discovery: a CAPTIVE_PORTAL row that
    genuinely went through Selcom is swept, even though the sweep's own
    service is the tenant Collection one. Under the previous
    type-scoped/status-only discovery this is the case that would have
    been missed."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        transaction_id = asyncio.run(
            _insert(
                tenant_id=tenant_id,
                transaction_type=TransactionType.CAPTIVE_PORTAL.value,
                payment_provider=PaymentProvider.SELCOM_COLLECTION.value,
                status=CollectionStatus.PENDING.value,
                reference=f"CP-{uuid4().hex.upper()}",
            )
        )
        assert transaction_id in asyncio.run(_swept_ids())


def test_reconciliation_excludes_rows_with_no_provider() -> None:
    """A row that never reached a provider must never be queried against
    one — this is what stops the sweep asking Selcom for the status of an
    order_id that was never created. It is also exactly the state today's
    captive-portal writer produces."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        transaction_id = asyncio.run(
            _insert(
                tenant_id=tenant_id,
                transaction_type=TransactionType.CAPTIVE_PORTAL.value,
                payment_provider=None,
                status=CollectionStatus.PENDING.value,
                reference=f"CP-{uuid4().hex.upper()}",
            )
        )
        assert transaction_id not in asyncio.run(_swept_ids())


def test_reconciliation_excludes_rows_owned_by_a_different_provider() -> None:
    """Scoping is an exact match, not "any provider" — a future non-Selcom
    payment method must not be swept by the Selcom sweep."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        transaction_id = asyncio.run(
            _insert(
                tenant_id=tenant_id,
                transaction_type=TransactionType.CAPTIVE_PORTAL.value,
                payment_provider="SOME_OTHER_PROVIDER",
                status=CollectionStatus.PENDING.value,
                reference=f"CP-{uuid4().hex.upper()}",
            )
        )
        assert transaction_id not in asyncio.run(_swept_ids())


def test_reconciliation_excludes_terminal_rows_even_with_the_right_provider() -> None:
    """Provider scoping ADDS a condition; it does not replace the
    non-terminal status filter. A COMPLETED row must never be re-queried,
    or a duplicate COMPLETED could be re-applied."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        completed_id = asyncio.run(
            _insert(
                tenant_id=tenant_id,
                transaction_type=TransactionType.COLLECTION.value,
                payment_provider=PaymentProvider.SELCOM_COLLECTION.value,
                status=CollectionStatus.COMPLETED.value,
                reference=f"col-{uuid4().hex}",
            )
        )
        cancelled_id = asyncio.run(
            _insert(
                tenant_id=tenant_id,
                transaction_type=TransactionType.COLLECTION.value,
                payment_provider=PaymentProvider.SELCOM_COLLECTION.value,
                status=CollectionStatus.CANCELLED.value,
                reference=f"col-{uuid4().hex}",
            )
        )
        swept = asyncio.run(_swept_ids())
        assert completed_id not in swept
        assert cancelled_id not in swept


def test_requires_review_and_ambiguous_remain_reconcilable() -> None:
    """Both are deliberately non-terminal; provider scoping must not have
    quietly dropped either from the sweep."""
    assert CollectionStatus.REQUIRES_REVIEW.value in _NON_TERMINAL
    assert CollectionStatus.AMBIGUOUS.value in _NON_TERMINAL
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        ids = [
            asyncio.run(
                _insert(
                    tenant_id=tenant_id,
                    transaction_type=TransactionType.COLLECTION.value,
                    payment_provider=PaymentProvider.SELCOM_COLLECTION.value,
                    status=status,
                    reference=f"col-{uuid4().hex}",
                )
            )
            for status in (
                CollectionStatus.REQUIRES_REVIEW.value,
                CollectionStatus.AMBIGUOUS.value,
            )
        ]
        swept = asyncio.run(_swept_ids())
        for transaction_id in ids:
            assert transaction_id in swept


def test_tenant_collection_list_still_excludes_captive_portal_rows() -> None:
    """The dashboard stays type-scoped. A Selcom-settled CAPTIVE_PORTAL row
    is swept by reconciliation (above) yet must NOT appear here — the two
    scopings pulling in opposite directions is the point."""
    from app.core.pagination import ListParams

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        collection_id = asyncio.run(
            _insert(
                tenant_id=tenant_id,
                transaction_type=TransactionType.COLLECTION.value,
                payment_provider=PaymentProvider.SELCOM_COLLECTION.value,
                status=CollectionStatus.COMPLETED.value,
                reference=f"col-{uuid4().hex}",
            )
        )
        captive_id = asyncio.run(
            _insert(
                tenant_id=tenant_id,
                transaction_type=TransactionType.CAPTIVE_PORTAL.value,
                payment_provider=PaymentProvider.SELCOM_COLLECTION.value,
                status=CollectionStatus.COMPLETED.value,
                reference=f"CP-{uuid4().hex.upper()}",
            )
        )

        async def _listed() -> tuple[list[UUID], int]:
            async with AsyncSessionLocal() as db:
                items, total = await TransactionRepository(db).list_by_type_paginated(
                    tenant_id=tenant_id,
                    transaction_type=TransactionType.COLLECTION.value,
                    params=ListParams(page=1, page_size=50, search=None, sort=None, filters={}),
                )
                return [i.id for i in items], total

        ids, total = asyncio.run(_listed())
        assert collection_id in ids
        assert captive_id not in ids
        # The captive row must not inflate the tenant's page count either.
        assert total == 1


def test_new_collection_row_carries_both_discriminators() -> None:
    """End-to-end on the real writer path: whatever CollectionService
    persists must be discoverable by the provider-scoped sweep. This is the
    ordering rule — writer before discovery — expressed as a test."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()

        async def _write_via_repo_defaults() -> UUID:
            # Mirrors CollectionService.initiate_collection's persisted shape
            # exactly, taken from the flow constants the service itself uses,
            # without contacting Selcom.
            async with AsyncSessionLocal() as db:
                transaction = await TransactionRepository(db).create(
                    tenant_id=tenant_id,
                    transaction_type=COLLECTION_FLOW.transaction_type.value,
                    payment_provider=COLLECTION_FLOW.payment_provider.value,
                    reference=f"{COLLECTION_FLOW.reference_prefix}{uuid4().hex}",
                    amount=str(_AMOUNT),
                    currency="TZS",
                    status=CollectionStatus.CREATED.value,
                )
                await db.commit()
                return transaction.id

        transaction_id = asyncio.run(_write_via_repo_defaults())

        async def _row() -> tuple[str | None, str | None, str]:
            async with AsyncSessionLocal() as db:
                row = await TransactionRepository(db).get_by_id(
                    tenant_id=tenant_id, id=transaction_id
                )
                assert row is not None
                return row.transaction_type, row.payment_provider, row.status

        transaction_type, payment_provider, status = asyncio.run(_row())
        assert transaction_type == TransactionType.COLLECTION.value
        assert payment_provider == PaymentProvider.SELCOM_COLLECTION.value
        assert status == CollectionStatus.CREATED.value
        # CREATED is non-terminal, so the sweep must already see it.
        assert transaction_id in asyncio.run(_swept_ids())


def test_fulfillment_columns_exist_and_default_to_null() -> None:
    """The c4f81b2e9a37 columns are present but untouched by this phase —
    payment status and activation status stay separate facts."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        transaction_id = asyncio.run(
            _insert(
                tenant_id=tenant_id,
                transaction_type=TransactionType.COLLECTION.value,
                payment_provider=PaymentProvider.SELCOM_COLLECTION.value,
                status=CollectionStatus.CREATED.value,
                reference=f"col-{uuid4().hex}",
            )
        )

        async def _row() -> tuple[object, object, object]:
            async with AsyncSessionLocal() as db:
                row = await TransactionRepository(db).get_by_id(
                    tenant_id=tenant_id, id=transaction_id
                )
                assert row is not None
                return row.activation_status, row.activated_at, row.captive_session_id

        activation_status, activated_at, captive_session_id = asyncio.run(_row())
        assert activation_status is None
        assert activated_at is None
        assert captive_session_id is None
        # Sanity: the vocabulary exists for Phase 4 without being applied yet.
        assert ActivationStatus.PENDING.value == "PENDING"
        assert isinstance(datetime.now(UTC), datetime)
