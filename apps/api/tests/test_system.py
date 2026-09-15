from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.v1.system import DependencyHealth
from app.main import app

client = TestClient(app)


def test_health_reports_not_configured_network_agent() -> None:
    with (
        patch(
            "app.api.v1.system._check_database",
            new=AsyncMock(return_value=DependencyHealth(status="ok")),
        ),
        patch(
            "app.api.v1.system._check_redis",
            new=AsyncMock(return_value=DependencyHealth(status="ok")),
        ),
    ):
        response = client.get("/api/v1/system/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["status"] == "ok"
    assert body["redis"]["status"] == "ok"
    assert body["network_agent"]["status"] == "not_configured"


def test_health_database_endpoint_reports_real_status() -> None:
    response = client.get("/api/v1/system/health/database")

    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "error"}


def test_health_redis_endpoint_reports_real_status() -> None:
    response = client.get("/api/v1/system/health/redis")

    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "error"}


def test_root_endpoint() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_response_carries_request_id_header() -> None:
    response = client.get("/api/v1/system/health/database")

    assert "x-request-id" in response.headers


def test_inbound_request_id_is_echoed_back() -> None:
    response = client.get(
        "/api/v1/system/health/database", headers={"X-Request-ID": "test-fixed-id"}
    )

    assert response.headers["x-request-id"] == "test-fixed-id"
