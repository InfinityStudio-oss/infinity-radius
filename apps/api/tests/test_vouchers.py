import re

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext, _sync_dsn

client = TestClient(app)


def _create_customer(headers: dict[str, str], *, phone: str = "0712345678") -> str:
    response = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"first_name": "Voucher", "last_name": "User", "phone": phone},
    )
    assert response.status_code == 201
    return str(response.json()["data"]["id"])


def _create_package(headers: dict[str, str], *, activation_type: str = "immediate") -> str:
    response = client.post(
        "/api/v1/packages",
        headers=headers,
        json={
            "name": "Voucher Package",
            "price_tzs": "1000",
            "duration_minutes": 60,
            "activation_type": activation_type,
        },
    )
    assert response.status_code == 201
    return str(response.json()["data"]["id"])


def _generate_one_voucher_code(headers: dict[str, str], package_id: str) -> str:
    batch_response = client.post(
        "/api/v1/vouchers/batches",
        headers=headers,
        json={"package_id": package_id, "quantity": 1},
    )
    assert batch_response.status_code == 201

    codes_response = client.get("/api/v1/vouchers/codes", headers=headers)
    codes = codes_response.json()["data"]
    assert len(codes) == 1
    return str(codes[0]["code"])


def test_voucher_batch_generates_cryptographically_random_non_sequential_codes() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        package_id = _create_package(headers)

        batch_response = client.post(
            "/api/v1/vouchers/batches",
            headers=headers,
            json={"package_id": package_id, "quantity": 50},
        )
        assert batch_response.status_code == 201

        codes_response = client.get(
            "/api/v1/vouchers/codes?page_size=50", headers=headers
        )
        codes = [item["code"] for item in codes_response.json()["data"]]

    assert len(codes) == 50
    assert len(set(codes)) == 50  # all unique
    for code in codes:
        assert re.fullmatch(r"[A-Z0-9]{10}", code)
    # Not a predictable/sequential scheme (e.g. a counter): with real random
    # generation across 50 codes, the first character can't plausibly be
    # the same every time.
    assert len({code[0] for code in codes}) > 1


def test_redeem_voucher_creates_and_activates_subscription_for_immediate_package() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        customer_id = _create_customer(headers)
        package_id = _create_package(headers, activation_type="immediate")
        code = _generate_one_voucher_code(headers, package_id)

        response = client.post(
            "/api/v1/vouchers/redeem",
            headers=headers,
            json={"code": code, "customer_id": customer_id},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["voucher"]["status"] == "USED"
    assert data["voucher"]["redeemed_by_customer_id"] == customer_id
    assert data["voucher"]["redeemed_subscription_id"] == data["subscription"]["id"]
    assert data["subscription"]["status"] == "ACTIVE"
    assert data["subscription"]["customer_id"] == customer_id
    assert data["subscription"]["voucher_id"] == data["voucher"]["id"]


def test_redeem_voucher_for_first_use_package_leaves_subscription_pending() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        customer_id = _create_customer(headers)
        package_id = _create_package(headers, activation_type="first_use")
        code = _generate_one_voucher_code(headers, package_id)

        response = client.post(
            "/api/v1/vouchers/redeem",
            headers=headers,
            json={"code": code, "customer_id": customer_id},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["voucher"]["status"] == "USED"
    assert data["subscription"]["status"] == "PENDING"


def test_redeeming_an_already_used_voucher_is_rejected() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        customer_id = _create_customer(headers)
        package_id = _create_package(headers)
        code = _generate_one_voucher_code(headers, package_id)

        first = client.post(
            "/api/v1/vouchers/redeem",
            headers=headers,
            json={"code": code, "customer_id": customer_id},
        )
        second = client.post(
            "/api/v1/vouchers/redeem",
            headers=headers,
            json={"code": code, "customer_id": customer_id},
        )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_redeeming_an_unknown_code_404s() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        customer_id = _create_customer(headers)

        response = client.post(
            "/api/v1/vouchers/redeem",
            headers=headers,
            json={"code": "DOESNOTEXIST", "customer_id": customer_id},
        )

    assert response.status_code == 404


def test_voucher_from_one_tenant_cannot_be_redeemed_by_another() -> None:
    with SeededContext() as ctx_a, SeededContext() as ctx_b:
        tenant_a = ctx_a.new_tenant(name="Tenant A")
        tenant_b = ctx_b.new_tenant(name="Tenant B")
        user_a = ctx_a.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_a)
        user_b = ctx_b.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_b)
        headers_a = auth_header(user_id=user_a)
        headers_b = auth_header(user_id=user_b)

        package_a = _create_package(headers_a)
        code = _generate_one_voucher_code(headers_a, package_a)
        customer_b = _create_customer(headers_b)

        response = client.post(
            "/api/v1/vouchers/redeem",
            headers=headers_b,
            json={"code": code, "customer_id": customer_b},
        )

    assert response.status_code == 404


