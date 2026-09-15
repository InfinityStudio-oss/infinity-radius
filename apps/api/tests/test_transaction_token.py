from uuid import uuid4

from app.core.router_token import create_router_token
from app.core.transaction_token import create_transaction_token, resolve_transaction_token


def test_create_then_resolve_round_trips_to_the_same_transaction_id() -> None:
    transaction_id = uuid4()
    token = create_transaction_token(transaction_id)
    assert resolve_transaction_token(token) == transaction_id


def test_token_never_contains_the_transaction_id_in_cleartext() -> None:
    transaction_id = uuid4()
    token = create_transaction_token(transaction_id)
    assert str(transaction_id) not in token


def test_garbage_token_resolves_to_none() -> None:
    assert resolve_transaction_token("not-a-real-token") is None


def test_tampered_token_resolves_to_none() -> None:
    transaction_id = uuid4()
    token = create_transaction_token(transaction_id)
    tampered = token[:-4] + ("A" if token[-4] != "A" else "B") + token[-3:]
    assert resolve_transaction_token(tampered) is None


def test_a_router_token_does_not_resolve_as_a_transaction_token() -> None:
    """The two token families use different keys — proves they're not
    interchangeable even though both wrap a bare UUID."""
    router_token = create_router_token(uuid4())
    assert resolve_transaction_token(router_token) is None
