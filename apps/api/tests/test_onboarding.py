"""Real onboarding orchestration — see app/services/onboarding.py.
SupabaseAdminClient is stubbed (tests/onboarding_helpers.py) since there is
no live Supabase project to call; Resend is never mocked — it's already
unconfigured in the test environment, so send_* calls exercise their real
fail-soft path (EmailSendResult(sent=False, ...)), which is itself part of
what these tests verify (email_events gets a FAILED row, account creation
still succeeds).
"""

import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.db_fixtures import _connect

MockSupabaseAdmin = dict[str, uuid.UUID]

client = TestClient(app)


def _valid_payload(**overrides: object) -> dict[str, object]:
    unique = uuid.uuid4().hex[:8]
    payload: dict[str, object] = {
        "first_name": "Amani",
        "last_name": "Mushi",
        "work_email": f"amani.{unique}@example-test.co.tz",
        "phone": "0712345678",
        "password": "Str0ngPassw0rd",
        "confirm_password": "Str0ngPassw0rd",
        "trading_name": f"Amani Networks {unique}",
        "legal_name": "Amani Networks Ltd",
        "business_type": "ISP",
        "business_email": f"business.{unique}@example-test.co.tz",
        "business_phone": "0713345678",
        "tin": "123-456-789",
        "business_license_number": "LIC-0001",
        "region": "Dar es Salaam",
        "district": "Ilala",
        "ward": "Kariakoo",
        "street_area": "Mchikichini",
        "business_address": "Plot 12, Mchikichini",
        "authorized_contact_name": None,
        "authorized_contact_position": None,
        "authorized_contact_phone": None,
        "authorized_contact_email": None,
        "accept_terms": True,
        "accept_privacy": True,
    }
    payload.update(overrides)
    return payload


