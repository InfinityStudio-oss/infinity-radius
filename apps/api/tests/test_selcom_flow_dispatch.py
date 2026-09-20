"""2026-09-20 production incident: a real CAPTIVE_PORTAL payment was
reconciled through CollectionService's own provider (COLLECTION_FLOW)
via POST /api/v1/internal/collections/reconcile. The wallet was credited
correctly — both flows' finalizers call the identical
WalletService.process_collection — but activation_status was never set,
because CollectionService's finalizer has no notion of activation at
all. Once the transaction reached its terminal COMPLETED status,
apply_order_status's own idempotency guard meant NO finalizer — correct
or otherwise — could ever run for it again. The payment was financially
safe and permanently stuck un-activated.

Root cause: reconciliation is intentionally discovered by
payment_provider, never by transaction_type (see
SelcomPaymentProvider.list_reconcilable), so the flow whose code happens
to receive a transaction_id or an inbound webhook's order_id is not
necessarily the flow that created it. Nothing verified that before
finalizing.

The fix is SelcomPaymentProvider._provider_for: every entry point that
can receive a transaction across flow boundaries (reconcile,
process_webhook) resolves the transaction's OWN flow first and dispatches
to that flow's provider, with apply_order_status carrying a hard,
directly-testable rejection as a backstop.

These tests reproduce the incident against each entry point and prove it
no longer happens, without ever calling Selcom.
"""

import asyncio
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.enums import ActivationStatus, CollectionStatus
from app.core.transaction_token import create_transaction_token
from app.db.session import AsyncSessionLocal
from app.integrations.selcom_collection.client import SelcomCollectionClient
from app.integrations.selcom_collection.schemas import (
    CreateOrderMinimalResponse,
    OrderStatusResponse,
    WalletPaymentResponse,
)
from app.main import app
from app.repositories.finance import TransactionRepository
from app.services.captive_portal import CaptivePortalService
from app.services.collections import CollectionService
from app.services.selcom_payment_provider import SelcomPaymentFlowMismatchError
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)

_AMOUNT = Decimal("1000")
_TEST_INTENT_KEY = "8ZQZ1yq8kJ1kZ9rN6Xk2mQ0pV7sT3wY5bA4cD6eF8gI="


@pytest.fixture(autouse=True)
def _intent_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CAPTIVE_INTENT_TOKEN_SIGNING_KEY", _TEST_INTENT_KEY)
    get_settings.cache_clear()
    import app.core.captive_intent_token as m

    m._fernet.cache_clear()
    yield
    get_settings.cache_clear()
    m._fernet.cache_clear()


@pytest.fixture
def selcom_env(monkeypatch: pytest.MonkeyPatch):
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
        return CreateOrderMinimalResponse(reference=str(kwargs["order_id"]), resultcode="000")

    monkeypatch.setattr(SelcomCollectionClient, "create_order_minimal", _fake)


def _fake_wallet_payment_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(self: SelcomCollectionClient, **kwargs: object) -> WalletPaymentResponse:
        return WalletPaymentResponse(reference=str(kwargs["order_id"]), resultcode="111")

    monkeypatch.setattr(SelcomCollectionClient, "wallet_payment", _fake)


def _fake_order_status_completed(monkeypatch: pytest.MonkeyPatch, *, order_id: str) -> None:
    async def _fake(self: SelcomCollectionClient, **kwargs: object) -> OrderStatusResponse:
        return OrderStatusResponse(
            reference=order_id,
            resultcode="000",
            data=[
                {
                    "order_id": order_id,
                    "transid": "DIK1TESTCHANNEL",
                    "amount": _AMOUNT,
                    "payment_status": "COMPLETED",
                    "channel": "MPESA",
                    "reference": "RCPT-DIK1TESTCHANNEL",
                }
            ],
        )

    monkeypatch.setattr(SelcomCollectionClient, "order_status", _fake)


def _seed_tenant(ctx: SeededContext, *, commission_rate: str = "0.00") -> tuple[UUID, UUID]:
    tenant_id = ctx.new_tenant()
    actor_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
    ctx.new_commercial_terms(tenant_id=tenant_id, commission_rate_percent=commission_rate)
    return tenant_id, actor_id


