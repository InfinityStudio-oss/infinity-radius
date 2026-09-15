"""Exercises verify_agent_signature against a minimal throwaway app —
isolated from the router registry / MikroTik client so these tests focus
purely on the HMAC + timestamp + nonce scheme."""

import time

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.security import verify_agent_signature
from tests.signing_helpers import sign

CURRENT_KEY = "test-agent-key-current"
PREVIOUS_KEY = "test-agent-key-previous"


class _Payload(BaseModel):
    value: int


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.post("/ping", dependencies=[Depends(verify_agent_signature)])
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/echo", dependencies=[Depends(verify_agent_signature)])
    async def echo(payload: _Payload) -> dict[str, int]:
        # Proves FastAPI's own JSON body parsing still works after
        # verify_agent_signature has already read request.body() —
        # Starlette caches the body so it can be read more than once.
        return {"value": payload.value}

    return app


client = TestClient(_make_app())


def test_valid_signature_is_accepted() -> None:
    headers = sign(key=CURRENT_KEY, method="POST", path="/ping")
    response = client.post("/ping", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_missing_signature_headers_rejected() -> None:
    response = client.post("/ping")
    assert response.status_code == 401


def test_wrong_key_rejected() -> None:
    headers = sign(key="not-a-real-key", method="POST", path="/ping")
    response = client.post("/ping", headers=headers)
    assert response.status_code == 401


def test_previous_key_accepted_during_rotation() -> None:
    headers = sign(key=PREVIOUS_KEY, method="POST", path="/ping")
    response = client.post("/ping", headers=headers)
    assert response.status_code == 200


def test_stale_timestamp_rejected() -> None:
    headers = sign(
        key=CURRENT_KEY, method="POST", path="/ping", timestamp=int(time.time()) - 10_000
    )
    response = client.post("/ping", headers=headers)
    assert response.status_code == 401


def test_signature_for_a_different_path_is_rejected() -> None:
    headers = sign(key=CURRENT_KEY, method="POST", path="/somewhere-else")
    response = client.post("/ping", headers=headers)
    assert response.status_code == 401


def test_tampered_body_invalidates_signature() -> None:
    headers = sign(key=CURRENT_KEY, method="POST", path="/echo", body=b'{"value": 1}')
    response = client.post("/echo", headers=headers, content=b'{"value": 2}')
    assert response.status_code == 401


def test_matching_body_with_valid_signature_is_accepted() -> None:
    body = b'{"value": 42}'
    headers = sign(key=CURRENT_KEY, method="POST", path="/echo", body=body)
    headers["Content-Type"] = "application/json"
    response = client.post("/echo", headers=headers, content=body)
    assert response.status_code == 200
    assert response.json() == {"value": 42}


def test_replayed_nonce_is_rejected_even_with_a_valid_signature() -> None:
    headers = sign(key=CURRENT_KEY, method="POST", path="/ping")

    first = client.post("/ping", headers=headers)
    second = client.post("/ping", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 401
