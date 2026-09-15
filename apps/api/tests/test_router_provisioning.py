"""The Add Router Wizard's backend: network config -> WireGuard -> RADIUS
-> hotspot -> walled garden -> public token -> complete. Every step is
exercised against the real database; encryption-at-rest is verified by
reading the raw column value back with a separate psycopg connection
(never through the app's own decrypt path, which would trivially "pass"
even if nothing were actually encrypted)."""

from uuid import UUID

from fastapi.testclient import TestClient

from app.core.crypto import decrypt_secret
from app.core.router_token import resolve_router_token
from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


def _create_router(headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/routers", headers=headers, json={"name": "Provisioning Test Router"}
    )
    assert response.status_code == 201
    return str(response.json()["data"]["id"])


def test_full_wizard_flow_end_to_end() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        router_id = _create_router(headers)

        # Step 3: network config
        network_response = client.put(
            f"/api/v1/routers/{router_id}/provisioning/network-config",
            headers=headers,
            json={
                "network_cidr": "10.5.50.0/24",
                "gateway_ip": "10.5.50.1",
                "dns_servers": ["1.1.1.1", "8.8.8.8"],
            },
        )
        assert network_response.status_code == 200
        assert network_response.json()["data"]["network_cidr"] == "10.5.50.0/24"

        # Step 4: WireGuard
        wg_response = client.post(
            f"/api/v1/routers/{router_id}/provisioning/wireguard", headers=headers
        )
        assert wg_response.status_code == 200
        wg_data = wg_response.json()["data"]
        assert wg_data["tunnel_ip"].startswith("10.90.0.")
        assert "router_private_key" in wg_data
        assert "/interface/wireguard add" in wg_data["router_config_script"]
        assert wg_data["router_public_key"] in wg_data["server_peer_block"]

        # Step 5: RADIUS
        radius_response = client.post(
            f"/api/v1/routers/{router_id}/provisioning/radius", headers=headers
        )
        assert radius_response.status_code == 200
        radius_data = radius_response.json()["data"]
        assert "/radius add" in radius_data["router_config_script"]
        assert radius_data["secret"] in radius_data["nas_client_block"]

        # Step 6: hotspot
        hotspot_response = client.post(
            f"/api/v1/routers/{router_id}/provisioning/hotspot", headers=headers
        )
        assert hotspot_response.status_code == 200
        assert "/ip/hotspot" in hotspot_response.json()["data"]["router_config_script"]

        # Step 7: walled garden
        walled_garden_response = client.post(
            f"/api/v1/routers/{router_id}/provisioning/walled-garden", headers=headers
        )
        assert walled_garden_response.status_code == 200
        wg_garden_data = walled_garden_response.json()["data"]
        assert len(wg_garden_data["domains"]) >= 1
        assert "walled-garden add" in wg_garden_data["router_config_script"]

        # Public token
        token_response = client.get(
            f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
        )
        assert token_response.status_code == 200
        token = token_response.json()["data"]["router_token"]
        assert resolve_router_token(token) == UUID(router_id)

        # Step 9: complete
        complete_response = client.post(
            f"/api/v1/routers/{router_id}/provisioning/complete", headers=headers
        )
        assert complete_response.status_code == 200
        assert complete_response.json()["data"]["provisioning_status"] == "completed"

        # RouterRead never exposes the encrypted secrets themselves.
        get_response = client.get(f"/api/v1/routers/{router_id}", headers=headers)
        assert "radius_secret_encrypted" not in get_response.json()["data"]
        assert "wireguard_private_key_encrypted" not in get_response.json()["data"]


def test_radius_secret_and_wireguard_private_key_are_encrypted_at_rest() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)
        router_id = _create_router(headers)

        wg_response = client.post(
            f"/api/v1/routers/{router_id}/provisioning/wireguard", headers=headers
        )
        real_private_key = wg_response.json()["data"]["router_private_key"]

        radius_response = client.post(
            f"/api/v1/routers/{router_id}/provisioning/radius", headers=headers
        )
        real_secret = radius_response.json()["data"]["secret"]

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT wireguard_private_key_encrypted, radius_secret_encrypted "
                "FROM routers WHERE id = %s",
                (router_id,),
            )
            row = cur.fetchone()

    assert row is not None
    stored_wg_key, stored_radius_secret = row

    # Never stored in plaintext...
    assert stored_wg_key != real_private_key
    assert stored_radius_secret != real_secret
    assert real_private_key not in stored_wg_key
    assert real_secret not in stored_radius_secret

    # ...but decryptable back to the exact value that was shown once.
    assert decrypt_secret(stored_wg_key) == real_private_key
    assert decrypt_secret(stored_radius_secret) == real_secret


def test_wireguard_generation_assigns_distinct_tunnel_ips_to_different_routers() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        router_a = _create_router(headers)
        router_b = _create_router(headers)

        ip_a = client.post(
            f"/api/v1/routers/{router_a}/provisioning/wireguard", headers=headers
        ).json()["data"]["tunnel_ip"]
        ip_b = client.post(
            f"/api/v1/routers/{router_b}/provisioning/wireguard", headers=headers
        ).json()["data"]["tunnel_ip"]

    assert ip_a != ip_b


def test_radius_config_requires_wireguard_config_first() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)
        router_id = _create_router(headers)

        response = client.post(
            f"/api/v1/routers/{router_id}/provisioning/radius", headers=headers
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_hotspot_config_requires_network_config_first() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)
        router_id = _create_router(headers)

        response = client.post(
            f"/api/v1/routers/{router_id}/provisioning/hotspot", headers=headers
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_network_config_rejects_a_gateway_outside_the_subnet() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)
        router_id = _create_router(headers)

        response = client.put(
            f"/api/v1/routers/{router_id}/provisioning/network-config",
            headers=headers,
            json={
                "network_cidr": "10.5.50.0/24",
                "gateway_ip": "10.9.9.1",
                "dns_servers": ["1.1.1.1"],
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_provisioning_steps_are_tenant_isolated() -> None:
    with SeededContext() as ctx_a, SeededContext() as ctx_b:
        tenant_a = ctx_a.new_tenant(name="Tenant A")
        tenant_b = ctx_b.new_tenant(name="Tenant B")
        user_a = ctx_a.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_a)
        user_b = ctx_b.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_b)

        router_id = _create_router(auth_header(user_id=user_a))

        response = client.put(
            f"/api/v1/routers/{router_id}/provisioning/network-config",
            headers=auth_header(user_id=user_b),
            json={
                "network_cidr": "10.5.50.0/24",
                "gateway_ip": "10.5.50.1",
                "dns_servers": ["1.1.1.1"],
            },
        )

    assert response.status_code == 404


def test_only_network_roles_can_run_provisioning_steps() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        cashier = ctx.new_user(role_code="CASHIER", tenant_id=tenant_id)
        router_id = _create_router(auth_header(user_id=admin))

        response = client.post(
            f"/api/v1/routers/{router_id}/provisioning/wireguard",
            headers=auth_header(user_id=cashier),
        )

    assert response.status_code == 403
