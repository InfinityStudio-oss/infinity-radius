"""Builds validly-signed request headers for tests — the same algorithm
apps/api's real client (app.integrations.network_agent.signing, in the
other project) uses, reimplemented here so network-agent's own test suite
doesn't depend on importing across the two separate Python projects."""

import hashlib
import hmac
import secrets
import time


def sign(
    *, key: str, method: str, path: str, body: bytes = b"", timestamp: int | None = None
) -> dict[str, str]:
    ts = str(timestamp if timestamp is not None else int(time.time()))
    nonce = secrets.token_hex(16)
    body_hash = hashlib.sha256(body).hexdigest()
    message = f"{ts}\n{nonce}\n{method.upper()}\n{path}\n{body_hash}".encode()
    signature = hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return {
        "X-Agent-Timestamp": ts,
        "X-Agent-Nonce": nonce,
        "X-Agent-Signature": signature,
    }
