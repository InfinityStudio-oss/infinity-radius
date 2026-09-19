"""POST /api/v1/admin/diagnostics/network-agent and .../selcom-business:
SUPER_ADMIN-only connectivity probes. There is no real Network Agent/
Selcom sandbox reachable from this test environment, so both clients are
monkeypatched at their own module boundary, same as
tests/test_routers_test_connection.py.
"""

from collections.abc import Iterator
from types import TracebackType

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import admin_diagnostics
from app.core.config import get_settings
from app.integrations.selcom_business.client import SelcomBusinessClient
from app.integrations.selcom_business.schemas import (
    AccountLookupResponse,
    BalanceData,
    BalanceResponse,
)
from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)

URL = "/api/v1/admin/diagnostics/network-agent"
SELCOM_URL = "/api/v1/admin/diagnostics/selcom-business"


@pytest.fixture
def real_settings_override(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_requires_authentication() -> None:
    response = client.post(URL)
    assert response.status_code == 401


def test_non_super_admin_is_forbidden() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.post(URL, headers=auth_header(user_id=user_id))
    assert response.status_code == 403


def test_reports_not_configured_when_network_agent_settings_are_unset() -> None:
    """NETWORK_AGENT_BASE_URL/NETWORK_AGENT_API_KEY are unset in this test
    environment — the endpoint must report that honestly, never fabricate
    a fake "reachable" result."""
    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.post(URL, headers=auth_header(user_id=admin_id))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reachable"] is False
    assert data["authenticated"] is False
    assert data["detail"] is not None


def test_reports_authenticated_when_network_agent_accepts_the_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeClient:
        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            return None

        async def diagnostic_ping(self) -> tuple[bool, int]:
            return True, 404

    monkeypatch.setattr(admin_diagnostics, "NetworkAgentClient", _FakeClient)

    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.post(URL, headers=auth_header(user_id=admin_id))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reachable"] is True
    assert data["authenticated"] is True
    assert data["status_code"] == 404


def test_reports_unauthenticated_when_network_agent_rejects_the_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeClient:
        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            return None

        async def diagnostic_ping(self) -> tuple[bool, int]:
            return False, 401

    monkeypatch.setattr(admin_diagnostics, "NetworkAgentClient", _FakeClient)

    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.post(URL, headers=auth_header(user_id=admin_id))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reachable"] is True
    assert data["authenticated"] is False
    assert data["status_code"] == 401


def test_response_never_includes_the_api_key_or_signing_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeClient:
        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            return None

        async def diagnostic_ping(self) -> tuple[bool, int]:
            return True, 404

    monkeypatch.setattr(admin_diagnostics, "NetworkAgentClient", _FakeClient)

    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.post(URL, headers=auth_header(user_id=admin_id))
    body = response.json()
    assert set(body["data"].keys()) == {"reachable", "authenticated", "status_code", "detail"}


# --------------------------------------------------------- Selcom Business


def test_selcom_business_requires_authentication() -> None:
    response = client.post(SELCOM_URL)
    assert response.status_code == 401


def test_selcom_business_non_super_admin_is_forbidden() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.post(SELCOM_URL, headers=auth_header(user_id=user_id))
    assert response.status_code == 403


def test_selcom_business_reports_not_configured_when_unset() -> None:
    """SELCOM_BUSINESS_* is unset in this test environment — must report
    honestly, never fabricate a fake "reachable" result."""
    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.post(SELCOM_URL, headers=auth_header(user_id=admin_id))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["configured"] is False
    assert data["reachable"] is False


def test_selcom_business_production_environment_refuses_to_call_sandbox_test_account(
    real_settings_override: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Environment-aware safety: SELCOM_BUSINESS_ENVIRONMENT=production
    must never fire Selcom's SANDBOX sample test account against a real
    production endpoint — this must refuse closed with no request sent,
    never guess a "safe" production account that isn't documented."""
    monkeypatch.setenv("SELCOM_BUSINESS_ENVIRONMENT", "production")
    monkeypatch.setenv("SELCOM_BUSINESS_BASE_URL", "https://api.selcom.business")
    monkeypatch.setenv("SELCOM_BUSINESS_API_KEY", "test-key-never-real")
    monkeypatch.setenv(
        "SELCOM_BUSINESS_PRIVATE_KEY_B64",
        __import__("base64").b64encode(b"not-a-real-pem-just-passes-is_configured").decode(),
    )
    get_settings.cache_clear()

    async def _fail_if_called(self: SelcomBusinessClient, **kwargs: object) -> None:
        raise AssertionError("account_lookup must never be called against production here")

    monkeypatch.setattr(SelcomBusinessClient, "account_lookup", _fail_if_called)

    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        response = client.post(SELCOM_URL, headers=auth_header(user_id=admin_id))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["configured"] is True
    assert data["environment"] == "production"
    assert data["reachable"] is False
    assert "sandbox" in data["detail"].lower()


def test_selcom_business_sandbox_environment_proceeds_to_the_real_call(
    real_settings_override: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mirror case — sandbox (the real, unmodified default in this
    test environment) is exactly what this diagnostic is for, so it must
    still reach the client."""
    monkeypatch.setenv("SELCOM_BUSINESS_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("SELCOM_BUSINESS_BASE_URL", "https://sandbox.selcom.business")
    monkeypatch.setenv("SELCOM_BUSINESS_API_KEY", "test-key-never-real")
    monkeypatch.setenv(
        "SELCOM_BUSINESS_PRIVATE_KEY_B64",
        __import__("base64").b64encode(b"not-a-real-pem-just-passes-is_configured").decode(),
    )
    get_settings.cache_clear()

    async def _fake_lookup(self: SelcomBusinessClient, **kwargs: object) -> AccountLookupResponse:
        return AccountLookupResponse(success=True, resultcode="000", message="ok")

    monkeypatch.setattr(SelcomBusinessClient, "account_lookup", _fake_lookup)

    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        response = client.post(SELCOM_URL, headers=auth_header(user_id=admin_id))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reachable"] is True
    assert data["resultcode"] == "000"


def test_selcom_business_diagnostic_never_returns_api_key_or_private_key(
    real_settings_override: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SELCOM_BUSINESS_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("SELCOM_BUSINESS_BASE_URL", "https://sandbox.selcom.business")
    monkeypatch.setenv("SELCOM_BUSINESS_API_KEY", "test-key-never-real")
    monkeypatch.setenv(
        "SELCOM_BUSINESS_PRIVATE_KEY_B64",
        __import__("base64").b64encode(b"not-a-real-pem-just-passes-is_configured").decode(),
    )
    get_settings.cache_clear()

    async def _fake_lookup(self: SelcomBusinessClient, **kwargs: object) -> AccountLookupResponse:
        return AccountLookupResponse(success=True, resultcode="000", message="ok")

    monkeypatch.setattr(SelcomBusinessClient, "account_lookup", _fake_lookup)

    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        response = client.post(SELCOM_URL, headers=auth_header(user_id=admin_id))

    body = response.json()
    assert set(body["data"].keys()) == {
        "configured", "environment", "reachable", "resultcode", "message", "detail",
    }
    assert "test-key-never-real" not in str(body)


# ------------------------------------------------ Selcom Provider Balance


BALANCE_URL = "/api/v1/admin/diagnostics/selcom-business/provider-balance"


def test_provider_balance_requires_authentication() -> None:
    response = client.post(BALANCE_URL)
    assert response.status_code == 401


def test_provider_balance_non_super_admin_is_forbidden() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.post(BALANCE_URL, headers=auth_header(user_id=user_id))
    assert response.status_code == 403


def test_provider_balance_reports_not_configured_when_unset() -> None:
    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        response = client.post(BALANCE_URL, headers=auth_header(user_id=admin_id))
    assert response.status_code == 200
    assert response.json()["data"]["configured"] is False


def test_provider_balance_masks_the_account_number_and_never_leaks_credentials(
    real_settings_override: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SELCOM_BUSINESS_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("SELCOM_BUSINESS_BASE_URL", "https://sandbox.selcom.business")
    monkeypatch.setenv("SELCOM_BUSINESS_API_KEY", "test-key-never-real")
    monkeypatch.setenv("SELCOM_BUSINESS_ACCOUNT_NUMBER", "8774738353235")
    monkeypatch.setenv(
        "SELCOM_BUSINESS_PRIVATE_KEY_B64",
        __import__("base64").b64encode(b"not-a-real-pem-just-passes-is_configured").decode(),
    )
    get_settings.cache_clear()

    async def _fake_balance(self: SelcomBusinessClient, **kwargs: object) -> BalanceResponse:
        return BalanceResponse(
            success=True,
            resultcode="000",
            data=BalanceData(available_balance="500000.00", currency="TZS"),
        )

    monkeypatch.setattr(SelcomBusinessClient, "balance", _fake_balance)

    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        response = client.post(BALANCE_URL, headers=auth_header(user_id=admin_id))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["configured"] is True
    assert data["available_balance"] == "500000.00"
    assert data["masked_account_number"] == "*********3235"
    assert "8774738353235" not in str(response.json())
    assert "test-key-never-real" not in str(response.json())


def test_provider_balance_production_environment_proceeds_to_the_real_call(
    real_settings_override: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unlike the account-lookup diagnostic (which uses a hardcoded
    sandbox-only test account and must never run in production), the
    balance check always queries whichever account_number is actually
    configured — safe, read-only, and correct in either environment. This
    is the non-money-moving production connectivity check the production
    activation runbook relies on."""
    monkeypatch.setenv("SELCOM_BUSINESS_ENVIRONMENT", "production")
    monkeypatch.setenv("SELCOM_BUSINESS_BASE_URL", "https://api.selcom.business")
    monkeypatch.setenv("SELCOM_BUSINESS_API_KEY", "test-key-never-real")
    monkeypatch.setenv("SELCOM_BUSINESS_ACCOUNT_NUMBER", "5529108708283")
    monkeypatch.setenv(
        "SELCOM_BUSINESS_PRIVATE_KEY_B64",
        __import__("base64").b64encode(b"not-a-real-pem-just-passes-is_configured").decode(),
    )
    get_settings.cache_clear()

    async def _fake_balance(self: SelcomBusinessClient, **kwargs: object) -> BalanceResponse:
        return BalanceResponse(
            success=True,
            resultcode="000",
            data=BalanceData(available_balance="1250000.00", currency="TZS"),
        )

    monkeypatch.setattr(SelcomBusinessClient, "balance", _fake_balance)

    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        response = client.post(BALANCE_URL, headers=auth_header(user_id=admin_id))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["configured"] is True
    assert data["environment"] == "production"
    assert data["available_balance"] == "1250000.00"
    assert data["masked_account_number"] == "*********8283"
    assert "5529108708283" not in str(response.json())
    assert "test-key-never-real" not in str(response.json())
