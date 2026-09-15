from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


def test_overview_requires_auth() -> None:
    response = client.get("/api/v1/tenant/overview")
    assert response.status_code == 401


def test_overview_rejects_customer_role() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="CUSTOMER", tenant_id=tenant_id)

        response = client.get("/api/v1/tenant/overview", headers=auth_header(user_id=user_id))

    assert response.status_code == 403


def test_overview_reports_not_configured_metrics_for_real_seeded_tenant_admin() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.get("/api/v1/tenant/overview", headers=auth_header(user_id=user_id))

    assert response.status_code == 200
    body = response.json()
    assert body["customers_total"]["status"] == "not_configured"
    assert body["customers_total"]["value"] is None


def test_list_known_resource_returns_empty() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="CASHIER", tenant_id=tenant_id)

        response = client.get(
            "/api/v1/tenant/resources/customers",
            headers=auth_header(user_id=user_id),
        )

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "status": "not_configured"}


def test_list_unknown_resource_404s() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)

        response = client.get(
            "/api/v1/tenant/resources/does-not-exist",
            headers=auth_header(user_id=user_id),
        )

    assert response.status_code == 404


def test_unrecognized_user_id_is_rejected() -> None:
    """A well-signed token whose `sub` matches no profiles row must be
    denied — tenant_id is never trusted from the token itself."""
    from uuid import uuid4

    response = client.get(
        "/api/v1/tenant/overview",
        headers=auth_header(user_id=uuid4()),
    )
    assert response.status_code == 403
