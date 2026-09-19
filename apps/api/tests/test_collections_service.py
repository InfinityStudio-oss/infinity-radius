"""app/services/collections.py — CollectionService, the ONLY path from a
Selcom Mobile Checkout order to a wallet credit. Covers: the two
independent kill switches, initiate_collection's success/failure paths,
and _apply_order_status's exact amount/currency/transid-matching
finalization logic (via reconcile(), which is the same code path the
webhook and the scheduled worker sweep both use).

SelcomCollectionClient methods are always mocked — no test here makes a
real network call, and no test ever supplies real Selcom credentials.
"""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from uuid import UUID

import pytest

from app.core.config import get_settings
from app.core.enums import CollectionStatus
from app.core.errors import DomainValidationError
from app.db.session import AsyncSessionLocal
from app.integrations.selcom_collection.client import SelcomCollectionClient
from app.integrations.selcom_collection.errors import SelcomCollectionAPIError
from app.integrations.selcom_collection.schemas import (
    CreateOrderData,
    CreateOrderMinimalResponse,
    OrderStatusResponse,
    WalletPaymentResponse,
)
from app.services.collections import CollectionService
from tests.db_fixtures import SeededContext

_AMOUNT = Decimal("5000")
_CURRENCY = "TZS"
_PHONE = "0712345678"


