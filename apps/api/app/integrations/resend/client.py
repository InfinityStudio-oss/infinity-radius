"""Thin wrapper around the official `resend` SDK. The SDK itself is
synchronous, so every send runs in a worker thread (asyncio.to_thread)
rather than blocking the event loop.
"""

import asyncio
from typing import Any

import resend

from app.integrations.resend.config import ResendConfig
from app.integrations.resend.exceptions import ResendNotConfiguredError, ResendSendError
from app.integrations.resend.schemas import EmailSendResult


class ResendClient:
    def __init__(self, config: ResendConfig) -> None:
        self._config = config

    async def send(self, *, to: str, subject: str, html: str) -> EmailSendResult:
        if not self._config.is_configured:
            raise ResendNotConfiguredError()

        params: dict[str, Any] = {
            "from": self._config.from_header,
            "to": [to],
            "subject": subject,
            "html": html,
        }

        def _send_sync() -> dict[str, Any]:
            resend.api_key = self._config.api_key
            return resend.Emails.send(params)  # type: ignore[arg-type,return-value]

        try:
            response = await asyncio.to_thread(_send_sync)
        except Exception as exc:  # resend raises its own httpx/requests-shaped errors
            raise ResendSendError(f"Resend send failed: {exc}") from exc

        message_id = response.get("id") if isinstance(response, dict) else None
        return EmailSendResult(sent=True, provider_message_id=message_id)
