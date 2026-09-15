"""A real, single-use, short-lived confirmation code guarding the maker's
own withdrawal request — the "2FA confirmation" step in the withdrawal
flow. Only the hash is ever stored; the raw code is returned exactly once,
at generation time, the same convention this codebase already uses for
RADIUS secrets and WireGuard private keys (app/services/router_provisioning.py).

DELIVERY CHANNEL IS A TODO, same honesty rule as Selcom's
TODO(selcom-docs): there is no SMS/email provider integrated anywhere in
this codebase yet (see docs/architecture.md), so this module does not
invent one. Until a real channel is wired in, the one-time code is
recorded only in the audit trail (`audit_logs`, via write_audit_log),
which is itself authenticated and role-gated (SUPER_ADMIN/FINANCE_ROLES
via GET /api/v1/audit) — an interim, auditable distribution path, not a
public one. This is explicitly a placeholder: it does not deliver the code
out-of-band to the requester's phone, so it is not yet a true second
factor. Replace with a real SMS/email send as soon as a provider is
approved and configured.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Withdrawal
from app.repositories.finance import WithdrawalRepository

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class TwoFactorService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WithdrawalRepository(db)

    async def issue_challenge(self, withdrawal: Withdrawal) -> str:
        """Generates a fresh 6-digit code, stores only its hash + a 10
        minute expiry, resets the attempt counter, and returns the raw
        code — once. Callers must not persist the raw code anywhere
        themselves beyond handing it to a delivery channel (see this
        module's docstring)."""
        code = f"{secrets.randbelow(1_000_000):06d}"
        await self.repo.update(
            withdrawal,
            two_factor_code_hash=_hash_code(code),
            two_factor_expires_at=datetime.now(UTC) + CODE_TTL,
            two_factor_attempts=0,
            two_factor_confirmed_at=None,
        )
        return code

    def is_exhausted(self, withdrawal: Withdrawal) -> bool:
        """True once no further verify() attempt could possibly succeed —
        either the code has expired, or the attempt limit is used up."""
        if withdrawal.two_factor_attempts >= MAX_ATTEMPTS:
            return True
        if withdrawal.two_factor_expires_at is None:
            return True
        expires_at = withdrawal.two_factor_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return datetime.now(UTC) > expires_at

    async def verify(self, withdrawal: Withdrawal, code: str) -> bool:
        """Constant-time hash comparison, rate-limited by two_factor_attempts.
        A wrong code always increments the attempt counter (persisted via
        repo.update -> flush) even though this method itself never raises
        or commits — the caller (PayoutService.confirm_two_factor) decides
        what a failed/exhausted attempt means for the withdrawal's status."""
        if withdrawal.two_factor_code_hash is None or self.is_exhausted(withdrawal):
            return False

        matches = secrets.compare_digest(_hash_code(code), withdrawal.two_factor_code_hash)
        if matches:
            await self.repo.update(withdrawal, two_factor_confirmed_at=datetime.now(UTC))
            return True

        await self.repo.update(withdrawal, two_factor_attempts=withdrawal.two_factor_attempts + 1)
        return False
