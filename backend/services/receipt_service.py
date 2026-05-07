"""
Collision-safe receipt_number and return_ref generation.

Strategy: Postgres advisory lock scoped to the current transaction, combined with
a COUNT query to find the next sequence number. Because both happen inside the same
transaction as the INSERT, the lock is held until commit/rollback — guaranteeing
no two concurrent transactions can claim the same number for a given day.

Advisory key derivation: blake2b hash of the date string, cast to signed int64.
"""
import hashlib
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _advisory_key(prefix: str) -> int:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    raw = hashlib.blake2b(f"{prefix}:{today}".encode(), digest_size=8).digest()
    val = int.from_bytes(raw, "big")
    # Cast to signed int64 range that pg_advisory_xact_lock expects
    if val >= 2**63:
        val -= 2**64
    return val


async def next_receipt_number(db: AsyncSession) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = _advisory_key("rcp")
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
    n = await db.scalar(
        text("SELECT COUNT(*) FROM sales WHERE receipt_number LIKE :p"),
        {"p": f"RCP-{today}-%"},
    )
    seq = (n or 0) + 1
    if seq > 9999:
        raise HTTPException(status_code=409, detail="Receipt number sequence exhausted for today")
    return f"RCP-{today}-{seq:04d}"


async def next_return_ref(db: AsyncSession) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = _advisory_key("rtn")
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
    n = await db.scalar(
        text("SELECT COUNT(*) FROM returns WHERE return_ref LIKE :p"),
        {"p": f"RTN-{today}-%"},
    )
    seq = (n or 0) + 1
    if seq > 9999:
        raise HTTPException(status_code=409, detail="Return ref sequence exhausted for today")
    return f"RTN-{today}-{seq:04d}"
