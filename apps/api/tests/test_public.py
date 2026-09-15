from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.router_token import create_router_token
from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


def test_resolve_without_a_token_is_rejected() -> None:
    response = client.get("/api/v1/public/captive-portal/resolve")
    assert response.status_code == 422  # router token is a required query param


def test_resolve_with_a_garbage_token_reports_invalid_token() -> None:
    response = client.get(
        "/api/v1/public/captive-portal/resolve",
        params={"router": "not-a-real-token", "mac": "AA:BB:CC:DD:EE:FF", "dst": "http://example.test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "invalid_token"
    assert body["mac"] == "AA:BB:CC:DD:EE:FF"
    assert body["dst"] == "http://example.test"


def test_resolve_with_a_well_formed_token_for_an_unknown_router_reports_not_found() -> None:
    token = create_router_token(uuid4())

    response = client.get("/api/v1/public/captive-portal/resolve", params={"router": token})

    assert response.status_code == 200
    assert response.json()["status"] == "router_not_found"


def test_resolve_never_exposes_a_tenant_id_only_router_and_site_name() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        location_response = client.post(
            "/api/v1/locations",
            headers=headers,
            json={"name": "Kariakoo Site", "region": "Dar es Salaam", "city": "Dar es Salaam"},
        )
        location_id = location_response.json()["data"]["id"]

        router_response = client.post(
            "/api/v1/routers",
            headers=headers,
            json={"name": "Kariakoo Router 1", "location_id": location_id},
        )
        router_id = router_response.json()["data"]["id"]

        token = create_router_token(router_id)
        response = client.get(
            "/api/v1/public/captive-portal/resolve",
            params={
                "router": token,
                "mac": "AA:BB:CC:DD:EE:FF",
                "dst": "http://example.test",
                "login": "http://10.5.50.1/login",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "router_name": "Kariakoo Router 1",
        "site_name": "Kariakoo Site",
        "mac": "AA:BB:CC:DD:EE:FF",
        "dst": "http://example.test",
        "login_url": "http://10.5.50.1/login",
    }
    assert "tenant_id" not in body
    assert "router_id" not in body


def test_branding_for_an_invalid_token_is_rejected() -> None:
    response = client.get(
        "/api/v1/public/captive-portal/branding", params={"router": "garbage"}
    )
    assert response.status_code == 401


def test_branding_returns_tenant_name_and_honestly_null_when_unset() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant(name="Kariakoo Networks")
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        router_id = client.post(
            "/api/v1/routers", headers=headers, json={"name": "Router"}
        ).json()["data"]["id"]
        token = create_router_token(router_id)

        response = client.get(
            "/api/v1/public/captive-portal/branding", params={"router": token}
        )

    assert response.status_code == 200
    assert response.json() == {
        "tenant_name": "Kariakoo Networks",
        "logo_url": None,
        "brand_color": None,
    }


def test_packages_for_an_invalid_token_reports_not_configured() -> None:
    response = client.get(
        "/api/v1/public/captive-portal/packages", params={"router": "garbage"}
    )

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "status": "not_configured"}


def test_packages_returns_only_this_routers_tenants_active_packages() -> None:
    with SeededContext() as ctx_a, SeededContext() as ctx_b:
        tenant_a = ctx_a.new_tenant(name="Tenant A")
        tenant_b = ctx_b.new_tenant(name="Tenant B")
        user_a = ctx_a.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_a)
        user_b = ctx_b.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_b)
        headers_a = auth_header(user_id=user_a)
        headers_b = auth_header(user_id=user_b)

        client.post(
            "/api/v1/packages",
            headers=headers_a,
            json={"name": "Tenant A Package", "price_tzs": "1000", "status": "active"},
        )
        client.post(
            "/api/v1/packages",
            headers=headers_a,
            json={"name": "Tenant A Archived", "price_tzs": "1000", "status": "archived"},
        )
        client.post(
            "/api/v1/packages",
            headers=headers_b,
            json={"name": "Tenant B Package", "price_tzs": "2000", "status": "active"},
        )

        router_response = client.post(
            "/api/v1/routers", headers=headers_a, json={"name": "Tenant A Router"}
        )
        router_id = router_response.json()["data"]["id"]
        token = create_router_token(router_id)

        response = client.get(
            "/api/v1/public/captive-portal/packages", params={"router": token}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Tenant A Package"
