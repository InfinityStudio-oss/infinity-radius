"""POST /api/v1/webhooks/selcom/disbursement — the legacy, still-unimplemented
Selcom Collection-style disbursement callback (app/integrations/selcom/).
Kept exactly as-is: `verify_callback` always raises until Selcom's official
signing scheme for THAT API is documented — see its own module docstring.

The REAL, implemented pipeline (Selcom Business API, RSA-signed) is
app/integrations/selcom_business/ + app/services/payouts.py, exercised end
to end below via POST /api/v1/webhooks/selcom-business/disbursement, which
never trusts the callback's own claims — it only triggers an authenticated
GET /v1/transaction/query (app/services/payouts.py.reconcile_withdrawal),
so the client mocks here are on SelcomBusinessClient, not the callback
payload's fields.
"""

import asyncio
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.enums import LedgerDirection, WalletBucket
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

_VERIFIED_NAME = "Jane Test Recipient"


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


def test_selcom_business_webhook_reachability_check_accepts_get_with_no_auth() -> None:
    """Selcom's own portal probes the configured callback URL with a
    GET/HEAD before accepting it as "verified" — separate from real
    callback delivery, which is always POST. Must return 200 with no
    auth required, or the portal reports the URL as unreachable even
    though the real POST path works fine."""
    response = client.get("/api/v1/webhooks/selcom-business/disbursement")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_selcom_business_webhook_reachability_check_accepts_head_with_no_auth() -> None:
    response = client.head("/api/v1/webhooks/selcom-business/disbursement")
    assert response.status_code == 200


