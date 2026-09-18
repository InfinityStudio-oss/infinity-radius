"""Stale-withdrawal alerting (PayoutService.maybe_alert_stale) — never a
payout retry, only a Super Admin status email once a withdrawal has been
PROCESSING/AMBIGUOUS longer than its configured threshold, deduplicated
via a cooldown tracked through the audit trail (no new table).

A real PROCESSING withdrawal is produced through the actual state machine
(request -> OTP -> confirm-2fa, with transaction_process mocked to return
INPROGRESS — the same technique test_disbursement_webhook.py already uses),
never hand-inserted. Elapsed time is then simulated the same way
test_payouts.py's OTP-expiry test does — a direct UPDATE of submitted_at
on the already-real row, not a time-freezing library (none is a project
dependency).
"""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.enums import LedgerDirection, WalletBucket
from app.db.session import AsyncSessionLocal
from app.integrations.resend.schemas import EmailSendResult
from app.integrations.selcom_business.client import SelcomBusinessClient
from app.integrations.selcom_business.schemas import (
    AccountLookupData,
    AccountLookupResponse,
    TransactionProcessData,
    TransactionProcessResponse,
)
from app.main import app
from app.services import payouts as payouts_module
from app.services.payouts import PayoutService
from app.services.wallet import WalletService
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


@pytest.fixture
def real_settings_override(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def capture_stale_alerts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []

    async def _fake_send(self: object, **kwargs: object) -> EmailSendResult:
        captured.append(str(kwargs["status"]))
        return EmailSendResult(sent=True, provider_message_id="test-alert-id")

    monkeypatch.setattr(
        payouts_module.ResendEmailService, "send_stale_withdrawal_alert_email", _fake_send
    )
    return captured


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


def _enable_payouts(ctx: SeededContext, *, tenant_id: UUID) -> None:
    ctx.new_settlement_config(tenant_id=tenant_id)
    ctx.new_tenant_feature_flags(tenant_id=tenant_id, payout_enabled=True)
    ctx.new_tenant_verification(tenant_id=tenant_id, status="APPROVED", email_verified=True)


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


def _create_stuck_processing_withdrawal(
    ctx: SeededContext,
    *,
    tenant_id: UUID,
    admin_id: UUID,
    owner_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
    capture_withdrawal_otp: list[str],
    minutes_ago: int,
) -> UUID:
    headers = auth_header(user_id=owner_id)
    _enable_payouts(ctx, tenant_id=tenant_id)
    asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))

    destination_id = client.post(
        "/api/v1/payouts/destinations",
        headers=headers,
        json={
            "label": "M-Pesa", "channel": "mobile_money",
            "destination_code": "MPESA", "account_number": "255700000000",
        },
    ).json()["data"]["id"]
    request_response = client.post(
        "/api/v1/payouts", headers=headers,
        json={"destination_id": destination_id, "amount": "600.00"},
    )
    withdrawal_id = request_response.json()["withdrawal"]["id"]
    code = capture_withdrawal_otp[-1]

    _fake_account_lookup(monkeypatch)
    _fake_transaction_process_inprogress(monkeypatch)
    confirm_response = client.post(
        f"/api/v1/payouts/{withdrawal_id}/confirm-2fa", headers=headers, json={"code": code}
    )
    assert confirm_response.json()["data"]["status"] == "PROCESSING"

    assert ctx._conn is not None
    with ctx._conn.cursor() as cur:
        cur.execute(
            "UPDATE withdrawals SET submitted_at = now() - (%s || ' minutes')::interval "
            "WHERE id = %s",
            (str(minutes_ago), withdrawal_id),
        )
    return UUID(withdrawal_id)


def test_no_alert_before_threshold(
    real_settings_override: None,
    monkeypatch: pytest.MonkeyPatch,
    capture_withdrawal_otp: list[str],
    capture_stale_alerts: list[str],
) -> None:
    monkeypatch.setenv("WITHDRAWAL_PROCESSING_ALERT_MINUTES", "30")
    get_settings.cache_clear()

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        withdrawal_id = _create_stuck_processing_withdrawal(
            ctx, tenant_id=tenant_id, admin_id=admin_id, owner_id=owner_id,
            monkeypatch=monkeypatch, capture_withdrawal_otp=capture_withdrawal_otp,
            minutes_ago=10,  # well under the 30-minute threshold
        )

        async def _check() -> bool:
            async with AsyncSessionLocal() as db:
                service = PayoutService(db)
                withdrawal = await service.repo.get_by_id(tenant_id=None, id=withdrawal_id)
                assert withdrawal is not None
                sent = await service.maybe_alert_stale(withdrawal)
                await db.commit()
                return sent

        sent = asyncio.run(_check())

    assert sent is False
    assert capture_stale_alerts == []


def test_alert_fires_once_threshold_is_reached(
    real_settings_override: None,
    monkeypatch: pytest.MonkeyPatch,
    capture_withdrawal_otp: list[str],
    capture_stale_alerts: list[str],
) -> None:
    monkeypatch.setenv("WITHDRAWAL_PROCESSING_ALERT_MINUTES", "30")
    get_settings.cache_clear()

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        withdrawal_id = _create_stuck_processing_withdrawal(
            ctx, tenant_id=tenant_id, admin_id=admin_id, owner_id=owner_id,
            monkeypatch=monkeypatch, capture_withdrawal_otp=capture_withdrawal_otp,
            minutes_ago=45,  # past the 30-minute threshold
        )

        async def _check() -> bool:
            async with AsyncSessionLocal() as db:
                service = PayoutService(db)
                withdrawal = await service.repo.get_by_id(tenant_id=None, id=withdrawal_id)
                assert withdrawal is not None
                sent = await service.maybe_alert_stale(withdrawal)
                await db.commit()
                return sent

        sent = asyncio.run(_check())

    assert sent is True
    assert capture_stale_alerts == ["PROCESSING"]