def _create_manual_collection_stk_sent(
    monkeypatch: pytest.MonkeyPatch, *, tenant_id: UUID, actor_id: UUID
) -> UUID:
    _fake_create_order_success(monkeypatch)
    _fake_wallet_payment_success(monkeypatch)

    async def _initiate() -> UUID:
        async with AsyncSessionLocal() as db:
            transaction = await CollectionService(db).initiate_collection(
                tenant_id=tenant_id, actor_id=actor_id, amount=_AMOUNT, currency="TZS",
                phone="0712345678",
            )
            await db.commit()
            return transaction.id

    return asyncio.run(_initiate())


def _create_captive_stk_sent(
    monkeypatch: pytest.MonkeyPatch, headers: dict[str, str], *, phone: str = "0712345679"
) -> UUID:
    _fake_create_order_success(monkeypatch)
    _fake_wallet_payment_success(monkeypatch)

    router_id = client.post(
        "/api/v1/routers", headers=headers, json={"name": "Dispatch Test Router"}
    ).json()["data"]["id"]
    package_id = client.post(
        "/api/v1/packages",
        headers=headers,
        json={"name": "Dispatch Test Package", "price_tzs": "1000", "status": "active"},
    ).json()["data"]["id"]
    router_token = client.get(
        f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
    ).json()["data"]["router_token"]
    intent = client.post(
        "/api/v1/public/captive-portal/session", json={"router": router_token}
    ).json()["intent_token"]
    initiate = client.post(
        "/api/v1/public/captive-portal/payments/initiate",
        json={"intent_token": intent, "package_id": package_id, "phone": phone},
    )
    from app.core.transaction_token import resolve_transaction_token

    transaction_id = resolve_transaction_token(initiate.json()["transaction_token"])
    assert transaction_id is not None
    return transaction_id


async def _row(transaction_id: UUID) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        t = await TransactionRepository(db).get_by_id(tenant_id=None, id=transaction_id)
        assert t is not None
        return {
            "transaction_type": t.transaction_type,
            "status": t.status,
            "activation_status": t.activation_status,
        }


async def _ledger_rows(tenant_id: UUID) -> list[tuple[str, str]]:
    from sqlalchemy import select

    from app.models.finance import LedgerEntry

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(LedgerEntry.entry_type, LedgerEntry.description).where(
                LedgerEntry.tenant_id == tenant_id
            )
        )
        return [(r[0], r[1]) for r in result.all()]


# ---------------------------------------------------------- reconcile()


