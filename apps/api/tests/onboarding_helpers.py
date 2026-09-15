"""Test-only stand-in for the real Supabase Admin API — there is no live
Supabase project to call in CI/local tests (see tests/db_fixtures.py's own
module docstring on why this suite runs against real local Postgres
instead of mocking the database). create_user/delete_user still perform
real INSERT/DELETE against auth.users (firing the same
handle_new_auth_user trigger a real Supabase project would), so
OnboardingService's orchestration is exercised for real end to end;
only the network call to Supabase itself is stubbed.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from app.core.supabase_admin import SupabaseAdminClient, SupabaseAuthUser, SupabaseAuthUserDetail
from tests.db_fixtures import _connect


@pytest.fixture
def mock_supabase_admin(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, UUID]]:
    conn = _connect()
    created: dict[str, UUID] = {}

    async def _create_user(
        self: SupabaseAdminClient,
        *,
        email: str,
        password: str,
        phone: str | None = None,
        user_metadata: dict[str, object] | None = None,
    ) -> SupabaseAuthUser:
        user_id = uuid4()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO auth.users (id, email) VALUES (%s, %s)", (user_id, email)
            )
        created[email] = user_id
        return SupabaseAuthUser(id=user_id, email=email)

    async def _delete_user(self: SupabaseAdminClient, user_id: UUID) -> None:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM auth.users WHERE id = %s", (user_id,))

    async def _generate_link(
        self: SupabaseAdminClient,
        *,
        link_type: str,
        email: str,
        password: str | None = None,
        redirect_to: str | None = None,
    ) -> str:
        return f"https://test.supabase.co/auth/v1/verify?type={link_type}&email={email}"

    async def _get_user(self: SupabaseAdminClient, user_id: UUID) -> SupabaseAuthUserDetail:
        with conn.cursor() as cur:
            cur.execute("SELECT email FROM auth.users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        email = row[0] if row else "unknown@example.test"
        return SupabaseAuthUserDetail(id=user_id, email=email, email_confirmed=True)

    monkeypatch.setattr(SupabaseAdminClient, "create_user", _create_user)
    monkeypatch.setattr(SupabaseAdminClient, "delete_user", _delete_user)
    monkeypatch.setattr(SupabaseAdminClient, "generate_link", _generate_link)
    monkeypatch.setattr(SupabaseAdminClient, "get_user", _get_user)

    yield created

    conn.close()
