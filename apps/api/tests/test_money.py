import json
from decimal import Decimal

import pytest
from pydantic import BaseModel

from app.core.money import DEFAULT_CURRENCY, Money, parse_money


class _Wrapper(BaseModel):
    amount: Money


def test_default_currency_is_tzs() -> None:
    assert DEFAULT_CURRENCY == "TZS"


def test_money_serializes_as_string_never_a_json_float() -> None:
    """The whole point of the Money type: Pydantic's default Decimal
    encoding goes through float and can corrupt precision — this proves
    the wire format is always a JSON string."""
    model = _Wrapper(amount=Decimal("15000.50"))
    raw = model.model_dump_json()
    parsed = json.loads(raw)

    assert isinstance(parsed["amount"], str)
    assert parsed["amount"] == "15000.50"


def test_money_round_trips_a_large_exact_value() -> None:
    tricky = Decimal("100000000000.10")
    model = _Wrapper(amount=tricky)

    assert json.loads(model.model_dump_json())["amount"] == "100000000000.10"


def test_parse_money_rejects_float_input() -> None:
    with pytest.raises(ValueError, match="not a float"):
        parse_money(15000.5)


def test_parse_money_accepts_string_and_quantizes_to_cents() -> None:
    assert parse_money("15000") == Decimal("15000.00")
    assert parse_money("15000.005") == Decimal("15000.01")
