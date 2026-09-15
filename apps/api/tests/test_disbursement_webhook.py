"""POST /api/v1/webhooks/selcom/disbursement, and the full disbursement
pipeline end to end.

Selcom's real disbursement callback field names and signature scheme are
unknown (see app/integrations/selcom/signatures.py) — so `verify_callback`
always raises today, and the *domain* pipeline downstream of verification
(idempotency, lookup by provider reference, the reserved -> total_disbursed
wallet move, the DISBURSEMENT ledger entry) is exercised here by
monkeypatching only the verification/extraction/initiate boundary, the
same convention test_selcom_webhook.py uses for the collection side —
nothing here touches runtime code, and production's verify_callback is
exercised completely unpatched by the tests that don't monkeypatch it.
"""

import asyncio
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.enums import LedgerDirection, WalletBucket
from app.db.session import AsyncSessionLocal
from app.integrations.selcom.disbursement import SelcomDisbursementService
from app.integrations.selcom.schemas import DisbursementOrderResponse
from app.main import app
from app.services.wallet import WalletService
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)

_PROVIDER_REFERENCE = "DISB-SIM-1"


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


def test_webhook_with_unimplemented_verification_saves_event_and_reports_unverified() -> None:
    response = client.post(
        "/api/v1/webhooks/selcom/disbursement", json={"anything": "at all"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "unverified"}


def _fake_initiate_disbursement(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(self: SelcomDisbursementService, request: object) -> DisbursementOrderResponse:
        return DisbursementOrderResponse(provider_reference=_PROVIDER_REFERENCE)

    monkeypatch.setattr(SelcomDisbursementService, "initiate_disbursement", _fake)


def _fake_callback_extractors(monkeypatch: pytest.MonkeyPatch, *, succeeded: bool) -> None:
    monkeypatch.setattr(SelcomDisbursementService, "verify_callback", lambda self, **kw: True)
    monkeypatch.setattr(
        SelcomDisbursementService,
        "_extract_provider_reference",
        lambda self, payload: payload["provider_reference"],
    )
    monkeypatch.setattr(
        SelcomDisbursementService, "_extract_status", lambda self, payload: succeeded
    )


def test_full_disbursement_pipeline_reaches_success_and_can_be_reversed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        checker_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        owner_headers = auth_header(user_id=owner_id)
        checker_headers = auth_header(user_id=checker_id)
        admin_headers = auth_header(user_id=admin_id)
        ctx.new_settlement_config(tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))

        destination_id = client.post(
            "/api/v1/payouts/destinations",
            headers=owner_headers,
            json={"label": "M-Pesa", "channel": "mobile_money", "account_number": "255700000000"},
        ).json()["data"]["id"]

        request_response = client.post(
            "/api/v1/payouts",
            headers=owner_headers,
            json={"destination_id": destination_id, "amount": "600.00"},
        )
        withdrawal_id = request_response.json()["withdrawal"]["id"]
        code = request_response.json()["two_factor_code"]
        client.post(
            f"/api/v1/payouts/{withdrawal_id}/confirm-2fa",
            headers=owner_headers,
            json={"code": code},
        )

        _fake_initiate_disbursement(monkeypatch)
        approve_response = client.post(
            f"/api/v1/payouts/{withdrawal_id}/approve", headers=checker_headers, json={}
        )
        assert approve_response.json()["data"]["status"] == "PROCESSING"
        assert approve_response.json()["data"]["provider_reference"] == _PROVIDER_REFERENCE

        _fake_callback_extractors(monkeypatch, succeeded=True)
        webhook_response = client.post(
            "/api/v1/webhooks/selcom/disbursement",
            json={"provider_reference": _PROVIDER_REFERENCE, "result": "success"},
        )
        assert webhook_response.json() == {"status": "processed"}

        after_success = client.get(f"/api/v1/payouts/{withdrawal_id}", headers=owner_headers)
        wallet_after_success = client.get("/api/v1/wallet", headers=owner_headers)
        ledger_after_success = client.get("/api/v1/wallet/ledger", headers=owner_headers)

        # A retried callback for the same reference must not double-apply.
        duplicate_response = client.post(
            "/api/v1/webhooks/selcom/disbursement",
            json={"provider_reference": _PROVIDER_REFERENCE, "result": "success"},
        )

        reverse_response = client.post(
            f"/api/v1/tenants/{tenant_id}/withdrawals/{withdrawal_id}/reverse",
            headers=admin_headers,
            json={"reason": "Recipient account was closed — provider returned the funds"},
        )
        wallet_after_reversal = client.get("/api/v1/wallet", headers=owner_headers)

    assert after_success.json()["data"]["status"] == "SUCCESS"
    wallet_success_data = wallet_after_success.json()["data"]
    assert wallet_success_data["reserved_balance_tzs"] == "0.00"
    assert wallet_success_data["total_disbursed_tzs"] == "600.00"
    disbursement_entries = [
        e for e in ledger_after_success.json()["data"] if e["entry_type"] == "DISBURSEMENT"
    ]
    assert len(disbursement_entries) == 1
    assert disbursement_entries[0]["amount"] == "600.00"

    assert duplicate_response.json() == {"status": "duplicate"}

    assert reverse_response.status_code == 200
    assert reverse_response.json()["data"]["status"] == "REVERSED"
    wallet_reversed_data = wallet_after_reversal.json()["data"]
    assert wallet_reversed_data["total_disbursed_tzs"] == "0.00"
    assert wallet_reversed_data["available_balance_tzs"] == "1000.00"
