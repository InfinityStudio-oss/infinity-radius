"""RADIUS provisioning endpoints.

These let the Railway backend grant a paying customer network access
WITHOUT the FreeRADIUS database ever being reachable from outside this
VPS. The agent is already the authenticated, IP-allowlisted, signature-
verified boundary for privileged local operations; provisioning is one
more of those, not a new trust relationship.

Every route depends on verify_agent_signature, and the IP allowlist is
enforced globally in app.main. A request carries only a username, a
package id and a derived password — never a database connection string,
never SQL, and never anything that would let the caller address a
different host.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.security import verify_agent_signature
from app.services import radius_provisioning
from app.services.radius_provisioning import RadiusProvisioningError

router = APIRouter(prefix="/radius", dependencies=[Depends(verify_agent_signature)])


class PackageGroupRequest(BaseModel):
    package_id: str
    download_speed_kbps: int | None = None
    upload_speed_kbps: int | None = None
    session_timeout_seconds: int | None = None
    simultaneous_sessions: int = Field(default=1, ge=1)


class ProvisionUserRequest(BaseModel):
    username: str
    package_id: str
    # Derived by the backend from the subscription id and its own secrets
    # key — never stored there, and never logged here.
    password: str


class RevokeUserRequest(BaseModel):
    username: str


class ProvisioningResult(BaseModel):
    ok: bool
    detail: str | None = None


class RadiusPingResult(BaseModel):
    reachable: bool


@router.get("/ping", response_model=RadiusPingResult)
def radius_ping() -> RadiusPingResult:
    """Lets the backend distinguish 'RADIUS not configured' from 'RADIUS
    down' BEFORE it tries to provision — so activation can fail fast and
    be retried rather than half-completing."""
    return RadiusPingResult(reachable=radius_provisioning.ping())


@router.post("/package-group", response_model=ProvisioningResult)
def sync_package_group(payload: PackageGroupRequest) -> ProvisioningResult:
    try:
        radius_provisioning.sync_package_group(
            package_id=payload.package_id,
            download_speed_kbps=payload.download_speed_kbps,
            upload_speed_kbps=payload.upload_speed_kbps,
            session_timeout_seconds=payload.session_timeout_seconds,
            simultaneous_sessions=payload.simultaneous_sessions,
        )
    except RadiusProvisioningError as exc:
        # 503, not 500: this is a recoverable dependency failure and the
        # backend's retry sweep should treat it as such.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return ProvisioningResult(ok=True)


@router.post("/user", response_model=ProvisioningResult)
def provision_user(payload: ProvisionUserRequest) -> ProvisioningResult:
    try:
        radius_provisioning.provision_user(
            username=payload.username,
            package_id=payload.package_id,
            password=payload.password,
        )
    except RadiusProvisioningError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return ProvisioningResult(ok=True)


@router.post("/user/revoke", response_model=ProvisioningResult)
def revoke_user(payload: RevokeUserRequest) -> ProvisioningResult:
    try:
        radius_provisioning.revoke_user(username=payload.username)
    except RadiusProvisioningError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return ProvisioningResult(ok=True)
