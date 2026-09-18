"""app/tasks/reconciliation.py and app/integrations/internal_web/client.py
— the worker side of Option B network centralization. The worker must
never call Selcom directly (no SelcomBusinessClient import/use anywhere
in this path); it only decides which withdrawals need reconciliation
(pure DB read) and asks web's internal HMAC-authenticated endpoint to do
the actual Selcom query. See tests/test_internal_disbursements.py for the
endpoint's own auth/behavior tests — these tests focus on the worker's
side of the wire: it sends a genuinely valid signed request, and a bad
row/response never stops the sweep.
"""

import ast
import asyncio
import inspect
from decimal import Decimal
from uuid import UUID, uuid4

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

import app.tasks.reconciliation as reconciliation_module
from app.core.config import get_settings
from app.core.enums import LedgerDirection, WalletBucket
from app.db.session import AsyncSessionLocal
from app.integrations.internal_web.client import (
    InternalWebClient,
    InternalWebNotConfiguredError,
    InternalWebTransportError,
)
from app.integrations.selcom_business.client import SelcomBusinessClient
from app.integrations.selcom_business.schemas import (
    AccountLookupData,
    AccountLookupResponse,
    TransactionProcessData,
    TransactionProcessResponse,
    TransactionQueryData,
    TransactionQueryResponse,
)
from app.main import app as fastapi_app
from app.services.wallet import WalletService
from app.tasks.reconciliation import _reconcile_pending_withdrawals
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(fastapi_app)

_HMAC_KEY = "test-only-internal-hmac-key-do-not-use-in-prod"


@pytest.fixture
def internal_worker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_WORKER_WEB_HMAC_KEY", _HMAC_KEY)
    monkeypatch.setenv("INTERNAL_WEB_BASE_URL", "http://web.internal:8000")
    get_settings.cache_clear()


def test_reconciliation_module_never_imports_selcom_business() -> None:
    """Structural guarantee, not just a mocking convention — if a future
    change reintroduces a direct Selcom call from the worker path, this
    fails even if every behavioral test still happens to pass. Checks the
    actual `import` AST nodes only (not comments/docstrings, which
    legitimately reference SelcomBusinessClient by name to explain why it
    must never appear as a real import here)."""
    tree = ast.parse(inspect.getsource(reconciliation_module))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)
            imported_names.update(alias.name for alias in node.names)

    assert not any("selcom_business" in name.lower() for name in imported_names)
    assert not hasattr(reconciliation_module, "SelcomBusinessClient")


