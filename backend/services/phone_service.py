import re

_NON_DIGITS = re.compile(r"\D+")
_E164_PATTERN = re.compile(r"^\+\d{10,15}$")
_PHONE_IN_MSG = re.compile(r"\+\d{10,15}")
_PHONE_PARAM = re.compile(r"(phone[=:][^&\s]{4,})", re.IGNORECASE)


def normalize_phone(raw: str, default_country: str = "1") -> str:
    """
    Normalize a phone number to E.164 format (+15551234567).
    Accepts: +1 555 123 4567, (555)123-4567, 5551234567, 15551234567, etc.
    Raises ValueError for unrecognized formats.
    """
    if not raw:
        raise ValueError("Phone number is required")

    stripped = raw.strip()

    # Already looks like E.164 — validate and return
    if stripped.startswith("+"):
        digits = _NON_DIGITS.sub("", stripped)
        result = "+" + digits
        if not _E164_PATTERN.match(result):
            raise ValueError(f"Invalid E.164 phone number: {raw!r}")
        return result

    # Strip everything except digits
    digits = _NON_DIGITS.sub("", stripped)

    if len(digits) == 10:
        return "+" + default_country + digits

    if len(digits) == 11 and digits[0] == default_country:
        return "+" + digits

    if len(digits) < 7 or len(digits) > 15:
        raise ValueError(f"Unrecognized phone number format: {raw!r}")

    # Best-effort for other lengths — prepend +
    return "+" + digits


def mask_phone(e164: str) -> str:
    """Return last 4 digits only: ***1234"""
    if not e164 or len(e164) < 4:
        return "***"
    return "***" + e164[-4:]


def scrub_phone_from_string(s: str) -> str:
    """Replace E.164 phone patterns in a log string with ***REDACTED***."""
    return _PHONE_IN_MSG.sub("***REDACTED***", s)


def scrub_phone_from_query(qs: str) -> str:
    """Mask phone= parameter values in query strings for logging."""
    return _PHONE_PARAM.sub(lambda m: m.group(0)[:m.group(0).index("=") + 1] + "***", qs)