def test_collection_reconcile_dispatches_a_captive_transaction_to_the_captive_finalizer(
    selcom_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact incident: CollectionService.reconcile() called on a
    CAPTIVE_PORTAL transaction_id. It must now dispatch to
    CaptivePortalService's own finalizer — proven by activation_status
    being set, which only that finalizer ever does — not silently credit
    the wallet as a plain Collection."""
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        headers = auth_header(user_id=actor_id)
        transaction_id = _create_captive_stk_sent(monkeypatch, headers, phone="0755910001")

        async def _row_ref() -> str:
            async with AsyncSessionLocal() as db:
                t = await TransactionRepository(db).get_by_id(tenant_id=None, id=transaction_id)
                assert t is not None
                return t.reference

        reference = asyncio.run(_row_ref())
        _fake_order_status_completed(monkeypatch, order_id=reference)

        async def _reconcile() -> None:
            async with AsyncSessionLocal() as db:
                # The exact call the incident made: the Collection-scoped
                # service, on a captive-portal transaction id.
                await CollectionService(db).reconcile(transaction_id=transaction_id)
                await db.commit()

        asyncio.run(_reconcile())

        row = asyncio.run(_row(transaction_id))
        ledger = asyncio.run(_ledger_rows(tenant_id))

    assert row["transaction_type"] == "CAPTIVE_PORTAL"  # never rewritten
    assert row["status"] == "COMPLETED"
    # THE bug: this was None after the incident. The captive finalizer is
    # the only code that ever sets it.
    assert row["activation_status"] == ActivationStatus.PENDING.value
    assert len(ledger) == 3
    # The captive finalizer's own description format, not Collection's
    # "Selcom Collection {reference}".
    assert any("Captive portal payment" in desc for _, desc in ledger)


def test_captive_reconcile_dispatches_a_collection_transaction_to_the_collection_finalizer(
    selcom_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reverse direction: CaptivePortalService.reconcile() called on
    a manual Collection transaction_id must dispatch to CollectionService's
    finalizer, never set activation_status on a row that was never a
    captive purchase."""
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        transaction_id = _create_manual_collection_stk_sent(
            monkeypatch, tenant_id=tenant_id, actor_id=actor_id
        )

        async def _row_ref() -> str:
            async with AsyncSessionLocal() as db:
                t = await TransactionRepository(db).get_by_id(tenant_id=None, id=transaction_id)
                assert t is not None
                return t.reference

        reference = asyncio.run(_row_ref())
        _fake_order_status_completed(monkeypatch, order_id=reference)

        async def _reconcile() -> None:
            async with AsyncSessionLocal() as db:
                await CaptivePortalService(db).reconcile(transaction_id=transaction_id)
                await db.commit()

        asyncio.run(_reconcile())

        row = asyncio.run(_row(transaction_id))
        ledger = asyncio.run(_ledger_rows(tenant_id))

    assert row["transaction_type"] == "COLLECTION"
    assert row["status"] == "COMPLETED"
    # activation_status has no meaning for a manual Collection row — the
    # captive finalizer must never have touched it.
    assert row["activation_status"] is None
    assert len(ledger) == 3
    assert any("Selcom Collection" in desc for _, desc in ledger)


def test_duplicate_completed_via_cross_dispatch_does_not_double_credit(
    selcom_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Idempotency must survive the fix: reconciling an already-terminal
    captive transaction through the Collection-scoped entry point again
    must add nothing."""
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        headers = auth_header(user_id=actor_id)
        transaction_id = _create_captive_stk_sent(monkeypatch, headers, phone="0755910002")

        async def _row_ref() -> str:
            async with AsyncSessionLocal() as db:
                t = await TransactionRepository(db).get_by_id(tenant_id=None, id=transaction_id)
                assert t is not None
                return t.reference

        reference = asyncio.run(_row_ref())
        _fake_order_status_completed(monkeypatch, order_id=reference)

        async def _reconcile() -> None:
            async with AsyncSessionLocal() as db:
                await CollectionService(db).reconcile(transaction_id=transaction_id)
                await db.commit()

        asyncio.run(_reconcile())
        asyncio.run(_reconcile())
        asyncio.run(_reconcile())

        ledger = asyncio.run(_ledger_rows(tenant_id))

    assert len(ledger) == 3  # not 9


# --------------------------------------------------- apply_order_status


def test_apply_order_status_rejects_a_flow_mismatch_directly() -> None:
    """The hard backstop, exercised without going through reconcile()'s
    dispatch at all — proves the guard itself works even if some future
    caller bypasses _provider_for."""
    from app.services.collections import COLLECTION_FLOW
    from app.services.selcom_payment_provider import SelcomPaymentProvider

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)

        async def _make_captive_row() -> Any:
            async with AsyncSessionLocal() as db:
                transaction = await TransactionRepository(db).create(
                    tenant_id=tenant_id,
                    transaction_type="CAPTIVE_PORTAL",
                    payment_provider="SELCOM_COLLECTION",
                    reference="CP-mismatchtest",
                    amount=str(_AMOUNT),
                    currency="TZS",
                    status=CollectionStatus.STK_SENT.value,
                )
                await db.commit()
                return transaction

        transaction = asyncio.run(_make_captive_row())

        async def _apply() -> None:
            async with AsyncSessionLocal() as db:
                # COLLECTION_FLOW's provider, called directly (bypassing
                # reconcile()'s dispatch) on a CAPTIVE_PORTAL row.
                async def _never_called(*_a: object, **_kw: object) -> None:
                    raise AssertionError("finalizer must never run on a flow mismatch")

                provider = SelcomPaymentProvider(
                    db, flow=COLLECTION_FLOW, finalize_payment=_never_called
                )
                t = await TransactionRepository(db).get_by_id_for_update(
                    tenant_id=None, id=transaction.id
                )
                assert t is not None
                from app.integrations.selcom_collection.schemas import OrderStatusData

                with pytest.raises(SelcomPaymentFlowMismatchError):
                    await provider.apply_order_status(
                        t,
                        status_data=OrderStatusData(
                            order_id=t.reference,
                            amount=_AMOUNT,
                            payment_status="COMPLETED",
                            transid="x",
                            channel="MPESA",
                            reference="y",
                        ),
                        actor_id=None,
                    )

        asyncio.run(_apply())

        row = asyncio.run(_row(transaction.id))
    # Rejected before any transition — status untouched.
    assert row["status"] == "STK_SENT"


# -------------------------------------------------------------- webhook


def test_webhook_dispatches_a_captive_order_to_the_captive_finalizer(
    selcom_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The webhook route always constructs CollectionService first (see
    app/api/v1/webhooks.py) — that must no longer determine which
    finalizer actually runs. A captive order_id arriving on the shared
    webhook must still set activation_status."""
    from collections import OrderedDict

    from app.integrations.selcom_collection.signing import sign_request

    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        headers = auth_header(user_id=actor_id)
        transaction_id = _create_captive_stk_sent(monkeypatch, headers, phone="0755910003")

        async def _row_ref_and_transid() -> tuple[str, str]:
            async with AsyncSessionLocal() as db:
                t = await TransactionRepository(db).get_by_id(tenant_id=None, id=transaction_id)
                assert t is not None
                assert t.collection_transid is not None
                return t.reference, t.collection_transid

        reference, transid = asyncio.run(_row_ref_and_transid())
        _fake_order_status_completed(monkeypatch, order_id=reference)

        signed_fields: OrderedDict[str, str] = OrderedDict(
            [
                ("transid", transid),
                ("order_id", reference),
                ("reference", f"RCPT-{transid}"),
                ("result", "SUCCESS"),
                ("resultcode", "000"),
                ("payment_status", "COMPLETED"),
            ]
        )
        signed = sign_request(
            api_key="test-collection-key-never-real",
            digest_method="HS256",
            api_secret="test-collection-secret-never-real",
            private_key_pem=None,
            fields=signed_fields,
        )
        body = dict(signed_fields)
        body["channel"] = "MPESA"
        body["amount"] = "1000"
        body["phone"] = "255712345679"

        response = client.post(
            "/api/v1/webhooks/selcom-collection/checkout",
            json=body,
            headers=signed.as_dict(),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "acknowledged"

        row = asyncio.run(_row(transaction_id))
        ledger = asyncio.run(_ledger_rows(tenant_id))

    assert row["status"] == "COMPLETED"
    assert row["activation_status"] == ActivationStatus.PENDING.value
    assert len(ledger) == 3
    assert any("Captive portal payment" in desc for _, desc in ledger)


def test_transaction_token_unaffected_by_dispatch_fix(
    selcom_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sanity: the public status token created at initiation still
    resolves correctly after a cross-flow-safe reconcile."""
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        headers = auth_header(user_id=actor_id)
        transaction_id = _create_captive_stk_sent(monkeypatch, headers, phone="0755910004")
        token = create_transaction_token(transaction_id)

        async def _row_ref() -> str:
            async with AsyncSessionLocal() as db:
                t = await TransactionRepository(db).get_by_id(tenant_id=None, id=transaction_id)
                assert t is not None
                return t.reference

        reference = asyncio.run(_row_ref())
        _fake_order_status_completed(monkeypatch, order_id=reference)

        async def _reconcile() -> None:
            async with AsyncSessionLocal() as db:
                await CollectionService(db).reconcile(transaction_id=transaction_id)
                await db.commit()

        asyncio.run(_reconcile())

        status = client.get(
            "/api/v1/public/captive-portal/payments/status", params={"token": token}
        ).json()

    assert status["status"] == "completed"
