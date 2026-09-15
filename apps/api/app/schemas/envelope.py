"""The standard response envelope every endpoint in the production API
returns. Callers (including the frontend) can rely on `success` +
`data` + `meta` being present on every 2xx response, and on
app.core.errors' shape for every non-2xx response — no endpoint hand-rolls
its own response shape.
"""

from pydantic import BaseModel


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class ApiResponse[T](BaseModel):
    success: bool = True
    data: T
    meta: dict[str, object] | None = None


class ApiListResponse[T](BaseModel):
    success: bool = True
    data: list[T]
    meta: PaginationMeta
