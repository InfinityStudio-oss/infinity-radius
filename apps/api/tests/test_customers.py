import re

from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)

_CUSTOMER_NUMBER_RE = re.compile(r"^CUS\d{6}$")


def test_list_customers_requires_auth() -> None:
    response = client.get("/api/v1/customers")
    assert response.status_code == 401


def test_list_customers_empty_tenant_returns_honest_empty_envelope() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.get("/api/v1/customers", headers=auth_header(user_id=user_id))

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "success": True,
        "data": [],
        "meta": {"page": 1, "page_size": 20, "total": 0, "total_pages": 0},
    }


def test_create_customer_generates_customer_number_and_normalizes_phone() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        create_response = client.post(
            "/api/v1/customers",
            headers=headers,
            json={
                "first_name": "Asha",
                "last_name": "Juma",
                "phone": "0712345678",
                "email": "asha.juma@mail.co.tz",
                "username": "asha.juma",
                "notes": "Referred by a friend",
            },
        )
        assert create_response.status_code == 201
        created = create_response.json()["data"]
        assert created["phone"] == "255712345678"
        assert created["tenant_id"] == str(tenant_id)
        assert created["first_name"] == "Asha"
        assert created["last_name"] == "Juma"
        assert created["username"] == "asha.juma"
        assert created["notes"] == "Referred by a friend"
        # Server-generated — never accepted as client input.
        assert _CUSTOMER_NUMBER_RE.match(created["customer_number"])

        list_response = client.get("/api/v1/customers", headers=headers)
        body = list_response.json()

    assert body["meta"]["total"] == 1
    assert body["data"][0]["phone"] == "255712345678"
    assert body["data"][0]["customer_number"] == created["customer_number"]


def test_create_customer_ignores_client_supplied_customer_number() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.post(
            "/api/v1/customers",
            headers=auth_header(user_id=user_id),
            json={
                "first_name": "Spoofed",
                "last_name": "Number",
                "phone": "0712345678",
                "customer_number": "CUS999999",
            },
        )

    assert response.status_code == 201
    assert response.json()["data"]["customer_number"] != "CUS999999"


def test_create_customer_rejects_invalid_phone() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.post(
            "/api/v1/customers",
            headers=auth_header(user_id=user_id),
            json={"first_name": "Bad", "last_name": "Phone", "phone": "12345"},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "validation_error"


def test_create_customer_rejects_duplicate_phone() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)
        payload = {"first_name": "Dup", "last_name": "Customer", "phone": "0712345678"}

        first = client.post("/api/v1/customers", headers=headers, json=payload)
        second = client.post("/api/v1/customers", headers=headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_create_customer_rejects_duplicate_username() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        first = client.post(
            "/api/v1/customers",
            headers=headers,
            json={
                "first_name": "First",
                "last_name": "User",
                "phone": "0712345678",
                "username": "takenname",
            },
        )
        second = client.post(
            "/api/v1/customers",
            headers=headers,
            json={
                "first_name": "Second",
                "last_name": "User",
                "phone": "0712345679",
                "username": "takenname",
            },
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_customers_are_isolated_between_tenants() -> None:
    with SeededContext() as ctx_a, SeededContext() as ctx_b:
        tenant_a = ctx_a.new_tenant(name="Tenant A")
        tenant_b = ctx_b.new_tenant(name="Tenant B")
        user_a = ctx_a.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_a)
        user_b = ctx_b.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_b)

        create_response = client.post(
            "/api/v1/customers",
            headers=auth_header(user_id=user_a),
            json={"first_name": "Tenant", "last_name": "A Customer", "phone": "0712345678"},
        )
        customer_id = create_response.json()["data"]["id"]

        # Tenant B cannot see tenant A's customer in its list...
        list_as_b = client.get("/api/v1/customers", headers=auth_header(user_id=user_b))
        assert list_as_b.json()["meta"]["total"] == 0

        # ...nor fetch it directly by id.
        get_as_b = client.get(
            f"/api/v1/customers/{customer_id}", headers=auth_header(user_id=user_b)
        )
        assert get_as_b.status_code == 404


def test_customer_care_can_create_but_network_technician_cannot() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        care_user = ctx.new_user(role_code="CUSTOMER_CARE", tenant_id=tenant_id)
        tech_user = ctx.new_user(role_code="NETWORK_TECHNICIAN", tenant_id=tenant_id)
        payload = {"first_name": "RBAC", "last_name": "Test", "phone": "0712345678"}

        allowed = client.post(
            "/api/v1/customers", headers=auth_header(user_id=care_user), json=payload
        )
        denied = client.post(
            "/api/v1/customers",
            headers=auth_header(user_id=tech_user),
            json={"first_name": "RBAC", "last_name": "Test 2", "phone": "0712345679"},
        )

    assert allowed.status_code == 201
    assert denied.status_code == 403


def test_search_and_pagination_params_are_honored() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        for i in range(3):
            client.post(
                "/api/v1/customers",
                headers=headers,
                json={"first_name": f"Customer{i}", "last_name": "Test", "phone": f"071234567{i}"},
            )

        page_1 = client.get("/api/v1/customers?page=1&page_size=2", headers=headers)
        page_2 = client.get("/api/v1/customers?page=2&page_size=2", headers=headers)
        searched = client.get("/api/v1/customers?search=Customer1", headers=headers)

    assert page_1.json()["meta"] == {"page": 1, "page_size": 2, "total": 3, "total_pages": 2}
    assert len(page_1.json()["data"]) == 2
    assert len(page_2.json()["data"]) == 1
    assert searched.json()["meta"]["total"] == 1
    assert searched.json()["data"][0]["first_name"] == "Customer1"
