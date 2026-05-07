import pytest
from services.phone_service import normalize_phone, mask_phone, scrub_phone_from_string


@pytest.mark.parametrize("raw,expected", [
    ("+15551234567", "+15551234567"),
    ("+1 555 123 4567", "+15551234567"),
    ("5551234567", "+15551234567"),
    ("15551234567", "+15551234567"),
    ("(555) 123-4567", "+15551234567"),
    ("555-123-4567", "+15551234567"),
])
def test_normalize_phone_variants(raw, expected):
    assert normalize_phone(raw) == expected


def test_normalize_phone_explicit_plus():
    assert normalize_phone("+447911123456") == "+447911123456"


def test_normalize_phone_invalid():
    with pytest.raises(ValueError):
        normalize_phone("not-a-phone")


def test_normalize_phone_empty():
    with pytest.raises(ValueError):
        normalize_phone("")


def test_mask_phone():
    assert mask_phone("+15551234567") == "***4567"


def test_mask_phone_short():
    assert mask_phone("12") == "***"


def test_scrub_phone_from_string():
    msg = "customer called from +15551234567"
    scrubbed = scrub_phone_from_string(msg)
    assert "+15551234567" not in scrubbed
    assert "***REDACTED***" in scrubbed