def test_selcom_business_webhook_with_unknown_reference_is_a_harmless_no_op() -> None:
    response = client.post(
        "/api/v1/webhooks/selcom-business/disbursement",
        json={"reference_id": "no-such-withdrawal", "status": "SUCCESS"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "unknown_reference"}


def test_selcom_business_webhook_with_malformed_payload_is_rejected() -> None:
    response = client.post("/api/v1/webhooks/selcom-business/disbursement", json={"foo": "bar"})
    assert response.status_code == 200
    assert response.json() == {"status": "malformed"}


def _fake_account_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(
        self: SelcomBusinessClient, *, bank: str, account: str, trans_id: str, amount: object = None
    ) -> AccountLookupResponse:
        return AccountLookupResponse(
            success=True,
            resultcode="000",
            data=AccountLookupData(
                account_name=_VERIFIED_NAME, operator=bank, total_charges=Decimal("0")
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
                trans_id=str(kwargs["trans_id"]),
                status="ACCEPTED",
                amount=Decimal(str(kwargs["amount"])),
                currency="TZS",
            ),
        )

    monkeypatch.setattr(SelcomBusinessClient, "transaction_process", _fake)


def _fake_transaction_query_completed(
    monkeypatch: pytest.MonkeyPatch, *, amount: str
) -> None:
    async def _fake(self: SelcomBusinessClient, *, trans_id: str) -> TransactionQueryResponse:
        return TransactionQueryResponse(
            success=True,
            resultcode="000",
            data=TransactionQueryData(
                trans_id=trans_id,
                status="COMPLETED",
                amount=Decimal(amount),
                currency="TZS",
                selcom_receipt=f"RCPT-{trans_id}",
            ),
        )

    monkeypatch.setattr(SelcomBusinessClient, "transaction_query", _fake)


def test_full_disbursement_pipeline_reaches_success_and_can_be_reversed(
    monkeypatch: pytest.MonkeyPatch, capture_withdrawal_otp: list[str]
) -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        owner_headers = auth_header(user_id=owner_id)
        admin_headers = auth_header(user_id=admin_id)
        ctx.new_settlement_config(tenant_id=tenant_id)
        ctx.new_tenant_feature_flags(tenant_id=tenant_id, payout_enabled=True)
        ctx.new_tenant_verification(tenant_id=tenant_id, status="APPROVED", email_verified=True)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))

        destination_id = client.post(
            "/api/v1/payouts/destinations",
            headers=owner_headers,
            json={
                "label": "M-Pesa",
                "channel": "mobile_money",
                "destination_code": "MPESA",
                "account_number": "255700000000",
            },
        ).json()["data"]["id"]

        request_response = client.post(
            "/api/v1/payouts",
            headers=owner_headers,
            json={"destination_id": destination_id, "amount": "600.00"},
        )
        withdrawal_id = request_response.json()["withdrawal"]["id"]
        code = capture_withdrawal_otp[-1]

        _fake_account_lookup(monkeypatch)
        _fake_transaction_process_inprogress(monkeypatch)

        confirm_response = client.post(
            f"/api/v1/payouts/{withdrawal_id}/confirm-2fa",
            headers=owner_headers,
            json={"code": code},
        )
        # At/under the threshold — 2FA confirmation itself submits.
        assert confirm_response.json()["data"]["status"] == "PROCESSING"
        provider_reference = confirm_response.json()["data"]["provider_reference"]
        assert confirm_response.json()["data"]["verified_recipient_name"] == _VERIFIED_NAME

        _fake_transaction_query_completed(monkeypatch, amount="600.00")
        webhook_response = client.post(
            "/api/v1/webhooks/selcom-business/disbursement",
            json={"reference_id": provider_reference, "status": "SUCCESS"},
        )
        assert webhook_response.json() == {"status": "acknowledged"}

        after_success = client.get(f"/api/v1/payouts/{withdrawal_id}", headers=owner_headers)
        wallet_after_success = client.get("/api/v1/wallet", headers=owner_headers)
        ledger_after_success = client.get("/api/v1/wallet/ledger", headers=owner_headers)

        # A retried callback for the same reference must not double-apply —
        # reconcile_withdrawal's own status-guard makes this idempotent
        # even though it re-queries every time.
        duplicate_response = client.post(
            "/api/v1/webhooks/selcom-business/disbursement",
            json={"reference_id": provider_reference, "status": "SUCCESS"},
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

    assert duplicate_response.json() == {"status": "acknowledged"}

    assert reverse_response.status_code == 200
    assert reverse_response.json()["data"]["status"] == "REVERSED"
    wallet_reversed_data = wallet_after_reversal.json()["data"]
    assert wallet_reversed_data["total_disbursed_tzs"] == "0.00"
    assert wallet_reversed_data["available_balance_tzs"] == "1000.00"


def test_transport_error_during_submission_never_resubmits_and_reconciles_via_query(
    monkeypatch: pytest.MonkeyPatch, capture_withdrawal_otp: list[str]
) -> None:
    """The critical timeout-safety case: transaction_process's HTTP call
    itself fails (timeout/connection error) — the withdrawal must stay
    PROCESSING (never blindly re-submitted, never marked FAILED on a
    merely-unknown outcome), and the SAME transId is used to query Selcom
    directly for what actually happened."""
    from app.integrations.selcom_business.errors import SelcomBusinessTransportError

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        owner_headers = auth_header(user_id=owner_id)
        ctx.new_settlement_config(tenant_id=tenant_id)
        ctx.new_tenant_feature_flags(tenant_id=tenant_id, payout_enabled=True)
        ctx.new_tenant_verification(tenant_id=tenant_id, status="APPROVED", email_verified=True)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))

        destination_id = client.post(
            "/api/v1/payouts/destinations",
            headers=owner_headers,
            json={
                "label": "M-Pesa",
                "channel": "mobile_money",
                "destination_code": "MPESA",
                "account_number": "255700000000",
            },
        ).json()["data"]["id"]
        request_response = client.post(
            "/api/v1/payouts",
            headers=owner_headers,
            json={"destination_id": destination_id, "amount": "600.00"},
        )
        withdrawal_id = request_response.json()["withdrawal"]["id"]
        code = capture_withdrawal_otp[-1]

        _fake_account_lookup(monkeypatch)

        async def _timeout(
            self: SelcomBusinessClient, **kwargs: object
        ) -> TransactionProcessResponse:
            raise SelcomBusinessTransportError("simulated timeout")

        monkeypatch.setattr(SelcomBusinessClient, "transaction_process", _timeout)
        _fake_transaction_query_completed(monkeypatch, amount="600.00")

        confirm_response = client.post(
            f"/api/v1/payouts/{withdrawal_id}/confirm-2fa",
            headers=owner_headers,
            json={"code": code},
        )

    # The reconciliation query (also mocked) resolved it to COMPLETED —
    # proving the timeout path queries rather than giving up or retrying.
    assert confirm_response.json()["data"]["status"] == "SUCCESS"


