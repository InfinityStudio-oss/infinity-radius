from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


def test_me_requires_auth() -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_returns_tenant_and_roles_resolved_from_database() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant(name="Acme Hotspots")
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.get("/api/v1/auth/me", headers=auth_header(user_id=user_id))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == str(user_id)
    assert data["tenant_id"] == str(tenant_id)
    assert data["tenant_name"] == "Acme Hotspots"
    assert data["roles"] == ["TENANT_ADMIN"]


def test_me_for_super_admin_has_no_tenant() -> None:
    with SeededContext() as ctx:
        user_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.get("/api/v1/auth/me", headers=auth_header(user_id=user_id))

    data = response.json()["data"]
    assert data["tenant_id"] is None
    assert data["tenant_name"] is None
    assert data["roles"] == ["SUPER_ADMIN"]
