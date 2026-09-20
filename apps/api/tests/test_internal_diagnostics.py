"""The internal RADIUS reachability diagnostic.

It exists to prove a three-hop chain before the first paying customer:

    Railway web --signed HMAC--> Network Agent --localhost--> RADIUS DB

The tests below pin the two properties that make it safe to have at all:
it is NOT publicly reachable, and it cannot mutate anything. A diagnostic
that could create a RADIUS user, or that anyone could call, would be a
worse problem than the gap it closes.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.internal_auth import sign_internal_request
from app.integrations.network_agent.client import (
    NetworkAgentClient,
    NetworkAgentError,
    NetworkAgentNotConfiguredError,
)
from app.main import app

client = TestClient(app)

_PATH = "/api/v1/internal/diagnostics/radius-ping"
_HMAC_KEY = "test-only-internal-hmac-key-do-not-use-in-prod"


@pytest.fixture(autouse=True)
def _internal_hmac_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INTERNAL_WORKER_WEB_HMAC_KEY", _HMAC_KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def internal_signed_headers(method: str, path: str, body: bytes) -> dict[str, str]:
    headers = sign_internal_request(
        secret=_HMAC_KEY, method=method, path=path, body=body
    ).as_dict()
    headers["Content-Type"] = "application/json"
    return headers


def _signed_post() -> Any:
    return client.post(
        _PATH, content=b"{}", headers=internal_signed_headers("POST", _PATH, b"{}")
    )


def _stub_client(monkeypatch: pytest.MonkeyPatch, *, radius: bool | Exception) -> None:
    """Replaces the agent client so no test ever touches a real VPS."""

    async def _aenter(self: NetworkAgentClient) -> NetworkAgentClient:
        return self

    async def _aexit(self: NetworkAgentClient, *_a: object) -> None:
        return None

    async def _ping(self: NetworkAgentClient) -> bool:
        if isinstance(radius, Exception):
            raise radius
        return radius

    monkeypatch.setattr(NetworkAgentClient, "__init__", lambda self: None)
    monkeypatch.setattr(NetworkAgentClient, "__aenter__", _aenter)
    monkeypatch.setattr(NetworkAgentClient, "__aexit__", _aexit)
    monkeypatch.setattr(NetworkAgentClient, "radius_ping", _ping)


def test_requires_internal_hmac_authentication() -> None:
    """Unsigned means rejected. This route must never be reachable the way
    the public captive endpoints are."""
    response = client.post(_PATH, json={})
    assert response.status_code in (401, 403)


def test_rejects_a_forged_signature() -> None:
    headers = internal_signed_headers("POST", _PATH, b"{}")
    headers["X-Internal-Signature"] = "0" * 64
    response = client.post(_PATH, content=b"{}", headers=headers)
    assert response.status_code in (401, 403)


def test_reports_success_when_the_whole_chain_is_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_client(monkeypatch, radius=True)
    response = _signed_post()
    assert response.status_code == 200
    body = response.json()
    assert body["agent_reachable"] is True
    assert body["radius_reachable"] is True


def test_distinguishes_agent_reachable_from_database_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two hops are reported separately on purpose: 'the agent
    answered but its database did not' is a completely different repair
    than 'the agent is unreachable'."""
    _stub_client(monkeypatch, radius=False)
    response = _signed_post()
    assert response.status_code == 200
    body = response.json()
    assert body["agent_reachable"] is True
    assert body["radius_reachable"] is False


def test_reports_failure_without_leaking_why(monkeypatch: pytest.MonkeyPatch) -> None:
    """A rejected signature, a blocked source IP and a missing route all
    look identical from outside — a diagnostic must not become a probe."""
    _stub_client(monkeypatch, radius=NetworkAgentError("403 Forbidden from 1.2.3.4"))
    response = _signed_post()
    assert response.status_code == 200
    body = response.json()
    assert body["agent_reachable"] is False
    assert body["radius_reachable"] is False
    assert "1.2.3.4" not in str(body)
    assert "403" not in str(body)


def test_handles_an_unconfigured_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_client(monkeypatch, radius=NetworkAgentNotConfiguredError("nope"))
    response = _signed_post()
    assert response.status_code == 200
    assert response.json()["agent_reachable"] is False


def test_response_carries_no_secrets_or_infrastructure_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_client(monkeypatch, radius=True)
    response = _signed_post()
    body: dict[str, Any] = response.json()
    # An exact field set — so adding a host, DSN or key later fails here.
    assert set(body) == {"agent_reachable", "radius_reachable", "detail"}
    blob = str(body).lower()
    for leak in ("postgres", "dsn", "password", "api_key", "signature", "127.0.0.1", "radius_app"):
        assert leak not in blob


def test_only_calls_the_non_mutating_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    """The endpoint must never reach a provisioning route. If someone
    later wires user/package-group in here, this fails."""
    called: list[str] = []

    async def _aenter(self: NetworkAgentClient) -> NetworkAgentClient:
        return self

    async def _aexit(self: NetworkAgentClient, *_a: object) -> None:
        return None

    async def _ping(self: NetworkAgentClient) -> bool:
        called.append("radius_ping")
        return True

    async def _forbidden(self: NetworkAgentClient, **_kw: object) -> None:
        raise AssertionError("diagnostic must never provision RADIUS")

    monkeypatch.setattr(NetworkAgentClient, "__init__", lambda self: None)
    monkeypatch.setattr(NetworkAgentClient, "__aenter__", _aenter)
    monkeypatch.setattr(NetworkAgentClient, "__aexit__", _aexit)
    monkeypatch.setattr(NetworkAgentClient, "radius_ping", _ping)
    monkeypatch.setattr(NetworkAgentClient, "provision_radius_user", _forbidden)
    monkeypatch.setattr(NetworkAgentClient, "sync_radius_package_group", _forbidden)
    monkeypatch.setattr(NetworkAgentClient, "revoke_radius_user", _forbidden)

    response = _signed_post()
    assert response.status_code == 200
    assert called == ["radius_ping"]