def test_admin_requery_requires_super_admin_and_never_resubmits(
    monkeypatch: pytest.MonkeyPatch, capture_withdrawal_otp: list[str]
) -> None:
    """POST /api/v1/admin/withdrawals/{id}/requery — the one safe manual
    action for a stuck withdrawal. Verifies RBAC (tenant forbidden), that
    it genuinely resolves a real PROCESSING row via query, and that it
    calls transaction_query exactly once and transaction_process zero
    times (never a resubmit)."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        owner_headers = auth_header(user_id=owner_id)
        admin_headers = auth_header(user_id=admin_id)
        ctx.new_settlement_config(tenant_id=tenant_id)
        ctx.new_tenant_feature_flags(tenant_id=tenant_id, payout_enabled=True)
        ctx.new_tenant_verification(tenant_id=tenant_id, status="APPROVED", email_verified=True)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))

        destination_id = client.post(
            "/api/v1/payouts/destinations",
            headers=owner_headers,
            json={
                "label": "M-Pesa",
                "channel": "mobile_money",
                "destination_code": "MPESA",
                "account_number": "255700000000",
            },
        ).json()["data"]["id"]
        request_response = client.post(
            "/api/v1/payouts",
            headers=owner_headers,
            json={"destination_id": destination_id, "amount": "600.00"},
        )
        withdrawal_id = request_response.json()["withdrawal"]["id"]
        code = capture_withdrawal_otp[-1]

        _fake_account_lookup(monkeypatch)
        _fake_transaction_process_inprogress(monkeypatch)

        confirm_response = client.post(
            f"/api/v1/payouts/{withdrawal_id}/confirm-2fa",
            headers=owner_headers,
            json={"code": code},
        )
        assert confirm_response.json()["data"]["status"] == "PROCESSING"

        process_calls = 0
        query_calls = 0

        async def _counting_transaction_process(
            self: SelcomBusinessClient, **kwargs: object
        ) -> None:
            nonlocal process_calls
            process_calls += 1
            raise AssertionError("transaction_process must never be called by requery")

        monkeypatch.setattr(
            SelcomBusinessClient, "transaction_process", _counting_transaction_process
        )

        async def _counting_query(self: SelcomBusinessClient, *, trans_id: str) -> object:
            nonlocal query_calls
            query_calls += 1
            return TransactionQueryResponse(
                success=True,
                resultcode="000",
                data=TransactionQueryData(
                    trans_id=trans_id, status="COMPLETED", amount=Decimal("600.00"),
                    currency="TZS", selcom_receipt=f"RCPT-{trans_id}",
                ),
            )

        monkeypatch.setattr(SelcomBusinessClient, "transaction_query", _counting_query)

        tenant_forbidden = client.post(
            f"/api/v1/admin/withdrawals/{withdrawal_id}/requery", headers=owner_headers
        )
        requery_response = client.post(
            f"/api/v1/admin/withdrawals/{withdrawal_id}/requery", headers=admin_headers
        )

    assert tenant_forbidden.status_code == 403
    assert requery_response.status_code == 200
    assert requery_response.json()["data"]["status"] == "SUCCESS"
    assert query_calls == 1
    assert process_calls == 0
