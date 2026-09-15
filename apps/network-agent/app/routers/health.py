"""Health check. Reports the agent process status and real WireGuard
interface state — never a fabricated "connected" value.
"""

import shutil
import subprocess
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_network_agent_settings

router = APIRouter()


class WireGuardStatus(BaseModel):
    status: Literal["up", "down", "unavailable"]
    detail: str | None = None


class ServiceStatus(BaseModel):
    status: Literal["active", "inactive", "unavailable"]
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    environment: str
    wireguard: WireGuardStatus
    freeradius: ServiceStatus
    radius_db: ServiceStatus


def _check_wireguard() -> WireGuardStatus:
    settings = get_network_agent_settings()

    if shutil.which("wg") is None:
        return WireGuardStatus(status="unavailable", detail="`wg` binary not found on this host")

    try:
        result = subprocess.run(  # noqa: S603
            ["wg", "show", settings.wireguard_interface],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return WireGuardStatus(status="unavailable", detail=str(exc))

    if result.returncode != 0:
        return WireGuardStatus(status="down", detail=result.stderr.strip() or "interface not found")

    return WireGuardStatus(status="up")


def _check_freeradius() -> ServiceStatus:
    """Whether the FreeRADIUS daemon on this VPS is running — a systemd
    process check, not a probe of the 1812/1813 UDP ports themselves (UDP
    has no handshake to probe meaningfully from here)."""
    if shutil.which("systemctl") is None:
        return ServiceStatus(status="unavailable", detail="systemctl not found on this host")

    try:
        result = subprocess.run(  # noqa: S603
            ["systemctl", "is-active", "freeradius"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ServiceStatus(status="unavailable", detail=str(exc))

    reported = result.stdout.strip()
    if reported == "active":
        return ServiceStatus(status="active")
    return ServiceStatus(status="inactive", detail=reported or "unknown")


def _check_radius_db() -> ServiceStatus:
    """Whether the local Postgres instance backing the RADIUS schema is
    running on this VPS — a systemd process check, deliberately not a real
    database connection: this agent holds no Postgres credentials at all
    (FreeRADIUS itself owns that connection), so this can only ever report
    "is the service up", never "can queries actually run"."""
    settings = get_network_agent_settings()
    if shutil.which("systemctl") is None:
        return ServiceStatus(status="unavailable", detail="systemctl not found on this host")

    try:
        result = subprocess.run(  # noqa: S603
            ["systemctl", "is-active", settings.radius_db_service_name],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ServiceStatus(status="unavailable", detail=str(exc))

    reported = result.stdout.strip()
    if reported == "active":
        return ServiceStatus(status="active")
    return ServiceStatus(status="inactive", detail=reported or "unknown")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_network_agent_settings()
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        wireguard=_check_wireguard(),
        freeradius=_check_freeradius(),
        radius_db=_check_radius_db(),
    )
