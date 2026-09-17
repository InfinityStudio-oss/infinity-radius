"""A real, single-use, short-lived withdrawal OTP — the "2FA confirmation"
step in the withdrawal flow, delivered by email via Resend (see
app/services/payouts.py, app/integrations/resend/service.py). Only the hash
is ever stored; the raw code is handed back to the immediate caller exactly
once, at generation time, purely so it can be embedded in the outbound
email — it is never itself persisted, logged, or returned by any API
response (see app/services/payouts.py.request_withdrawal/resend_otp).

Hashing is HMAC-SHA256 keyed by Settings.otp_verification_secret, not a
bare hash of the code: a 6-digit OTP has only one million possible values,
so an unkeyed hash (even SHA-256) would let anyone who ever saw the DB
brute-force every stored code offline in well under a second. Keying it
with a server-only secret makes that infeasible without also having the
secret, which never leaves Railway Variables (see app/core/config.py).
"""

import hmac
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import DomainValidationError
from app.models.finance import Withdrawal
from app.repositories.finance import WithdrawalRepository


def _otp_secret() -> str:
    secret = get_settings().otp_verification_secret
    if not secret:
        # Fail closed: never fall back to an unkeyed/predictable hash just
        # because the secret wasn't configured — no OTP can be issued or
        # verified at all until it is (Railway Variables only, see
        # app/core/config.py).
        raise DomainValidationError(
            "Withdrawal verification is not available right now — please contact support."
        )
    return secret


def _hash_code(*, withdrawal_id: str, code: str) -> str:
    message = f"{withdrawal_id}:{code}".encode()
    return hmac.new(_otp_secret().encode(), message, sha256).hexdigest()


class TwoFactorService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WithdrawalRepository(db)

    async def issue_challenge(self, withdrawal: Withdrawal, *, sent_to_email: str) -> str:
        """Generates a fresh 6-digit code, stores only its HMAC hash plus a
        configurable expiry, resets the attempt counter, records which
        email address it was (about to be) sent to, and returns the raw
        code — once. The caller must hand it directly to the email send
        and never persist/log it itself (see this module's docstring)."""
        settings = get_settings()
        code = f"{secrets.randbelow(1_000_000):06d}"
        await self.repo.update(
            withdrawal,
            two_factor_code_hash=_hash_code(withdrawal_id=str(withdrawal.id), code=code),
            two_factor_expires_at=datetime.now(UTC)
            + timedelta(seconds=settings.withdrawal_otp_ttl_seconds),
            two_factor_attempts=0,
            two_factor_confirmed_at=None,
            otp_sent_to_email=sent_to_email,
        )
        return code

    def is_exhausted(self, withdrawal: Withdrawal) -> bool:
        """True once no further verify() attempt could possibly succeed —
        either the code has expired, or the attempt limit is used up."""
        if withdrawal.two_factor_attempts >= get_settings().withdrawal_otp_max_attempts:
            return True
        if withdrawal.two_factor_expires_at is None:
            return True
        expires_at = withdrawal.two_factor_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return datetime.now(UTC) > expires_at

    async def verify(self, withdrawal: Withdrawal, code: str, *, current_email: str | None) -> bool:
        """Constant-time hash comparison, rate-limited by two_factor_attempts.
        Also refuses if the account's email has changed since the OTP was
        issued (otp_sent_to_email) — the code was only ever proven
        deliverable to the address on file at issue time, never to
        whatever the account's email happens to be now. A wrong/refused
        code always increments the attempt counter (persisted via
        repo.update -> flush) even though this method itself never raises
        or commits — the caller (PayoutService.confirm_two_factor) decides
        what a failed/exhausted attempt means for the withdrawal's status."""
        if withdrawal.two_factor_code_hash is None or self.is_exhausted(withdrawal):
            return False
        if current_email is not None and withdrawal.otp_sent_to_email != current_email:
            return False

        candidate = _hash_code(withdrawal_id=str(withdrawal.id), code=code)
        matches = secrets.compare_digest(candidate, withdrawal.two_factor_code_hash)
        if matches:
            await self.repo.update(withdrawal, two_factor_confirmed_at=datetime.now(UTC))
            return True

        await self.repo.update(withdrawal, two_factor_attempts=withdrawal.two_factor_attempts + 1)
        return False
