from fastapi.testclient import TestClient

from app.main import app


def test_health_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["wireguard"]["status"] in {"up", "down", "unavailable"}
    assert body["freeradius"]["status"] in {"active", "inactive", "unavailable"}
    assert body["radius_db"]["status"] in {"active", "inactive", "unavailable"}
