"""POST /api/v1/internal/disbursements/reconcile — the Celery worker's
ONLY path to Selcom (Option B network centralization). Never a tenant or
Super Admin JWT; authenticated purely by app/core/internal_auth.py's HMAC
scheme. Reuses PayoutService.reconcile_if_pending (itself reusing
_reconcile_locked, the exact code the webhook/requery paths already use),
so these tests focus on: the auth boundary, the PROCESSING/AMBIGUOUS-only
guard, and the structural guarantee that this path can never reach
transaction/process.
"""

import asyncio
import json
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.enums import LedgerDirection, WalletBucket
from app.core.internal_auth import sign_internal_request
from app.db.session import AsyncSessionLocal
from app.integrations.selcom_business.client import SelcomBusinessClient
from app.integrations.selcom_business.schemas import (
    AccountLookupData,
    AccountLookupResponse,
    TransactionProcessData,
    TransactionProcessResponse,
    TransactionQueryData,
    TransactionQueryResponse,
)
from app.main import app
from app.services.wallet import WalletService
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)

_PATH = "/api/v1/internal/disbursements/reconcile"
_HMAC_KEY = "test-only-internal-hmac-key-do-not-use-in-prod"


@pytest.fixture
def internal_hmac_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("INTERNAL_WORKER_WEB_HMAC_KEY", _HMAC_KEY)
    get_settings.cache_clear()
    yield _HMAC_KEY
    get_settings.cache_clear()


def _signed_post(withdrawal_id: UUID | str, *, secret: str = _HMAC_KEY) -> Any:
    body = json.dumps({"withdrawal_id": str(withdrawal_id)}).encode("utf-8")
    headers = sign_internal_request(secret=secret, method="POST", path=_PATH, body=body).as_dict()
    headers["Content-Type"] = "application/json"
    return client.post(_PATH, content=body, headers=headers)


async def _credit_available(tenant_id: UUID, actor_id: UUID, amount: str) -> None:
    async with AsyncSessionLocal() as db:
        await WalletService(db).create_adjustment(
            tenant_id=tenant_id,
            wallet_bucket=WalletBucket.AVAILABLE,
            direction=LedgerDirection.CREDIT,
            amount=Decimal(amount),
            reason="test setup — seed available balance",
            actor_id=actor_id,
        )
        await db.commit()


def _fake_account_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(
        self: SelcomBusinessClient, *, bank: str, account: str, trans_id: str, amount: object = None
    ) -> AccountLookupResponse:
        return AccountLookupResponse(
            success=True,
            resultcode="000",
            data=AccountLookupData(
                account_name="Jane Test", operator=bank, total_charges=Decimal("0")
            ),
        )

    monkeypatch.setattr(SelcomBusinessClient, "account_lookup", _fake)


def _fake_transaction_process_inprogress(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(self: SelcomBusinessClient, **kwargs: object) -> TransactionProcessResponse:
        return TransactionProcessResponse(
            success=True,
            resultcode="111",
            message="Transaction in progress",
            data=TransactionProcessData(
                trans_id=str(kwargs["trans_id"]), status="ACCEPTED",
                amount=Decimal(str(kwargs["amount"])), currency="TZS",
            ),
        )

    monkeypatch.setattr(SelcomBusinessClient, "transaction_process", _fake)


def _create_processing_withdrawal(
    ctx: SeededContext, *, tenant_id: UUID, admin_id: UUID, owner_id: UUID,
    monkeypatch: pytest.MonkeyPatch, capture_withdrawal_otp: list[str],
) -> UUID:
    owner_headers = auth_header(user_id=owner_id)
    ctx.new_settlement_config(tenant_id=tenant_id)
    ctx.new_tenant_feature_flags(tenant_id=tenant_id, payout_enabled=True)
    ctx.new_tenant_verification(tenant_id=tenant_id, status="APPROVED", email_verified=True)
    asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))

    destination_id = client.post(
        "/api/v1/payouts/destinations", headers=owner_headers,
        json={
            "label": "M-Pesa", "channel": "mobile_money",
            "destination_code": "MPESA", "account_number": "255700000000",
        },
    ).json()["data"]["id"]
    request_response = client.post(
        "/api/v1/payouts", headers=owner_headers,
        json={"destination_id": destination_id, "amount": "600.00"},
    )
    withdrawal_id = request_response.json()["withdrawal"]["id"]
    code = capture_withdrawal_otp[-1]

    _fake_account_lookup(monkeypatch)
    _fake_transaction_process_inprogress(monkeypatch)
    confirm_response = client.post(
        f"/api/v1/payouts/{withdrawal_id}/confirm-2fa", headers=owner_headers, json={"code": code}
    )
    assert confirm_response.json()["data"]["status"] == "PROCESSING"
    return UUID(withdrawal_id)


def _seed_basic_tenant(ctx: SeededContext) -> tuple[UUID, UUID, UUID]:
    tenant_id = ctx.new_tenant()
    admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
    owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
    return tenant_id, admin_id, owner_id


# --- Auth boundary -----------------------------------------------------


def test_missing_signature_is_rejected(internal_hmac_key: str) -> None:
    response = client.post(_PATH, json={"withdrawal_id": str(uuid4())})
    assert response.status_code == 401


