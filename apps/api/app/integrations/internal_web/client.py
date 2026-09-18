"""Worker-side client for the internal disbursement-reconciliation
endpoint (app/api/v1/internal_disbursements.py) — the Celery worker's
ONLY path to Selcom Business. Reaches web over Railway private networking
(INTERNAL_WEB_BASE_URL, e.g. "http://<RAILWAY_PRIVATE_DOMAIN>:8000") and
authenticates with a dedicated HMAC signature (app/core/internal_auth.py),
never a tenant/Super Admin JWT and never relying on private networking
alone. Never imports or references SelcomBusinessClient — the worker has
no Selcom awareness at all after Option B; see app/tasks/reconciliation.py.
"""

import json
from types import TracebackType
from uuid import UUID

import httpx2 as httpx
import structlog

from app.core.config import get_settings
from app.core.internal_auth import sign_internal_request

logger = structlog.get_logger("integrations.internal_web")

_RECONCILE_PATH_SUFFIX = "/internal/disbursements/reconcile"


class InternalWebNotConfiguredError(RuntimeError):
    """Raised when INTERNAL_WEB_BASE_URL/INTERNAL_WORKER_WEB_HMAC_KEY are unset."""


class InternalWebError(RuntimeError):
    """Raised when web rejects or fails to process the reconcile request."""


class InternalWebTransportError(RuntimeError):
    """Raised on a network-level failure (timeout, connection error) —
    distinct from InternalWebError so callers can treat "unknown, try
    again next sweep" (transport) differently from "web actively
    rejected this" (e.g. a real 401/404), though both are currently
    handled the same safe way (skip this row, keep going)."""


class InternalReconcileResult:
    __slots__ = ("withdrawal_id", "status", "reconciled")

    def __init__(self, *, withdrawal_id: UUID, status: str, reconciled: bool) -> None:
        self.withdrawal_id = withdrawal_id
        self.status = status
        self.reconciled = reconciled


class InternalWebClient:
    """One bounded retry on a transport-level failure only (never on a
    4xx/5xx response body) — a single flaky connection attempt must not
    make an otherwise-healthy sweep skip a row it could have resolved."""

    _TIMEOUT_SECONDS = 15.0
    _MAX_ATTEMPTS = 2

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.internal_web_base_url or not settings.internal_worker_web_hmac_key:
            raise InternalWebNotConfiguredError(
                "INTERNAL_WEB_BASE_URL and INTERNAL_WORKER_WEB_HMAC_KEY must both be set."
            )
        self._base_url = settings.internal_web_base_url.rstrip("/")
        self._hmac_key = settings.internal_worker_web_hmac_key
        self._path = f"{settings.api_v1_prefix}{_RECONCILE_PATH_SUFFIX}"
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=self._TIMEOUT_SECONDS)

    async def __aenter__(self) -> "InternalWebClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def reconcile_withdrawal(self, *, withdrawal_id: UUID) -> InternalReconcileResult:
        body = json.dumps({"withdrawal_id": str(withdrawal_id)}).encode("utf-8")

        last_transport_error: httpx.HTTPError | None = None
        for attempt in range(1, self._MAX_ATTEMPTS + 1):
            headers = sign_internal_request(
                secret=self._hmac_key, method="POST", path=self._path, body=body
            ).as_dict()
            headers["Content-Type"] = "application/json"
            try:
                response = await self._client.post(self._path, content=body, headers=headers)
                break
            except httpx.HTTPError as exc:
                last_transport_error = exc
                logger.warning(
                    "internal_web.request_failed",
                    withdrawal_id=str(withdrawal_id),
                    attempt=attempt,
                    error=str(exc),
                )
        else:
            raise InternalWebTransportError(
                f"Internal web request failed after {self._MAX_ATTEMPTS} attempts"
            ) from last_transport_error

        if response.status_code == 404:
            raise InternalWebError("Unknown withdrawal_id")
        if response.status_code >= 400:
            # Never logs response body — it's web's own error envelope, not
            # provider data, but keeping this endpoint's failure surface as
            # narrow as any other integration's is the safer default.
            raise InternalWebError(f"Internal web returned {response.status_code}")

        # The internal route returns its minimal shape directly, unwrapped —
        # no ApiResponse envelope, no provider payload — see
        # app/api/v1/internal_disbursements.py.
        data = response.json()
        return InternalReconcileResult(
            withdrawal_id=UUID(str(data["withdrawal_id"])),
            status=str(data["status"]),
            reconciled=bool(data["reconciled"]),
        )
