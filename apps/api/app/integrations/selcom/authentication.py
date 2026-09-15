"""Selcom API authentication — TODO(selcom-docs).

Selcom's Collection/Disbursement APIs require some authentication scheme
on outbound requests — an API key header? An HMAC-signed Authorization
header? A token-exchange step first? — that Anthropic has not been given
official documentation for. Do not guess: a wrong guess here would send
requests that could appear to work against a lenient sandbox and fail
unpredictably (or worse, silently misbehave) in production.

Fill in `build_auth_headers` once Selcom's official integration guide
specifies:
  - the exact header name(s) and value format(s) required
  - whether credentials belong in headers, query string, or request body
  - any token/session exchange this needs to perform first
  - how MERCHANT_ID factors into the request (header? body field?)
"""

from app.integrations.selcom.config import SelcomConfig
from app.integrations.selcom.exceptions import SelcomNotConfiguredError, SelcomNotImplementedError


class SelcomAuthenticator:
    """Builds whatever authentication Selcom's API requires for an
    outbound request. Raises until the real scheme is documented — see
    this module's docstring."""

    def __init__(self, config: SelcomConfig) -> None:
        self._config = config

    def build_auth_headers(self, *, method: str, path: str, body: bytes) -> dict[str, str]:
        """TODO(selcom-docs): return the real headers Selcom's Collection/
        Disbursement API requires for an outbound request to `path`."""
        if not self._config.is_configured:
            raise SelcomNotConfiguredError(
                "Selcom credentials are not configured. Set SELCOM_API_BASE_URL, "
                "SELCOM_API_KEY, SELCOM_API_SECRET, and SELCOM_MERCHANT_ID."
            )
        raise SelcomNotImplementedError(
            "Selcom's outbound request authentication scheme is not implemented — "
            "awaiting official API documentation (header names, value format, any "
            "token-exchange step)."
        )
