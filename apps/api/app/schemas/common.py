"""Response shapes shared by every tenant/super-admin list and overview endpoint.

These exist specifically so the API can never fabricate data: a metric that
has no real source yet reports its `status` honestly (`not_configured`,
`unavailable`, `no_data`) instead of a made-up number, and a list resource
whose backing schema doesn't exist yet returns real empty results with that
same honesty — never a mocked row.
"""

from typing import Any, Literal

from pydantic import BaseModel

MetricStatus = Literal["ok", "no_data", "not_configured", "unavailable"]
ResourceStatus = Literal["ok", "not_configured"]


class MetricValue(BaseModel):
    status: MetricStatus
    value: float | str | None = None
    caption: str | None = None

    @classmethod
    def not_configured(cls, caption: str | None = None) -> "MetricValue":
        return cls(status="not_configured", value=None, caption=caption)


class ResourceListResponse(BaseModel):
    items: list[dict[str, Any]] = []
    total: int = 0
    status: ResourceStatus = "not_configured"
