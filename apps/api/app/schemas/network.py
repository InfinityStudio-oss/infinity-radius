from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RouterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    location_id: UUID | None
    name: str
    serial_number: str | None
    model: str | None
    management_ip: str | None
    mac_address: str | None
    firmware_version: str | None
    status: str
    last_seen_at: datetime | None
    provisioning_status: str
    hotspot_network_cidr: str | None
    hotspot_gateway_ip: str | None
    hotspot_dns_servers: str | None
    wireguard_public_key: str | None
    wireguard_tunnel_ip: str | None
    created_at: datetime
    updated_at: datetime


class RouterCreate(BaseModel):
    name: str
    location_id: UUID | None = None
    model: str | None = None
    management_ip: str | None = None
    mac_address: str | None = None


class RouterHealthRead(BaseModel):
    """Router health-panel row. `status`/`last_seen_at` are real DB columns
    (see Router model — only ever written by the Network Agent integration,
    which doesn't exist yet, so `status` is realistically always "unknown"
    and `last_seen_at` null today, not fabricated to look otherwise).
    `active_users`/`latency_ms`/`cpu_load_pct`/`uptime_seconds` have no
    backing telemetry pipeline at all — always None until one exists;
    the frontend renders "Unavailable" for a None value here, never a
    random/guessed number."""

    id: UUID
    name: str
    status: str
    last_seen_at: datetime | None
    active_users: int | None
    latency_ms: int | None
    cpu_load_pct: float | None
    uptime_seconds: int | None
