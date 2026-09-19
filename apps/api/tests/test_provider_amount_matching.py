"""app/services/payouts.py.match_provider_amount — the ONLY two shapes a
Selcom transaction/query amount is ever accepted as explaining a
withdrawal. Added after a real production incident (2026-09-19): Selcom
reported data.amount as principal + its own transfer charge
(5000.00 + 150.00 = 5150.00) for a completed transfer, which the
then-existing exact-principal-only check correctly refused to finalize
on trust, moving the withdrawal to AMBIGUOUS rather than guessing.

Deliberately pure-function tests — no DB, no HTTP — exhaustively covering
every shape in the incident write-up, run in milliseconds. See
test_provider_amount_matching_reconciliation.py for the wiring (currency/
transId checks, and the full reconcile path) these can't cover alone.
"""

from decimal import Decimal

from app.core.enums import ProviderAmountMatch
from app.services.payouts import match_provider_amount

_PRINCIPAL = Decimal("5000")
_CHARGE = Decimal("150")


def test_real_incident_shape_matches_principal_plus_stored_charge() -> None:
    """The exact real production case: query amount = principal + the
    charge this withdrawal's own authenticated lookup already recorded."""
    result = match_provider_amount(
        provider_amount=Decimal("5150"),
        withdrawal_amount=_PRINCIPAL,
        stored_provider_charge=_CHARGE,
    )
    assert result == ProviderAmountMatch.PRINCIPAL_PLUS_STORED_PROVIDER_CHARGE


def test_standard_documented_shape_matches_principal_exact() -> None:
    """Selcom's public docs describe transaction/query amount as principal
    only — this must keep working if/when Selcom's real behavior matches
    the docs (a different transaction, a future API version, etc.)."""
    result = match_provider_amount(
        provider_amount=_PRINCIPAL,
        withdrawal_amount=_PRINCIPAL,
        stored_provider_charge=_CHARGE,
    )
    assert result == ProviderAmountMatch.PRINCIPAL_EXACT


def test_principal_exact_matches_even_with_no_stored_charge() -> None:
    result = match_provider_amount(
        provider_amount=_PRINCIPAL,
        withdrawal_amount=_PRINCIPAL,
        stored_provider_charge=None,
    )
    assert result == ProviderAmountMatch.PRINCIPAL_EXACT


def test_one_shilling_under_the_charged_total_is_ambiguous() -> None:
    result = match_provider_amount(
        provider_amount=Decimal("5149"),
        withdrawal_amount=_PRINCIPAL,
        stored_provider_charge=_CHARGE,
    )
    assert result is None


def test_one_shilling_over_the_charged_total_is_ambiguous() -> None:
    result = match_provider_amount(
        provider_amount=Decimal("5151"),
        withdrawal_amount=_PRINCIPAL,
        stored_provider_charge=_CHARGE,
    )
    assert result is None


def test_a_wildly_different_amount_is_ambiguous() -> None:
    result = match_provider_amount(
        provider_amount=Decimal("5200"),
        withdrawal_amount=_PRINCIPAL,
        stored_provider_charge=_CHARGE,
    )
    assert result is None


def test_charged_total_without_any_stored_charge_is_ambiguous() -> None:
    """provider_amount happens to equal principal+150, but this
    withdrawal never recorded a charge at all — never invent one to make
    the match succeed."""
    result = match_provider_amount(
        provider_amount=Decimal("5150"),
        withdrawal_amount=_PRINCIPAL,
        stored_provider_charge=None,
    )
    assert result is None


def test_charged_total_against_a_different_stored_charge_is_ambiguous() -> None:
    """The stored charge for THIS withdrawal was 100, not 150 — even
    though 5150 would match a 150 charge, it must not match a withdrawal
    that never recorded that charge."""
    result = match_provider_amount(
        provider_amount=Decimal("5150"),
        withdrawal_amount=_PRINCIPAL,
        stored_provider_charge=Decimal("100"),
    )
    assert result is None


def test_negative_stored_charge_is_never_trusted() -> None:
    """A negative provider_charge should never happen, but however it got
    there, it must never be used to justify a match — not even an exact
    principal match slipping through some other arithmetic coincidence."""
    result = match_provider_amount(
        provider_amount=Decimal("4850"),  # 5000 + (-150)
        withdrawal_amount=_PRINCIPAL,
        stored_provider_charge=Decimal("-150"),
    )
    assert result is None


def test_zero_stored_charge_still_allows_the_second_form() -> None:
    """A legitimately zero charge is a valid non-negative charge — both
    forms happen to coincide here, but this confirms zero isn't rejected
    by the `>= 0` guard."""
    result = match_provider_amount(
        provider_amount=_PRINCIPAL,
        withdrawal_amount=_PRINCIPAL,
        stored_provider_charge=Decimal("0"),
    )
    assert result == ProviderAmountMatch.PRINCIPAL_EXACT


def test_never_matches_on_provider_amount_greater_or_equal_alone() -> None:
    """Guards against ever accidentally reintroducing a `>=` style loose
    match — an amount far above both accepted forms must stay ambiguous
    even though it's "at least" the principal."""
    result = match_provider_amount(
        provider_amount=Decimal("999999"),
        withdrawal_amount=_PRINCIPAL,
        stored_provider_charge=_CHARGE,
    )
    assert result is None
