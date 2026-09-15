"""Router-control endpoints. Every route takes only a router UUID in the
path — never a host/IP — and resolves it via app.core.router_registry.
Every route depends on verify_agent_signature (see app.core.security);
the IP allowlist is enforced globally in app.main.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.router_registry import RouterConnection, RouterRegistry, get_router_registry
from app.core.security import verify_agent_signature
from app.schemas.mikrotik import (
    DisconnectResult,
    HotspotActiveSession,
    InterfaceInfo,
    RadiusClientStatus,
    RouterIdentity,
    RouterResource,
    TestConnectionResult,
)
from app.services import mikrotik_client

router = APIRouter(
    prefix="/routers/{router_id}",
    dependencies=[Depends(verify_agent_signature)],
)


class DisconnectRequest(BaseModel):
    session_id: str


def _resolve(router_id: UUID, registry: RouterRegistry) -> RouterConnection:
    connection = registry.resolve(router_id)
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown router_id — this agent has no registered connection details for it",
        )
    return connection


@router.post("/test", response_model=TestConnectionResult)
async def test_router(
    router_id: UUID, registry: RouterRegistry = Depends(get_router_registry)
) -> TestConnectionResult:
    connection = _resolve(router_id, registry)
    return await mikrotik_client.test_connection(connection)


@router.get("/identity", response_model=RouterIdentity)
async def get_identity(
    router_id: UUID, registry: RouterRegistry = Depends(get_router_registry)
) -> RouterIdentity:
    connection = _resolve(router_id, registry)
    try:
        return await mikrotik_client.get_identity(connection)
    except mikrotik_client.RouterOSError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/resource", response_model=RouterResource)
async def get_resource(
    router_id: UUID, registry: RouterRegistry = Depends(get_router_registry)
) -> RouterResource:
    """RouterOS version, CPU load, memory, and uptime in one call."""
    connection = _resolve(router_id, registry)
    try:
        return await mikrotik_client.get_resource(connection)
    except mikrotik_client.RouterOSError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/hotspot/active", response_model=list[HotspotActiveSession])
async def get_active_hotspot_sessions(
    router_id: UUID, registry: RouterRegistry = Depends(get_router_registry)
) -> list[HotspotActiveSession]:
    connection = _resolve(router_id, registry)
    try:
        return await mikrotik_client.get_active_hotspot_sessions(connection)
    except mikrotik_client.RouterOSError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/hotspot/disconnect", response_model=DisconnectResult)
async def disconnect_hotspot_user(
    router_id: UUID,
    payload: DisconnectRequest,
    registry: RouterRegistry = Depends(get_router_registry),
) -> DisconnectResult:
    connection = _resolve(router_id, registry)
    try:
        return await mikrotik_client.disconnect_hotspot_user(connection, payload.session_id)
    except mikrotik_client.RouterOSError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/interfaces", response_model=list[InterfaceInfo])
async def get_interfaces(
    router_id: UUID, registry: RouterRegistry = Depends(get_router_registry)
) -> list[InterfaceInfo]:
    connection = _resolve(router_id, registry)
    try:
        return await mikrotik_client.get_interfaces(connection)
    except mikrotik_client.RouterOSError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/radius-status", response_model=list[RadiusClientStatus])
async def get_radius_status(
    router_id: UUID, registry: RouterRegistry = Depends(get_router_registry)
) -> list[RadiusClientStatus]:
    """The router's own configured RADIUS client entries (`/radius/print`) —
    confirms it's pointed at the right FreeRADIUS address/ports, not a
    liveness check of FreeRADIUS itself (see /health for the agent's own
    dependency status)."""
    connection = _resolve(router_id, registry)
    try:
        return await mikrotik_client.get_radius_status(connection)
    except mikrotik_client.RouterOSError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
