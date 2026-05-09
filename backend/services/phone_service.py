import re

import phonenumbers
from phonenumbers import (
    NumberParseException,
    PhoneNumberFormat,
    PhoneNumberType,
    number_type,
)
from sqlalchemy.ext.asyncio import AsyncSession

_PHONE_IN_MSG = re.compile(r"\+\d{10,15}")
_PHONE_PARAM = re.compile(r"(phone[=:][^&\s]{4,})", re.IGNORECASE)

_MOBILE_TYPES = frozenset([
    PhoneNumberType.MOBILE,
    PhoneNumberType.FIXED_LINE_OR_MOBILE,
])


def _preprocess(raw: str, region: str) -> str:
    """
    Normalize region-specific trunk prefixes before library parsing.
    India uses 091 as an informal local IDD shorthand: "091 XXXX" → "+91 XXXX".
    """
    if region == "IN" and re.match(r"^091\s*\d", raw):
        return "+91" + raw[3:]
    return raw


def normalize_and_validate(raw: str, region: str = "IN") -> str:
    """
    Parse, validate, and return E.164 format.
    Accepts: 9876543210 / +91 98765 43210 / 091 98765 43210 / 98765-43210
    Raises ValueError with a UI-safe message on invalid input.
    """
    if not raw or not raw.strip():
        raise ValueError("Phone number is required")
    cleaned = _preprocess(raw.strip(), region)
    try:
        parsed = phonenumbers.parse(cleaned, region)
    except NumberParseException:
        raise ValueError("Enter a valid phone number")
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("Enter a valid phone number")
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


def get_display_format(e164: str) -> str:
    """E.164 → international display: +91 98765 43210"""
    try:
        parsed = phonenumbers.parse(e164, None)
        return phonenumbers.format_number(parsed, PhoneNumberFormat.INTERNATIONAL)
    except Exception:
        return e164


def get_masked_format(e164: str) -> str:
    """E.164 → masked with last 5 digits visible: +91 XXXXX 43210"""
    if not e164:
        return "***"
    try:
        parsed = phonenumbers.parse(e164, None)
        cc_len = len(str(parsed.country_code))
        display = phonenumbers.format_number(parsed, PhoneNumberFormat.INTERNATIONAL)
        # Digits after "+CC " belong to the national number
        prefix_end = 1 + cc_len + 1  # e.g. "+91 " = index 4
        national_digit_positions = [
            i for i, c in enumerate(display)
            if c.isdigit() and i >= prefix_end
        ]
        if len(national_digit_positions) < 5:
            return display
        chars = list(display)
        for pos in national_digit_positions[:-5]:
            chars[pos] = "X"
        return "".join(chars)
    except Exception:
        return "***"


def is_mobile(e164: str) -> bool:
    """True if the number is mobile (or FIXED_LINE_OR_MOBILE). False for landlines."""
    try:
        parsed = phonenumbers.parse(e164, None)
        return number_type(parsed) in _MOBILE_TYPES
    except Exception:
        return False


async def get_default_region(db: AsyncSession, tenant_id: int = 1) -> str:
    """Read default_phone_region from system_settings (60 s cache)."""
    from services import settings_service  # avoid circular at import time
    region = await settings_service.get(db, "default_phone_region", tenant_id)
    return region or "IN"


# ── Backward-compat helpers kept for existing callers ────────────────────────

def mask_phone(e164: str) -> str:
    """Last 4 digits only: ***1234"""
    if not e164 or len(e164) < 4:
        return "***"
    return "***" + e164[-4:]


def scrub_phone_from_string(s: str) -> str:
    """Replace E.164 patterns in a log string with ***REDACTED***."""
    return _PHONE_IN_MSG.sub("***REDACTED***", s)


def scrub_phone_from_query(qs: str) -> str:
    """Mask phone= values in query strings for logging."""
    return _PHONE_PARAM.sub(lambda m: m.group(0)[:m.group(0).index("=") + 1] + "***", qs)
