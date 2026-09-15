"""POST /api/v1/routers/{id}/test-connection: the Railway -> HTTPS ->
Network Agent leg of the router-control path. There is no real Network
Agent/router in this test environment, so NetworkAgentClient is
monkeypatched at its own module boundary — the same class of exception
this project already makes for hardware/external-service dependencies
(see apps/network-agent's own MikroTik client tests). Everything about
OUR side (routing, auth, honest not-configured reporting) is exercised
for real.
"""

from types import TracebackType
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.integrations.network_agent.schemas import TestConnectionResult
from app.main import app
from app.services import network_routers
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


def _create_router(headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/routers", headers=headers, json={"name": "Test Router"}
    )
    assert response.status_code == 201
    return str(response.json()["data"]["id"])


def test_reports_not_configured_when_network_agent_settings_are_unset() -> None:
    """NETWORK_AGENT_BASE_URL/NETWORK_AGENT_API_KEY are unset in this test
    environment — the endpoint must report that honestly, never fabricate
    a fake "reachable" result."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        router_id = _create_router(headers)
        response = client.post(f"/api/v1/routers/{router_id}/test-connection", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reachable"] is False
    assert data["detail"] is not None


def test_reports_reachable_when_network_agent_confirms_it(monkeypatch: pytest.MonkeyPatch) -> None:
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

        async def test_connection(self, *, router_id: UUID) -> TestConnectionResult:
            return TestConnectionResult(reachable=True, latency_ms=8.5)

    monkeypatch.setattr(network_routers, "NetworkAgentClient", _FakeClient)

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        router_id = _create_router(headers)
        response = client.post(f"/api/v1/routers/{router_id}/test-connection", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reachable"] is True
    assert data["latency_ms"] == 8.5


def test_unknown_router_id_404s() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        response = client.post(f"/api/v1/routers/{uuid4()}/test-connection", headers=headers)

    assert response.status_code == 404


def test_customer_care_cannot_test_router_connection() -> None:
    """Only NETWORK_ROLES may trigger a router connection test."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        care = ctx.new_user(role_code="CUSTOMER_CARE", tenant_id=tenant_id)
        router_id = _create_router(auth_header(user_id=admin))

        response = client.post(
            f"/api/v1/routers/{router_id}/test-connection", headers=auth_header(user_id=care)
        )

    assert response.status_code == 403
