"""
System settings read/write with 60-second in-process cache.
Cache is per (key, tenant_id) pair.
"""
import asyncio
import time
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.system_settings import SystemSetting

_CACHE: dict[tuple[str, int], tuple[str, float]] = {}  # (key, tenant_id) → (value, expires_at)
_TTL = 60.0
_LOCK = asyncio.Lock()


async def get(db: AsyncSession, key: str, tenant_id: int = 1) -> Optional[str]:
    cache_key = (key, tenant_id)
    entry = _CACHE.get(cache_key)
    if entry and entry[1] > time.monotonic():
        return entry[0]

    row = await db.scalar(
        select(SystemSetting.value).where(
            SystemSetting.key == key, SystemSetting.tenant_id == tenant_id
        )
    )
    if row is not None:
        _CACHE[cache_key] = (row, time.monotonic() + _TTL)
    return row


async def get_decimal(db: AsyncSession, key: str, default: Decimal = Decimal("0"), tenant_id: int = 1) -> Decimal:
    raw = await get(db, key, tenant_id)
    if raw is None:
        return default
    try:
        return Decimal(raw)
    except InvalidOperation:
        return default


async def get_int(db: AsyncSession, key: str, default: int = 0, tenant_id: int = 1) -> int:
    raw = await get(db, key, tenant_id)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


async def set_value(db: AsyncSession, key: str, value: str, user_id: int, tenant_id: int = 1) -> None:
    row = await db.scalar(
        select(SystemSetting).where(SystemSetting.key == key, SystemSetting.tenant_id == tenant_id)
    )
    if row is None:
        db.add(SystemSetting(key=key, value=value, updated_by=user_id, tenant_id=tenant_id))
    else:
        row.value = value
        row.updated_by = user_id
    await db.commit()
    invalidate(key, tenant_id)


def invalidate(key: str, tenant_id: int = 1) -> None:
    _CACHE.pop((key, tenant_id), None)
