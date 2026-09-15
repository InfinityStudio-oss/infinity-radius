"""Response shapes for every MikroTik RouterOS function this agent exposes.
Every field here comes from a real RouterOS API call (see
app.services.mikrotik_client) — nothing is fabricated if a router is
unreachable; callers get a clear error instead."""

from pydantic import BaseModel


class TestConnectionResult(BaseModel):
    reachable: bool
    latency_ms: float | None = None
    detail: str | None = None


class RouterIdentity(BaseModel):
    name: str


class RouterResource(BaseModel):
    routeros_version: str
    board_name: str | None = None
    cpu_load_percent: int
    free_memory_bytes: int
    total_memory_bytes: int
    uptime: str


class HotspotActiveSession(BaseModel):
    session_id: str
    user: str
    address: str | None = None
    mac_address: str | None = None
    uptime: str | None = None
    bytes_in: int | None = None
    bytes_out: int | None = None


class DisconnectResult(BaseModel):
    disconnected: bool
    detail: str | None = None


class InterfaceInfo(BaseModel):
    name: str
    type: str
    running: bool
    disabled: bool
    rx_bytes: int | None = None
    tx_bytes: int | None = None


class RadiusClientStatus(BaseModel):
    address: str
    service: str
    disabled: bool
