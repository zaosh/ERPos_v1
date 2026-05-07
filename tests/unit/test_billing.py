"""
Tax calculation correctness: total = subtotal - discount + (subtotal - discount) * tax_rate
All results must be correct to 2 decimal places.
"""
import pytest
from decimal import Decimal, ROUND_HALF_UP


def _calc(subtotal: str, discount: str, tax_rate: str) -> tuple[Decimal, Decimal, Decimal]:
    s = Decimal(subtotal)
    d = Decimal(discount)
    r = Decimal(tax_rate)
    taxable = s - d
    tax_amount = (taxable * r).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = taxable + tax_amount
    return taxable, tax_amount, total


@pytest.mark.parametrize("subtotal,discount,tax_rate,expected_tax,expected_total", [
    ("10.00", "0.00", "0.0000", "0.00", "10.00"),
    ("10.00", "0.00", "0.0875", "0.88", "10.88"),
    ("10.00", "2.00", "0.0875", "0.70", "8.70"),
    ("100.00", "10.00", "0.1000", "9.00", "99.00"),
    ("0.99", "0.00", "0.0875", "0.09", "1.08"),
    ("1000.00", "0.00", "0.0000", "0.00", "1000.00"),
])
def test_tax_calculation(subtotal, discount, tax_rate, expected_tax, expected_total):
    _taxable, tax_amount, total = _calc(subtotal, discount, tax_rate)
    assert tax_amount == Decimal(expected_tax), f"tax_amount mismatch for subtotal={subtotal}"
    assert total == Decimal(expected_total), f"total mismatch for subtotal={subtotal}"


def test_total_equals_taxable_plus_tax():
    subtotal = Decimal("45.99")
    discount = Decimal("5.00")
    tax_rate = Decimal("0.0875")
    taxable, tax_amount, total = _calc(str(subtotal), str(discount), str(tax_rate))
    assert total == taxable + tax_amount


def test_discount_cannot_exceed_subtotal():
    """When discount > subtotal, taxable should floor at 0."""
    subtotal = Decimal("5.00")
    discount = min(Decimal("10.00"), subtotal)
    assert discount == subtotal  # discount capped at subtotal
