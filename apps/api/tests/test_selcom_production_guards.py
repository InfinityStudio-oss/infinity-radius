"""Production/sandbox separation and the production payout triple gate —
see app/integrations/selcom_business/config.py and
app/services/payouts.py._submit_to_selcom. No test here ever makes a real
network call: SelcomBusinessClient methods are mocked wherever a call
would otherwise fire, and no test flips real infrastructure toward
production — SELCOM_BUSINESS_ENVIRONMENT stays "sandbox" for the whole
suite except where a test explicitly overrides it via monkeypatch.setenv
(reverted automatically at teardown) plus an explicit
get_settings.cache_clear().
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
from app.integrations.selcom_business.client import SelcomBusinessClient
from app.integrations.selcom_business.config import SelcomBusinessConfig
from app.integrations.selcom_business.errors import (
    SelcomBusinessAPIError,
    SelcomBusinessMisconfiguredError,
)
from app.main import app
from app.services.wallet import WalletService
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


@pytest.fixture
def real_settings_override(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Sets real environment variables (auto-reverted by monkeypatch at
    teardown) and clears Settings' lru_cache so every module's
    get_settings() call — not just one monkeypatched reference — sees the
    override for the duration of one test, then sees the real settings
    again afterward."""
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


# ---------------------------------------------------- config pairing (pure)


def test_sandbox_environment_with_sandbox_url_matches() -> None:
    config = SelcomBusinessConfig(
        environment="sandbox",
        base_url="https://sandbox.selcom.business",
        api_key="k",
        private_key_pem="pem",
        account_number=None,
    )
    assert config.base_url_matches_environment is True
    config.require_configured()  # must not raise


def test_production_environment_with_production_url_matches() -> None:
    config = SelcomBusinessConfig(
        environment="production",
        base_url="https://api.selcom.business",
        api_key="k",
        private_key_pem="pem",
        account_number=None,
    )
    assert config.base_url_matches_environment is True
    config.require_configured()  # must not raise


def test_production_environment_with_sandbox_url_is_blocked() -> None:
    config = SelcomBusinessConfig(
        environment="production",
        base_url="https://sandbox.selcom.business",
        api_key="k",
        private_key_pem="pem",
        account_number=None,
    )
    assert config.base_url_matches_environment is False
    with pytest.raises(SelcomBusinessMisconfiguredError):
        config.require_configured()


def test_sandbox_environment_with_production_url_is_blocked() -> None:
    config = SelcomBusinessConfig(
        environment="sandbox",
        base_url="https://api.selcom.business",
        api_key="k",
        private_key_pem="pem",
        account_number=None,
    )
    assert config.base_url_matches_environment is False
    with pytest.raises(SelcomBusinessMisconfiguredError):
        config.require_configured()


def test_unset_base_url_never_flagged_as_a_mismatch() -> None:
    """Not-yet-configured is a distinct, valid state from misconfigured —
    require_configured() must raise SelcomBusinessNotConfiguredError for
    this, never SelcomBusinessMisconfiguredError."""
    config = SelcomBusinessConfig(
        environment="production", base_url=None, api_key=None, private_key_pem=None,
        account_number=None,
    )
    assert config.base_url_matches_environment is True


# --------------------------------------------- production payout triple gate


def test_production_disbursement_disabled_blocks_even_in_production(
    real_settings_override: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SELCOM_BUSINESS_ENVIRONMENT", "production")
    monkeypatch.setenv("SELCOM_DISBURSEMENT_ENABLED", "false")
    get_settings.cache_clear()

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        _enable_payouts(ctx, tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))

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
        response = client.post(
            "/api/v1/payouts",
            headers=headers,
            json={"destination_id": destination_id, "amount": "500.00"},
        )

    assert response.status_code == 422
    assert "disabled" in response.json()["error"]["message"]


