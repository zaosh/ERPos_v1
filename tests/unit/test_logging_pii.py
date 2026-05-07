import logging
from middleware.logging import PIILogFilter, _scrub_query, _scrub_path


def _make_record(msg: str, **extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg=msg, args=(), exc_info=None,
    )
    for k, v in extra.items():
        setattr(record, k, v)
    return record


def test_pii_filter_redacts_e164_in_msg():
    f = PIILogFilter()
    record = _make_record("customer called from +15551234567 today")
    f.filter(record)
    assert "+15551234567" not in record.msg
    assert "***REDACTED***" in record.msg


def test_pii_filter_redacts_phone_param_in_msg():
    f = PIILogFilter()
    record = _make_record("GET /customers/lookup?phone=5551234567")
    f.filter(record)
    assert "5551234567" not in record.msg


def test_pii_filter_redacts_pii_extra_fields():
    f = PIILogFilter()
    record = _make_record("user action")
    record.phone = "+15551234567"
    record.first_name = "John"
    f.filter(record)
    assert record.phone == "***"
    assert record.first_name == "***"


def test_pii_filter_allows_non_pii():
    f = PIILogFilter()
    record = _make_record("item barcode THR-20260507-00001 scanned")
    original_msg = record.msg
    f.filter(record)
    assert record.msg == original_msg


def test_scrub_query_masks_phone_param():
    qs = "phone=5551234567&limit=10"
    scrubbed = _scrub_query(qs)
    assert "5551234567" not in scrubbed
    assert "phone=***" in scrubbed
    assert "limit=10" in scrubbed


def test_scrub_path_masks_e164():
    path = "/customers/+15551234567/gdpr-erase"
    scrubbed = _scrub_path(path)
    assert "+15551234567" not in scrubbed
    assert "***" in scrubbed
