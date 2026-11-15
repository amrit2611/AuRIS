"""Tests for the GSTIN format + checksum validator."""
import pytest

from auris.gstin import compute_gstin_checksum, is_valid_gstin


class TestComputeChecksum:
    def test_checksum_is_round_tripable(self) -> None:
        """Any 14-char base that we build a GSTIN around validates with is_valid_gstin."""
        base = "27AAPFU0939F1Z"
        assert len(base) == 14
        checksum = compute_gstin_checksum(base)
        assert len(checksum) == 1
        assert is_valid_gstin(base + checksum) is True

    def test_checksum_is_deterministic(self) -> None:
        base = "29ABCDE1234F1Z"
        assert compute_gstin_checksum(base) == compute_gstin_checksum(base)

    def test_different_bases_produce_different_checksums(self) -> None:
        """Changing the base14 input generally changes the checksum (sanity, not a hash claim)."""
        a = compute_gstin_checksum("27AAPFU0939F1Z")
        b = compute_gstin_checksum("27AAPFU0939F2Z")
        c = compute_gstin_checksum("29ABCDE1234F1Z")
        assert not (a == b == c), "trivially identical outputs mean the formula is broken"

    def test_rejects_wrong_length(self) -> None:
        with pytest.raises(ValueError, match="exactly 14"):
            compute_gstin_checksum("too short")
        with pytest.raises(ValueError, match="exactly 14"):
            compute_gstin_checksum("A" * 15)

    def test_rejects_bad_character(self) -> None:
        with pytest.raises(ValueError, match="invalid character"):
            compute_gstin_checksum("27AAPFU0939F1a")  # lowercase 'a' not in base-36 alphabet


class TestIsValidGstin:
    def test_none_is_invalid(self) -> None:
        assert is_valid_gstin(None) is False

    def test_empty_string_is_invalid(self) -> None:
        assert is_valid_gstin("") is False
        assert is_valid_gstin("   ") is False

    def test_wrong_length_is_invalid(self) -> None:
        base = "27AAPFU0939F1Z"
        checksum = compute_gstin_checksum(base)
        valid = base + checksum
        assert is_valid_gstin(valid[:14]) is False
        assert is_valid_gstin(valid + "X") is False

    def test_lowercase_is_invalid(self) -> None:
        """GSTIN is uppercase by GSTN definition; lowercase must fail the regex."""
        base = "27AAPFU0939F1Z"
        valid = base + compute_gstin_checksum(base)
        assert is_valid_gstin(valid.lower()) is False

    def test_missing_fixed_z_is_invalid(self) -> None:
        """Position 14 is a mandatory 'Z'; swapping it must fail."""
        base = "27AAPFU0939F1Z"
        valid = base + compute_gstin_checksum(base)
        bad = valid[:13] + "A" + valid[14]  # 'A' at pos 14 instead of 'Z'
        assert is_valid_gstin(bad) is False

    def test_valid_format_but_bad_checksum_is_invalid(self) -> None:
        """A GSTIN with the right shape but flipped check digit must fail."""
        base = "27AAPFU0939F1Z"
        valid = base + compute_gstin_checksum(base)
        flipped = valid[:-1] + ("A" if valid[-1] != "A" else "B")
        assert is_valid_gstin(flipped) is False

    def test_whitespace_is_stripped_before_validation(self) -> None:
        base = "27AAPFU0939F1Z"
        valid = base + compute_gstin_checksum(base)
        assert is_valid_gstin(f"  {valid}  ") is True

    def test_valid_round_trip_from_known_shape(self) -> None:
        """Build a few GSTINs via the checksum function and confirm every one validates."""
        bases = [
            "01DNNWC2657RWZ",
            "02ULACH0084KEZ",
            "27AAPFU0939F1Z",
            "29ABCDE1234F1Z",
            "33QWERT5678F9Z",
        ]
        for base in bases:
            checksum = compute_gstin_checksum(base)
            assert is_valid_gstin(base + checksum) is True, f"{base} failed round trip"

    def test_pan_block_requires_letters_in_the_right_positions(self) -> None:
        """Positions 3-7 must be letters; a digit there must fail even with a correct checksum."""
        bad_base = "271APFU0939F1Z"  # position 3 is '1' instead of a letter
        # Compute what the checksum "would" be, then verify the full string still fails.
        checksum = compute_gstin_checksum(bad_base)
        assert is_valid_gstin(bad_base + checksum) is False
