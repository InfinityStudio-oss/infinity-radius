"""Withdrawal safety limits (app/services/payouts.py._enforce_withdrawal_limits)
— every limit is None/disabled by default (no product policy has been
decided), so these tests explicitly opt each one in via monkeypatch.setenv
+ get_settings.cache_clear() and never assume a limit is active outside
their own test. Decimal throughout — never float.
"""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.enums import LedgerDirection, WalletBucket
from app.db.session import AsyncSessionLocal
from app.main import app
from app.services.wallet import WalletService
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


@pytest.fixture
def real_settings_override(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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


def _request(headers: dict[str, str], destination_id: str, amount: str) -> httpx.Response:
    return client.post(
        "/api/v1/payouts",
        headers=headers,
        json={"destination_id": destination_id, "amount": amount},
    )


@pytest.mark.parametrize(
    ("amount", "expect_allowed"),
    [
        ("500.00", False),  # below minimum
        ("1000.00", True),  # at minimum
        ("5000.00", True),  # normal
        ("50000.00", True),  # at maximum
        ("50000.01", False),  # above maximum
    ],
)
def test_min_and_max_single_amount_limits(
    real_settings_override: None,
    monkeypatch: pytest.MonkeyPatch,
    amount: str,
    expect_allowed: bool,
) -> None:
    monkeypatch.setenv("WITHDRAWAL_MIN_AMOUNT_TZS", "1000")
    monkeypatch.setenv("WITHDRAWAL_MAX_SINGLE_AMOUNT_TZS", "50000")
    get_settings.cache_clear()

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        _enable_payouts(ctx, tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000000.00"))

        destination_id = client.post(
            "/api/v1/payouts/destinations",
            headers=headers,
            json={
                "label": "M-Pesa",
                "channel": "mobile_money",
                "destination_code": "MPESA",
                "account_number": "255700000000",
            },
        ).json()["data"]["id"]
        response = _request(headers, destination_id, amount)

    if expect_allowed:
        assert response.status_code == 201
    else:
        assert response.status_code == 422
        assert "minimum" in response.json()["error"]["message"] or "maximum" in response.json()[
            "error"
        ]["message"]


def test_daily_amount_limit_blocks_once_exceeded(
    real_settings_override: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WITHDRAWAL_DAILY_LIMIT_TZS", "10000")
    get_settings.cache_clear()

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        _enable_payouts(ctx, tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000000.00"))

        destination_id = client.post(
            "/api/v1/payouts/destinations",
            headers=headers,
            json={
                "label": "M-Pesa",
                "channel": "mobile_money",
                "destination_code": "MPESA",
                "account_number": "255700000000",
            },
        ).json()["data"]["id"]

        # Exactly at the daily limit — allowed.
        first = _request(headers, destination_id, "6000.00")
        second_at_boundary = _request(headers, destination_id, "4000.00")
        # One more shilling over the (now-exhausted) daily limit — blocked.
        third_over = _request(headers, destination_id, "1.00")

    assert first.status_code == 201
    assert second_at_boundary.status_code == 201
    assert third_over.status_code == 422
    assert "limit" in third_over.json()["error"]["message"].lower()


def test_daily_count_limit_blocks_once_exceeded(
    real_settings_override: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WITHDRAWAL_DAILY_COUNT_LIMIT", "2")
    get_settings.cache_clear()

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        _enable_payouts(ctx, tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000000.00"))

        destination_id = client.post(
            "/api/v1/payouts/destinations",
            headers=headers,
            json={
                "label": "M-Pesa",
                "channel": "mobile_money",
                "destination_code": "MPESA",
                "account_number": "255700000000",
            },
        ).json()["data"]["id"]

        first = _request(headers, destination_id, "100.00")
        second = _request(headers, destination_id, "100.00")
        third = _request(headers, destination_id, "100.00")

    assert first.status_code == 201
    assert second.status_code == 201
    assert third.status_code == 422
    assert "limit" in third.json()["error"]["message"].lower()


def test_limits_disabled_by_default() -> None:
    """No monkeypatched env here at all — the real, unmodified test
    settings (every withdrawal_*_limit_* is None) must never block a
    large, otherwise-normal withdrawal."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        _enable_payouts(ctx, tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "10000000.00"))

        destination_id = client.post(
            "/api/v1/payouts/destinations",
            headers=headers,
            json={
                "label": "M-Pesa",
                "channel": "mobile_money",
                "destination_code": "MPESA",
                "account_number": "255700000000",
            },
        ).json()["data"]["id"]
        response = _request(headers, destination_id, "5000000.00")

    assert response.status_code == 201
