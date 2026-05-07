import secrets
import string
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.customer import Customer

_ALPHABET = string.ascii_uppercase + string.digits  # 36 chars → 36^6 = 2.18B combinations


def _new_uid() -> str:
    return "CUST-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


async def generate_customer_uid(db: AsyncSession) -> str:
    """
    Generate a unique CUST-XXXXXX customer UID.
    Retries up to 10 times on collision (astronomically unlikely in practice).
    DB unique constraint is the final guard.
    """
    for _ in range(10):
        uid = _new_uid()
        exists = await db.scalar(select(Customer.id).where(Customer.customer_uid == uid))
        if not exists:
            return uid
    raise RuntimeError("customer_uid generation exhausted 10 retries — database may be near capacity")
