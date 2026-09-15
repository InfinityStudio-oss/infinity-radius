"""Endpoint wiring for app/routers/mikrotik.py: auth enforcement, router-id
resolution (404 for unknown UUIDs — never an arbitrary host), and response
shaping. The MikroTik RouterOS API calls themselves are monkeypatched at
the app.services.mikrotik_client boundary — there is no real router to
test against, the same class of exception this project already makes for
Selcom/hardware dependencies. Everything about THIS agent's own protocol
(signing, routing, error handling) is exercised for real.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.router_registry import RouterConnection, get_router_registry
from app.main import app
from app.schemas.mikrotik import (
    DisconnectResult,
    RouterIdentity,
    RouterResource,
    TestConnectionResult,
)
from app.services import mikrotik_client
from tests.signing_helpers import sign

CURRENT_KEY = "test-agent-key-current"
KNOWN_ROUTER_ID = uuid4()
_CONNECTION = RouterConnection(
    router_id=KNOWN_ROUTER_ID, host="10.90.0.2", username="agent", password="secret"
)


class _FakeRegistry:
    def resolve(self, router_id: UUID) -> RouterConnection | None:
        if router_id == KNOWN_ROUTER_ID:
            return _CONNECTION
        return None


@pytest.fixture(autouse=True)
def _override_registry() -> Iterator[None]:
    app.dependency_overrides[get_router_registry] = lambda: _FakeRegistry()
    yield
    app.dependency_overrides.pop(get_router_registry, None)


client = TestClient(app)


def _signed_post(path: str, *, body: bytes = b"") -> dict[str, str]:
    headers = sign(key=CURRENT_KEY, method="POST", path=path, body=body)
    if body:
        headers["Content-Type"] = "application/json"
    return headers


def _signed_get(path: str) -> dict[str, str]:
    return sign(key=CURRENT_KEY, method="GET", path=path)


def test_unsigned_request_is_rejected() -> None:
    response = client.post(f"/routers/{KNOWN_ROUTER_ID}/test")
    assert response.status_code == 401


def test_unknown_router_id_returns_404_never_an_arbitrary_connection() -> None:
    unknown_id = uuid4()
    headers = _signed_post(f"/routers/{unknown_id}/test")
    response = client.post(f"/routers/{unknown_id}/test", headers=headers)
    assert response.status_code == 404


def test_test_router_returns_reachability_result(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_test_connection(conn: RouterConnection) -> TestConnectionResult:
        assert conn.router_id == KNOWN_ROUTER_ID
        return TestConnectionResult(reachable=True, latency_ms=12.3)

    monkeypatch.setattr(mikrotik_client, "test_connection", fake_test_connection)

    path = f"/routers/{KNOWN_ROUTER_ID}/test"
    response = client.post(path, headers=_signed_post(path))

    assert response.status_code == 200
    assert response.json() == {"reachable": True, "latency_ms": 12.3, "detail": None}


def test_get_identity_returns_router_name(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_identity(conn: RouterConnection) -> RouterIdentity:
        return RouterIdentity(name="hotspot-kariakoo-1")

    monkeypatch.setattr(mikrotik_client, "get_identity", fake_get_identity)

    path = f"/routers/{KNOWN_ROUTER_ID}/identity"
    response = client.get(path, headers=_signed_get(path))

    assert response.status_code == 200
    assert response.json() == {"name": "hotspot-kariakoo-1"}


def test_get_resource_returns_version_cpu_memory_uptime(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_resource(conn: RouterConnection) -> RouterResource:
        return RouterResource(
            routeros_version="7.15 (stable)",
            board_name="RB750Gr3",
            cpu_load_percent=7,
            free_memory_bytes=123_456,
            total_memory_bytes=256_000,
            uptime="3d4h5m",
        )

    monkeypatch.setattr(mikrotik_client, "get_resource", fake_get_resource)

    path = f"/routers/{KNOWN_ROUTER_ID}/resource"
    response = client.get(path, headers=_signed_get(path))

    assert response.status_code == 200
    body = response.json()
    assert body["routeros_version"] == "7.15 (stable)"
    assert body["cpu_load_percent"] == 7
    assert body["uptime"] == "3d4h5m"


def test_disconnect_hotspot_user_passes_session_id_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    async def fake_disconnect(conn: RouterConnection, session_id: str) -> DisconnectResult:
        captured["session_id"] = session_id
        return DisconnectResult(disconnected=True)

    monkeypatch.setattr(mikrotik_client, "disconnect_hotspot_user", fake_disconnect)

    path = f"/routers/{KNOWN_ROUTER_ID}/hotspot/disconnect"
    body = b'{"session_id": "*3"}'
    response = client.post(path, headers=_signed_post(path, body=body), content=body)

    assert response.status_code == 200
    assert response.json() == {"disconnected": True, "detail": None}
    assert captured["session_id"] == "*3"


def test_router_os_error_is_reported_as_bad_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_identity(conn: RouterConnection) -> RouterIdentity:
        raise mikrotik_client.RouterOSError("connection refused")

    monkeypatch.setattr(mikrotik_client, "get_identity", fake_get_identity)

    path = f"/routers/{KNOWN_ROUTER_ID}/identity"
    response = client.get(path, headers=_signed_get(path))

    assert response.status_code == 502
