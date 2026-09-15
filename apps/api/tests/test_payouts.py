"""Tenant payouts — the full maker-checker withdrawal lifecycle: request
(balance reserved, 2FA issued) -> confirm 2FA -> approve/reject (never by
the requester) -> submit to Selcom -> await its authoritative result.

Also covers the /destinations route-ordering fix (it used to be shadowed
by /{withdrawal_id} — see app/api/v1/payouts.py) and the settlement-mode
gate (DIRECT_MERCHANT_SETTLEMENT is the default and blocks withdrawals
entirely — see app/services/settlement_config.py).
"""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.enums import LedgerDirection, WalletBucket
from app.db.session import AsyncSessionLocal
from app.main import app
from app.services.wallet import WalletService
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


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


def _create_destination(headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/payouts/destinations",
        headers=headers,
        json={
            "label": "M-Pesa Main",
            "channel": "mobile_money",
            "account_name": "Test Tenant",
            "account_number": "255712345678",
            "is_default": True,
        },
    )
    assert response.status_code == 201
    return str(response.json()["data"]["id"])


def test_destinations_route_is_reachable_and_not_shadowed_by_withdrawal_id() -> None:
    """Regression test: /destinations used to be registered after
    /{withdrawal_id}, so FastAPI tried (and failed) to parse "destinations"
    as a UUID before ever reaching this route."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        get_response = client.get("/api/v1/payouts/destinations", headers=headers)
        post_response = client.post(
            "/api/v1/payouts/destinations",
            headers=headers,
            json={"label": "Bank", "channel": "bank", "is_default": False},
        )

    assert get_response.status_code == 200
    assert post_response.status_code == 201


def test_request_withdrawal_is_blocked_in_default_direct_merchant_settlement_mode() -> None:
    """No settlement config seeded — the tenant is in the default,
    do-not-assume-custody mode, so Infinity Radius refuses to hold or
    disburse its funds at all."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))
        destination_id = _create_destination(headers)

        response = client.post(
            "/api/v1/payouts",
            headers=headers,
            json={"destination_id": destination_id, "amount": "500.00"},
        )

    assert response.status_code == 422
    assert "direct merchant settlement" in response.json()["error"]["message"]


def test_request_withdrawal_reserves_funds_and_issues_a_two_factor_code() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        ctx.new_settlement_config(tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))
        destination_id = _create_destination(headers)

        withdrawal_response = client.post(
            "/api/v1/payouts",
            headers=headers,
            json={"destination_id": destination_id, "amount": "600.00"},
        )
        assert withdrawal_response.status_code == 201
        body = withdrawal_response.json()
        assert body["withdrawal"]["status"] == "DRAFT"
        assert len(body["two_factor_code"]) == 6

        wallet_response = client.get("/api/v1/wallet", headers=headers)

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                'SELECT "metadata" FROM audit_logs WHERE action = %s '
                "ORDER BY created_at DESC LIMIT 1",
                ("withdrawal.two_factor_issued",),
            )
            row = cur.fetchone()

    wallet_data = wallet_response.json()["data"]
    assert wallet_data["available_balance_tzs"] == "400.00"
    assert wallet_data["reserved_balance_tzs"] == "600.00"
    assert row is not None
    assert row[0]["code"] == body["two_factor_code"]


def test_request_withdrawal_rejects_amount_exceeding_available_balance() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        ctx.new_settlement_config(tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "100.00"))
        destination_id = _create_destination(headers)

        response = client.post(
            "/api/v1/payouts",
            headers=headers,
            json={"destination_id": destination_id, "amount": "500.00"},
        )

    assert response.status_code == 422


def test_request_withdrawal_is_blocked_when_disbursement_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.payouts as payouts_module

    monkeypatch.setattr(
        payouts_module, "get_settings", lambda: SimpleNamespace(selcom_disbursement_enabled=False)
    )
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        ctx.new_settlement_config(tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))
        destination_id = _create_destination(headers)

        response = client.post(
            "/api/v1/payouts",
            headers=headers,
            json={"destination_id": destination_id, "amount": "500.00"},
        )

    assert response.status_code == 422
    assert "disabled" in response.json()["error"]["message"]


def _request_withdrawal(
    ctx: SeededContext, *, owner_headers: dict[str, str], amount: str = "600.00"
) -> tuple[str, str]:
    destination_id = _create_destination(owner_headers)
    response = client.post(
        "/api/v1/payouts",
        headers=owner_headers,
        json={"destination_id": destination_id, "amount": amount},
    )
    assert response.status_code == 201
    body = response.json()
    return body["withdrawal"]["id"], body["two_factor_code"]


def test_confirm_two_factor_with_wrong_code_increments_attempts_then_cancels() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        ctx.new_settlement_config(tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))
        withdrawal_id, _real_code = _request_withdrawal(ctx, owner_headers=headers)

        last_response = None
        for _ in range(5):
            last_response = client.post(
                f"/api/v1/payouts/{withdrawal_id}/confirm-2fa",
                headers=headers,
                json={"code": "000000"},
            )

        wallet_response = client.get("/api/v1/wallet", headers=headers)
        get_response = client.get(f"/api/v1/payouts/{withdrawal_id}", headers=headers)

    assert last_response is not None
    assert last_response.status_code == 422
    assert "cancelled" in last_response.json()["error"]["message"]
    assert get_response.json()["data"]["status"] == "CANCELLED"
    wallet_data = wallet_response.json()["data"]
    assert wallet_data["available_balance_tzs"] == "1000.00"
    assert wallet_data["reserved_balance_tzs"] == "0.00"


