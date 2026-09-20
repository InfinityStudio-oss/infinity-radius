"""Calls the Network Agent over HTTPS: Railway (this process) -> HTTPS ->
Network Agent (VPS) -> WireGuard -> MikroTik.

Every method takes only a `router_id` (the router's UUID in our own
`public.routers` table) — never an IP, host, or credential. The Network
Agent resolves that UUID to real connection details itself (see
apps/network-agent/app/core/router_registry.py); this client has no way to
even express "connect to this arbitrary address" because the wire
protocol has no field for one.

TLS certificate verification is never disabled — `verify=False` is not a
parameter this client accepts, on purpose (see `_client()`).
"""

import json
from types import TracebackType
from typing import Any
from uuid import UUID

import httpx2 as httpx
import structlog

from app.core.config import get_settings
from app.integrations.network_agent.schemas import (
    DisconnectResult,
    HotspotActiveSession,
    InterfaceInfo,
    RadiusClientStatus,
    RouterIdentity,
    RouterResource,
    TestConnectionResult,
)
from app.integrations.network_agent.signing import sign_request

logger = structlog.get_logger("integrations.network_agent")


class NetworkAgentNotConfiguredError(RuntimeError):
    """Raised when NETWORK_AGENT_BASE_URL/NETWORK_AGENT_API_KEY are unset."""


class NetworkAgentError(RuntimeError):
    """Raised when the Network Agent is unreachable or returns an error."""


class NetworkAgentClient:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.network_agent_base_url or not settings.network_agent_api_key:
            raise NetworkAgentNotConfiguredError(
                "NETWORK_AGENT_BASE_URL and NETWORK_AGENT_API_KEY must both be set."
            )
        self._base_url = settings.network_agent_base_url.rstrip("/")
        self._api_key = settings.network_agent_api_key
        # verify defaults to True in httpx2 and is never overridden here —
        # there is deliberately no way to construct this client with
        # certificate verification disabled.
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)

    async def __aenter__(self) -> "NetworkAgentClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def _request(
        self, method: str, path: str, *, json_body: dict[str, Any] | None = None
    ) -> Any:
        body = json.dumps(json_body).encode("utf-8") if json_body is not None else b""
        headers = sign_request(api_key=self._api_key, method=method, path=path, body=body).as_dict()
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        try:
            response = await self._client.request(method, path, content=body, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("network_agent.request_failed", path=path, error=str(exc))
            raise NetworkAgentError(f"Network Agent request failed: {exc}") from exc

        if response.status_code == 404:
            raise NetworkAgentError("Unknown router_id")
        if response.status_code >= 400:
            raise NetworkAgentError(
                f"Network Agent returned {response.status_code}: {response.text}"
            )
        return response.json()

    async def test_connection(self, *, router_id: UUID) -> TestConnectionResult:
        data = await self._request("POST", f"/routers/{router_id}/test")
        return TestConnectionResult.model_validate(data)

    async def get_identity(self, *, router_id: UUID) -> RouterIdentity:
        data = await self._request("GET", f"/routers/{router_id}/identity")
        return RouterIdentity.model_validate(data)

    async def get_resource(self, *, router_id: UUID) -> RouterResource:
        data = await self._request("GET", f"/routers/{router_id}/resource")
        return RouterResource.model_validate(data)

    async def get_active_hotspot_sessions(self, *, router_id: UUID) -> list[HotspotActiveSession]:
        data = await self._request("GET", f"/routers/{router_id}/hotspot/active")
        return [HotspotActiveSession.model_validate(item) for item in data]

    async def disconnect_hotspot_user(
        self, *, router_id: UUID, session_id: str
    ) -> DisconnectResult:
        data = await self._request(
            "POST",
            f"/routers/{router_id}/hotspot/disconnect",
            json_body={"session_id": session_id},
        )
        return DisconnectResult.model_validate(data)

    async def get_interfaces(self, *, router_id: UUID) -> list[InterfaceInfo]:
        data = await self._request("GET", f"/routers/{router_id}/interfaces")
        return [InterfaceInfo.model_validate(item) for item in data]

    async def get_radius_status(self, *, router_id: UUID) -> list[RadiusClientStatus]:
        data = await self._request("GET", f"/routers/{router_id}/radius-status")
        return [RadiusClientStatus.model_validate(item) for item in data]

    # --- RADIUS provisioning -------------------------------------------
    # These do NOT take a router_id: they act on the VPS's own local
    # FreeRADIUS database, not on a MikroTik. They live here because this
    # client is already the authenticated, signed channel to that VPS —
    # which is precisely what makes exposing the RADIUS database to the
    # internet unnecessary.

    async def radius_ping(self) -> bool:
        """True if the agent can reach its local RADIUS database. Lets the
        caller distinguish 'not configured' from 'down' before attempting
        to provision."""
        data = await self._request("GET", "/radius/ping")
        return bool(data.get("reachable", False))

    async def sync_radius_package_group(
        self,
        *,
        package_id: UUID,
        download_speed_kbps: int | None,
        upload_speed_kbps: int | None,
        session_timeout_seconds: int | None,
        simultaneous_sessions: int,
    ) -> None:
        await self._request(
            "POST",
            "/radius/package-group",
            json_body={
                "package_id": str(package_id),
                "download_speed_kbps": download_speed_kbps,
                "upload_speed_kbps": upload_speed_kbps,
                "session_timeout_seconds": session_timeout_seconds,
                "simultaneous_sessions": simultaneous_sessions,
            },
        )

    async def provision_radius_user(
        self, *, username: str, package_id: UUID, password: str
    ) -> None:
        """The password is derived by this process from the subscription id
        and never stored; it crosses to the agent inside a signed request
        over TLS and is never logged on either side."""
        await self._request(
            "POST",
            "/radius/user",
            json_body={
                "username": username,
                "package_id": str(package_id),
                "password": password,
            },
        )

    async def revoke_radius_user(self, *, username: str) -> None:
        await self._request(
            "POST", "/radius/user/revoke", json_body={"username": username}
        )

    async def diagnostic_ping(self) -> tuple[bool, int]:
        """Authenticated reachability probe for the Super Admin diagnostics
        endpoint. Every Network Agent route requires a router UUID, so this
        signs a GET against the nil UUID (never a real router) on the
        cheapest read-only route (`/identity`) and reads the raw status
        code directly — unlike `_request`, it never raises on 4xx, since a
        404 here ("Unknown router_id") is itself the expected, successful
        outcome: it proves the signature and IP allowlist were both
        accepted before the route body ever ran. Returns
        (authenticated, status_code); 401/403 means rejected before the
        route ran, anything else (normally 404) means accepted.
        """
        path = "/routers/00000000-0000-0000-0000-000000000000/identity"
        headers = sign_request(api_key=self._api_key, method="GET", path=path).as_dict()
        response = await self._client.request("GET", path, headers=headers)
        authenticated = response.status_code not in (401, 403)
        return authenticated, response.status_code
