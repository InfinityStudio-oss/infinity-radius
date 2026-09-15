"""Talks to a MikroTik router's RouterOS API — the only module in this
codebase that does. Every function here takes a resolved RouterConnection
(see app.core.router_registry) and nothing else; there is no code path
that accepts a caller-supplied host/IP.

`routeros_api` is a synchronous, blocking-socket library, so every call
runs in a worker thread via `asyncio.to_thread` rather than blocking the
agent's event loop.

TLS: RouterOS API-SSL (port 8729) with certificate verification is the
default and is refused to be disabled in production (see
NetworkAgentSettings._forbid_insecure_mikrotik_tls_in_production) — this
module never passes ssl_verify=False on its own initiative.
"""

import asyncio
import time
from typing import Any

import routeros_api
from routeros_api.exceptions import RouterOsApiConnectionError, RouterOsApiError

from app.core.config import get_network_agent_settings
from app.core.router_registry import RouterConnection
from app.schemas.mikrotik import (
    DisconnectResult,
    HotspotActiveSession,
    InterfaceInfo,
    RadiusClientStatus,
    RouterIdentity,
    RouterResource,
    TestConnectionResult,
)


class RouterOSError(Exception):
    """Raised when a router is unreachable or rejects a command — always
    caught at the route handler boundary and turned into a typed error
    response, never allowed to leak a raw socket/library exception."""


def _open_connection(conn: RouterConnection) -> routeros_api.RouterOsApiPool:
    settings = get_network_agent_settings()
    port = conn.api_ssl_port if conn.use_ssl else conn.api_port
    return routeros_api.RouterOsApiPool(
        conn.host,
        username=conn.username,
        password=conn.password,
        port=port,
        use_ssl=conn.use_ssl,
        ssl_verify=settings.mikrotik_ssl_verify,
        ssl_verify_hostname=settings.mikrotik_ssl_verify,
        plaintext_login=True,
    )


def _as_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "yes"}


def _as_int(value: object, *, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _test_connection_sync(conn: RouterConnection) -> TestConnectionResult:
    started = time.monotonic()
    pool = _open_connection(conn)
    try:
        api = pool.get_api()
        api.get_resource("/system/identity").get()
        latency_ms = (time.monotonic() - started) * 1000
        return TestConnectionResult(reachable=True, latency_ms=round(latency_ms, 2))
    finally:
        pool.disconnect()


def _get_identity_sync(conn: RouterConnection) -> RouterIdentity:
    pool = _open_connection(conn)
    try:
        api = pool.get_api()
        rows = api.get_resource("/system/identity").get()
        name = rows[0]["name"] if rows else "unknown"
        return RouterIdentity(name=name)
    finally:
        pool.disconnect()


def _get_resource_sync(conn: RouterConnection) -> RouterResource:
    pool = _open_connection(conn)
    try:
        api = pool.get_api()
        rows = api.get_resource("/system/resource").get()
        row: dict[str, Any] = rows[0] if rows else {}
        return RouterResource(
            routeros_version=str(row.get("version", "unknown")),
            board_name=row.get("board-name"),
            cpu_load_percent=_as_int(row.get("cpu-load")),
            free_memory_bytes=_as_int(row.get("free-memory")),
            total_memory_bytes=_as_int(row.get("total-memory")),
            uptime=str(row.get("uptime", "unknown")),
        )
    finally:
        pool.disconnect()


def _get_active_hotspot_sessions_sync(conn: RouterConnection) -> list[HotspotActiveSession]:
    pool = _open_connection(conn)
    try:
        api = pool.get_api()
        rows = api.get_resource("/ip/hotspot/active").get()
        sessions = []
        for row in rows:
            bytes_in = row.get("bytes-in")
            bytes_out = row.get("bytes-out")
            if bytes_in is None and bytes_out is None and "bytes" in row:
                # Older RouterOS versions report a single combined "in/out" field.
                parts = str(row["bytes"]).split("/")
                if len(parts) == 2:
                    bytes_in, bytes_out = parts
            sessions.append(
                HotspotActiveSession(
                    session_id=str(row.get(".id", "")),
                    user=str(row.get("user", "")),
                    address=row.get("address"),
                    mac_address=row.get("mac-address"),
                    uptime=row.get("uptime"),
                    bytes_in=_as_int(bytes_in) if bytes_in is not None else None,
                    bytes_out=_as_int(bytes_out) if bytes_out is not None else None,
                )
            )
        return sessions
    finally:
        pool.disconnect()


def _disconnect_hotspot_user_sync(conn: RouterConnection, session_id: str) -> DisconnectResult:
    pool = _open_connection(conn)
    try:
        api = pool.get_api()
        api.get_resource("/ip/hotspot/active").remove(id=session_id)
        return DisconnectResult(disconnected=True)
    finally:
        pool.disconnect()


def _get_interfaces_sync(conn: RouterConnection) -> list[InterfaceInfo]:
    pool = _open_connection(conn)
    try:
        api = pool.get_api()
        rows = api.get_resource("/interface").get()
        return [
            InterfaceInfo(
                name=str(row.get("name", "")),
                type=str(row.get("type", "")),
                running=_as_bool(row.get("running")),
                disabled=_as_bool(row.get("disabled")),
                rx_bytes=_as_int(row.get("rx-byte")) if "rx-byte" in row else None,
                tx_bytes=_as_int(row.get("tx-byte")) if "tx-byte" in row else None,
            )
            for row in rows
        ]
    finally:
        pool.disconnect()


def _get_radius_status_sync(conn: RouterConnection) -> list[RadiusClientStatus]:
    pool = _open_connection(conn)
    try:
        api = pool.get_api()
        rows = api.get_resource("/radius").get()
        return [
            RadiusClientStatus(
                address=str(row.get("address", "")),
                service=str(row.get("service", "")),
                disabled=_as_bool(row.get("disabled")),
            )
            for row in rows
        ]
    finally:
        pool.disconnect()


async def _run(fn: Any, *args: Any) -> Any:
    try:
        return await asyncio.to_thread(fn, *args)
    except (RouterOsApiConnectionError, RouterOsApiError, OSError) as exc:
        raise RouterOSError(str(exc)) from exc


async def test_connection(conn: RouterConnection) -> TestConnectionResult:
    try:
        return await _run(_test_connection_sync, conn)  # type: ignore[no-any-return]
    except RouterOSError as exc:
        return TestConnectionResult(reachable=False, detail=str(exc))


async def get_identity(conn: RouterConnection) -> RouterIdentity:
    return await _run(_get_identity_sync, conn)  # type: ignore[no-any-return]


async def get_resource(conn: RouterConnection) -> RouterResource:
    return await _run(_get_resource_sync, conn)  # type: ignore[no-any-return]


async def get_active_hotspot_sessions(conn: RouterConnection) -> list[HotspotActiveSession]:
    return await _run(_get_active_hotspot_sessions_sync, conn)  # type: ignore[no-any-return]


async def disconnect_hotspot_user(conn: RouterConnection, session_id: str) -> DisconnectResult:
    return await _run(_disconnect_hotspot_user_sync, conn, session_id)  # type: ignore[no-any-return]


async def get_interfaces(conn: RouterConnection) -> list[InterfaceInfo]:
    return await _run(_get_interfaces_sync, conn)  # type: ignore[no-any-return]


async def get_radius_status(conn: RouterConnection) -> list[RadiusClientStatus]:
    return await _run(_get_radius_status_sync, conn)  # type: ignore[no-any-return]
