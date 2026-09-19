"""POST /api/v1/webhooks/selcom-collection/checkout — Selcom Mobile
Checkout's Collection callback. Unlike the legacy captive-portal webhook
(tests/test_selcom_webhook.py) and the Business Disbursement webhook
(unsigned per Selcom's own docs), this one DOES carry a real
Authorization/Digest-Method/Digest/Timestamp/Signed-Fields signature — so
these tests build genuinely valid signed requests (using the same
sign_request the real client would use) rather than monkeypatching
verification away.

The webhook is always only a SIGNAL: even a validly-signed COMPLETED
claim must trigger an authenticated order-status query (mocked here)
before anything is credited — the webhook body's own amount/channel/
phone are never trusted directly.
"""

import asyncio
from collections import OrderedDict
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.enums import CollectionStatus
from app.db.session import AsyncSessionLocal
from app.integrations.selcom_collection.client import SelcomCollectionClient
from app.integrations.selcom_collection.schemas import (
    CreateOrderMinimalResponse,
    WalletPaymentResponse,
)
from app.integrations.selcom_collection.signing import sign_request
from app.main import app
from app.services.collections import CollectionService
from tests.db_fixtures import SeededContext

client = TestClient(app)

_API_KEY = "test-collection-key-never-real"
_API_SECRET = "test-collection-secret-never-real"
_AMOUNT = Decimal("5000")
_PHONE = "0712345678"


@pytest.fixture
def collection_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("SELCOM_COLLECTION_BASE_URL", "https://apigwtest.selcommobile.com")
    monkeypatch.setenv("SELCOM_COLLECTION_API_KEY", _API_KEY)
    monkeypatch.setenv("SELCOM_COLLECTION_API_SECRET", _API_SECRET)
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


def _seed_tenant(ctx: SeededContext, *, commission_rate: str = "10.00") -> tuple[UUID, UUID]:
    tenant_id = ctx.new_tenant()
    actor_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
    ctx.new_commercial_terms(tenant_id=tenant_id, commission_rate_percent=commission_rate)
    return tenant_id, actor_id


def _create_stk_sent_transaction(
    monkeypatch: pytest.MonkeyPatch, *, tenant_id: UUID, actor_id: UUID
) -> tuple[UUID, str, str]:
    """Returns (transaction_id, reference, transid) for a real STK_SENT row."""
    _fake_create_order_success(monkeypatch)
    _fake_wallet_payment_success(monkeypatch)

    async def _initiate() -> tuple[UUID, str, str]:
        async with AsyncSessionLocal() as db:
            service = CollectionService(db)
            transaction = await service.initiate_collection(
                tenant_id=tenant_id, actor_id=actor_id, amount=_AMOUNT, currency="TZS", phone=_PHONE
            )
            await db.commit()
            assert transaction.collection_transid is not None
            return transaction.id, transaction.reference, transaction.collection_transid

    return asyncio.run(_initiate())


def _signed_webhook_request(
    *, order_id: str, transid: str, result: str, resultcode: str, payment_status: str
) -> tuple[dict[str, str], dict[str, str]]:
    """Signs exactly the fields Selcom's docs list as ever part of
    Signed-Fields for the webhook callback (transid/order_id/reference/
    result/resultcode/payment_status) — channel/amount/phone are
    deliberately left unsigned, matching schemas.WebhookPayload's
    docstring."""
    signed_fields: OrderedDict[str, str] = OrderedDict(
        [
            ("transid", transid),
            ("order_id", order_id),
            ("reference", f"RCPT-{transid}"),
            ("result", result),
            ("resultcode", resultcode),
            ("payment_status", payment_status),
        ]
    )
    signed = sign_request(
        api_key=_API_KEY,
        digest_method="HS256",
        api_secret=_API_SECRET,
        private_key_pem=None,
        fields=signed_fields,
    )
    body: dict[str, str] = dict(signed_fields)
    # Unsigned context-only fields, present in the body but not signed.
    body["channel"] = "MPESA"
    body["amount"] = "5000"
    body["phone"] = "255712345678"
    return signed.as_dict(), body