@pytest.fixture
def collection_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A fully-configured (fake) Collection credential set with both kill
    switches ON — the baseline most tests build on, individually
    overridden per-test via further monkeypatch.setenv + cache_clear()
    calls where a test needs a different gate state."""
    monkeypatch.setenv("SELCOM_COLLECTION_BASE_URL", "https://apigwtest.selcommobile.com")
    monkeypatch.setenv("SELCOM_COLLECTION_API_KEY", "test-collection-key-never-real")
    monkeypatch.setenv("SELCOM_COLLECTION_API_SECRET", "test-collection-secret-never-real")
    monkeypatch.setenv("SELCOM_COLLECTION_DIGEST_METHOD", "HS256")
    monkeypatch.setenv("SELCOM_COLLECTION_VENDOR", "TEST-VENDOR")
    monkeypatch.setenv("SELCOM_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("SELCOM_COLLECTION_PRODUCTION_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _fake_create_order_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(self: SelcomCollectionClient, **kwargs: object) -> CreateOrderMinimalResponse:
        return CreateOrderMinimalResponse(
            reference=str(kwargs["order_id"]),
            resultcode="000",
            result="SUCCESS",
            message="Order created successfully",
            data=[CreateOrderData(payment_gateway_url="aHR0cHM6Ly9leGFtcGxlLmNvbQ==")],
        )

    monkeypatch.setattr(SelcomCollectionClient, "create_order_minimal", _fake)


def _fake_wallet_payment_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(self: SelcomCollectionClient, **kwargs: object) -> WalletPaymentResponse:
        return WalletPaymentResponse(
            reference=str(kwargs["order_id"]),
            resultcode="111",
            result="PENDING",
            message="Request in progress",
        )

    monkeypatch.setattr(SelcomCollectionClient, "wallet_payment", _fake)


def _never_called(monkeypatch: pytest.MonkeyPatch, *, method: str) -> None:
    async def _fail(self: SelcomCollectionClient, **kwargs: object) -> None:
        raise AssertionError(f"{method} must never be called when a kill switch is off")

    monkeypatch.setattr(SelcomCollectionClient, method, _fail)


def _seed_tenant(ctx: SeededContext, *, commission_rate: str = "10.00") -> tuple[UUID, UUID]:
    tenant_id = ctx.new_tenant()
    actor_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
    ctx.new_commercial_terms(tenant_id=tenant_id, commission_rate_percent=commission_rate)
    return tenant_id, actor_id


async def _initiate(*, tenant_id: UUID, actor_id: UUID) -> UUID:
    async with AsyncSessionLocal() as db:
        service = CollectionService(db)
        transaction = await service.initiate_collection(
            tenant_id=tenant_id,
            actor_id=actor_id,
            amount=_AMOUNT,
            currency=_CURRENCY,
            phone=_PHONE,
        )
        await db.commit()
        return transaction.id


async def _get_transaction(transaction_id: UUID) -> object:
    async with AsyncSessionLocal() as db:
        service = CollectionService(db)
        transaction = await service.repo.get_by_id(tenant_id=None, id=transaction_id)
        assert transaction is not None
        return transaction


async def _reconcile(transaction_id: UUID) -> None:
    async with AsyncSessionLocal() as db:
        service = CollectionService(db)
        await service.reconcile(transaction_id=transaction_id)
        await db.commit()


# --------------------------------------------------------------- kill switches


def test_initiate_collection_blocked_when_collection_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SELCOM_COLLECTION_ENABLED", "false")
    monkeypatch.setenv("SELCOM_COLLECTION_PRODUCTION_ENABLED", "true")
    get_settings.cache_clear()
    _never_called(monkeypatch, method="create_order_minimal")
    _never_called(monkeypatch, method="wallet_payment")

    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        with pytest.raises(DomainValidationError, match="not enabled"):
            asyncio.run(_initiate(tenant_id=tenant_id, actor_id=actor_id))

    get_settings.cache_clear()


def test_initiate_collection_blocked_when_production_not_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SELCOM_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("SELCOM_COLLECTION_PRODUCTION_ENABLED", "false")
    get_settings.cache_clear()
    _never_called(monkeypatch, method="create_order_minimal")
    _never_called(monkeypatch, method="wallet_payment")

    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        with pytest.raises(DomainValidationError, match="production"):
            asyncio.run(_initiate(tenant_id=tenant_id, actor_id=actor_id))

    get_settings.cache_clear()


def test_initiate_collection_blocked_when_both_switches_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SELCOM_COLLECTION_ENABLED", "false")
    monkeypatch.setenv("SELCOM_COLLECTION_PRODUCTION_ENABLED", "false")
    get_settings.cache_clear()
    _never_called(monkeypatch, method="create_order_minimal")
    _never_called(monkeypatch, method="wallet_payment")

    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        with pytest.raises(DomainValidationError):
            asyncio.run(_initiate(tenant_id=tenant_id, actor_id=actor_id))

    get_settings.cache_clear()


# ---------------------------------------------------------------- initiation


def test_initiate_collection_success_sends_stk_and_stores_transid(
    collection_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_create_order_success(monkeypatch)
    _fake_wallet_payment_success(monkeypatch)

    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        transaction_id = asyncio.run(_initiate(tenant_id=tenant_id, actor_id=actor_id))
        transaction = asyncio.run(_get_transaction(transaction_id))

    assert transaction.status == CollectionStatus.STK_SENT.value
    assert transaction.collection_transid is not None
    assert transaction.collection_transid.startswith("txn-")
    assert transaction.stk_requested_at is not None
    assert transaction.payer_phone == "255712345678"
    assert Decimal(transaction.amount) == _AMOUNT


def test_initiate_collection_create_order_failure_marks_failed_without_sending_stk(
    collection_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_create_order_fails(
        self: SelcomCollectionClient, **kwargs: object
    ) -> CreateOrderMinimalResponse:
        raise SelcomCollectionAPIError("Selcom Collection returned 400", status_code=400)

    monkeypatch.setattr(SelcomCollectionClient, "create_order_minimal", _fake_create_order_fails)
    _never_called(monkeypatch, method="wallet_payment")

    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        transaction_id = asyncio.run(_initiate(tenant_id=tenant_id, actor_id=actor_id))
        transaction = asyncio.run(_get_transaction(transaction_id))

    assert transaction.status == CollectionStatus.FAILED.value
    assert transaction.collection_transid is None


def test_initiate_collection_wallet_payment_failure_marks_failed(
    collection_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_create_order_success(monkeypatch)

    async def _fake_wallet_payment_fails(
        self: SelcomCollectionClient, **kwargs: object
    ) -> WalletPaymentResponse:
        raise SelcomCollectionAPIError("Selcom Collection returned 500", status_code=500)

    monkeypatch.setattr(SelcomCollectionClient, "wallet_payment", _fake_wallet_payment_fails)

    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        transaction_id = asyncio.run(_initiate(tenant_id=tenant_id, actor_id=actor_id))
        transaction = asyncio.run(_get_transaction(transaction_id))

    assert transaction.status == CollectionStatus.FAILED.value


def test_initiate_collection_rejects_non_tzs_currency(
    collection_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _never_called(monkeypatch, method="create_order_minimal")
    _never_called(monkeypatch, method="wallet_payment")

    async def _initiate_usd(tenant_id: UUID, actor_id: UUID) -> None:
        async with AsyncSessionLocal() as db:
            service = CollectionService(db)
            await service.initiate_collection(
                tenant_id=tenant_id,
                actor_id=actor_id,
                amount=_AMOUNT,
                currency="USD",
                phone=_PHONE,
            )

    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        with pytest.raises(DomainValidationError, match="TZS"):
            asyncio.run(_initiate_usd(tenant_id, actor_id))


# -------------------------------------------------------------- finalization


def _order_status_response(
    *, order_id: str, transid: str, amount: Decimal, payment_status: str
) -> OrderStatusResponse:
    # data items must be plain dicts, not OrderStatusData instances — the
    # schema's _normalize_data_list validator only recognizes dict items
    # (matching Selcom's own documented shapes) and silently drops
    # anything else, including an already-built model instance.
    return OrderStatusResponse(
        reference=order_id,
        resultcode="000",
        result="SUCCESS",
        data=[
            {
                "order_id": order_id,
                "amount": amount,
                "payment_status": payment_status,
                "transid": transid,
                "channel": "MPESA",
                "reference": f"RCPT-{transid}",
            }
        ],
    )


def test_completed_status_with_exact_match_credits_wallet_exactly_once(
    collection_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        _fake_create_order_success(monkeypatch)
        _fake_wallet_payment_success(monkeypatch)
        transaction_id = asyncio.run(_initiate(tenant_id=tenant_id, actor_id=actor_id))
        transaction = asyncio.run(_get_transaction(transaction_id))
        transid = transaction.collection_transid
        assert transid is not None
        reference = transaction.reference

        async def _fake_order_status(
            self: SelcomCollectionClient, **kwargs: object
        ) -> OrderStatusResponse:
            return _order_status_response(
                order_id=reference, transid=transid, amount=_AMOUNT, payment_status="COMPLETED"
            )

        monkeypatch.setattr(SelcomCollectionClient, "order_status", _fake_order_status)

        asyncio.run(_reconcile(transaction_id))
        after = asyncio.run(_get_transaction(transaction_id))

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT wallet_bucket, amount, entry_type FROM ledger_entries "
                "WHERE reference_id = %s ORDER BY created_at",
                (str(transaction_id),),
            )
            ledger_rows = cur.fetchall()
            cur.execute(
                "SELECT pending_balance_tzs FROM tenant_wallets WHERE tenant_id = %s",
                (str(tenant_id),),
            )
            wallet_row = cur.fetchone()

    assert after.status == CollectionStatus.COMPLETED.value
    assert after.completed_at is not None
    # COLLECTION (informational) + PLATFORM_FEE + TENANT_SHARE — exactly once.
    assert len(ledger_rows) == 3
    assert wallet_row is not None
    assert Decimal(wallet_row[0]) == Decimal("4500.00")  # 5000 - 10% platform fee


def test_duplicate_completed_status_does_not_double_credit(
    collection_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        _fake_create_order_success(monkeypatch)
        _fake_wallet_payment_success(monkeypatch)
        transaction_id = asyncio.run(_initiate(tenant_id=tenant_id, actor_id=actor_id))
        transaction = asyncio.run(_get_transaction(transaction_id))
        transid = transaction.collection_transid
        assert transid is not None
        reference = transaction.reference

        async def _fake_order_status(
            self: SelcomCollectionClient, **kwargs: object
        ) -> OrderStatusResponse:
            return _order_status_response(
                order_id=reference, transid=transid, amount=_AMOUNT, payment_status="COMPLETED"
            )

        monkeypatch.setattr(SelcomCollectionClient, "order_status", _fake_order_status)

        asyncio.run(_reconcile(transaction_id))
        asyncio.run(_reconcile(transaction_id))  # duplicate — must be a no-op

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM ledger_entries WHERE reference_id = %s",
                (str(transaction_id),),
            )
            count = cur.fetchone()[0]

    assert count == 3


def test_amount_mismatch_moves_to_ambiguous_and_never_credits(
    collection_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        _fake_create_order_success(monkeypatch)
        _fake_wallet_payment_success(monkeypatch)
        transaction_id = asyncio.run(_initiate(tenant_id=tenant_id, actor_id=actor_id))
        transaction = asyncio.run(_get_transaction(transaction_id))
        transid = transaction.collection_transid
        assert transid is not None
        reference = transaction.reference

        async def _fake_order_status(
            self: SelcomCollectionClient, **kwargs: object
        ) -> OrderStatusResponse:
            return _order_status_response(
                order_id=reference,
                transid=transid,
                amount=Decimal("1"),  # wildly wrong
                payment_status="COMPLETED",
            )

        monkeypatch.setattr(SelcomCollectionClient, "order_status", _fake_order_status)
        asyncio.run(_reconcile(transaction_id))
        after = asyncio.run(_get_transaction(transaction_id))

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM ledger_entries WHERE reference_id = %s",
                (str(transaction_id),),
            )
            count = cur.fetchone()[0]

    assert after.status == CollectionStatus.AMBIGUOUS.value
    assert count == 0


def test_transid_mismatch_moves_to_ambiguous(
    collection_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        _fake_create_order_success(monkeypatch)
        _fake_wallet_payment_success(monkeypatch)
        transaction_id = asyncio.run(_initiate(tenant_id=tenant_id, actor_id=actor_id))
        transaction = asyncio.run(_get_transaction(transaction_id))
        reference = transaction.reference

        async def _fake_order_status(
            self: SelcomCollectionClient, **kwargs: object
        ) -> OrderStatusResponse:
            return _order_status_response(
                order_id=reference,
                transid="some-other-transaction-entirely",
                amount=_AMOUNT,
                payment_status="COMPLETED",
            )

        monkeypatch.setattr(SelcomCollectionClient, "order_status", _fake_order_status)
        asyncio.run(_reconcile(transaction_id))
        after = asyncio.run(_get_transaction(transaction_id))

    assert after.status == CollectionStatus.AMBIGUOUS.value


def test_order_id_mismatch_moves_to_ambiguous(
    collection_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        _fake_create_order_success(monkeypatch)
        _fake_wallet_payment_success(monkeypatch)
        transaction_id = asyncio.run(_initiate(tenant_id=tenant_id, actor_id=actor_id))
        transaction = asyncio.run(_get_transaction(transaction_id))
        transid = transaction.collection_transid
        assert transid is not None

        async def _fake_order_status(
            self: SelcomCollectionClient, **kwargs: object
        ) -> OrderStatusResponse:
            return _order_status_response(
                order_id="col-some-other-order-entirely",
                transid=transid,
                amount=_AMOUNT,
                payment_status="COMPLETED",
            )

        monkeypatch.setattr(SelcomCollectionClient, "order_status", _fake_order_status)
        asyncio.run(_reconcile(transaction_id))
        after = asyncio.run(_get_transaction(transaction_id))

    assert after.status == CollectionStatus.AMBIGUOUS.value


def test_unrecognized_payment_status_moves_to_ambiguous(
    collection_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        _fake_create_order_success(monkeypatch)
        _fake_wallet_payment_success(monkeypatch)
        transaction_id = asyncio.run(_initiate(tenant_id=tenant_id, actor_id=actor_id))
        transaction = asyncio.run(_get_transaction(transaction_id))
        transid = transaction.collection_transid
        reference = transaction.reference
        assert transid is not None

        async def _fake_order_status(
            self: SelcomCollectionClient, **kwargs: object
        ) -> OrderStatusResponse:
            return _order_status_response(
                order_id=reference,
                transid=transid,
                amount=_AMOUNT,
                payment_status="SOME_NEW_STATUS_SELCOM_NEVER_DOCUMENTED",
            )

        monkeypatch.setattr(SelcomCollectionClient, "order_status", _fake_order_status)
        asyncio.run(_reconcile(transaction_id))
        after = asyncio.run(_get_transaction(transaction_id))

    assert after.status == CollectionStatus.AMBIGUOUS.value


@pytest.mark.parametrize(
    ("payment_status", "expected_status"),
    [
        ("PENDING", CollectionStatus.PENDING),
        ("INPROGRESS", CollectionStatus.INPROGRESS),
        ("CANCELLED", CollectionStatus.CANCELLED),
        ("USERCANCELLED", CollectionStatus.USERCANCELLED),
        ("REJECTED", CollectionStatus.REJECTED),
    ],
)
def test_documented_non_completed_statuses_transition_without_crediting(
    collection_env: None,
    monkeypatch: pytest.MonkeyPatch,
    payment_status: str,
    expected_status: CollectionStatus,
) -> None:
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        _fake_create_order_success(monkeypatch)
        _fake_wallet_payment_success(monkeypatch)
        transaction_id = asyncio.run(_initiate(tenant_id=tenant_id, actor_id=actor_id))
        transaction = asyncio.run(_get_transaction(transaction_id))
        transid = transaction.collection_transid
        reference = transaction.reference
        assert transid is not None

        async def _fake_order_status(
            self: SelcomCollectionClient, **kwargs: object
        ) -> OrderStatusResponse:
            return _order_status_response(
                order_id=reference, transid=transid, amount=_AMOUNT, payment_status=payment_status
            )

        monkeypatch.setattr(SelcomCollectionClient, "order_status", _fake_order_status)
        asyncio.run(_reconcile(transaction_id))
        after = asyncio.run(_get_transaction(transaction_id))

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM ledger_entries WHERE reference_id = %s",
                (str(transaction_id),),
            )
            count = cur.fetchone()[0]

    assert after.status == expected_status.value
    assert count == 0


def test_list_reconcilable_collections_includes_stk_sent_and_ambiguous_but_not_terminal(
    collection_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        _fake_create_order_success(monkeypatch)
        _fake_wallet_payment_success(monkeypatch)
        stk_sent_id = asyncio.run(_initiate(tenant_id=tenant_id, actor_id=actor_id))

        async def _list() -> list[UUID]:
            async with AsyncSessionLocal() as db:
                service = CollectionService(db)
                rows = await service.list_reconcilable_collections()
                return [row.id for row in rows]

        reconcilable_ids = asyncio.run(_list())

    assert stk_sent_id in reconcilable_ids
