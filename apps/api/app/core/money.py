"""Money handling: Decimal everywhere, TZS by default, never float.

`Money` is the Pydantic field type every schema uses for a monetary amount.
Pydantic v2's default JSON encoding turns Decimal into a float, which would
silently reintroduce the exact rounding error this whole system exists to
avoid — so it's annotated with a PlainSerializer that always emits a
string, matching `packages/types/src/money.ts` on the frontend and
Postgres' NUMERIC on the way in.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated

from pydantic import PlainSerializer

DEFAULT_CURRENCY = "TZS"
_CENTS = Decimal("0.01")


def _serialize_decimal(value: Decimal) -> str:
    return str(value)


Money = Annotated[Decimal, PlainSerializer(_serialize_decimal, return_type=str)]


def quantize_tzs(value: Decimal) -> Decimal:
    """Rounds a computed (not client-supplied) Decimal to 2dp, TZS's minor
    unit — e.g. a fee-split calculation. Same rounding rule as parse_money
    so a computed amount and a client-supplied one are never inconsistent."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def parse_money(raw: str | int | float | Decimal) -> Decimal:
    """Parses a monetary amount from client input. Rejects float input
    outright — a float has already lost precision by the time it reaches
    here, and accepting one would just hide where the imprecision came from.
    """
    if isinstance(raw, float):
        raise ValueError("Monetary amounts must be provided as a string or integer, not a float")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid monetary amount: {raw!r}") from exc
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)