def _row(conn: psycopg.Connection, sql: str, params: tuple[object, ...]) -> tuple[Any, ...] | None:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _cleanup_by_email(conn: psycopg.Connection, email: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM auth.users WHERE email = %s", (email,))


@pytest.fixture
def db_conn() -> Iterator[psycopg.Connection]:
    conn = _connect()
    yield conn
    conn.close()


def test_register_rejects_invalid_email(mock_supabase_admin: MockSupabaseAdmin) -> None:
    response = client.post(
        "/api/v1/onboarding/register", json=_valid_payload(work_email="not-an-email")
    )
    assert response.status_code == 422


def test_register_rejects_duplicate_email(
    mock_supabase_admin: MockSupabaseAdmin, db_conn: psycopg.Connection
) -> None:
    payload = _valid_payload()
    email = payload["work_email"]
    try:
        first = client.post("/api/v1/onboarding/register", json=payload)
        assert first.status_code == 201

        second = client.post("/api/v1/onboarding/register", json=_valid_payload(work_email=email))
        assert second.status_code == 409
    finally:
        _cleanup_by_email(db_conn, str(email))


def test_register_rejects_invalid_tanzania_phone(mock_supabase_admin: MockSupabaseAdmin) -> None:
    response = client.post(
        "/api/v1/onboarding/register", json=_valid_payload(phone="12345")
    )
    assert response.status_code == 422


def test_register_rejects_weak_password(mock_supabase_admin: MockSupabaseAdmin) -> None:
    response = client.post(
        "/api/v1/onboarding/register",
        json=_valid_payload(password="short", confirm_password="short"),
    )
    assert response.status_code == 422


def test_register_rejects_mismatched_passwords(mock_supabase_admin: MockSupabaseAdmin) -> None:
    response = client.post(
        "/api/v1/onboarding/register",
        json=_valid_payload(confirm_password="SomethingElse1"),
    )
    assert response.status_code == 422


def test_register_rejects_missing_terms_acceptance(mock_supabase_admin: MockSupabaseAdmin) -> None:
    response = client.post(
        "/api/v1/onboarding/register", json=_valid_payload(accept_terms=False)
    )
    assert response.status_code == 422


def test_register_rejects_missing_privacy_acceptance(
    mock_supabase_admin: MockSupabaseAdmin,
) -> None:
    response = client.post(
        "/api/v1/onboarding/register", json=_valid_payload(accept_privacy=False)
    )
    assert response.status_code == 422


def test_register_creates_tenant_profile_wallet_flags_and_verification(
    mock_supabase_admin: MockSupabaseAdmin, db_conn: psycopg.Connection
) -> None:
    payload = _valid_payload()
    email = str(payload["work_email"])
    try:
        response = client.post("/api/v1/onboarding/register", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        tenant_id = body["data"]["tenant_id"]
        assert body["data"]["status"] == "submitted"

        tenant_row = _row(
            db_conn,
            "SELECT status, name, business_type, region, district "
            "FROM public.tenants WHERE id = %s",
            (tenant_id,),
        )
        assert tenant_row is not None
        assert tenant_row[0] == "PENDING_VERIFICATION"
        assert tenant_row[1] == payload["trading_name"]
        assert tenant_row[2] == "ISP"

        owner_id = mock_supabase_admin[email]
        profile_row = _row(
            db_conn,
            "SELECT tenant_id, first_name, last_name, phone, status "
            "FROM public.profiles WHERE id = %s",
            (owner_id,),
        )
        assert profile_row is not None
        assert str(profile_row[0]) == tenant_id
        assert profile_row[1] == "Amani"
        assert profile_row[2] == "Mushi"
        assert profile_row[3] == "255712345678"
        assert profile_row[4] == "active"

        role_row = _row(
            db_conn,
            """
            SELECT r.code FROM public.profile_roles pr
            JOIN public.roles r ON r.id = pr.role_id
            WHERE pr.profile_id = %s AND pr.tenant_id = %s
            """,
            (owner_id, tenant_id),
        )
        assert role_row is not None
        assert role_row[0] == "TENANT_OWNER"

        wallet_row = _row(
            db_conn,
            "SELECT available_balance_tzs FROM public.tenant_wallets WHERE tenant_id = %s",
            (tenant_id,),
        )
        assert wallet_row is not None
        assert float(wallet_row[0]) == 0.0

        flags_row = _row(
            db_conn,
            "SELECT collection_enabled, payout_enabled, api_enabled "
            "FROM public.tenant_feature_flags WHERE tenant_id = %s",
            (tenant_id,),
        )
        assert flags_row == (False, False, False)

        settings_row = _row(
            db_conn, "SELECT id FROM public.tenant_settings WHERE tenant_id = %s", (tenant_id,)
        )
        assert settings_row is not None

        verification_row = _row(
            db_conn,
            "SELECT status FROM public.tenant_verifications WHERE tenant_id = %s",
            (tenant_id,),
        )
        assert verification_row == ("PENDING_VERIFICATION",)

        # Whether Resend is configured varies by environment (this repo's
        # local .env may carry a real key) — either way, the attempt must
        # be recorded honestly as SENT or FAILED, never silently dropped.
        email_event_row = _row(
            db_conn,
            "SELECT status FROM public.email_events "
            "WHERE tenant_id = %s AND email_type = 'VERIFY_EMAIL'",
            (tenant_id,),
        )
        assert email_event_row is not None
        assert email_event_row[0] in ("SENT", "FAILED")

        audit_actions = {
            row[0]
            for row in _fetch_all(
                db_conn,
                "SELECT action FROM public.audit_logs WHERE tenant_id = %s",
                (tenant_id,),
            )
        }
        assert "TENANT_REGISTERED" in audit_actions
        assert "PROFILE_CREATED" in audit_actions
    finally:
        _cleanup_by_email(db_conn, email)


def _fetch_all(
    conn: psycopg.Connection, sql: str, params: tuple[object, ...]
) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def test_register_compensates_by_deleting_auth_user_on_local_failure(
    monkeypatch: pytest.MonkeyPatch,
    mock_supabase_admin: MockSupabaseAdmin,
    db_conn: psycopg.Connection,
) -> None:
    """If DB orchestration fails after the Supabase user was created, the
    auth user must not be left orphaned."""

    async def _boom(self: object, *, tenant_id: object) -> None:
        raise RuntimeError("simulated wallet failure")

    monkeypatch.setattr("app.services.wallet.WalletService.get_or_create_wallet", _boom)

    # TestClient re-raises unhandled exceptions by default (useful for
    # every other test's stack traces) — here the 500 itself, produced by
    # app.core.errors.unhandled_exception_handler, is what's under test.
    non_raising_client = TestClient(app, raise_server_exceptions=False)
    payload = _valid_payload()
    email = str(payload["work_email"])
    response = non_raising_client.post("/api/v1/onboarding/register", json=payload)
    assert response.status_code == 500

    owner_id = mock_supabase_admin.get(email)
    assert owner_id is not None
    auth_row = _row(db_conn, "SELECT id FROM auth.users WHERE id = %s", (owner_id,))
    assert auth_row is None  # compensating delete_user ran

    tenant_row = _row(
        db_conn, "SELECT id FROM public.tenants WHERE name = %s", (payload["trading_name"],)
    )
    assert tenant_row is None  # rolled back, never committed


def test_resend_verification_email_does_not_leak_account_existence(
    mock_supabase_admin: MockSupabaseAdmin,
) -> None:
    response = client.post(
        "/api/v1/onboarding/resend-verification-email",
        json={"email": "definitely-not-registered@example-test.co.tz"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["sent"] is True
