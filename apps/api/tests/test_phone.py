import pytest

from app.core.phone import is_valid_tz_phone, normalize_tz_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0712345678", "255712345678"),
        ("0612345678", "255612345678"),
        ("+255712345678", "255712345678"),
        ("255712345678", "255712345678"),
        ("+255 712 345 678", "255712345678"),
        ("0712-345-678", "255712345678"),
    ],
)
def test_normalize_tz_phone_accepts_all_documented_formats(raw: str, expected: str) -> None:
    assert normalize_tz_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "0812345678",  # invalid leading digit (not 6 or 7)
        "071234567",  # too short
        "07123456789",  # too long
        "not-a-phone",
        "",
        "254712345678",  # wrong country code (Kenya)
    ],
)
def test_normalize_tz_phone_rejects_invalid_numbers(raw: str) -> None:
    with pytest.raises(ValueError, match="Invalid Tanzania phone number"):
        normalize_tz_phone(raw)


def test_normalize_does_not_assume_a_single_operator() -> None:
    """Both the 6xx and 7xx ranges are accepted — operators share and port
    prefixes, so this must not hard-code a specific carrier's block."""
    assert normalize_tz_phone("0654321098").startswith("25565")
    assert normalize_tz_phone("0754321098").startswith("25575")


def test_is_valid_tz_phone() -> None:
    assert is_valid_tz_phone("0712345678") is True
    assert is_valid_tz_phone("not-a-phone") is False
