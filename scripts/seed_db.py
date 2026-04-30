#!/usr/bin/env python3
"""Seed the database with realistic test data for development."""

import asyncio
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

for _p in [Path(__file__).parent.parent / "backend", Path("/app")]:
    if _p.exists():
        sys.path.insert(0, str(_p))
        break

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from config import settings
from models.base import Base
from models.user import User, UserRole
from models.item import Item, ItemCategory, ItemType, ItemCondition, ItemStatus
from models.sale import Sale, SaleItem, PaymentType
from auth import hash_password

USERS = [
    {"username": "admin", "password": "admin1234", "role": UserRole.admin, "full_name": "Store Manager"},
    {"username": "staff1", "password": "staff1234", "role": UserRole.staff, "full_name": "Alice Smith"},
    {"username": "staff2", "password": "staff1234", "role": UserRole.staff, "full_name": "Bob Jones"},
]

ITEM_POOL = [
    {"category": ItemCategory.tshirt, "type": ItemType.band, "label": "AC/DC", "color": "black"},
    {"category": ItemCategory.tshirt, "type": ItemType.band, "label": "Metallica", "color": "black"},
    {"category": ItemCategory.tshirt, "type": ItemType.band, "label": "Nirvana", "color": "grey"},
    {"category": ItemCategory.tshirt, "type": ItemType.anime, "label": "Dragon Ball Z", "color": "orange"},
    {"category": ItemCategory.tshirt, "type": ItemType.anime, "label": "Naruto", "color": "blue"},
    {"category": ItemCategory.tshirt, "type": ItemType.plain, "label": None, "color": "white"},
    {"category": ItemCategory.tshirt, "type": ItemType.plain, "label": None, "color": "black"},
    {"category": ItemCategory.tshirt, "type": ItemType.plain, "label": None, "color": "navy"},
    {"category": ItemCategory.tshirt, "type": ItemType.sports, "label": "Chicago Bulls", "color": "red"},
    {"category": ItemCategory.tshirt, "type": ItemType.sports, "label": "Lakers", "color": "yellow"},
    {"category": ItemCategory.tshirt, "type": ItemType.branded, "label": "Nike", "color": "grey"},
    {"category": ItemCategory.tshirt, "type": ItemType.branded, "label": "Adidas", "color": "white"},
    {"category": ItemCategory.tshirt, "type": ItemType.vintage_graphic, "label": "Vintage NASA", "color": "blue"},
    {"category": ItemCategory.pants, "type": ItemType.plain, "label": "Levi's", "color": "blue"},
    {"category": ItemCategory.pants, "type": ItemType.plain, "label": None, "color": "black"},
    {"category": ItemCategory.jacket, "type": ItemType.plain, "label": "Columbia", "color": "green"},
    {"category": ItemCategory.hoodie, "type": ItemType.plain, "label": "Champion", "color": "grey"},
    {"category": ItemCategory.hoodie, "type": ItemType.plain, "label": None, "color": "black"},
    {"category": ItemCategory.sweater, "type": ItemType.plain, "label": None, "color": "burgundy"},
    {"category": ItemCategory.dress, "type": ItemType.patterned, "label": None, "color": "floral"},
]

SIZES = ["XS", "S", "M", "L", "XL", "XXL"]
CONDITIONS = [ItemCondition.excellent, ItemCondition.good, ItemCondition.good, ItemCondition.fair, ItemCondition.worn]

PRICE_BY_CONDITION = {
    ItemCondition.excellent: (6, 14),
    ItemCondition.good: (4, 10),
    ItemCondition.fair: (2, 6),
    ItemCondition.worn: (1, 3),
}

def make_barcode(date: datetime, seq: int) -> str:
    return f"THR-{date.strftime('%Y%m%d')}-{seq:05d}"

def random_price(condition: ItemCondition) -> Decimal:
    lo, hi = PRICE_BY_CONDITION[condition]
    return Decimal(str(round(random.uniform(lo, hi) * 2) / 2))

async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # Check if already seeded
        result = await db.execute(text("SELECT COUNT(*) FROM users"))
        count = result.scalar_one()
        if count > 0:
            print(f"DB already has {count} users — skipping seed. Use --force to re-seed.")
            if "--force" not in sys.argv:
                await engine.dispose()
                return

        if "--force" in sys.argv:
            print("Force mode: truncating tables...")
            await db.execute(text("TRUNCATE sale_items, sales, items, audit_log, users RESTART IDENTITY CASCADE"))
            await db.commit()

        print("Creating users...")
        user_objs = []
        for u in USERS:
            user = User(
                username=u["username"],
                password_hash=hash_password(u["password"]),
                role=u["role"],
                is_active=True,
            )
            db.add(user)
            user_objs.append(user)
        await db.flush()

        admin_user = user_objs[0]
        staff_user = user_objs[1]

        print("Creating items (90 days of history)...")
        all_items = []
        now = datetime.utcnow()
        seq = 1

        for day_offset in range(89, -1, -1):
            date = now - timedelta(days=day_offset)
            items_today = random.randint(2, 8)
            for _ in range(items_today):
                template = random.choice(ITEM_POOL)
                condition = random.choice(CONDITIONS)
                price = random_price(condition)
                item = Item(
                    barcode=make_barcode(date, seq),
                    category=template["category"],
                    color=template["color"],
                    type=template["type"],
                    label=template.get("label"),
                    size=random.choice(SIZES),
                    condition=condition,
                    price=price,
                    cv_confidence=round(random.uniform(0.35, 0.95), 2),
                    status=ItemStatus.in_stock,
                    created_by=staff_user.id,
                    created_at=date,
                    updated_at=date,
                )
                db.add(item)
                all_items.append((item, date))
                seq += 1

        await db.flush()

        print("Creating sales...")
        sale_seq = 1
        for item, intake_date in all_items:
            days_ago = (now - intake_date).days
            sell_prob = 0.7 if days_ago > 21 else 0.3
            if random.random() < sell_prob:
                sold_date = intake_date + timedelta(days=random.randint(1, max(1, days_ago)))
                if sold_date > now:
                    continue

                sale_ref = f"SALE-{sold_date.strftime('%Y%m%d')}-{sale_seq:03d}"
                sale = Sale(
                    sale_ref=sale_ref,
                    total_amount=item.price,
                    discount=Decimal("0"),
                    payment_type=random.choice([PaymentType.cash, PaymentType.card]),
                    cashier_id=staff_user.id,
                    created_at=sold_date,
                )
                db.add(sale)
                await db.flush()

                sale_item = SaleItem(sale_id=sale.id, item_id=item.id, price=item.price)
                db.add(sale_item)

                item.status = ItemStatus.sold
                item.sold_at = sold_date
                sale_seq += 1

        await db.commit()
        print(f"Seed complete: {len(USERS)} users, {seq-1} items, {sale_seq-1} sales")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed())