def test_wrong_secret_is_rejected(internal_hmac_key: str) -> None:
    response = _signed_post(uuid4(), secret="not-the-real-secret")
    assert response.status_code == 401


def test_tenant_jwt_without_hmac_is_rejected(internal_hmac_key: str) -> None:
    with SeededContext() as ctx:
        tenant_id, _admin_id, owner_id = _seed_basic_tenant(ctx)
        response = client.post(
            _PATH, headers=auth_header(user_id=owner_id), json={"withdrawal_id": str(uuid4())}
        )
    assert response.status_code == 401


def test_super_admin_jwt_without_hmac_is_rejected(internal_hmac_key: str) -> None:
    with SeededContext() as ctx:
        _tenant_id, admin_id, _owner_id = _seed_basic_tenant(ctx)
        response = client.post(
            _PATH, headers=auth_header(user_id=admin_id), json={"withdrawal_id": str(uuid4())}
        )
    assert response.status_code == 401


def test_not_configured_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """No INTERNAL_WORKER_WEB_HMAC_KEY set at all — must never be treated
    as 'auth disabled'."""
    monkeypatch.delenv("INTERNAL_WORKER_WEB_HMAC_KEY", raising=False)
    get_settings.cache_clear()
    try:
        response = client.post(_PATH, json={"withdrawal_id": str(uuid4())})
    finally:
        get_settings.cache_clear()
    assert response.status_code == 503


# --- Behavior ------------------------------------------------------------


def test_unknown_withdrawal_id_is_404(internal_hmac_key: str) -> None:
    response = _signed_post(uuid4())
    assert response.status_code == 404


def test_processing_withdrawal_is_queried_exactly_once(
    internal_hmac_key: str, monkeypatch: pytest.MonkeyPatch, capture_withdrawal_otp: list[str]
) -> None:
    query_calls = 0
    process_calls = 0

    async def _counting_query(
        self: SelcomBusinessClient, *, trans_id: str
    ) -> TransactionQueryResponse:
        nonlocal query_calls
        query_calls += 1
        return TransactionQueryResponse(
            success=True, resultcode="000",
            data=TransactionQueryData(
                trans_id=trans_id, status="COMPLETED", amount=Decimal("600.00"),
                currency="TZS", selcom_receipt=f"RCPT-{trans_id}",
            ),
        )

    async def _failing_process(self: SelcomBusinessClient, **kwargs: object) -> None:
        nonlocal process_calls
        process_calls += 1
        raise AssertionError("transaction_process must never be called via the internal route")

    with SeededContext() as ctx:
        tenant_id, admin_id, owner_id = _seed_basic_tenant(ctx)
        withdrawal_id = _create_processing_withdrawal(
            ctx, tenant_id=tenant_id, admin_id=admin_id, owner_id=owner_id,
            monkeypatch=monkeypatch, capture_withdrawal_otp=capture_withdrawal_otp,
        )

        monkeypatch.setattr(SelcomBusinessClient, "transaction_query", _counting_query)
        monkeypatch.setattr(SelcomBusinessClient, "transaction_process", _failing_process)

        response = _signed_post(withdrawal_id)

    assert response.status_code == 200
    body = response.json()
    assert body["withdrawal_id"] == str(withdrawal_id)
    assert body["status"] == "SUCCESS"
    assert body["reconciled"] is True
    assert query_calls == 1
    assert process_calls == 0


def test_terminal_withdrawal_is_a_safe_no_op(
    internal_hmac_key: str, monkeypatch: pytest.MonkeyPatch, capture_withdrawal_otp: list[str]
) -> None:
    """A withdrawal already resolved (SUCCESS/FAILED/etc.) must never be
    re-queried — proves the PROCESSING/AMBIGUOUS guard, not just that
    reconcile_withdrawal is idempotent."""
    query_calls = 0

    async def _counting_query(
        self: SelcomBusinessClient, *, trans_id: str
    ) -> TransactionQueryResponse:
        nonlocal query_calls
        query_calls += 1
        return TransactionQueryResponse(
            success=True, resultcode="000",
            data=TransactionQueryData(
                trans_id=trans_id, status="COMPLETED", amount=Decimal("600.00"),
                currency="TZS", selcom_receipt=f"RCPT-{trans_id}",
            ),
        )

    with SeededContext() as ctx:
        tenant_id, admin_id, owner_id = _seed_basic_tenant(ctx)
        withdrawal_id = _create_processing_withdrawal(
            ctx, tenant_id=tenant_id, admin_id=admin_id, owner_id=owner_id,
            monkeypatch=monkeypatch, capture_withdrawal_otp=capture_withdrawal_otp,
        )
        monkeypatch.setattr(SelcomBusinessClient, "transaction_query", _counting_query)

        # First call resolves it to SUCCESS (a real terminal state)...
        first = _signed_post(withdrawal_id)
        assert first.json()["status"] == "SUCCESS"
        assert query_calls == 1

        # ...a second call for the now-terminal withdrawal must not query again.
        second = _signed_post(withdrawal_id)

    assert second.status_code == 200
    assert second.json() == {
        "withdrawal_id": str(withdrawal_id), "status": "SUCCESS", "reconciled": False,
    }
    assert query_calls == 1  # unchanged
