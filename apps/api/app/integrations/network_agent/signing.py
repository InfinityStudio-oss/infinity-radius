"""Signs outbound requests to the Network Agent.

Must exactly match the Network Agent's own verification
(apps/network-agent/app/core/security.py) — the two are separate Python
projects (no shared package between them), so any change here needs the
identical change made there too:

    signature = HMAC-SHA256(
        key = shared secret,
        message = f"{timestamp}\\n{nonce}\\n{METHOD}\\n{path}\\n{sha256(body).hexdigest()}",
    )
"""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class SignedRequestHeaders:
    timestamp: str
    nonce: str
    signature: str

    def as_dict(self) -> dict[str, str]:
        return {
            "X-Agent-Timestamp": self.timestamp,
            "X-Agent-Nonce": self.nonce,
            "X-Agent-Signature": self.signature,
        }


def sign_request(
    *, api_key: str, method: str, path: str, body: bytes = b""
) -> SignedRequestHeaders:
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    body_hash = hashlib.sha256(body).hexdigest()
    message = f"{timestamp}\n{nonce}\n{method.upper()}\n{path}\n{body_hash}".encode()
    signature = hmac.new(api_key.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return SignedRequestHeaders(timestamp=timestamp, nonce=nonce, signature=signature)
