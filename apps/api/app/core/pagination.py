"""Shared list-query parsing: every list endpoint accepts the same
page/page_size/search/sort/filter query parameters, parsed once here
rather than reimplemented per module.
"""

import math
from dataclasses import dataclass, field

from fastapi import Query, Request

from app.schemas.envelope import PaginationMeta

_RESERVED_QUERY_KEYS = {"page", "page_size", "search", "sort"}


@dataclass(frozen=True)
class ListParams:
    page: int
    page_size: int
    search: str | None
    sort: str | None
    """Any query param not in page/page_size/search/sort — exact-match
    filters, applied by each repository only for the columns it explicitly
    allows (see BaseRepository.filterable_fields)."""
    filters: dict[str, str] = field(default_factory=dict)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def list_params(
    request: Request,
    page: int = Query(default=1, ge=1, description="1-indexed page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Rows per page (max 100)"),
    search: str | None = Query(default=None, description="Free-text search"),
    sort: str | None = Query(
        default=None,
        description="Column to sort by; prefix with - for descending, e.g. -created_at",
    ),
) -> ListParams:
    filters = {
        key: value
        for key, value in request.query_params.items()
        if key not in _RESERVED_QUERY_KEYS
    }
    return ListParams(page=page, page_size=page_size, search=search, sort=sort, filters=filters)


def build_pagination_meta(*, total: int, params: ListParams) -> PaginationMeta:
    total_pages = math.ceil(total / params.page_size) if total > 0 else 0
    return PaginationMeta(
        page=params.page,
        page_size=params.page_size,
        total=total,
        total_pages=total_pages,
    )
