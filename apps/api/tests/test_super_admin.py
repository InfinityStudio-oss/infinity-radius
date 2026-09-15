from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


def test_overview_rejects_tenant_admin() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.get("/api/v1/super-admin/overview", headers=auth_header(user_id=user_id))

    assert response.status_code == 403


def test_overview_reports_not_configured_metrics() -> None:
    with SeededContext() as ctx:
        user_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.get("/api/v1/super-admin/overview", headers=auth_header(user_id=user_id))

    assert response.status_code == 200
    body = response.json()
    assert body["tenants_total"]["status"] == "not_configured"


def test_system_health_reports_not_configured() -> None:
    with SeededContext() as ctx:
        user_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.get(
            "/api/v1/super-admin/system-health",
            headers=auth_header(user_id=user_id),
        )

    assert response.status_code == 200
    body = response.json()
    assert all(metric["status"] == "not_configured" for metric in body.values())


def test_list_known_resource_returns_empty() -> None:
    with SeededContext() as ctx:
        user_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.get(
            "/api/v1/super-admin/resources/tenants",
            headers=auth_header(user_id=user_id),
        )

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "status": "not_configured"}
