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
