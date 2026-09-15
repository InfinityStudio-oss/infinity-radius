"""IPAllowlistMiddleware in isolation. Starlette's TestClient always
connects as "testclient" (not a real IP), so these tests drive the
middleware's pure helper functions directly rather than asserting on
TestClient's fake client address."""

from starlette.requests import Request

from app.core.ip_allowlist import _client_ip, _is_allowed


def _request(*, client_host: str | None, forwarded_for: str | None = None) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": (client_host, 12345) if client_host else None,
    }
    return Request(scope)


def test_direct_client_ip_is_used_when_not_behind_the_trusted_proxy() -> None:
    request = _request(client_host="203.0.113.5")
    assert _client_ip(request) == "203.0.113.5"


def test_forwarded_for_is_trusted_only_from_localhost() -> None:
    request = _request(client_host="127.0.0.1", forwarded_for="203.0.113.9, 10.0.0.1")
    assert _client_ip(request) == "203.0.113.9"


def test_forwarded_for_is_ignored_from_a_non_proxy_host() -> None:
    """A direct (non-localhost) peer can't spoof its IP by just setting
    X-Forwarded-For — only requests arriving via the trusted local Caddy
    proxy get that header honored."""
    request = _request(client_host="203.0.113.5", forwarded_for="1.2.3.4")
    assert _client_ip(request) == "203.0.113.5"


def test_ip_allowed_by_exact_match() -> None:
    assert _is_allowed("203.0.113.5", ("203.0.113.5",)) is True
    assert _is_allowed("203.0.113.6", ("203.0.113.5",)) is False


def test_ip_allowed_by_cidr_range() -> None:
    assert _is_allowed("203.0.113.5", ("203.0.113.0/24",)) is True
    assert _is_allowed("203.0.114.5", ("203.0.113.0/24",)) is False


def test_no_client_ip_is_never_allowed() -> None:
    assert _is_allowed(None, ("203.0.113.5",)) is False
