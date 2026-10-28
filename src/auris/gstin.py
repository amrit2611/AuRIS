"""GSTIN format and checksum validation.

A GSTIN is India's 15-character Goods and Services Tax Identification
Number assigned by GSTN to every registered taxpayer. Its shape is:

    [2-digit state code]
    [10-char PAN: 5 letters + 4 digits + 1 letter]
    [1 entity code: digit 1-9 or letter A-Z]
    'Z' (fixed)
    [1 check digit: digit 0-9 or letter A-Z]

Example: `27AAPFU0939F1ZV`

This module exposes two things:

- `is_valid_gstin(gstin)` returns True only when the input matches both
  the regex above and the GSTN base-36 check-digit formula.
- `compute_gstin_checksum(base14)` computes the 15th character for the
  first 14 characters of a GSTIN.

The checksum rule is the public GSTN algorithm: walk the first 14
characters from right to left with alternating factors (2, then 1, then
2, then 1, ...). For each character, look up its base-36 code point,
multiply by the factor, split the product as `(quotient_36, remainder_36)`
and add their sum to a running total. The check digit is the base-36
character whose code point is `(36 - total % 36) % 36`.
"""
import re
from typing import Final

__all__ = ["compute_gstin_checksum", "is_valid_gstin"]

_CODE_POINTS: Final[str] = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_CODE_POINT_INDEX: Final[dict[str, int]] = {ch: idx for idx, ch in enumerate(_CODE_POINTS)}
_GSTIN_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
)


def compute_gstin_checksum(base14: str) -> str:
    """Return the 15th-character GSTIN check digit for the first 14 characters."""
    if len(base14) != 14:
        raise ValueError(f"base14 must be exactly 14 characters, got {len(base14)}")
    factor = 2
    total = 0
    for ch in reversed(base14):
        if ch not in _CODE_POINT_INDEX:
            raise ValueError(f"base14 contains invalid character {ch!r}")
        value = _CODE_POINT_INDEX[ch]
        addend = factor * value
        factor = 1 if factor == 2 else 2
        addend = (addend // 36) + (addend % 36)
        total += addend
    remainder = total % 36
    check_index = (36 - remainder) % 36
    return _CODE_POINTS[check_index]


def is_valid_gstin(gstin: str | None) -> bool:
    """True iff `gstin` matches the GSTIN regex AND its check digit is correct.

    Treats None, empty string, and whitespace-only input as invalid.
    """
    if gstin is None:
        return False
    gstin = gstin.strip()
    if not gstin:
        return False
    if not _GSTIN_REGEX.match(gstin):
        return False
    expected = compute_gstin_checksum(gstin[:14])
    return expected == gstin[14]
