from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


def _create_customer(headers: dict[str, str], *, phone: str = "0712345678") -> str:
    response = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"first_name": "Sub", "last_name": "Scriber", "phone": phone},
    )
    assert response.status_code == 201
    return str(response.json()["data"]["id"])


def _create_package(
    headers: dict[str, str], *, activation_type: str = "immediate", duration_minutes: int = 60
) -> str:
    response = client.post(
        "/api/v1/packages",
        headers=headers,
        json={
            "name": "Test Package",
            "price_tzs": "1000",
            "duration_minutes": duration_minutes,
            "activation_type": activation_type,
        },
    )
    assert response.status_code == 201
    return str(response.json()["data"]["id"])


def test_creating_a_subscription_for_an_immediate_package_activates_it() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        customer_id = _create_customer(headers)
        package_id = _create_package(headers, activation_type="immediate")

        response = client.post(
            "/api/v1/subscriptions",
            headers=headers,
            json={"customer_id": customer_id, "package_id": package_id},
        )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "ACTIVE"
    assert data["activated_at"] is not None
    assert data["expires_at"] is not None
    assert data["bytes_used"] == 0


def test_creating_a_subscription_for_a_first_use_package_stays_pending() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        customer_id = _create_customer(headers)
        package_id = _create_package(headers, activation_type="first_use")

        create_response = client.post(
            "/api/v1/subscriptions",
            headers=headers,
            json={"customer_id": customer_id, "package_id": package_id},
        )
        assert create_response.status_code == 201
        subscription = create_response.json()["data"]
        assert subscription["status"] == "PENDING"
        assert subscription["activated_at"] is None

        activate_response = client.post(
            f"/api/v1/subscriptions/{subscription['id']}/activate", headers=headers
        )

    assert activate_response.status_code == 200
    activated = activate_response.json()["data"]
    assert activated["status"] == "ACTIVE"
    assert activated["activated_at"] is not None
    assert activated["expires_at"] is not None


def test_activating_an_already_active_subscription_is_rejected() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        customer_id = _create_customer(headers)
        package_id = _create_package(headers, activation_type="immediate")

        create_response = client.post(
            "/api/v1/subscriptions",
            headers=headers,
            json={"customer_id": customer_id, "package_id": package_id},
        )
        subscription_id = create_response.json()["data"]["id"]

        response = client.post(
            f"/api/v1/subscriptions/{subscription_id}/activate", headers=headers
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_subscription_for_archived_package_is_rejected() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        customer_id = _create_customer(headers)
        package_response = client.post(
            "/api/v1/packages",
            headers=headers,
            json={"name": "Archived Package", "price_tzs": "1000", "status": "archived"},
        )
        package_id = package_response.json()["data"]["id"]

        response = client.post(
            "/api/v1/subscriptions",
            headers=headers,
            json={"customer_id": customer_id, "package_id": package_id},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_subscription_customer_must_belong_to_tenant() -> None:
    with SeededContext() as ctx_a, SeededContext() as ctx_b:
        tenant_a = ctx_a.new_tenant(name="Tenant A")
        tenant_b = ctx_b.new_tenant(name="Tenant B")
        user_a = ctx_a.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_a)
        user_b = ctx_b.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_b)
        headers_a = auth_header(user_id=user_a)
        headers_b = auth_header(user_id=user_b)

        customer_a = _create_customer(headers_a)
        package_b = _create_package(headers_b)

        response = client.post(
            "/api/v1/subscriptions",
            headers=headers_b,
            json={"customer_id": customer_a, "package_id": package_b},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_frontline_role_can_create_subscription_network_technician_cannot() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        cashier = ctx.new_user(role_code="CASHIER", tenant_id=tenant_id)
        technician = ctx.new_user(role_code="NETWORK_TECHNICIAN", tenant_id=tenant_id)
        admin_headers = auth_header(user_id=admin)
        cashier_headers = auth_header(user_id=cashier)

        # Package creation is a MANAGEMENT_ROLES action — a cashier can only
        # sell against a catalog an admin already created.
        customer_id = _create_customer(cashier_headers)
        package_id = _create_package(admin_headers)

        allowed = client.post(
            "/api/v1/subscriptions",
            headers=cashier_headers,
            json={"customer_id": customer_id, "package_id": package_id},
        )
        denied = client.post(
            "/api/v1/subscriptions",
            headers=auth_header(user_id=technician),
            json={"customer_id": customer_id, "package_id": package_id},
        )

    assert allowed.status_code == 201
    assert denied.status_code == 403
    assert isinstance(UUID(allowed.json()["data"]["id"]), UUID)
