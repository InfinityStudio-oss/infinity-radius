"""Tanzania mobile number normalization.

Accepts any of the three formats a human or a MikroTik hotspot form is
likely to produce and normalizes them all to the same canonical
`255XXXXXXXXX` (12 digits, no leading `+`) used everywhere internally:

    07XXXXXXXX      (10 digits, local)
    +2557XXXXXXXX   (international, with +)
    2557XXXXXXXX    (international, no +)

The subscriber number itself is validated only against Tanzania's national
numbering plan shape (9 digits, starting 6 or 7) — deliberately not
restricted to any single operator's prefix range, since prefixes are
reassigned and ported between operators over time.
"""

import re

_LOCAL = re.compile(r"^0([67]\d{8})$")
_INTERNATIONAL = re.compile(r"^\+?255([67]\d{8})$")


def normalize_tz_phone(raw: str) -> str:
    """Returns the canonical `255XXXXXXXXX` form, or raises ValueError."""
    cleaned = re.sub(r"[\s\-()]", "", raw.strip())

    if match := _LOCAL.match(cleaned):
        return f"255{match.group(1)}"
    if match := _INTERNATIONAL.match(cleaned):
        return f"255{match.group(1)}"

    raise ValueError(
        f"Invalid Tanzania phone number: {raw!r} "
        "(expected 07XXXXXXXX, +2557XXXXXXXX, or 2557XXXXXXXX)"
    )


def is_valid_tz_phone(raw: str) -> bool:
    try:
        normalize_tz_phone(raw)
    except ValueError:
        return False
    return True