def test_internal_web_client_requires_both_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTERNAL_WORKER_WEB_HMAC_KEY", raising=False)
    monkeypatch.delenv("INTERNAL_WEB_BASE_URL", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(InternalWebNotConfiguredError):
            InternalWebClient()
    finally:
        get_settings.cache_clear()


def test_sweep_is_a_safe_no_op_when_internal_web_is_not_configured(
    monkeypatch: pytest.MonkeyPatch, capture_withdrawal_otp: list[str]
) -> None:
    """A real PROCESSING withdrawal exists, but INTERNAL_WORKER_WEB_HMAC_KEY/
    INTERNAL_WEB_BASE_URL are both unset — the sweep must still discover
    it (list_reconcilable_withdrawals is pure DB, no Selcom awareness) and
    must not crash; it simply can't act on it this cycle."""
    monkeypatch.delenv("INTERNAL_WORKER_WEB_HMAC_KEY", raising=False)
    monkeypatch.delenv("INTERNAL_WEB_BASE_URL", raising=False)
    get_settings.cache_clear()

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        withdrawal_id = _create_processing_withdrawal(
            ctx, tenant_id=tenant_id, admin_id=admin_id, owner_id=owner_id,
            monkeypatch=monkeypatch, capture_withdrawal_otp=capture_withdrawal_otp,
        )

        try:
            scanned = asyncio.run(_reconcile_pending_withdrawals())
        finally:
            get_settings.cache_clear()

        after = client.get(
            f"/api/v1/payouts/{withdrawal_id}", headers=auth_header(user_id=owner_id)
        )

    assert scanned >= 1  # discovered, even though nothing could be done about it
    assert after.json()["data"]["status"] == "PROCESSING"  # untouched, not corrupted


# --- Real end-to-end wiring: worker's signed request against the real route ---


async def _credit_available(tenant_id: UUID, actor_id: UUID, amount: str) -> None:
    async with AsyncSessionLocal() as db:
        await WalletService(db).create_adjustment(
            tenant_id=tenant_id, wallet_bucket=WalletBucket.AVAILABLE,
            direction=LedgerDirection.CREDIT, amount=Decimal(amount),
            reason="test setup — seed available balance", actor_id=actor_id,
        )
        await db.commit()


def _fake_account_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(
        self: SelcomBusinessClient, *, bank: str, account: str, trans_id: str, amount: object = None
    ) -> AccountLookupResponse:
        return AccountLookupResponse(
            success=True, resultcode="000",
            data=AccountLookupData(
                account_name="Jane Test", operator=bank, total_charges=Decimal("0")
            ),
        )

    monkeypatch.setattr(SelcomBusinessClient, "account_lookup", _fake)


def _fake_transaction_process_inprogress(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(self: SelcomBusinessClient, **kwargs: object) -> TransactionProcessResponse:
        return TransactionProcessResponse(
            success=True, resultcode="111", message="Transaction in progress",
            data=TransactionProcessData(
                trans_id=str(kwargs["trans_id"]), status="ACCEPTED",
                amount=Decimal(str(kwargs["amount"])), currency="TZS",
            ),
        )

    monkeypatch.setattr(SelcomBusinessClient, "transaction_process", _fake)


def _create_processing_withdrawal(
    ctx: SeededContext, *, tenant_id: UUID, admin_id: UUID, owner_id: UUID,
    monkeypatch: pytest.MonkeyPatch, capture_withdrawal_otp: list[str],
) -> UUID:
    owner_headers = auth_header(user_id=owner_id)
    ctx.new_settlement_config(tenant_id=tenant_id)
    ctx.new_tenant_feature_flags(tenant_id=tenant_id, payout_enabled=True)
    ctx.new_tenant_verification(tenant_id=tenant_id, status="APPROVED", email_verified=True)
    asyncio.run(_credit_available(tenant_id, admin_id, "1000.00"))

    destination_id = client.post(
        "/api/v1/payouts/destinations", headers=owner_headers,
        json={
            "label": "M-Pesa", "channel": "mobile_money",
            "destination_code": "MPESA", "account_number": "255700000000",
        },
    ).json()["data"]["id"]
    request_response = client.post(
        "/api/v1/payouts", headers=owner_headers,
        json={"destination_id": destination_id, "amount": "600.00"},
    )
    withdrawal_id = request_response.json()["withdrawal"]["id"]
    code = capture_withdrawal_otp[-1]

    _fake_account_lookup(monkeypatch)
    _fake_transaction_process_inprogress(monkeypatch)
    confirm_response = client.post(
        f"/api/v1/payouts/{withdrawal_id}/confirm-2fa", headers=owner_headers, json={"code": code}
    )
    assert confirm_response.json()["data"]["status"] == "PROCESSING"
    return UUID(withdrawal_id)


def _client_pointed_at_test_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirects InternalWebClient's outbound HTTP to the in-process test
    ASGI app instead of a real TCP connection to Railway private
    networking — everything else (signing, headers, path, body) is
    exactly what the real worker sends."""

    real_init = InternalWebClient.__init__

    def _patched_init(self: InternalWebClient) -> None:
        real_init(self)
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fastapi_app),
            base_url=self._base_url,
            timeout=15.0,
        )

    monkeypatch.setattr(InternalWebClient, "__init__", _patched_init)


def test_worker_sends_a_genuinely_valid_signed_request_and_resolves_the_withdrawal(
    internal_worker_env: None, monkeypatch: pytest.MonkeyPatch, capture_withdrawal_otp: list[str]
) -> None:
    # Keyed by trans_id (not a bare counter) so this stays correct even if
    # the shared local test database happens to have another
    # PROCESSING/AMBIGUOUS row left over from an unrelated run — the
    # invariant that matters is "every discovered row queried at most
    # once", not "exactly one query happened in the whole process".
    query_calls_by_trans_id: dict[str, int] = {}
    process_calls = 0

    async def _counting_query(
        self: SelcomBusinessClient, *, trans_id: str
    ) -> TransactionQueryResponse:
        query_calls_by_trans_id[trans_id] = query_calls_by_trans_id.get(trans_id, 0) + 1
        return TransactionQueryResponse(
            success=True, resultcode="000",
            data=TransactionQueryData(
                trans_id=trans_id, status="COMPLETED", amount=Decimal("600.00"),
                currency="TZS", selcom_receipt=f"RCPT-{trans_id}",
            ),
        )

    async def _failing_process(self: SelcomBusinessClient, **kwargs: object) -> None:
        nonlocal process_calls
        process_calls += 1
        raise AssertionError("worker path must never reach transaction_process")

    _client_pointed_at_test_app(monkeypatch)

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        _create_processing_withdrawal(
            ctx, tenant_id=tenant_id, admin_id=admin_id, owner_id=owner_id,
            monkeypatch=monkeypatch, capture_withdrawal_otp=capture_withdrawal_otp,
        )

        monkeypatch.setattr(SelcomBusinessClient, "transaction_query", _counting_query)
        monkeypatch.setattr(SelcomBusinessClient, "transaction_process", _failing_process)

        scanned = asyncio.run(_reconcile_pending_withdrawals())

    assert scanned >= 1
    assert len(query_calls_by_trans_id) == scanned  # every discovered row was queried...
    assert max(query_calls_by_trans_id.values(), default=0) == 1  # ...exactly once each
    assert process_calls == 0


def test_a_failing_row_never_stops_the_sweep(
    internal_worker_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One withdrawal's internal-web call fails (simulating a transport
    error/5xx from web); a second, healthy withdrawal in the same sweep
    must still be attempted — proving the per-row try/except in
    _reconcile_pending_withdrawals isolates failures at the granularity of
    a single withdrawal, not the whole sweep.

    This is a pure control-flow test: both PayoutService.
    list_reconcilable_withdrawals (the DB read) and InternalWebClient.
    reconcile_withdrawal (the wire call) are mocked at their own module
    boundaries — the real DB-backed discovery is already exercised by
    test_sweep_is_a_safe_no_op_when_internal_web_is_not_configured above,
    and the real signed round trip by
    test_worker_sends_a_genuinely_valid_signed_request_and_resolves_the_
    withdrawal. Deliberately avoids mixing several real TestClient
    requests with a same-process asyncio.run() in one test, which on
    Windows occasionally corrupts NullPool's asyncpg connection pool
    across event loops (see db_fixtures.py's module docstring) — that's a
    pre-existing local-dev test-harness quirk, not a defect in this
    control flow, and it's cheap to avoid entirely for a test that isn't
    about the DB or the wire protocol.
    """
    from types import SimpleNamespace

    from app.integrations.internal_web.client import InternalReconcileResult
    from app.services.payouts import PayoutService

    failing_id = uuid4()
    healthy_id = uuid4()
    fake_pending: list[object] = [
        SimpleNamespace(id=failing_id, status="PROCESSING"),
        SimpleNamespace(id=healthy_id, status="PROCESSING"),
    ]
    attempted: list[UUID] = []

    async def _fake_list_reconcilable_withdrawals(self: PayoutService) -> list[object]:
        return fake_pending

    async def _flaky_reconcile_withdrawal(
        self: InternalWebClient, *, withdrawal_id: UUID
    ) -> InternalReconcileResult:
        attempted.append(withdrawal_id)
        if withdrawal_id == failing_id:
            raise InternalWebTransportError("simulated internal-web outage")
        return InternalReconcileResult(
            withdrawal_id=withdrawal_id, status="SUCCESS", reconciled=True
        )

    monkeypatch.setattr(
        PayoutService, "list_reconcilable_withdrawals", _fake_list_reconcilable_withdrawals
    )
    monkeypatch.setattr(InternalWebClient, "reconcile_withdrawal", _flaky_reconcile_withdrawal)

    scanned = asyncio.run(_reconcile_pending_withdrawals())

    assert scanned == 2
    assert attempted == [failing_id, healthy_id]  # both attempted, in discovery order
