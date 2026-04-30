"""Unit tests for barcode_service — uses fakeredis."""
import re
import pytest
import fakeredis.aioredis

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from services.barcode_service import generate_barcode, validate_barcode_format

_BARCODE_RE = re.compile(r"^THR-\d{8}-\d{5}$")


@pytest.fixture
async def redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.flushall()
    await r.aclose()


class TestBarcodeFormat:
    @pytest.mark.asyncio
    async def test_format_matches_pattern(self, redis):
        bc = await generate_barcode(redis)
        assert _BARCODE_RE.match(bc), f"Barcode {bc!r} does not match pattern"

    @pytest.mark.asyncio
    async def test_sequential_codes_increment(self, redis):
        bc1 = await generate_barcode(redis)
        bc2 = await generate_barcode(redis)
        seq1 = int(bc1.split("-")[2])
        seq2 = int(bc2.split("-")[2])
        assert seq2 == seq1 + 1

    @pytest.mark.asyncio
    async def test_all_unique(self, redis):
        barcodes = [await generate_barcode(redis) for _ in range(10)]
        assert len(set(barcodes)) == 10

    @pytest.mark.asyncio
    async def test_starts_with_thr(self, redis):
        bc = await generate_barcode(redis)
        assert bc.startswith("THR-")


class TestValidateBarcodeFormat:
    def test_valid_barcode(self):
        assert validate_barcode_format("THR-20260429-00001") is True

    def test_wrong_prefix(self):
        assert validate_barcode_format("ABC-20260429-00001") is False

    def test_wrong_date_length(self):
        assert validate_barcode_format("THR-202604-00001") is False

    def test_wrong_seq_length(self):
        assert validate_barcode_format("THR-20260429-001") is False

    def test_non_digits(self):
        assert validate_barcode_format("THR-2026ABCD-00001") is False

    def test_empty_string(self):
        assert validate_barcode_format("") is False