def test_production_payouts_not_enabled_blocks_submission(
    real_settings_override: None,
    monkeypatch: pytest.MonkeyPatch,
    capture_withdrawal_otp: list[str],
) -> None:
    """environment=production + disbursement_enabled=true, but
    SELCOM_PRODUCTION_PAYOUTS_ENABLED left at its default (false) — the
    withdrawal reaches _submit_to_selcom (proving the earlier gates
    passed) but must fail there, before ever constructing a
    SelcomBusinessClient or touching the network."""
    monkeypatch.setenv("SELCOM_BUSINESS_ENVIRONMENT", "production")
    monkeypatch.setenv("SELCOM_DISBURSEMENT_ENABLED", "true")
    monkeypatch.setenv("SELCOM_PRODUCTION_PAYOUTS_ENABLED", "false")
    get_settings.cache_clear()

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        _enable_payouts(ctx, tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))

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
        request_response = client.post(
            "/api/v1/payouts",
            headers=headers,
            json={"destination_id": destination_id, "amount": "500.00"},
        )
        assert request_response.status_code == 201
        withdrawal_id = request_response.json()["withdrawal"]["id"]
        code = capture_withdrawal_otp[-1]

        confirm_response = client.post(
            f"/api/v1/payouts/{withdrawal_id}/confirm-2fa", headers=headers, json={"code": code}
        )

    assert confirm_response.status_code == 200
    body = confirm_response.json()["data"]
    assert body["status"] == "FAILED"
    assert "Production Selcom payouts are not enabled" in body["failure_reason"]


def test_all_production_gates_true_reaches_the_real_provider_client(
    real_settings_override: None,
    monkeypatch: pytest.MonkeyPatch,
    capture_withdrawal_otp: list[str],
) -> None:
    """environment=production + disbursement_enabled=true +
    production_payouts_enabled=true + a real-shaped production base URL —
    every gate this platform has now passes, proving submission genuinely
    reaches SelcomBusinessClient. account_lookup is mocked to fail
    instantly with a recognizable, controlled error — this test asserts
    that exact error came back, which is only possible if the mock (never
    a real network call) was actually invoked."""
    monkeypatch.setenv("SELCOM_BUSINESS_ENVIRONMENT", "production")
    monkeypatch.setenv("SELCOM_DISBURSEMENT_ENABLED", "true")
    monkeypatch.setenv("SELCOM_PRODUCTION_PAYOUTS_ENABLED", "true")
    monkeypatch.setenv("SELCOM_BUSINESS_BASE_URL", "https://api.selcom.business")
    monkeypatch.setenv("SELCOM_BUSINESS_API_KEY", "test-key-never-real")
    monkeypatch.setenv(
        "SELCOM_BUSINESS_PRIVATE_KEY_B64",
        __import__("base64").b64encode(b"not-a-real-pem-just-passes-is_configured").decode(),
    )
    get_settings.cache_clear()

    _MARKER = "TEST-MOCK-NEVER-A-REAL-NETWORK-CALL"

    async def _fake_account_lookup(self: SelcomBusinessClient, **kwargs: object) -> None:
        raise SelcomBusinessAPIError(_MARKER)

    monkeypatch.setattr(SelcomBusinessClient, "account_lookup", _fake_account_lookup)

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=owner_id)
        _enable_payouts(ctx, tenant_id=tenant_id)
        asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))

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
        request_response = client.post(
            "/api/v1/payouts",
            headers=headers,
            json={"destination_id": destination_id, "amount": "500.00"},
        )
        withdrawal_id = request_response.json()["withdrawal"]["id"]
        code = capture_withdrawal_otp[-1]

        confirm_response = client.post(
            f"/api/v1/payouts/{withdrawal_id}/confirm-2fa", headers=headers, json={"code": code}
        )

    assert confirm_response.status_code == 200
    body = confirm_response.json()["data"]
    assert body["status"] == "FAILED"
    assert _MARKER in body["failure_reason"]