def _fake_order_status_completed(order_id: str, transid: str, amount: Decimal) -> Any:
    async def _fake(self: SelcomCollectionClient, **kwargs: object) -> Any:
        from app.integrations.selcom_collection.schemas import OrderStatusResponse

        return OrderStatusResponse(
            reference=order_id,
            resultcode="000",
            data=[
                {
                    "order_id": order_id,
                    "transid": transid,
                    "amount": amount,
                    "payment_status": "COMPLETED",
                    "channel": "MPESA",
                    "reference": f"RCPT-{transid}",
                }
            ],
        )

    return _fake


# ------------------------------------------------------- reachability check


def test_reachability_check_get_returns_ok() -> None:
    response = client.get("/api/v1/webhooks/selcom-collection/checkout")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_reachability_check_head_returns_ok() -> None:
    response = client.head("/api/v1/webhooks/selcom-collection/checkout")
    assert response.status_code == 200


# --------------------------------------------------------- signature checks


def test_webhook_with_no_signature_headers_is_rejected(collection_env: None) -> None:
    response = client.post(
        "/api/v1/webhooks/selcom-collection/checkout",
        json={"order_id": "col-doesnotexist", "payment_status": "COMPLETED"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "rejected"}


def test_webhook_with_tampered_digest_is_rejected(
    collection_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        transaction_id, reference, transid = _create_stk_sent_transaction(
            monkeypatch, tenant_id=tenant_id, actor_id=actor_id
        )
        headers, body = _signed_webhook_request(
            order_id=reference,
            transid=transid,
            result="SUCCESS",
            resultcode="000",
            payment_status="COMPLETED",
        )
        headers["Digest"] = "dGFtcGVyZWQ="  # base64("tampered")

        response = client.post(
            "/api/v1/webhooks/selcom-collection/checkout", json=body, headers=headers
        )

        async def _status() -> str:
            async with AsyncSessionLocal() as db:
                service = CollectionService(db)
                transaction = await service.repo.get_by_id(tenant_id=None, id=transaction_id)
                assert transaction is not None
                return transaction.status

        after = asyncio.run(_status())

    assert response.json() == {"status": "rejected"}
    # Never even queried order-status — still exactly where it was.
    assert after == CollectionStatus.STK_SENT.value


def test_webhook_when_collection_not_configured_is_rejected() -> None:
    """No SELCOM_COLLECTION_* credentials configured at all (the default
    test-suite state) — verification can never even be attempted, so this
    must safely reject rather than crash."""
    response = client.post(
        "/api/v1/webhooks/selcom-collection/checkout",
        json={"order_id": "col-doesnotexist", "payment_status": "COMPLETED"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "rejected"}


# ------------------------------------------------------------ happy path(s)


def test_valid_webhook_for_completed_order_queries_and_credits_wallet(
    collection_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        transaction_id, reference, transid = _create_stk_sent_transaction(
            monkeypatch, tenant_id=tenant_id, actor_id=actor_id
        )
        monkeypatch.setattr(
            SelcomCollectionClient,
            "order_status",
            _fake_order_status_completed(reference, transid, _AMOUNT),
        )
        headers, body = _signed_webhook_request(
            order_id=reference,
            transid=transid,
            result="SUCCESS",
            resultcode="000",
            payment_status="COMPLETED",
        )

        response = client.post(
            "/api/v1/webhooks/selcom-collection/checkout", json=body, headers=headers
        )

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM transactions WHERE id = %s", (str(transaction_id),)
            )
            status_row = cur.fetchone()
            cur.execute(
                "SELECT count(*) FROM ledger_entries WHERE reference_id = %s",
                (str(transaction_id),),
            )
            ledger_count = cur.fetchone()[0]
            cur.execute(
                "SELECT signature_verified, processed FROM payment_webhooks "
                "WHERE provider = 'selcom_collection' ORDER BY received_at DESC LIMIT 1"
            )
            webhook_row = cur.fetchone()

    assert response.json() == {"status": "acknowledged"}
    assert status_row is not None
    assert status_row[0] == CollectionStatus.COMPLETED.value
    assert ledger_count == 3
    assert webhook_row == (True, True)


def test_duplicate_valid_webhook_does_not_double_credit(
    collection_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        transaction_id, reference, transid = _create_stk_sent_transaction(
            monkeypatch, tenant_id=tenant_id, actor_id=actor_id
        )
        monkeypatch.setattr(
            SelcomCollectionClient,
            "order_status",
            _fake_order_status_completed(reference, transid, _AMOUNT),
        )
        headers, body = _signed_webhook_request(
            order_id=reference,
            transid=transid,
            result="SUCCESS",
            resultcode="000",
            payment_status="COMPLETED",
        )

        first = client.post(
            "/api/v1/webhooks/selcom-collection/checkout", json=body, headers=headers
        )
        second = client.post(
            "/api/v1/webhooks/selcom-collection/checkout", json=body, headers=headers
        )

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM ledger_entries WHERE reference_id = %s",
                (str(transaction_id),),
            )
            ledger_count = cur.fetchone()[0]

    assert first.json() == {"status": "acknowledged"}
    assert second.json() == {"status": "acknowledged"}
    assert ledger_count == 3


def test_valid_webhook_for_unknown_order_id_is_acknowledged_as_unknown(
    collection_env: None,
) -> None:
    headers, body = _signed_webhook_request(
        order_id="col-does-not-exist-anywhere",
        transid="txn-does-not-exist",
        result="SUCCESS",
        resultcode="000",
        payment_status="COMPLETED",
    )
    response = client.post(
        "/api/v1/webhooks/selcom-collection/checkout", json=body, headers=headers
    )
    assert response.status_code == 200
    assert response.json() == {"status": "unknown_reference"}


def test_valid_webhook_missing_order_id_is_malformed(collection_env: None) -> None:
    signed_fields: OrderedDict[str, str] = OrderedDict(
        [("result", "SUCCESS"), ("resultcode", "000"), ("payment_status", "COMPLETED")]
    )
    signed = sign_request(
        api_key=_API_KEY,
        digest_method="HS256",
        api_secret=_API_SECRET,
        private_key_pem=None,
        fields=signed_fields,
    )
    response = client.post(
        "/api/v1/webhooks/selcom-collection/checkout",
        json=dict(signed_fields),
        headers=signed.as_dict(),
    )
    assert response.status_code == 200
    assert response.json() == {"status": "malformed"}


def test_valid_webhook_never_trusts_its_own_unsigned_amount_for_crediting(
    collection_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The webhook body claims amount=5000 (matches), but the authenticated
    order-status query this triggers reports a different amount — the
    query result must win, moving the transaction to AMBIGUOUS rather than
    trusting the webhook's own (unsigned) amount field."""
    with SeededContext() as ctx:
        tenant_id, actor_id = _seed_tenant(ctx)
        transaction_id, reference, transid = _create_stk_sent_transaction(
            monkeypatch, tenant_id=tenant_id, actor_id=actor_id
        )
        monkeypatch.setattr(
            SelcomCollectionClient,
            "order_status",
            _fake_order_status_completed(reference, transid, Decimal("1")),  # mismatched
        )
        headers, body = _signed_webhook_request(
            order_id=reference,
            transid=transid,
            result="SUCCESS",
            resultcode="000",
            payment_status="COMPLETED",
        )
        assert body["amount"] == "5000"  # the (unsigned) claim in the webhook body

        response = client.post(
            "/api/v1/webhooks/selcom-collection/checkout", json=body, headers=headers
        )

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute("SELECT status FROM transactions WHERE id = %s", (str(transaction_id),))
            status_row = cur.fetchone()
            cur.execute(
                "SELECT count(*) FROM ledger_entries WHERE reference_id = %s",
                (str(transaction_id),),
            )
            ledger_count = cur.fetchone()[0]

    assert response.json() == {"status": "acknowledged"}
    assert status_row is not None
    assert status_row[0] == CollectionStatus.AMBIGUOUS.value
    assert ledger_count == 0
