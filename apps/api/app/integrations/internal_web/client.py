"""Worker-side client for the internal reconciliation endpoints — the
Celery worker's ONLY path to either Selcom integration (Business
Disbursement: app/api/v1/internal_disbursements.py; Mobile Checkout
Collection: app/api/v1/internal_collections.py). Reaches web over Railway
private networking (INTERNAL_WEB_BASE_URL, e.g.
"http://<RAILWAY_PRIVATE_DOMAIN>:8000") and authenticates with a
dedicated HMAC signature (app/core/internal_auth.py), never a tenant/
Super Admin JWT and never relying on private networking alone. Never
imports or references SelcomBusinessClient/SelcomCollectionClient — the
worker has no Selcom awareness at all after Option B; see
app/tasks/reconciliation.py and app/tasks/collections.py. One shared
client class for both, since the transport/signing/retry logic is
identical — only the path and payload shape differ per reconcile_*
method, deliberately not a second HMAC secret (see
INTERNAL_WORKER_WEB_HMAC_KEY, reused as-is).
"""

import json
from types import TracebackType
from uuid import UUID

import httpx2 as httpx
import structlog

from app.core.config import get_settings
from app.core.internal_auth import sign_internal_request

logger = structlog.get_logger("integrations.internal_web")

_DISBURSEMENT_RECONCILE_PATH_SUFFIX = "/internal/disbursements/reconcile"
_COLLECTION_RECONCILE_PATH_SUFFIX = "/internal/collections/reconcile"


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


class InternalCollectionReconcileResult:
    __slots__ = ("transaction_id", "status")

    def __init__(self, *, transaction_id: UUID, status: str) -> None:
        self.transaction_id = transaction_id
        self.status = status


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
        self._disbursement_path = f"{settings.api_v1_prefix}{_DISBURSEMENT_RECONCILE_PATH_SUFFIX}"
        self._collection_path = f"{settings.api_v1_prefix}{_COLLECTION_RECONCILE_PATH_SUFFIX}"
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

    async def _post_json(
        self, *, path: str, body_obj: dict[str, str], log_context: dict[str, str]
    ) -> dict[str, object]:
        """Shared signed-POST-with-bounded-retry used by both
        reconcile_withdrawal and reconcile_collection — identical
        transport/signing/retry behavior, only the path/body/error
        context differ per caller."""
        body = json.dumps(body_obj).encode("utf-8")

        last_transport_error: httpx.HTTPError | None = None
        for attempt in range(1, self._MAX_ATTEMPTS + 1):
            headers = sign_internal_request(
                secret=self._hmac_key, method="POST", path=path, body=body
            ).as_dict()
            headers["Content-Type"] = "application/json"
            try:
                response = await self._client.post(path, content=body, headers=headers)
                break
            except httpx.HTTPError as exc:
                last_transport_error = exc
                logger.warning(
                    "internal_web.request_failed", attempt=attempt, error=str(exc), **log_context
                )
        else:
            raise InternalWebTransportError(
                f"Internal web request failed after {self._MAX_ATTEMPTS} attempts"
            ) from last_transport_error

        if response.status_code == 404:
            raise InternalWebError("Unknown id")
        if response.status_code >= 400:
            # Never logs response body — it's web's own error envelope, not
            # provider data, but keeping this endpoint's failure surface as
            # narrow as any other integration's is the safer default.
            raise InternalWebError(f"Internal web returned {response.status_code}")

        result: dict[str, object] = response.json()
        return result

    async def reconcile_withdrawal(self, *, withdrawal_id: UUID) -> InternalReconcileResult:
        # The internal route returns its minimal shape directly, unwrapped —
        # no ApiResponse envelope, no provider payload — see
        # app/api/v1/internal_disbursements.py.
        data = await self._post_json(
            path=self._disbursement_path,
            body_obj={"withdrawal_id": str(withdrawal_id)},
            log_context={"withdrawal_id": str(withdrawal_id)},
        )
        return InternalReconcileResult(
            withdrawal_id=UUID(str(data["withdrawal_id"])),
            status=str(data["status"]),
            reconciled=bool(data["reconciled"]),
        )

    async def reconcile_collection(
        self, *, transaction_id: UUID
    ) -> InternalCollectionReconcileResult:
        # Same minimal, unwrapped response shape — see
        # app/api/v1/internal_collections.py.
        data = await self._post_json(
            path=self._collection_path,
            body_obj={"transaction_id": str(transaction_id)},
            log_context={"transaction_id": str(transaction_id)},
        )
        return InternalCollectionReconcileResult(
            transaction_id=UUID(str(data["transaction_id"])),
            status=str(data["status"]),
        )
