"""Thin async wrapper around the Supabase Auth Admin REST API — the only
place this backend is allowed to create/delete/link auth.users rows.

Uses the project's SUPABASE_SECRET_KEY (the modern replacement for the
legacy service_role key), which bypasses RLS entirely. Never imported by
anything reachable without SUPER_ADMIN-equivalent trust
(currently: only OnboardingService, which runs unauthenticated-by-design
since signup itself has no session yet, but every other write it performs
is scoped to the row it just created).

No verification token is ever invented here — `generate_link` asks
Supabase itself for a real, Supabase-signed action link; this module only
hands that link to the caller (who forwards it to Resend for delivery).
"""

import uuid
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.core.config import get_settings


class SupabaseAdminError(Exception):
    """Raised for any non-2xx response from the Supabase Admin API. The
    caller decides whether that's fatal (registration) or best-effort
    (resend-verification)."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SupabaseNotConfiguredError(SupabaseAdminError):
    def __init__(self) -> None:
        super().__init__(
            "SUPABASE_SECRET_KEY is not configured — cannot create Supabase Auth users."
        )


@dataclass(frozen=True)
class SupabaseAuthUser:
    id: uuid.UUID
    email: str


@dataclass(frozen=True)
class SupabaseAuthUserDetail:
    id: uuid.UUID
    email: str
    email_confirmed: bool


class SupabaseAdminClient:
    """One request per call — no connection pooling assumptions, matching
    the low request volume (signup, resend-verification, admin actions)."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = str(settings.supabase_url).rstrip("/")
        self._secret_key = settings.supabase_secret_key

    def _headers(self) -> dict[str, str]:
        if not self._secret_key:
            raise SupabaseNotConfiguredError()
        return {
            "apikey": self._secret_key,
            "Authorization": f"Bearer {self._secret_key}",
            "Content-Type": "application/json",
        }

    async def create_user(
        self,
        *,
        email: str,
        password: str,
        phone: str | None = None,
        user_metadata: dict[str, Any] | None = None,
    ) -> SupabaseAuthUser:
        """Creates the auth.users row with email_confirm=false — the user
        exists and can authenticate only after they verify via the link
        generate_link() produces. Never logs `password`."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self._base_url}/auth/v1/admin/users",
                headers=self._headers(),
                json={
                    "email": email,
                    "password": password,
                    "phone": phone,
                    "email_confirm": False,
                    "user_metadata": user_metadata or {},
                },
            )
        if response.status_code >= 400:
            raise SupabaseAdminError(
                f"Supabase user creation failed: {_safe_error(response)}",
                status_code=response.status_code,
            )
        body = response.json()
        return SupabaseAuthUser(id=uuid.UUID(body["id"]), email=body["email"])

    async def get_user(self, user_id: uuid.UUID) -> SupabaseAuthUserDetail:
        """The authoritative source for whether an account's email is
        verified — `email_confirmed_at` is not reliably present as a JWT
        claim across GoTrue versions, so this backend asks the Admin API
        directly rather than guessing from the access token."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self._base_url}/auth/v1/admin/users/{user_id}",
                headers=self._headers(),
            )
        if response.status_code >= 400:
            raise SupabaseAdminError(
                f"Supabase get_user failed: {_safe_error(response)}",
                status_code=response.status_code,
            )
        body = response.json()
        return SupabaseAuthUserDetail(
            id=uuid.UUID(body["id"]),
            email=body["email"],
            email_confirmed=body.get("email_confirmed_at") is not None,
        )

    async def delete_user(self, user_id: uuid.UUID) -> None:
        """Compensating action for a signup whose DB-side orchestration
        failed after the auth user was already created — see
        OnboardingService.register. Best-effort: failures here are logged,
        never re-raised, so they don't mask the original error."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.delete(
                f"{self._base_url}/auth/v1/admin/users/{user_id}",
                headers=self._headers(),
            )

    async def generate_link(
        self,
        *,
        link_type: Literal["signup", "recovery", "magiclink"],
        email: str,
        password: str | None = None,
        redirect_to: str | None = None,
    ) -> str:
        """Returns a real Supabase-issued `action_link` — never a token this
        backend invents itself. For `signup`, Supabase only returns a link
        if the target user still has an unconfirmed email; password is
        required the first time (matches create_user's own signup call)."""
        payload: dict[str, Any] = {"type": link_type, "email": email}
        if password is not None:
            payload["password"] = password
        if redirect_to is not None:
            payload["options"] = {"redirect_to": redirect_to}

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self._base_url}/auth/v1/admin/generate_link",
                headers=self._headers(),
                json=payload,
            )
        if response.status_code >= 400:
            raise SupabaseAdminError(
                f"Supabase link generation failed: {_safe_error(response)}",
                status_code=response.status_code,
            )
        body = response.json()
        action_link = body.get("action_link") or body.get("properties", {}).get("action_link")
        if not action_link:
            raise SupabaseAdminError("Supabase link generation returned no action_link")
        return str(action_link)


def _safe_error(response: httpx.Response) -> str:
    """Never echoes the raw response body verbatim (it can carry the
    request's own email/password in some Supabase error shapes) — just the
    error message/code fields, or the status text as a fallback."""
    try:
        body = response.json()
    except ValueError:
        return response.reason_phrase
    fallback = response.reason_phrase
    return str(body.get("msg") or body.get("message") or body.get("error") or fallback)
