import re
import pytest
from unittest.mock import AsyncMock, patch
from services.customer_service import _new_uid, generate_customer_uid

_UID_PATTERN = re.compile(r"^CUST-[A-Z0-9]{6}$")


def test_uid_format():
    for _ in range(100):
        assert _UID_PATTERN.match(_new_uid()), "uid must match CUST-XXXXXX"


def test_uid_uniqueness():
    uids = {_new_uid() for _ in range(10_000)}
    # 36^6 = 2.18B combinations; 10k draws should be unique
    assert len(uids) == 10_000


@pytest.mark.asyncio
async def test_generate_customer_uid_success():
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=None)  # no collision
    uid = await generate_customer_uid(mock_db)
    assert _UID_PATTERN.match(uid)


@pytest.mark.asyncio
async def test_generate_customer_uid_collision_retry():
    mock_db = AsyncMock()
    # Simulate 3 collisions then success
    call_count = 0

    async def mock_scalar(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return 1 if call_count <= 3 else None  # collision, collision, collision, success

    mock_db.scalar = mock_scalar
    uid = await generate_customer_uid(mock_db)
    assert _UID_PATTERN.match(uid)
    assert call_count == 4


@pytest.mark.asyncio
async def test_generate_customer_uid_exhausted():
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=1)  # always collides
    with pytest.raises(RuntimeError, match="exhausted"):
        await generate_customer_uid(mock_db)
