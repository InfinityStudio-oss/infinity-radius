"""The only source of truth this agent trusts for "where is router X and
what are its credentials" — a router UUID in, real connection details out.

The FastAPI backend sends only a router UUID (`public.routers.id` in the
primary database). It never sends an IP, hostname, port, or credential —
this agent resolves that itself from `routers.yaml`, so a compromised or
buggy caller can at most ask about a UUID, never make this agent connect
to an arbitrary attacker-supplied address. This is the "never expose
arbitrary IP query functionality" requirement, enforced structurally
rather than by a filter on caller input.

`routers.yaml` is populated operationally (see
infrastructure/scripts/add-router-peer.sh's final step) and is never
committed — see routers.yaml.example for its shape.
"""

from pathlib import Path
from uuid import UUID

import yaml
from pydantic import BaseModel, Field

from app.core.config import get_network_agent_settings


class RouterConnection(BaseModel):
    router_id: UUID
    host: str  # WireGuard tunnel IP — never a public address
    username: str
    password: str
    api_port: int = 8728
    api_ssl_port: int = 8729
    use_ssl: bool = True


class _RegistryEntry(BaseModel):
    host: str
    username: str
    password: str
    api_port: int = 8728
    api_ssl_port: int = 8729
    use_ssl: bool = True


class _RegistryFile(BaseModel):
    routers: dict[UUID, _RegistryEntry] = Field(default_factory=dict)


class RouterRegistry:
    def __init__(self, path: Path) -> None:
        self._path = path

    def resolve(self, router_id: UUID) -> RouterConnection | None:
        entries = self._load()
        entry = entries.get(router_id)
        if entry is None:
            return None
        return RouterConnection(
            router_id=router_id,
            host=entry.host,
            username=entry.username,
            password=entry.password,
            api_port=entry.api_port,
            api_ssl_port=entry.api_ssl_port,
            use_ssl=entry.use_ssl,
        )

    def _load(self) -> dict[UUID, _RegistryEntry]:
        if not self._path.exists():
            return {}
        raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        parsed = _RegistryFile.model_validate({"routers": raw.get("routers", {})})
        return parsed.routers


def get_router_registry() -> RouterRegistry:
    settings = get_network_agent_settings()
    return RouterRegistry(settings.router_registry_path)
