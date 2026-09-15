from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


def test_new_tenant_has_no_default_or_sample_packages() -> None:
    """No package is ever seeded for a tenant — a fresh tenant creates its
    own catalog from nothing."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.get("/api/v1/packages", headers=auth_header(user_id=user_id))

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "success": True,
        "data": [],
        "meta": {"page": 1, "page_size": 20, "total": 0, "total_pages": 0},
    }


def test_create_package_with_full_field_set() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.post(
            "/api/v1/packages",
            headers=auth_header(user_id=user_id),
            json={
                "name": "Daily 1GB",
                "description": "24-hour 1GB hotspot bundle",
                "price_tzs": "1500",
                "duration_minutes": 1440,
                "bytes_limit": 1_000_000_000,
                "download_speed_kbps": 2048,
                "upload_speed_kbps": 1024,
                "device_limit": 2,
                "simultaneous_sessions": 1,
                "activation_type": "first_use",
                "status": "active",
            },
        )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["tenant_id"] == str(tenant_id)
    assert data["price_tzs"] == "1500.00"
    assert isinstance(data["price_tzs"], str)  # never a JSON float
    assert data["bytes_limit"] == 1_000_000_000
    assert data["download_speed_kbps"] == 2048
    assert data["upload_speed_kbps"] == 1024
    assert data["simultaneous_sessions"] == 1
    assert data["activation_type"] == "first_use"
    assert data["status"] == "active"


def test_create_package_defaults_activation_type_immediate() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.post(
            "/api/v1/packages",
            headers=auth_header(user_id=user_id),
            json={"name": "Unlimited Weekly", "price_tzs": "5000"},
        )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["activation_type"] == "immediate"
    assert data["status"] == "active"
    assert data["bytes_limit"] is None
    assert data["duration_minutes"] is None


def test_only_management_roles_can_create_packages() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        cashier_user = ctx.new_user(role_code="CASHIER", tenant_id=tenant_id)

        response = client.post(
            "/api/v1/packages",
            headers=auth_header(user_id=cashier_user),
            json={"name": "Cashier Attempt", "price_tzs": "1000"},
        )

    assert response.status_code == 403


def test_packages_are_isolated_between_tenants() -> None:
    with SeededContext() as ctx_a, SeededContext() as ctx_b:
        tenant_a = ctx_a.new_tenant(name="Tenant A")
        tenant_b = ctx_b.new_tenant(name="Tenant B")
        user_a = ctx_a.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_a)
        user_b = ctx_b.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_b)

        client.post(
            "/api/v1/packages",
            headers=auth_header(user_id=user_a),
            json={"name": "Tenant A Package", "price_tzs": "1000"},
        )

        list_as_b = client.get("/api/v1/packages", headers=auth_header(user_id=user_b))

    assert list_as_b.json()["meta"]["total"] == 0
