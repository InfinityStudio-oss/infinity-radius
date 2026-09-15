"""POST /api/v1/admin/diagnostics/network-agent: SUPER_ADMIN-only probe of
the Railway -> Network Agent signed-request path. There is no real Network
Agent in this test environment, so NetworkAgentClient is monkeypatched at
its own module boundary, same as tests/test_routers_test_connection.py.
"""

from types import TracebackType

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import admin_diagnostics
from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)

URL = "/api/v1/admin/diagnostics/network-agent"


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
