"""Every error response, regardless of what raised it, comes back in the
same {"success": false, "error": {code, message, request_id}} envelope."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


def test_not_found_error_envelope() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.get(
            f"/api/v1/customers/{uuid4()}", headers=auth_header(user_id=user_id)
        )

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "not_found"
    assert "request_id" in body["error"]


def test_unauthorized_error_envelope() -> None:
    response = client.get("/api/v1/customers")

    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "unauthorized"


def test_forbidden_error_envelope_for_platform_only_account_on_tenant_route() -> None:
    with SeededContext() as ctx:
        user_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.get("/api/v1/customers", headers=auth_header(user_id=user_id))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_validation_error_envelope_on_malformed_body() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.post(
            "/api/v1/customers",
            headers=auth_header(user_id=user_id),
            json={"first_name": "Test", "last_name": "Customer", "email": None},  # missing `phone`
        )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "validation_error"
    assert "phone" in body["error"]["message"]