def test_confirm_two_factor_with_correct_code_moves_to_pending_approval() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        ctx.new_settlement_config(tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))
        withdrawal_id, code = _request_withdrawal(ctx, owner_headers=headers)

        response = client.post(
            f"/api/v1/payouts/{withdrawal_id}/confirm-2fa", headers=headers, json={"code": code}
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "PENDING_APPROVAL"


def test_only_the_requester_can_confirm_their_own_two_factor_code() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        other_owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        other_headers = auth_header(user_id=other_owner_id)
        ctx.new_settlement_config(tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))
        withdrawal_id, code = _request_withdrawal(ctx, owner_headers=headers)

        response = client.post(
            f"/api/v1/payouts/{withdrawal_id}/confirm-2fa",
            headers=other_headers,
            json={"code": code},
        )

    assert response.status_code == 422


def _confirm(ctx: SeededContext, *, headers: dict[str, str], withdrawal_id: str, code: str) -> None:
    response = client.post(
        f"/api/v1/payouts/{withdrawal_id}/confirm-2fa", headers=headers, json={"code": code}
    )
    assert response.status_code == 200


def test_maker_cannot_approve_their_own_withdrawal() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        ctx.new_settlement_config(tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))
        withdrawal_id, code = _request_withdrawal(ctx, owner_headers=headers)
        _confirm(ctx, headers=headers, withdrawal_id=withdrawal_id, code=code)

        response = client.post(
            f"/api/v1/payouts/{withdrawal_id}/approve", headers=headers, json={}
        )

    assert response.status_code == 422
    assert "maker-checker" in response.json()["error"]["message"]


def test_checker_approval_submits_to_selcom_and_fails_closed_when_unconfigured() -> None:
    """Selcom credentials are unset in the test environment — approval
    should still transition PENDING_APPROVAL -> APPROVED -> PROCESSING ->
    FAILED (never silently stuck, never a fake success), releasing the
    reservation back to available."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        checker_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        checker_headers = auth_header(user_id=checker_id)
        ctx.new_settlement_config(tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))
        withdrawal_id, code = _request_withdrawal(ctx, owner_headers=headers)
        _confirm(ctx, headers=headers, withdrawal_id=withdrawal_id, code=code)

        approve_response = client.post(
            f"/api/v1/payouts/{withdrawal_id}/approve", headers=checker_headers, json={}
        )
        wallet_response = client.get("/api/v1/wallet", headers=headers)
        events_response = client.get(f"/api/v1/payouts/{withdrawal_id}/events", headers=headers)

    assert approve_response.status_code == 200
    body = approve_response.json()["data"]
    assert body["status"] == "FAILED"
    assert body["failure_reason"] is not None

    wallet_data = wallet_response.json()["data"]
    assert wallet_data["available_balance_tzs"] == "1000.00"
    assert wallet_data["reserved_balance_tzs"] == "0.00"

    statuses = [event["to_status"] for event in events_response.json()["data"]]
    assert statuses == ["DRAFT", "PENDING_APPROVAL", "APPROVED", "PROCESSING", "FAILED"]


def test_reject_withdrawal_requires_a_reason_and_releases_the_reservation() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        checker_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        checker_headers = auth_header(user_id=checker_id)
        ctx.new_settlement_config(tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))
        withdrawal_id, code = _request_withdrawal(ctx, owner_headers=headers)
        _confirm(ctx, headers=headers, withdrawal_id=withdrawal_id, code=code)

        missing_reason_response = client.post(
            f"/api/v1/payouts/{withdrawal_id}/reject", headers=checker_headers, json={"reason": ""}
        )
        reject_response = client.post(
            f"/api/v1/payouts/{withdrawal_id}/reject",
            headers=checker_headers,
            json={"reason": "Destination account could not be verified"},
        )
        wallet_response = client.get("/api/v1/wallet", headers=headers)

    assert missing_reason_response.status_code == 422
    assert reject_response.status_code == 200
    assert reject_response.json()["data"]["status"] == "REJECTED"
    wallet_data = wallet_response.json()["data"]
    assert wallet_data["available_balance_tzs"] == "1000.00"
    assert wallet_data["reserved_balance_tzs"] == "0.00"


def test_requester_can_cancel_their_own_draft_withdrawal() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        ctx.new_settlement_config(tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))
        withdrawal_id, _code = _request_withdrawal(ctx, owner_headers=headers)

        cancel_response = client.post(
            f"/api/v1/payouts/{withdrawal_id}/cancel",
            headers=headers,
            json={"reason": "Changed my mind"},
        )
        wallet_response = client.get("/api/v1/wallet", headers=headers)

    assert cancel_response.status_code == 200
    assert cancel_response.json()["data"]["status"] == "CANCELLED"
    wallet_data = wallet_response.json()["data"]
    assert wallet_data["available_balance_tzs"] == "1000.00"
    assert wallet_data["reserved_balance_tzs"] == "0.00"
