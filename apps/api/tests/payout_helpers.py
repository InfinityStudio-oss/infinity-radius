"""Test-only stand-in for Resend, specifically for the withdrawal OTP
email — there is no live Resend account to send through in CI/local tests,
and (by design, see app/services/payouts.py) the OTP is never returned by
any API response or written to any log/audit row, so a test has no other
way to learn what code was actually issued. This is the
"test-specific fixture/mock" the OTP task calls for, never a production
response structure.
"""

from collections.abc import Iterator

import pytest

from app.integrations.resend.schemas import EmailSendResult
from app.services import payouts as payouts_module


@pytest.fixture
def capture_withdrawal_otp(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Yields a list this test can read the most recently issued OTP from
    (`otp_inbox[-1]`) — appended in send order, one entry per real send/
    resend, never persisted anywhere the app itself could read back."""
    captured: list[str] = []

    async def _fake_send(self: object, **kwargs: object) -> EmailSendResult:
        captured.append(str(kwargs["otp"]))
        return EmailSendResult(sent=True, provider_message_id="test-message-id")

    monkeypatch.setattr(
        payouts_module.ResendEmailService, "send_withdrawal_otp_email", _fake_send
    )
    yield captured
