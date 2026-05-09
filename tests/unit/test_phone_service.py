import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import pytest
from services.phone_service import (
    normalize_and_validate,
    get_display_format,
    get_masked_format,
    is_mobile,
    mask_phone,
    scrub_phone_from_string,
)

# ── normalize_and_validate ────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("9876543210",          "+919876543210"),
    ("+91 98765 43210",     "+919876543210"),
    ("091 98765 43210",     "+919876543210"),
    ("98765-43210",         "+919876543210"),
    ("+919876543210",       "+919876543210"),
    ("  9876543210  ",      "+919876543210"),  # leading/trailing spaces
])
def test_normalize_valid_indian_mobile(raw, expected):
    assert normalize_and_validate(raw, "IN") == expected


def test_normalize_with_plus91_prefix():
    assert normalize_and_validate("+91 98765 43210") == "+919876543210"


def test_normalize_with_091_prefix():
    assert normalize_and_validate("091 98765 43210") == "+919876543210"


def test_normalize_with_spaces_and_dashes():
    assert normalize_and_validate("98765-43210") == "+919876543210"


def test_normalize_invalid_raises():
    with pytest.raises(ValueError, match="valid phone number"):
        normalize_and_validate("not-a-phone")


def test_normalize_empty_raises():
    with pytest.raises(ValueError, match="required"):
        normalize_and_validate("")


def test_normalize_whitespace_only_raises():
    with pytest.raises(ValueError, match="required"):
        normalize_and_validate("   ")


def test_normalize_non_indian_with_in_region_raises():
    # A US number (555 area code) is not valid in India
    with pytest.raises(ValueError):
        normalize_and_validate("+15551234567", "IN")


def test_normalize_too_short_raises():
    with pytest.raises(ValueError):
        normalize_and_validate("123", "IN")


# ── get_display_format ────────────────────────────────────────────────────────

def test_display_format_indian_mobile():
    result = get_display_format("+919876543210")
    assert result == "+91 98765 43210"


def test_display_format_passthrough_on_bad_input():
    result = get_display_format("not-e164")
    assert result == "not-e164"


# ── get_masked_format ─────────────────────────────────────────────────────────

def test_masked_format_last5_visible():
    result = get_masked_format("+919876543210")
    # last 5 national digits: 43210
    assert result.endswith("43210")
    assert "X" in result
    # country code +91 must be intact
    assert result.startswith("+91")


def test_masked_format_hides_first_digits():
    result = get_masked_format("+919876543210")
    # "98765" should be masked
    assert "98765" not in result


def test_masked_format_empty_returns_stars():
    assert get_masked_format("") == "***"


def test_masked_format_exact_shape():
    # +91 98765 43210 → +91 XXXXX 43210
    result = get_masked_format("+919876543210")
    assert result == "+91 XXXXX 43210"


# ── is_mobile ─────────────────────────────────────────────────────────────────

def test_is_mobile_indian_mobile():
    assert is_mobile("+919876543210") is True


def test_is_mobile_starts_with_6():
    assert is_mobile("+916001234567") is True


def test_is_mobile_starts_with_7():
    assert is_mobile("+917001234567") is True


def test_is_mobile_landline_returns_false():
    # Indian landline: Mumbai 022 + 8-digit number
    assert is_mobile("+912228001234") is False


def test_is_mobile_bad_input_returns_false():
    assert is_mobile("not-a-number") is False


# ── mask_phone (backward compat) ──────────────────────────────────────────────

def test_mask_phone_last4():
    assert mask_phone("+919876543210") == "***3210"


def test_mask_phone_short():
    assert mask_phone("12") == "***"


# ── scrub_phone_from_string ───────────────────────────────────────────────────

def test_scrub_phone_from_string():
    msg = "customer called from +919876543210"
    scrubbed = scrub_phone_from_string(msg)
    assert "+919876543210" not in scrubbed
    assert "***REDACTED***" in scrubbed
