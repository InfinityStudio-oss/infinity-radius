"""Selcom request/webhook signing — TODO(selcom-docs).

Neither the outbound request-signing scheme nor the inbound webhook
signature-verification scheme is implemented: Anthropic has not been
given Selcom's official specification for either of:
  - the digest algorithm (HMAC-SHA256? RSA? something else?)
  - which fields are concatenated/hashed, and in what order
  - which request/response header carries the signature
  - the encoding (hex? base64?)

Guessing any of this would produce code that looks like it works but is
silently insecure or simply wrong — this is exactly why
`verify_webhook_signature` must never return True until it is a real,
documented check: doing otherwise would let anyone forge a "payment
succeeded" callback (see app/integrations/selcom/collection.py, which
never marks a transaction SUCCESS unless this function has genuinely
verified the request).
"""

from app.integrations.selcom.config import SelcomConfig
from app.integrations.selcom.exceptions import SelcomNotConfiguredError, SelcomNotImplementedError


def sign_request(*, config: SelcomConfig, method: str, path: str, body: bytes) -> str:
    """TODO(selcom-docs): compute the real outbound request signature."""
    if not config.is_configured:
        raise SelcomNotConfiguredError(
            "Selcom credentials are not configured. Set SELCOM_API_BASE_URL, "
            "SELCOM_API_KEY, SELCOM_API_SECRET, and SELCOM_MERCHANT_ID."
        )
    raise SelcomNotImplementedError(
        "Selcom's outbound request signing scheme is not implemented — awaiting "
        "official documentation (algorithm, signed fields, header name, encoding)."
    )


def verify_webhook_signature(*, config: SelcomConfig, headers: dict[str, str], body: bytes) -> bool:
    """TODO(selcom-docs): verify an inbound webhook's authenticity against
    Selcom's real signing scheme. MUST NOT return True until this is a
    genuine, documented check."""
    if not config.is_configured:
        raise SelcomNotConfiguredError(
            "Selcom credentials are not configured. Set SELCOM_API_BASE_URL, "
            "SELCOM_API_KEY, SELCOM_API_SECRET, and SELCOM_MERCHANT_ID."
        )
    raise SelcomNotImplementedError(
        "Selcom's webhook signature verification is not implemented — awaiting "
        "official documentation (signing algorithm, which header carries the "
        "signature, which fields are covered, encoding)."
    )
