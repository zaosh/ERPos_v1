#!/usr/bin/env python3
"""
Stress-test seeder: 2 months of realistic thrift store data.

  ~3,000 unique customers (Indian names, +91 numbers)
  ~15,000 inventory items across all categories
  6,000 sales over 60 days (100/day), each with 1–4 items
  ~5% return rate (~300 returns)
  Realistic payment split, discount spread, time-of-day distribution

Usage:
    cd backend && python ../scripts/stress_seed.py
    cd backend && python ../scripts/stress_seed.py --fresh   # wipe seed data first
"""

import asyncio
import random
import sys
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from models.customer import Customer
from models.item import Item, ItemCategory, ItemCondition, ItemStatus, ItemType
from models.return_ import Return, ReturnItem, RefundMethod, ReturnStatus
from models.sale import Sale, SaleItem, PaymentType
from models.user import User

# ── Seed window: March 1 – April 30 2026 (clearly historical) ─────────────────
SEED_START = datetime(2026, 3, 1, tzinfo=timezone.utc)
SEED_DAYS  = 60
SALES_PER_DAY = 100
TAG = "SS"          # prefix on all seeded barcodes / refs / UIDs so easy to wipe

rng = random.Random(42)   # reproducible

# ── Indian first / last name pools ────────────────────────────────────────────
FIRST_NAMES = [
    "Aarav","Vivaan","Aditya","Vihaan","Arjun","Sai","Reyansh","Ayaan","Krishna","Ishaan",
    "Ananya","Aadhya","Pari","Aanya","Riya","Priya","Kavya","Diya","Pooja","Neha",
    "Rohan","Karan","Varun","Rahul","Ravi","Amit","Suresh","Vikram","Nikhil","Deepak",
    "Sunita","Meera","Anjali","Shilpa","Rekha","Lalita","Geeta","Nisha","Sonal","Divya",
    "Aryan","Yash","Dev","Rishab","Kabir","Mihir","Dhruv","Aakash","Sameer","Manish",
    "Sneha","Tanvi","Shruti","Pallavi","Swati","Archana","Usha","Manju","Hema","Rani",
    "Farhan","Imran","Zara","Aisha","Bilal","Salman","Nasrin","Rukhsar","Adnan","Sana",
    "Gurpreet","Harpreet","Simran","Jaswinder","Amarjit","Kulwinder","Navjot","Parmjit",
    "Rajan","Suraj","Mohan","Laxmi","Savita","Kamla","Sarla","Poonam","Seema","Vandana",
    "Tejas","Omkar","Siddharth","Shubham","Pranav","Gaurav","Sumit","Tarun","Ajay","Vijay",
]
LAST_NAMES = [
    "Sharma","Verma","Patel","Singh","Kumar","Gupta","Joshi","Mehta","Shah","Nair",
    "Reddy","Rao","Pillai","Iyer","Menon","Krishnan","Naidu","Choudhury","Agarwal","Jain",
    "Mishra","Pandey","Tiwari","Shukla","Dubey","Srivastava","Bajpai","Tripathi","Bhat","Das",
    "Chatterjee","Banerjee","Mukherjee","Ghosh","Bose","Sen","Roy","Datta","Chakraborty","Paul",
    "Khan","Ansari","Qureshi","Siddiqui","Shaikh","Malik","Hussain","Mirza","Pathan","Shaikh",
    "Gill","Sidhu","Grewal","Dhillon","Brar","Sandhu","Bajwa","Cheema","Sodhi","Aulakh",
    "Naik","Gawde","Sawant","Pawar","Desai","Kulkarni","Patil","More","Shinde","Jadhav",
    "Thomas","Joseph","Mathew","George","Abraham","John","Paul","Philip","Simon","Jacob",
]

