"""Full end-to-end reconciliation wiring for the amount/currency/transId
fail-safe checks in app/services/payouts.py._apply_provider_result —
tests/test_provider_amount_matching.py covers match_provider_amount in
isolation; these prove the checks are actually wired into the real
request -> OTP -> confirm -> query pipeline, using the exact real
production incident shape (2026-09-19): a completed transfer where
Selcom's transaction/query reported principal + its own transfer charge.
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
_PRINCIPAL = "5000.00"
_CHARGE = "150.00"


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


def _fake_account_lookup_with_charge(monkeypatch: pytest.MonkeyPatch, *, charge: str) -> None:
    async def _fake(
        self: SelcomBusinessClient, *, bank: str, account: str, trans_id: str, amount: object = None
    ) -> AccountLookupResponse:
        return AccountLookupResponse(
            success=True,
            resultcode="000",
            data=AccountLookupData(
                account_name=_VERIFIED_NAME, operator=bank, total_charges=Decimal(charge)
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


def _create_processing_withdrawal(
    ctx: SeededContext,
    *,
    tenant_id: UUID,
    admin_id: UUID,
    owner_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
    capture_withdrawal_otp: list[str],
    charge: str,
) -> tuple[UUID, str]:
    """Returns (withdrawal_id, provider_trans_id) for a real PROCESSING
    withdrawal, with provider_charge stored exactly as `charge` — the
    authenticated-lookup source of truth match_provider_amount's second
    form is allowed to trust."""
    owner_headers = auth_header(user_id=owner_id)
    ctx.new_settlement_config(tenant_id=tenant_id)
    ctx.new_tenant_feature_flags(tenant_id=tenant_id, payout_enabled=True)
    ctx.new_tenant_verification(tenant_id=tenant_id, status="APPROVED", email_verified=True)
    asyncio.run(_credit_available(tenant_id, admin_id, "1000000.00"))

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
        json={"destination_id": destination_id, "amount": _PRINCIPAL},
    )
    withdrawal_id = request_response.json()["withdrawal"]["id"]
    code = capture_withdrawal_otp[-1]

    _fake_account_lookup_with_charge(monkeypatch, charge=charge)
    _fake_transaction_process_inprogress(monkeypatch)
    confirm_response = client.post(
        f"/api/v1/payouts/{withdrawal_id}/confirm-2fa", headers=owner_headers, json={"code": code}
    )
    data = confirm_response.json()["data"]
    assert data["status"] == "PROCESSING"
    assert data["provider_charge"] == charge
    return UUID(withdrawal_id), data["provider_reference"]


def _seed_basic_tenant(ctx: SeededContext) -> tuple[UUID, UUID, UUID]:
    tenant_id = ctx.new_tenant()
    admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
    owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
    return tenant_id, admin_id, owner_id


def test_real_incident_shape_finalizes_success_with_principal_only_debit(
    monkeypatch: pytest.MonkeyPatch, capture_withdrawal_otp: list[str]
) -> None:
    """The exact real production shape: principal 5000, stored charge
    150, transaction/query reports 5150 — must finalize SUCCESS, and the
    wallet must debit exactly the 5000 principal, never 5150."""

    async def _query_charge_inclusive(
        self: SelcomBusinessClient, *, trans_id: str
    ) -> TransactionQueryResponse:
        return TransactionQueryResponse(
            success=True,
            resultcode="000",
            data=TransactionQueryData(
                trans_id=trans_id,
                status="COMPLETED",
                amount=Decimal("5150.00"),  # principal + charge, the real incident shape
                currency="TZS",
                selcom_receipt=f"RCPT-{trans_id}",
            ),
        )

    with SeededContext() as ctx:
        tenant_id, admin_id, owner_id = _seed_basic_tenant(ctx)
        owner_headers = auth_header(user_id=owner_id)
        withdrawal_id, provider_reference = _create_processing_withdrawal(
            ctx,
            tenant_id=tenant_id,
            admin_id=admin_id,
            owner_id=owner_id,
            monkeypatch=monkeypatch,
            capture_withdrawal_otp=capture_withdrawal_otp,
            charge=_CHARGE,
        )
        monkeypatch.setattr(SelcomBusinessClient, "transaction_query", _query_charge_inclusive)

        webhook_response = client.post(
            "/api/v1/webhooks/selcom-business/disbursement",
            json={"reference_id": provider_reference, "status": "SUCCESS"},
        )
        after = client.get(f"/api/v1/payouts/{withdrawal_id}", headers=owner_headers)
        wallet_after = client.get("/api/v1/wallet", headers=owner_headers)

    assert webhook_response.json() == {"status": "acknowledged"}
    assert after.json()["data"]["status"] == "SUCCESS"
    wallet_data = wallet_after.json()["data"]
    assert wallet_data["reserved_balance_tzs"] == "0.00"
    # Exactly the 5000 principal — never the provider-reported 5150 total.
    assert wallet_data["total_disbursed_tzs"] == _PRINCIPAL


def test_standard_documented_shape_still_finalizes_success(
    monkeypatch: pytest.MonkeyPatch, capture_withdrawal_otp: list[str]
) -> None:
    """If Selcom ever returns exactly the principal (matching its own
    public docs), the exact-match path must keep working unchanged."""

    async def _query_principal_only(
        self: SelcomBusinessClient, *, trans_id: str
    ) -> TransactionQueryResponse:
        return TransactionQueryResponse(
            success=True,
            resultcode="000",
            data=TransactionQueryData(
                trans_id=trans_id,
                status="COMPLETED",
                amount=Decimal(_PRINCIPAL),
                currency="TZS",
                selcom_receipt=f"RCPT-{trans_id}",
            ),
        )

    with SeededContext() as ctx:
        tenant_id, admin_id, owner_id = _seed_basic_tenant(ctx)
        owner_headers = auth_header(user_id=owner_id)
        withdrawal_id, provider_reference = _create_processing_withdrawal(
            ctx,
            tenant_id=tenant_id,
            admin_id=admin_id,
            owner_id=owner_id,
            monkeypatch=monkeypatch,
            capture_withdrawal_otp=capture_withdrawal_otp,
            charge=_CHARGE,
        )
        monkeypatch.setattr(SelcomBusinessClient, "transaction_query", _query_principal_only)

        client.post(
            "/api/v1/webhooks/selcom-business/disbursement",
            json={"reference_id": provider_reference, "status": "SUCCESS"},
        )
        after = client.get(f"/api/v1/payouts/{withdrawal_id}", headers=owner_headers)

    assert after.json()["data"]["status"] == "SUCCESS"


def test_currency_mismatch_never_finalizes(
    monkeypatch: pytest.MonkeyPatch, capture_withdrawal_otp: list[str]
) -> None:
    async def _query_wrong_currency(
        self: SelcomBusinessClient, *, trans_id: str
    ) -> TransactionQueryResponse:
        return TransactionQueryResponse(
            success=True,
            resultcode="000",
            data=TransactionQueryData(
                trans_id=trans_id,
                status="COMPLETED",
                amount=Decimal(_PRINCIPAL),
                currency="USD",  # wrong currency — must never finalize on this
                selcom_receipt=f"RCPT-{trans_id}",
            ),
        )

    with SeededContext() as ctx:
        tenant_id, admin_id, owner_id = _seed_basic_tenant(ctx)
        owner_headers = auth_header(user_id=owner_id)
        withdrawal_id, provider_reference = _create_processing_withdrawal(
            ctx,
            tenant_id=tenant_id,
            admin_id=admin_id,
            owner_id=owner_id,
            monkeypatch=monkeypatch,
            capture_withdrawal_otp=capture_withdrawal_otp,
            charge=_CHARGE,
        )
        monkeypatch.setattr(SelcomBusinessClient, "transaction_query", _query_wrong_currency)

        client.post(
            "/api/v1/webhooks/selcom-business/disbursement",
            json={"reference_id": provider_reference, "status": "SUCCESS"},
        )
        after = client.get(f"/api/v1/payouts/{withdrawal_id}", headers=owner_headers)

    assert after.json()["data"]["status"] == "AMBIGUOUS"


def test_trans_id_mismatch_never_finalizes(
    monkeypatch: pytest.MonkeyPatch, capture_withdrawal_otp: list[str]
) -> None:
    async def _query_wrong_trans_id(
        self: SelcomBusinessClient, *, trans_id: str
    ) -> TransactionQueryResponse:
        return TransactionQueryResponse(
            success=True,
            resultcode="000",
            data=TransactionQueryData(
                trans_id="some-other-transaction-entirely",
                status="COMPLETED",
                amount=Decimal(_PRINCIPAL),
                currency="TZS",
                selcom_receipt="RCPT-other",
            ),
        )

    with SeededContext() as ctx:
        tenant_id, admin_id, owner_id = _seed_basic_tenant(ctx)
        owner_headers = auth_header(user_id=owner_id)
        withdrawal_id, provider_reference = _create_processing_withdrawal(
            ctx,
            tenant_id=tenant_id,
            admin_id=admin_id,
            owner_id=owner_id,
            monkeypatch=monkeypatch,
            capture_withdrawal_otp=capture_withdrawal_otp,
            charge=_CHARGE,
        )
        monkeypatch.setattr(SelcomBusinessClient, "transaction_query", _query_wrong_trans_id)

        client.post(
            "/api/v1/webhooks/selcom-business/disbursement",
            json={"reference_id": provider_reference, "status": "SUCCESS"},
        )
        after = client.get(f"/api/v1/payouts/{withdrawal_id}", headers=owner_headers)

    assert after.json()["data"]["status"] == "AMBIGUOUS"


def test_missing_stored_charge_with_charged_total_stays_ambiguous(
    monkeypatch: pytest.MonkeyPatch, capture_withdrawal_otp: list[str]
) -> None:
    """This withdrawal's own lookup recorded a ZERO charge, but the query
    reports principal+150 anyway — must not invent a charge to explain it."""

    async def _query_charge_inclusive(
        self: SelcomBusinessClient, *, trans_id: str
    ) -> TransactionQueryResponse:
        return TransactionQueryResponse(
            success=True,
            resultcode="000",
            data=TransactionQueryData(
                trans_id=trans_id,
                status="COMPLETED",
                amount=Decimal("5150.00"),
                currency="TZS",
                selcom_receipt=f"RCPT-{trans_id}",
            ),
        )

    with SeededContext() as ctx:
        tenant_id, admin_id, owner_id = _seed_basic_tenant(ctx)
        owner_headers = auth_header(user_id=owner_id)
        withdrawal_id, provider_reference = _create_processing_withdrawal(
            ctx,
            tenant_id=tenant_id,
            admin_id=admin_id,
            owner_id=owner_id,
            monkeypatch=monkeypatch,
            capture_withdrawal_otp=capture_withdrawal_otp,
            charge="0.00",
        )
        monkeypatch.setattr(SelcomBusinessClient, "transaction_query", _query_charge_inclusive)

        client.post(
            "/api/v1/webhooks/selcom-business/disbursement",
            json={"reference_id": provider_reference, "status": "SUCCESS"},
        )
        after = client.get(f"/api/v1/payouts/{withdrawal_id}", headers=owner_headers)

    assert after.json()["data"]["status"] == "AMBIGUOUS"


def test_success_finalization_records_which_amount_match_was_used(
    monkeypatch: pytest.MonkeyPatch, capture_withdrawal_otp: list[str]
) -> None:
    """Part 9's audit requirement — the SUCCESS transition's audit_logs
    row records amount_match=PRINCIPAL_PLUS_STORED_PROVIDER_CHARGE."""

    async def _query_charge_inclusive(
        self: SelcomBusinessClient, *, trans_id: str
    ) -> TransactionQueryResponse:
        return TransactionQueryResponse(
            success=True,
            resultcode="000",
            data=TransactionQueryData(
                trans_id=trans_id,
                status="COMPLETED",
                amount=Decimal("5150.00"),
                currency="TZS",
                selcom_receipt=f"RCPT-{trans_id}",
            ),
        )

    with SeededContext() as ctx:
        tenant_id, admin_id, owner_id = _seed_basic_tenant(ctx)
        withdrawal_id, provider_reference = _create_processing_withdrawal(
            ctx,
            tenant_id=tenant_id,
            admin_id=admin_id,
            owner_id=owner_id,
            monkeypatch=monkeypatch,
            capture_withdrawal_otp=capture_withdrawal_otp,
            charge=_CHARGE,
        )
        monkeypatch.setattr(SelcomBusinessClient, "transaction_query", _query_charge_inclusive)

        client.post(
            "/api/v1/webhooks/selcom-business/disbursement",
            json={"reference_id": provider_reference, "status": "SUCCESS"},
        )

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT metadata FROM audit_logs WHERE target_id = %s AND action = "
                "'withdrawal.success' ORDER BY created_at DESC LIMIT 1",
                (str(withdrawal_id),),
            )
            row = cur.fetchone()

    assert row is not None
    assert row[0]["amount_match"] == "PRINCIPAL_PLUS_STORED_PROVIDER_CHARGE"
