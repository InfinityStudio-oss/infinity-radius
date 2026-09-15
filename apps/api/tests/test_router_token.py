from uuid import uuid4

from app.core.router_token import create_router_token, resolve_router_token


def test_create_then_resolve_round_trips_to_the_same_router_id() -> None:
    router_id = uuid4()
    token = create_router_token(router_id)
    assert resolve_router_token(token) == router_id


def test_token_never_contains_the_router_id_in_cleartext() -> None:
    router_id = uuid4()
    token = create_router_token(router_id)
    assert str(router_id) not in token


def test_garbage_token_resolves_to_none() -> None:
    assert resolve_router_token("not-a-real-token") is None


def test_tampered_token_resolves_to_none() -> None:
    router_id = uuid4()
    token = create_router_token(router_id)
    tampered = token[:-4] + ("A" if token[-4] != "A" else "B") + token[-3:]
    assert resolve_router_token(tampered) is None


def test_two_different_routers_get_different_tokens() -> None:
    first = create_router_token(uuid4())
    second = create_router_token(uuid4())
    assert first != second


def test_token_is_url_safe() -> None:
    """Must survive being embedded as a query parameter in a hotspot
    redirect URL (router=<token>) without needing extra encoding beyond
    normal URL query-escaping."""
    import string

    token = create_router_token(uuid4())
    url_safe_chars = set(string.ascii_letters + string.digits + "-_=")
    assert set(token) <= url_safe_chars