# ── Category-aware label / size pools ─────────────────────────────────────────
LABELS = {
    "tshirt": [
        "Nirvana Band", "AC/DC Tee", "Pink Floyd", "Metallica", "Led Zeppelin",
        "Vintage Surf Co", "University of Mumbai", "Nike Plain", "Adidas Logo",
        "Pokemon Print", "Dragon Ball Z", "One Piece", "Naruto Graphic",
        "Retro 90s Tee", "Plain White", "Pocket Tee", "Levi's Basic",
        "Hard Rock Cafe", "Woodstock 99", "Rolling Stones", "The Beatles",
        "IPL Chennai", "Indian Cricket", "Kolkata Knight Riders",
        "Brooklyn Nine-Nine", "Friends TV", "Peaky Blinders",
    ],
    "pants": [
        "Levi's 501", "Levi's 511", "Wrangler Regular", "Corduroy Straight",
        "Khaki Chino", "Wool Trousers", "Relaxed Fit", "Slim Taper",
        "Lee Regular", "Cargo Trousers", "Formal Black", "Beige Linen",
        "Wide Leg", "Jogger Fit",
    ],
    "jacket": [
        "Denim Jacket", "Leather Biker", "Army Surplus", "Carhartt Chore",
        "Windbreaker", "Corduroy Blazer", "Track Jacket", "Bomber",
        "Linen Blazer", "Fleece Zip", "Varsity Jacket", "Utility Jacket",
        "Rain Jacket", "Quilted Jacket",
    ],
    "dress": [
        "Midi Sundress", "Floral Wrap", "Slip Dress", "A-line Cotton",
        "Maxi Boho", "Bodycon Black", "Polka Dot Mini", "Denim Pinafore",
        "Shirt Dress", "Vintage Midi", "Halter Neck", "Co-ord Set Dress",
    ],
    "skirt": [
        "A-Line Mini", "Pleated Midi", "Denim Mini", "Floral Midi",
        "High Waist Pencil", "Tiered Maxi", "Wrap Skirt", "Plaid Pleated",
    ],
    "shorts": [
        "Denim Cut-off", "Cargo Shorts", "Athletic Shorts", "Chino Shorts",
        "High Waist Denim", "Linen Shorts", "Board Shorts", "Bermuda",
    ],
    "sweater": [
        "Cable Knit Crew", "Fair Isle", "Mohair Grandpa", "Fisherman Knit",
        "Oversized Chunky", "Turtleneck Rib", "Cardigan Open Front",
        "V-Neck Wool", "Varsity Stripe", "Balloon Sleeve",
    ],
    "hoodie": [
        "Champion Zip", "Patagonia Pullover", "Nike Tech Fleece",
        "Adidas Trefoil", "Cropped Fleece", "Vintage Hoodie",
        "University Print", "Plain Terry", "Heavyweight Zip",
    ],
    "other": [
        "Silk Scarf", "Leather Belt", "Canvas Tote", "Wool Beanie",
        "Baseball Cap", "Bucket Hat", "Leather Bag", "Crossbody Bag",
        "Sunglasses", "Hair Band Set", "Bandana", "Suspenders",
    ],
}

SIZES = {
    "tshirt":  ["XS","S","M","L","XL","XXL"],
    "pants":   ["28","30","32","34","36","38"],
    "jacket":  ["XS","S","M","L","XL","XXL"],
    "dress":   ["XS","S","M","L","XL"],
    "skirt":   ["XS","S","M","L","XL"],
    "shorts":  ["28","30","32","34","36"],
    "sweater": ["XS","S","M","L","XL","XXL"],
    "hoodie":  ["XS","S","M","L","XL","XXL"],
    "other":   ["OS"],
}

COLORS = ["black","white","grey","navy","blue","red","green","brown","cream",
          "pink","purple","yellow","orange","khaki","olive","denim","tan",
          "maroon","teal","beige","floral","plaid","mixed","charcoal"]

ITEM_TYPES_BY_CAT = {
    "tshirt":  ["plain","graphic","band","anime","sports","vintage_graphic","branded","statement"],
    "pants":   ["plain","patterned","striped"],
    "jacket":  ["plain","patterned","branded"],
    "dress":   ["plain","patterned","striped","graphic"],
    "skirt":   ["plain","patterned","striped"],
    "shorts":  ["plain","patterned"],
    "sweater": ["plain","patterned","striped"],
    "hoodie":  ["plain","graphic","branded","sports"],
    "other":   ["plain","patterned","branded"],
}