def test_voucher_row_lock_blocks_a_concurrent_transaction() -> None:
    """VoucherService.redeem relies on `SELECT ... FOR UPDATE` (see
    OfflineVoucherRepository.get_by_code_for_update) to serialize concurrent
    redemptions of the same code — this is what test_redeeming_an_already_
    used_voucher_is_rejected above depends on for correctness under a real
    race, not just sequentially.

    Driving that race through two real HTTP requests needs two OS threads
    each running the ASGI app through TestClient's anyio blocking portal —
    reliable in isolation, but on this Windows/ProactorEventLoop setup it
    reliably deadlocks once enough prior TestClient calls have already run
    in the same process (i.e. deep into the full suite, never standalone).
    That's the same async-stack-vs-Windows friction tests/db_fixtures.py
    already works around by using plain synchronous psycopg instead of the
    app's async engine — so this test does the same: it exercises the lock
    directly at the SQL level with two real psycopg connections, which
    proves the exact mechanism the service depends on without going anywhere
    near TestClient/anyio.
    """
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        package_id = _create_package(headers)
        code = _generate_one_voucher_code(headers, package_id)

        conn1 = psycopg.connect(_sync_dsn())
        conn2 = psycopg.connect(_sync_dsn())
        try:
            conn1.autocommit = False
            conn2.autocommit = False

            with conn1.cursor() as cur1:
                cur1.execute(
                    "SELECT id FROM offline_vouchers WHERE tenant_id = %s AND code = %s "
                    "FOR UPDATE",
                    (str(tenant_id), code),
                )
                assert cur1.fetchone() is not None
            # conn1's transaction is left open — the row lock is held.

            with conn2.cursor() as cur2, pytest.raises(psycopg.errors.LockNotAvailable):
                cur2.execute(
                    "SELECT id FROM offline_vouchers WHERE tenant_id = %s AND code = %s "
                    "FOR UPDATE NOWAIT",
                    (str(tenant_id), code),
                )
            conn2.rollback()

            conn1.commit()

            # Once released, the same row is immediately lockable again.
            with conn2.cursor() as cur2:
                cur2.execute(
                    "SELECT id FROM offline_vouchers WHERE tenant_id = %s AND code = %s "
                    "FOR UPDATE NOWAIT",
                    (str(tenant_id), code),
                )
                assert cur2.fetchone() is not None
            conn2.commit()
        finally:
            conn1.close()
            conn2.close()


def test_only_frontline_roles_can_redeem_vouchers() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_user = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        technician = ctx.new_user(role_code="NETWORK_TECHNICIAN", tenant_id=tenant_id)
        admin_headers = auth_header(user_id=admin_user)

        customer_id = _create_customer(admin_headers)
        package_id = _create_package(admin_headers)
        code = _generate_one_voucher_code(admin_headers, package_id)

        response = client.post(
            "/api/v1/vouchers/redeem",
            headers=auth_header(user_id=technician),
            json={"code": code, "customer_id": customer_id},
        )

    assert response.status_code == 403