def test_no_duplicate_alert_within_cooldown(
    real_settings_override: None,
    monkeypatch: pytest.MonkeyPatch,
    capture_withdrawal_otp: list[str],
    capture_stale_alerts: list[str],
) -> None:
    """Simulates two consecutive Beat cycles both finding the same
    withdrawal still stuck — the second must not re-send."""
    monkeypatch.setenv("WITHDRAWAL_PROCESSING_ALERT_MINUTES", "30")
    monkeypatch.setenv("WITHDRAWAL_STALE_ALERT_COOLDOWN_MINUTES", "60")
    get_settings.cache_clear()

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        withdrawal_id = _create_stuck_processing_withdrawal(
            ctx, tenant_id=tenant_id, admin_id=admin_id, owner_id=owner_id,
            monkeypatch=monkeypatch, capture_withdrawal_otp=capture_withdrawal_otp,
            minutes_ago=45,
        )

        async def _check() -> bool:
            async with AsyncSessionLocal() as db:
                service = PayoutService(db)
                withdrawal = await service.repo.get_by_id(tenant_id=None, id=withdrawal_id)
                assert withdrawal is not None
                sent = await service.maybe_alert_stale(withdrawal)
                await db.commit()
                return sent

        first_sweep = asyncio.run(_check())
        second_sweep = asyncio.run(_check())  # "the next Beat cycle", 120s later in reality

    assert first_sweep is True
    assert second_sweep is False
    assert capture_stale_alerts == ["PROCESSING"]  # exactly one email total


def test_realerts_after_cooldown_expires(
    real_settings_override: None,
    monkeypatch: pytest.MonkeyPatch,
    capture_withdrawal_otp: list[str],
    capture_stale_alerts: list[str],
) -> None:
    monkeypatch.setenv("WITHDRAWAL_PROCESSING_ALERT_MINUTES", "30")
    monkeypatch.setenv("WITHDRAWAL_STALE_ALERT_COOLDOWN_MINUTES", "60")
    get_settings.cache_clear()

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        withdrawal_id = _create_stuck_processing_withdrawal(
            ctx, tenant_id=tenant_id, admin_id=admin_id, owner_id=owner_id,
            monkeypatch=monkeypatch, capture_withdrawal_otp=capture_withdrawal_otp,
            minutes_ago=45,
        )

        async def _check() -> bool:
            async with AsyncSessionLocal() as db:
                service = PayoutService(db)
                withdrawal = await service.repo.get_by_id(tenant_id=None, id=withdrawal_id)
                assert withdrawal is not None
                sent = await service.maybe_alert_stale(withdrawal)
                await db.commit()
                return sent

        first_sweep = asyncio.run(_check())

        # Back-date the alert we just sent past the cooldown window.
        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "UPDATE audit_logs SET created_at = now() - interval '61 minutes' "
                "WHERE action = 'withdrawal.stale_alert_sent' AND target_id = %s",
                (str(withdrawal_id),),
            )

        second_sweep = asyncio.run(_check())

    assert first_sweep is True
    assert second_sweep is True
    assert capture_stale_alerts == ["PROCESSING", "PROCESSING"]


def test_stale_alert_email_never_includes_raw_account_number(
    real_settings_override: None,
    monkeypatch: pytest.MonkeyPatch,
    capture_withdrawal_otp: list[str],
) -> None:
    """The template only ever receives withdrawal_id/tenant_name/amount/
    currency/status/provider_reference/stuck_minutes — never a destination
    account number at all (see app/integrations/resend/service.py's
    send_stale_withdrawal_alert_email signature)."""
    monkeypatch.setenv("WITHDRAWAL_PROCESSING_ALERT_MINUTES", "30")
    get_settings.cache_clear()

    captured_kwargs: dict[str, object] = {}

    async def _fake_send(self: object, **kwargs: object) -> EmailSendResult:
        captured_kwargs.update(kwargs)
        return EmailSendResult(sent=True, provider_message_id="test-alert-id")

    monkeypatch.setattr(
        payouts_module.ResendEmailService, "send_stale_withdrawal_alert_email", _fake_send
    )

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        withdrawal_id = _create_stuck_processing_withdrawal(
            ctx, tenant_id=tenant_id, admin_id=admin_id, owner_id=owner_id,
            monkeypatch=monkeypatch, capture_withdrawal_otp=capture_withdrawal_otp,
            minutes_ago=45,
        )

        async def _check() -> None:
            async with AsyncSessionLocal() as db:
                service = PayoutService(db)
                withdrawal = await service.repo.get_by_id(tenant_id=None, id=withdrawal_id)
                assert withdrawal is not None
                await service.maybe_alert_stale(withdrawal)
                await db.commit()

        asyncio.run(_check())

    assert "account_number" not in captured_kwargs
    assert "255700000000" not in str(captured_kwargs)