# INR price ranges by category + condition
PRICE_RANGES = {
    ("tshirt",   "excellent"): (350, 900),
    ("tshirt",   "good"):      (200, 650),
    ("tshirt",   "fair"):      (100, 350),
    ("tshirt",   "worn"):      (50,  150),
    ("pants",    "excellent"): (600, 1800),
    ("pants",    "good"):      (400, 1200),
    ("pants",    "fair"):      (200, 600),
    ("pants",    "worn"):      (100, 300),
    ("jacket",   "excellent"): (1200, 3500),
    ("jacket",   "good"):      (800, 2500),
    ("jacket",   "fair"):      (400, 1200),
    ("jacket",   "worn"):      (200, 500),
    ("dress",    "excellent"): (700, 2000),
    ("dress",    "good"):      (450, 1300),
    ("dress",    "fair"):      (200, 700),
    ("dress",    "worn"):      (100, 300),
    ("skirt",    "excellent"): (400, 1200),
    ("skirt",    "good"):      (250, 800),
    ("skirt",    "fair"):      (100, 400),
    ("skirt",    "worn"):      (50,  200),
    ("shorts",   "excellent"): (350, 900),
    ("shorts",   "good"):      (200, 600),
    ("shorts",   "fair"):      (100, 350),
    ("shorts",   "worn"):      (50,  150),
    ("sweater",  "excellent"): (800, 2200),
    ("sweater",  "good"):      (500, 1500),
    ("sweater",  "fair"):      (250, 700),
    ("sweater",  "worn"):      (100, 350),
    ("hoodie",   "excellent"): (700, 2000),
    ("hoodie",   "good"):      (450, 1400),
    ("hoodie",   "fair"):      (200, 700),
    ("hoodie",   "worn"):      (100, 300),
    ("other",    "excellent"): (200, 1200),
    ("other",    "good"):      (120, 800),
    ("other",    "fair"):      (50,  400),
    ("other",    "worn"):      (20,  150),
}

CONDITIONS = ["excellent", "good", "fair", "worn"]
COND_WEIGHTS = [15, 45, 30, 10]   # good condition dominates

CATEGORIES = list(LABELS.keys())
CAT_WEIGHTS = [30, 15, 12, 10, 8, 8, 8, 6, 3]  # tshirt heavy, other rare


def rand_price(cat: str, cond: str) -> Decimal:
    lo, hi = PRICE_RANGES[(cat, cond)]
    raw = rng.randint(lo * 2, hi * 2) / 2
    # snap to nearest 10
    snapped = round(raw / 10) * 10
    return Decimal(str(max(snapped, lo)))


def rand_phone() -> str:
    prefixes = ["98", "97", "96", "95", "94", "93", "91", "90", "89", "88", "87", "86", "85", "84", "83", "82", "81", "80", "79", "78", "77", "76", "75", "74", "73", "70"]
    return "+91" + rng.choice(prefixes) + str(rng.randint(10000000, 99999999))


def rand_time(day: datetime) -> datetime:
    """Return a realistic store-hours timestamp for a given day."""
    # Store open 10:00–20:00; peak 11:00–13:00 and 16:00–19:00
    hour_weights = [0]*10 + [3,8,10,8,5,4,8,10,7,3] + [0]*4
    hour = rng.choices(range(24), weights=hour_weights)[0]
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    return day.replace(hour=hour, minute=minute, second=second)


# ── Main ───────────────────────────────────────────────────────────────────────

async def run():
    fresh = "--fresh" in sys.argv
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        if fresh:
            print("⚠  --fresh: removing all SS-prefixed seed data…")
            for stmt in [
                "DELETE FROM return_items WHERE item_id IN (SELECT id FROM items WHERE barcode LIKE 'SS-%')",
                "DELETE FROM returns     WHERE return_ref LIKE 'SS-RTN-%'",
                "DELETE FROM sale_items  WHERE item_id IN (SELECT id FROM items WHERE barcode LIKE 'SS-%')",
                "DELETE FROM sales       WHERE sale_ref LIKE 'SS-SALE-%'",
                "DELETE FROM items       WHERE barcode LIKE 'SS-%'",
                "DELETE FROM customers   WHERE customer_uid LIKE 'SS-C-%'",
            ]:
                await db.execute(text(stmt))
            await db.commit()
            print("   Done.\n")

        # ── Find or create staff/admin user ───────────────────────────────────
        result = await db.execute(select(User).where(User.username == "admin").limit(1))
        admin = result.scalar_one_or_none()
        if admin is None:
            result2 = await db.execute(select(User).limit(1))
            admin = result2.scalar_one_or_none()
        if admin is None:
            print("✗  No users found. Run the main seed first: python scripts/seed_db.py")
            return
        print(f"✓  Using user '{admin.username}' (id={admin.id}) as cashier / processor\n")

        # ── 1. Customers ──────────────────────────────────────────────────────
        NUM_CUSTOMERS = 3000
        print(f"Creating {NUM_CUSTOMERS:,} customers…", end=" ", flush=True)

        existing_phones: set[str] = set()
        ex = await db.execute(select(Customer.phone).where(Customer.phone.isnot(None)))
        existing_phones = set(ex.scalars().all())

        customers: list[Customer] = []
        used_phones: set[str] = set(existing_phones)
        for i in range(NUM_CUSTOMERS):
            fn = rng.choice(FIRST_NAMES)
            ln = rng.choice(LAST_NAMES)
            uid = f"SS-C-{i+1:05d}"
            # unique phone
            for _ in range(20):
                ph = rand_phone()
                if ph not in used_phones:
                    used_phones.add(ph)
                    break
            else:
                ph = None  # give up, walk-in

            joined = SEED_START - timedelta(days=rng.randint(0, 90))
            c = Customer(
                customer_uid=uid,
                first_name=fn,
                last_name=ln,
                phone=ph,
                is_active=True,
                created_at=joined,
                updated_at=joined,
            )
            customers.append(c)
            db.add(c)

        await db.flush()
        print(f"done  ({len(customers):,} rows)")

        # ── 2. Items ──────────────────────────────────────────────────────────
        # Need ~2 items per sale × 6000 sales = 12000 sold items + ~3000 in_stock
        NUM_ITEMS = 15_000
        print(f"Creating {NUM_ITEMS:,} inventory items…", end=" ", flush=True)

        items: list[Item] = []
        for i in range(NUM_ITEMS):
            cat = rng.choices(CATEGORIES, weights=CAT_WEIGHTS)[0]
            cond = rng.choices(CONDITIONS, weights=COND_WEIGHTS)[0]
            itype = rng.choice(ITEM_TYPES_BY_CAT[cat])
            color = rng.choice(COLORS)
            size  = rng.choice(SIZES[cat])
            label = rng.choice(LABELS[cat])
            price = rand_price(cat, cond)

            # Spread intake dates across the seed window + a bit before
            intake_offset = rng.randint(-15, SEED_DAYS - 1)
            intake_dt = SEED_START + timedelta(days=intake_offset)
            intake_dt = intake_dt.replace(
                hour=rng.randint(8, 18),
                minute=rng.randint(0, 59),
                second=rng.randint(0, 59),
            )

            barcode = f"SS-{cat[:2].upper()}-{i+1:06d}"

            item = Item(
                barcode=barcode,
                category=ItemCategory(cat),
                type=ItemType(itype),
                color=color,
                label=label,
                size=size,
                condition=ItemCondition(cond),
                price=price,
                status=ItemStatus.in_stock,
                created_by=admin.id,
                created_at=intake_dt,
                updated_at=intake_dt,
                cv_phase_b_complete=False,
            )
            items.append(item)
            db.add(item)

        await db.flush()
        print(f"done  ({len(items):,} rows)")

        # ── 3. Sales ─────────────────────────────────────────────────────────
        TAX_RATE = Decimal("0.18")
        print(f"Creating {SEED_DAYS} days × {SALES_PER_DAY} sales…", flush=True)

        # Build pool of available items (sorted by intake date for realism)
        available_pool = sorted(items, key=lambda x: x.created_at)
        pool_idx = 0          # consume items sequentially
        all_sales: list[Sale] = []
        all_sale_items: list[tuple[Sale, list[Item]]] = []

        for day_offset in range(SEED_DAYS):
            day_dt = SEED_START + timedelta(days=day_offset)
            day_str = day_dt.strftime("%Y%m%d")

            for sale_seq in range(1, SALES_PER_DAY + 1):
                if pool_idx >= len(available_pool) - 4:
                    break   # ran out of items

                # Pick 1–4 items, only from items intake'd before this day
                n_items = rng.choices([1, 2, 3, 4], weights=[20, 45, 25, 10])[0]
                sale_items_list: list[Item] = []
                for _ in range(n_items):
                    while pool_idx < len(available_pool):
                        candidate = available_pool[pool_idx]
                        if candidate.created_at.date() <= day_dt.date():
                            sale_items_list.append(candidate)
                            pool_idx += 1
                            break
                        else:
                            pool_idx += 1
                    else:
                        break

                if not sale_items_list:
                    continue

                # Discount: 20% of sales get a discount
                subtotal = sum(it.price for it in sale_items_list)
                discount_pct = rng.choices([0, 5, 10, 15, 20], weights=[80, 8, 6, 4, 2])[0]
                discount_amt = (subtotal * Decimal(discount_pct) / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
                taxable = subtotal - discount_amt
                tax_amt = (taxable * TAX_RATE).quantize(Decimal("0.01"), ROUND_HALF_UP)
                total = taxable + tax_amt

                payment = rng.choices(
                    [PaymentType.cash, PaymentType.card, PaymentType.other],
                    weights=[50, 40, 10]
                )[0]

                # Pick customer — 70% have a linked customer
                customer = rng.choice(customers) if rng.random() < 0.70 else None

                sale_time = rand_time(day_dt)
                sale_ref = f"SS-SALE-{day_str}-{sale_seq:03d}"
                receipt_number = f"SS-RCP-{day_str}-{sale_seq:04d}"

                sale = Sale(
                    sale_ref=sale_ref,
                    receipt_number=receipt_number,
                    customer_id=customer.id if customer else None,
                    subtotal=subtotal,
                    discount_amount=discount_amt,
                    tax_rate=TAX_RATE,
                    tax_amount=tax_amt,
                    total_amount=total,
                    payment_type=payment,
                    cashier_id=admin.id,
                    created_at=sale_time,
                    updated_at=sale_time,
                )
                db.add(sale)
                all_sales.append(sale)
                all_sale_items.append((sale, sale_items_list))

            # Flush every day to get IDs, report progress
            await db.flush()
            sold_at = day_dt.replace(hour=20, minute=0, second=0)

            # Create SaleItems and mark items sold
            for sale, sale_items_list in all_sale_items[-SALES_PER_DAY:]:
                for it in sale_items_list:
                    si = SaleItem(sale_id=sale.id, item_id=it.id, price=it.price)
                    db.add(si)
                    it.status = ItemStatus.sold
                    it.sold_at = sale.created_at
                    it.updated_at = sale.created_at

            if (day_offset + 1) % 10 == 0:
                print(f"  day {day_offset+1:3d}/{SEED_DAYS}  "
                      f"sales so far: {len(all_sales):,}")
                await db.flush()

        await db.flush()
        print(f"✓  {len(all_sales):,} sales created\n")

        # ── 4. Returns (~5% of sales) ─────────────────────────────────────────
        # Pick sales from days 3–14 before end of window; deduplicate by sale id
        end_dt = SEED_START + timedelta(days=SEED_DAYS)
        seen_sale_ids: set[int] = set()
        return_pool: list[tuple[Sale, list[Item]]] = []
        for s, si_list in all_sale_items:
            age = (end_dt - s.created_at).days
            if 3 <= age <= 14 and s.id not in seen_sale_ids:
                seen_sale_ids.add(s.id)
                return_pool.append((s, si_list))
        rng.shuffle(return_pool)
        TARGET_RETURNS = 300
        return_pool = return_pool[:TARGET_RETURNS]

        print(f"Creating {len(return_pool)} returns…", end=" ", flush=True)
        RETURN_REASONS = [
            "Size does not fit", "Changed mind", "Wrong item given",
            "Item has hidden damage", "Customer found similar at home",
            "Gifted but recipient does not like it", "Colour mismatch",
            "Quality not as expected", "Duplicate purchase",
        ]

        returned_item_ids: set[int] = set()   # guard against uq_return_items_item_id
        return_seq_by_day: dict[str, int] = {}
        created_returns = 0

        for sale, si_list in return_pool:
            # Only pick items not already in another return
            eligible = [it for it in si_list if it.id not in returned_item_ids]
            if not eligible:
                continue

            days_after = rng.randint(1, 3)
            ret_dt = sale.created_at + timedelta(days=days_after)
            ret_dt = rand_time(ret_dt)
            day_key = ret_dt.strftime("%Y%m%d")
            seq = return_seq_by_day.get(day_key, 0) + 1
            return_seq_by_day[day_key] = seq

            return_ref = f"SS-RTN-{day_key}-{seq:04d}"
            n_return = rng.randint(1, len(eligible))
            items_to_return = rng.sample(eligible, n_return)
            for it in items_to_return:
                returned_item_ids.add(it.id)

            refund_total = sum(it.price for it in items_to_return)
            resellable = rng.random() < 0.85

            ret = Return(
                return_ref=return_ref,
                original_sale_id=sale.id,
                customer_id=sale.customer_id,
                return_reason=rng.choice(RETURN_REASONS),
                processed_by=admin.id,
                refund_amount=refund_total,
                refund_method=rng.choice([RefundMethod.cash, RefundMethod.card, RefundMethod.store_credit]),
                status=ReturnStatus.completed,
                completed_at=ret_dt,
                created_at=ret_dt,
                updated_at=ret_dt,
            )
            db.add(ret)
            await db.flush()

            for it in items_to_return:
                db.add(ReturnItem(
                    return_id=ret.id,
                    item_id=it.id,
                    original_price=it.price,
                    refund_price=it.price,
                ))
                if resellable:
                    it.status = ItemStatus.in_stock
                    it.sold_at = None
                    it.updated_at = ret_dt
                else:
                    it.status = ItemStatus.archived
                    it.updated_at = ret_dt

            created_returns += 1

        await db.flush()
        print(f"done  ({created_returns} returns)")

        # ── 5. Summary ────────────────────────────────────────────────────────
        await db.commit()

        sold_count    = sum(1 for it in items if it.status == ItemStatus.sold)
        in_stock      = sum(1 for it in items if it.status == ItemStatus.in_stock)
        archived      = sum(1 for it in items if it.status == ItemStatus.archived)
        total_revenue = sum(s.total_amount for s in all_sales)

        print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Stress-seed complete  🎉
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Period        {SEED_START.date()}  →  {(SEED_START + timedelta(days=SEED_DAYS-1)).date()}
  Customers     {len(customers):>8,}
  Items         {len(items):>8,}   (in_stock: {in_stock:,}  sold: {sold_count:,}  archived: {archived:,})
  Sales         {len(all_sales):>8,}   (avg {len(all_sales)//SEED_DAYS}/day)
  Returns       {created_returns:>8,}   ({created_returns*100//len(all_sales) if all_sales else 0}% return rate)
  Revenue       ₹{total_revenue:>12,.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  All seeded records are prefixed with "SS-"
  To wipe:  python scripts/stress_seed.py --fresh
""")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
