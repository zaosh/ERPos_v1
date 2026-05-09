# Exchange System — Implementation Plan

> Target migration: **008_exchange_system.py** (HEAD is 007).
> Audience: Sonnet implementer. Every section is intended to be unambiguous.
> All monetary fields are `NUMERIC(10,2)`. All timestamps are `TIMESTAMP WITH TIME ZONE`.

---

## 1. Goals & Invariants (read first)

1. Exchange eligibility is **decided at checkout time only**. There is no PATCH route, no admin override, no "after the fact" toggle. If a customer didn't pay the fee at the original sale, they cannot exchange — period.
2. An item can only be exchanged **once**. Once `items.status = 'exchanged'` it terminates. The new item swapped in starts a fresh life as `is_exchange_item = true`.
3. Exchange always requires a customer record. Anonymous sales must be linked to a customer first via a new endpoint.
4. Item identity is confirmed by **bill + customer + original photo**, not by barcode of the returned item. The original barcode is destroyed/discarded with the returned tag.
5. `image_confirmed` (server schema field `returned_item_image_confirmed`) must be `true` before the exchange row can be created. Server enforces, not the client.
6. Exchange items on their second sale contribute to **revenue totals only**. They are filtered out of all trend, velocity, dead-stock, top-performer, CV accuracy, and label/color analytics. `is_exchange_item` is a one-way flag — never cleared.
7. New exchange item cannot be re-exchanged unless the buyer opts in (and pays the fee) again at *its* purchase.
8. Physical re-intake marker is a printed A6 orange card with black "EXCHANGE" text placed to the left of the item in the camera frame. CV detection wiring is built now but gated behind a TODO until the cards are printed.

---

## 2. Schema Diagram

```
                       customers
                          │
                          │ (FK customer_id)
                          ▼
sales ─────────────► exchanges ◄──────── users (processed_by)
  │  ▲                  │   │
  │  │                  │   │
  │  │ original_sale_id │   │ original_item_id   ┌──── items (returned)
  │  │                  │   └────────────────────┤    status = exchanged
  │  │                  │                        │    is_exchange_item = false
  │  │                  │ new_item_id  ┌─────────┴──── items (replacement)
  │  │                  └──────────────┤              status = sold (after complete)
  │  │                                 │              is_exchange_item = true
  │  │                                 │              original_item_id ─┐
  │  │                                                                  │
  │  │                                                                  ▼
  │  │                                                         (back-pointer to
  │  │                                                          returned item)
  │  │
  │  │  (FK sale_id)
  │  └───────────► bill_history
  │                  │  event_type ∈ {purchase, exchange_initiated,
  │                  │   exchange_completed, return_initiated,
  │                  │   return_completed, item_added}
  │                  │  optional FKs: item_id, exchange_id, return_id
  │                  ▼
  │              users (created_by)
  │
  └─── sale_items, returns (existing, untouched except for FK references)
```

Cardinalities:
- `sales 1—N exchanges` (a bill can have multiple exchanges over its lifetime, one per item).
- `items 1—1 exchanges` via `original_item_id` (unique).
- `items 0..1—0..1 exchanges` via `new_item_id` (unique when not null — a replacement item is used once).
- `sales 1—N bill_history` (every event appended).

---

## 3. State Machines

### 3.1 `item_status` (PostgreSQL ENUM `item_status`)

Existing values: `in_stock`, `sold`, `reserved`, `archived`.
**New value:** `exchanged`.

```
              ┌──────────────────────────────────────────┐
              │                                          │
              ▼                                          │
        ┌──────────┐    sale         ┌──────┐  return    │
   ─►   │ in_stock │ ──────────────► │ sold │ ─────────► │ in_stock (existing return flow)
        └──────────┘                 └──────┘            │
              │ ▲                       │                │
   reserve    │ │ unreserve             │ exchange       │
              ▼ │                       ▼                │
        ┌──────────┐                 ┌────────────┐      │
        │ reserved │                 │ exchanged  │ ◄── terminal (no transitions out)
        └──────────┘                 └────────────┘
              │
              │ admin archive
              ▼
        ┌──────────┐
        │ archived │
        └──────────┘
```

Notes:
- `exchanged` is **terminal**. No transition out of it.
- A returned-via-return-flow item still goes back to `in_stock` (existing behavior preserved).
- The replacement item flows `in_stock → sold` on `complete_exchange`. It does not pass through `exchanged`.

### 3.2 `exchange_status_enum`

```
            initiate_exchange()           complete_exchange(new_item_id)
   (none) ───────────────────► pending ───────────────────────────────► completed
                                  │
                                  │ cancel_exchange()  (admin only, future)
                                  ▼
                              cancelled
```

- `pending`: row exists, original item still `sold`, no replacement chosen yet.
- `completed`: replacement item linked, original item `exchanged`, replacement `sold`, `completed_at` set.
- `cancelled`: created by an admin-only future endpoint (out of scope for v1, but enum value reserved). No state side-effects on items required because pending never mutated them.

---

## 4. Files Touched / Created

### New files
| Path | Purpose |
|---|---|
| `backend/migrations/versions/008_exchange_system.py` | Schema + ENUM + seeds |
| `backend/models/exchange.py` | `Exchange`, `BillHistory`, enums |
| `backend/schemas/exchange.py` | Pydantic request/response |
| `backend/services/exchange_service.py` | Core logic + advisory ref generator |
| `backend/routes/exchanges.py` | `/exchanges/*` endpoints |
| `tests/unit/test_exchange_service.py` | Eligibility, ref, transitions |
| `tests/integration/test_exchanges.py` | Full flows + analytics exclusion |
| `frontend/src/pages/Exchange.tsx` | 5-step UI |
| `frontend/src/components/BillHistoryTimeline.tsx` | Reusable timeline |

### Modified files
| Path | Change |
|---|---|
| `backend/models/item.py` | Add columns: `exchange_eligible`, `exchange_fee_paid`, `is_exchange_item`, `exchange_marker_detected`, `original_item_id`, `exchanged_at`; add `exchanged` to `ItemStatus` enum |
| `backend/models/sale.py` | Add `exchange_fee_total` |
| `backend/models/__init__.py` | Export `Exchange`, `BillHistory` |
| `backend/schemas/item.py` | Surface new fields on `ItemResponse`; `SaleItemInput` gains `exchange_eligible: bool = False` |
| `backend/schemas/sale.py` | `SaleResponse` gains `exchange_fee_total`; line items expose `exchange_eligible`, `exchange_fee_paid` |
| `backend/services/analytics_service.py` | Add `is_exchange_item = false` predicate to 5 queries; add `exchange_stats` block to `get_summary` |
| `backend/services/cv_service.py` | Document exchange-card marker; add prompt + `is_exchange_marker` field with TODO gate |
| `backend/services/receipt_service.py` | (Optional) co-locate `next_exchange_ref`, OR put it in `exchange_service.py` (chosen: latter, to keep concerns separate) |
| `backend/routes/sales.py` | Accept `exchange_eligible` per line; compute `exchange_fee_total`; emit `bill_history` (`purchase`); add `GET /sales/{sale_ref}/history`; add `POST /sales/{sale_ref}/link-customer` |
| `backend/routes/customers.py` | Add `GET /customers/{customer_uid}/exchanges` (admin only) |
| `backend/routes/items.py` | On `POST /items/`: read `cv_raw_output.is_exchange_marker`; if true set `is_exchange_item=true`, `exchange_marker_detected=true`, skip phase-B and fashion jobs |
| `backend/main.py` | `include_router(exchanges_router)` |
| `frontend/src/pages/Checkout.tsx` | Per-item exchange toggle; running fee total; receipt UI |
| `frontend/src/App.tsx` | Add `/exchange` route + nav (staff+) |
| `frontend/src/utils/api.ts` | (No structural change; new endpoints are typed in pages) |
| `CHANGELOG.md` | Add "Exchange system" entry |
| `PLANNING.md` | Move "exchange flow" out of open questions |
| `CLAUDE.md` | Append SESSION NOTES (2026-05-09) describing exchange model |

---

## 5. Migration 008 — Detailed SQL & Strategy

### 5.1 Adding `exchanged` to existing PostgreSQL ENUM

PostgreSQL enums are **not** mutable inside a transaction with the same statement that uses them. `ALTER TYPE ... ADD VALUE` must commit before the new value can be referenced. Alembic by default wraps the migration in one transaction. Two safe options:

**Option A (chosen): two-step migration with `op.execute` and an explicit commit boundary.**

```python
# in upgrade()
op.execute("COMMIT")
op.execute("ALTER TYPE item_status ADD VALUE IF NOT EXISTS 'exchanged'")
op.execute("BEGIN")
```

This works because Alembic opens a new transaction after our manual COMMIT. We must run this **before** any DDL that references `'exchanged'::item_status` (we don't reference it in DDL — only seed data uses string `'sold'` etc., so order is moot, but we still do this first).

**Option B (fallback if hosting forbids `COMMIT` mid-migration):** disable transactional DDL for this migration:

```python
def upgrade():
    ...
# at module level
transactional_ddl = False
```

We will **use Option A** because the rest of the migration benefits from atomicity.

`downgrade()` cannot remove an enum value in PostgreSQL without recreating the type. Document this — downgrade will leave `exchanged` in the enum (no-op for that line, comment explains).

### 5.2 New ENUM types (create before tables)

```sql
CREATE TYPE returned_item_condition_enum AS ENUM ('excellent','good','fair','worn','damaged');
CREATE TYPE exchange_status_enum         AS ENUM ('pending','completed','cancelled');
CREATE TYPE bill_event_type_enum         AS ENUM (
    'purchase','exchange_initiated','exchange_completed',
    'return_initiated','return_completed','item_added'
);
```

Use SQLAlchemy `postgresql.ENUM(..., name=..., create_type=True)` with `.create(op.get_bind(), checkfirst=True)` so down-migrations can drop them cleanly.

### 5.3 `items` column additions

```sql
ALTER TABLE items
  ADD COLUMN exchange_eligible       BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN exchange_fee_paid       NUMERIC(10,2),
  ADD COLUMN is_exchange_item        BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN exchange_marker_detected BOOLEAN,
  ADD COLUMN original_item_id        INTEGER REFERENCES items(id),
  ADD COLUMN exchanged_at            TIMESTAMP WITH TIME ZONE;

CREATE INDEX idx_items_is_exchange_item   ON items(is_exchange_item) WHERE is_exchange_item = TRUE;
CREATE INDEX idx_items_exchange_eligible  ON items(exchange_eligible) WHERE exchange_eligible = TRUE;
```

(Partial indexes — most rows are FALSE, so partial keeps them tiny.)

### 5.4 `sales` column addition

```sql
ALTER TABLE sales
  ADD COLUMN exchange_fee_total NUMERIC(10,2) NOT NULL DEFAULT 0;
```

### 5.5 `exchanges` table

```sql
CREATE TABLE exchanges (
    id                              BIGSERIAL PRIMARY KEY,
    exchange_ref                    VARCHAR(30) UNIQUE NOT NULL,
    original_sale_id                INTEGER NOT NULL REFERENCES sales(id),
    original_item_id                INTEGER NOT NULL REFERENCES items(id),
    new_item_id                     INTEGER REFERENCES items(id),
    customer_id                     BIGINT  NOT NULL REFERENCES customers(id),
    exchange_reason                 TEXT NOT NULL,
    returned_item_condition         returned_item_condition_enum NOT NULL,
    returned_item_image_confirmed   BOOLEAN NOT NULL DEFAULT FALSE,
    exchange_fee                    NUMERIC(10,2) NOT NULL,
    status                          exchange_status_enum NOT NULL DEFAULT 'pending',
    processed_by                    INTEGER NOT NULL REFERENCES users(id),
    notes                           TEXT,
    created_at                      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at                    TIMESTAMP WITH TIME ZONE,
    tenant_id                       INTEGER NOT NULL DEFAULT 1,

    CONSTRAINT uq_exchanges_original_item UNIQUE (original_item_id),
    CONSTRAINT uq_exchanges_new_item      UNIQUE (new_item_id),
    CONSTRAINT chk_exchanges_image_confirmed CHECK (returned_item_image_confirmed = TRUE)
);
CREATE INDEX idx_exchanges_sale     ON exchanges(original_sale_id);
CREATE INDEX idx_exchanges_customer ON exchanges(customer_id);
CREATE INDEX idx_exchanges_status   ON exchanges(status);
```

The `chk_exchanges_image_confirmed` CHECK enforces server-side that no row exists with image not confirmed (matches invariant 5; service must set true before insert).

### 5.6 `bill_history` table

```sql
CREATE TABLE bill_history (
    id           BIGSERIAL PRIMARY KEY,
    sale_id      INTEGER NOT NULL REFERENCES sales(id),
    event_type   bill_event_type_enum NOT NULL,
    item_id      INTEGER REFERENCES items(id),
    exchange_id  BIGINT  REFERENCES exchanges(id),
    return_id    BIGINT  REFERENCES returns(id),
    description  TEXT NOT NULL,
    created_by   INTEGER NOT NULL REFERENCES users(id),
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    tenant_id    INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_bill_history_sale       ON bill_history(sale_id);
CREATE INDEX idx_bill_history_created_at ON bill_history(created_at);
```

### 5.7 system_settings seeds

```python
op.execute("""
    INSERT INTO system_settings (key, value, description) VALUES
    ('exchange_window_days', '30', 'Days after purchase during which exchange is allowed'),
    ('exchange_fee_amount',  '0',  'Flat exchange fee charged at original sale time (per item)')
    ON CONFLICT (key) DO NOTHING
""")
```

### 5.8 Backfill

- `is_exchange_item = false` (column default handles all existing rows).
- `exchange_eligible = false` (default handles).
- Existing sales: `exchange_fee_total = 0` (default).
- No data backfill required.

### 5.9 Downgrade

Drop in reverse order:
1. `bill_history`
2. `exchanges`
3. drop sale column, item columns, partial indexes
4. drop the three new ENUM types
5. seed deletes (`DELETE FROM system_settings WHERE key IN (...)`).
6. **Cannot remove** `'exchanged'` from `item_status` — leave a comment.

---

## 6. Models (SQLAlchemy)

### `backend/models/item.py` additions

Add to `ItemStatus` enum:
```python
class ItemStatus(str, enum.Enum):
    in_stock = "in_stock"
    sold = "sold"
    reserved = "reserved"
    archived = "archived"
    exchanged = "exchanged"   # NEW — terminal
```

Add columns on `Item`:
```python
exchange_eligible:        Mapped[bool]            = mapped_column(Boolean, nullable=False, server_default=text("false"))
exchange_fee_paid:        Mapped[Decimal | None]  = mapped_column(Numeric(10,2))
is_exchange_item:         Mapped[bool]            = mapped_column(Boolean, nullable=False, server_default=text("false"))
exchange_marker_detected: Mapped[bool | None]     = mapped_column(Boolean)
original_item_id:         Mapped[int | None]      = mapped_column(ForeignKey("items.id"))
exchanged_at:             Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

### `backend/models/sale.py`

```python
exchange_fee_total: Mapped[Decimal] = mapped_column(Numeric(10,2), nullable=False, server_default=text("0"))
```

### `backend/models/exchange.py` (new)

```python
class ReturnedItemCondition(str, enum.Enum): ...    # excellent..damaged
class ExchangeStatus(str, enum.Enum): ...           # pending, completed, cancelled
class BillEventType(str, enum.Enum): ...            # 6 values

class Exchange(Base, TimestampMixin):
    __tablename__ = "exchanges"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    exchange_ref: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    original_sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), nullable=False)
    original_item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False, unique=True)
    new_item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), unique=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("customers.id"), nullable=False)
    exchange_reason: Mapped[str] = mapped_column(Text, nullable=False)
    returned_item_condition: Mapped[ReturnedItemCondition] = ...
    returned_item_image_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    exchange_fee: Mapped[Decimal] = mapped_column(Numeric(10,2), nullable=False)
    status: Mapped[ExchangeStatus] = ...  default pending
    processed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[int] = mapped_column(Integer, server_default=text("1"))

class BillHistory(Base):
    __tablename__ = "bill_history"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), nullable=False)
    event_type: Mapped[BillEventType] = ...
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"))
    exchange_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("exchanges.id"))
    return_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("returns.id"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tenant_id: Mapped[int] = mapped_column(Integer, server_default=text("1"))
```

---

## 7. `backend/services/exchange_service.py`

```python
class ExchangeNotEligibleError(Exception):
    """Raised when an item cannot be exchanged. Mapped to HTTP 422 by route layer."""
    def __init__(self, code: str, detail: str):
        self.code = code        # e.g. NOT_ON_SALE, NOT_ELIGIBLE, ALREADY_EXCHANGED, WINDOW_EXPIRED, NOT_SOLD
        self.detail = detail
        super().__init__(detail)


async def generate_exchange_ref(db: AsyncSession) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = _advisory_key("exc")          # reuse helper from receipt_service or duplicate locally
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
    n = await db.scalar(
        text("SELECT COUNT(*) FROM exchanges WHERE exchange_ref LIKE :p"),
        {"p": f"EXC-{today}-%"}
    )
    seq = (n or 0) + 1
    if seq > 9999:
        raise HTTPException(409, "Exchange ref sequence exhausted for today")
    return f"EXC-{today}-{seq:04d}"


async def validate_exchange_eligibility(
    item_id: int, sale_id: int, customer_id: int, db: AsyncSession
) -> None:
    # 1. Sale belongs to customer (or after link-customer call)
    # 2. SaleItem(sale_id, item_id) exists
    # 3. items.exchange_eligible = true
    # 4. items.status = 'sold'
    # 5. No completed/pending exchange row already for this item
    # 6. now() <= sale.created_at + exchange_window_days (from system_settings)
    # Raise ExchangeNotEligibleError with specific code per failure


async def initiate_exchange(
    *, sale_id: int, item_id: int, customer_id: int,
    reason: str, condition: ReturnedItemCondition,
    confirmed_by_image: bool, processed_by: int,
    db: AsyncSession,
) -> Exchange:
    if not confirmed_by_image:
        raise HTTPException(422, "Image confirmation required")
    await validate_exchange_eligibility(item_id, sale_id, customer_id, db)
    fee = (await get_item(item_id, db)).exchange_fee_paid or Decimal("0")
    ex = Exchange(
        exchange_ref=await generate_exchange_ref(db),
        original_sale_id=sale_id, original_item_id=item_id,
        customer_id=customer_id, exchange_reason=reason,
        returned_item_condition=condition,
        returned_item_image_confirmed=True,
        exchange_fee=fee, status=ExchangeStatus.pending,
        processed_by=processed_by,
    )
    db.add(ex); await db.flush()
    await _append_history(db, sale_id, BillEventType.exchange_initiated,
                          item_id=item_id, exchange_id=ex.id,
                          description=f"Exchange initiated for item {item_id}",
                          created_by=processed_by)
    await db.commit(); await db.refresh(ex)
    return ex


async def complete_exchange(
    *, exchange_ref: str, new_item_id: int, processed_by: int, db: AsyncSession,
) -> Exchange:
    # SELECT ... FOR UPDATE on exchange row
    # assert status == pending
    # assert new_item.status == in_stock and deleted_at is null
    # Within single transaction:
    #   - exchange.status = completed; completed_at = now(); new_item_id = ...
    #   - original_item.status = exchanged; original_item.exchanged_at = now()
    #   - new_item.status = sold; new_item.sold_at = now();
    #     new_item.is_exchange_item = true; new_item.original_item_id = original_item.id
    #   - bill_history append (exchange_completed)
    # commit


async def get_bill_history(sale_id: int, db: AsyncSession) -> list[BillHistory]:
    # ORDER BY created_at ASC, id ASC
```

`_append_history` is a private helper used by `sales`, `returns`, and `exchanges` services (extract a shared util in `services/exchange_service.py` and import where needed; or keep `_append_history` inside each call site — chosen: shared helper exported from `exchange_service.py`).

---

## 8. Routes

### `backend/routes/exchanges.py`

| Method | Path | Auth | Body / Query | Response |
|---|---|---|---|---|
| POST | `/exchanges/initiate` | staff+ | `{sale_ref, item_id, customer_uid, reason, condition, image_confirmed}` | `ExchangeResponse (status=pending)` |
| POST | `/exchanges/{exchange_ref}/complete` | staff+ | `{new_item_barcode}` | `ExchangeResponse (status=completed)` |
| GET  | `/exchanges/{exchange_ref}` | staff+ | — | `ExchangeResponse` |

### Adds to `backend/routes/customers.py`
| Method | Path | Auth |
|---|---|---|
| GET | `/customers/{customer_uid}/exchanges` | **admin only** |

### Adds to `backend/routes/sales.py`
| Method | Path | Auth |
|---|---|---|
| GET  | `/sales/{sale_ref}/history` | staff+ |
| POST | `/sales/{sale_ref}/link-customer` | staff+ — body `{customer_uid}` |

### Modify `POST /sales/` (existing)
- `SaleCreate.items[*].exchange_eligible: bool = False` (server default false even if client omits).
- For each line where `exchange_eligible=True`: read `exchange_fee_amount` from `system_settings` once; set `item.exchange_eligible=True`, `item.exchange_fee_paid=fee`; add fee to running `exchange_fee_total`.
- Sale total = `subtotal - discount + tax + exchange_fee_total`.
- Write `bill_history` row with `event_type=purchase` after sale committed.

### `backend/main.py`
```python
from routes import exchanges as exchanges_router
app.include_router(exchanges_router.router)
```

---

## 9. Analytics Exclusion Checklist

Add the comment block once at the top of `analytics_service.py`:

```python
# EXCHANGE ITEMS EXCLUDED: is_exchange_item = true
# These items are counted in revenue totals only.
# Reason: exchange items skew trend data because they represent recycled inventory not new intake.
```

Predicate to add: **`AND is_exchange_item = false`** (or `is_exchange_item = FALSE` — Postgres-friendly).

| Function | Query block | Add predicate? |
|---|---|---|
| `get_summary` (main row, lines 28-34) — total/sold/in_stock/revenue/avg/today | **NO** — revenue must include exchange items |
| `get_summary` (sell-through inner, lines 45-52) | **YES** — sell-through is an analytical metric |
| `get_summary` `top_labels` query | **YES** |
| `get_summary` exchange_stats (NEW block) | n/a — explicitly counts exchanges from `exchanges` table |
| `get_trends` (line ~90, `WHERE status='sold'`) | **YES** |
| `get_dead_stock` (line ~127, `WHERE status='in_stock'`) | **YES** |
| `get_cv_performance` (lines 142-154, all sub-queries on items) | **YES** on every items-scan query |
| `get_velocity` (line ~270) | **YES** |

Add to `get_summary` return dict:
```python
exchange_stats = {
    "total_exchanges_this_period": <int>,        # COUNT exchanges WHERE status='completed' AND completed_at >= since
    "exchange_revenue":             <Decimal>,    # SUM exchange_fee_total over sales in period (or SUM exchange_fee from exchanges)
    "most_exchanged_category":      <str | None>, # MODE category from items joined on exchanges.original_item_id
    "avg_exchange_condition":       <str | None>, # MODE returned_item_condition
}
```

---

## 10. Checkout (`routes/sales.py` + `frontend/src/pages/Checkout.tsx`)

### Backend schema (`schemas/sale.py`)
```python
class SaleItemInput(BaseModel):
    barcode: str
    price_override: Decimal | None = None
    exchange_eligible: bool = False    # NEW
```

### Frontend — `Checkout.tsx`
- `CartItem` type adds `exchange_eligible: boolean; exchangeFee: number`.
- `useEffect` once on mount: fetch `system_settings/exchange_fee_amount` → store in component state.
- Per-row UI: small toggle "Exchange eligible — +₹{fee}" beside price.
- Cart totals area: a new line "Exchange fee × N — ₹{total}" between subtotal and tax.
- POST body sends `exchange_eligible` per line.
- On `SaleComplete`: receipt panel lists exchange-eligible items with their window expiry date (`created_at + window_days`).

---

## 11. CV Infrastructure (orange marker card)

In `backend/services/cv_service.py`, add a top-of-file documentation block:

```python
# === EXCHANGE ITEM MARKER (TODO: activate once cards are printed) ===
# Marker: A6 orange card (~105×148mm), bright orange, black text "EXCHANGE",
# placed in the camera frame to the LEFT of the garment during re-intake.
# When detected, the item being photographed is a returned/replacement item
# from a completed exchange and must be tagged is_exchange_item=true.
# Flow:
#   - quick_analyze prompt asks: "Is there a bright-orange A6 card with the
#     word 'EXCHANGE' in black text on the LEFT side of the frame?"
#   - cv_raw_output gains: { "is_exchange_marker": bool, "marker_confidence": float }
# Until physical cards exist this is wired but NOT acted on. Routes/items.py
# already reads is_exchange_marker; toggle the gate by removing the
# `EXCHANGE_MARKER_ENABLED = False` constant.
EXCHANGE_MARKER_ENABLED = False  # TODO: flip to True when cards are printed
```

Update `quick_analyze` (or whichever fn writes `cv_raw_output`) to add `is_exchange_marker` and `marker_confidence` keys (default false / 0.0 until enabled).

In `backend/routes/items.py` `POST /`:
```python
cv = payload.cv_raw_output or {}
if EXCHANGE_MARKER_ENABLED and cv.get("is_exchange_marker") is True:
    item.is_exchange_item = True
    item.exchange_marker_detected = True
    item.notes = (item.notes or "") + "\n[CV] Exchange marker detected at intake."
    skip_phase_b = True
    skip_fashion_attributes = True
else:
    skip_phase_b = False
    skip_fashion_attributes = False
# enqueue background jobs gated on those flags
```

---

## 12. Frontend

### `frontend/src/pages/Exchange.tsx` — 5 steps

1. **Phone lookup** — input → `GET /customers?phone=…` → show customer card.
2. **Bill picker** — `GET /customers/{uid}/sales?eligible_for_exchange=true` (or filter client-side using `created_at` + `exchange_window_days`). Show only items whose `exchange_eligible=true` and not already exchanged.
3. **Item confirmation** — show original photo (`item.image_path` via `IMAGE_BASE_URL`). Required toggle "Image matches physical item" (sets `image_confirmed`). Required `condition` dropdown. Required `reason` textarea.
4. **New item entry** — barcode scan/input, validates `status=in_stock`. Shows preview.
5. **Complete** — `POST /exchanges/initiate` then `POST /exchanges/{ref}/complete`. Render confirmation + `BillHistoryTimeline` for that sale.

### `frontend/src/components/BillHistoryTimeline.tsx`
- Props: `events: BillHistoryEvent[]`.
- Vertical, accent dot per event type:
  - `purchase` → teal
  - `exchange_initiated` / `exchange_completed` → amber
  - `return_initiated` / `return_completed` → blue
  - `item_added` → grey
- Used by Exchange page step 5 and a new "History" tab on the existing `Sales.tsx` (out of scope for v1 but timeline is reusable).

### `frontend/src/App.tsx`
- Add `<Route path="/exchange" element={<Exchange />} />`
- Nav link "Exchange" — visible to staff and admin.

---

## 13. Tests

### Unit — `tests/unit/test_exchange_service.py`
1. `validate_exchange_eligibility` succeeds for valid case.
2. Fails `NOT_ON_SALE` when item not part of sale.
3. Fails `NOT_ELIGIBLE` when `exchange_eligible=false`.
4. Fails `WINDOW_EXPIRED` when sale older than window.
5. Fails `ALREADY_EXCHANGED` when an `exchanges` row exists for item.
6. Fails `NOT_SOLD` when item already exchanged (status=exchanged).
7. `generate_exchange_ref` returns pattern `EXC-YYYYMMDD-NNNN` and increments under contention (run 5 in parallel via `asyncio.gather`).
8. `complete_exchange`: pending → completed transition; status assertions; rejects when status already completed.
9. `complete_exchange`: rejects when `new_item.status != 'in_stock'`.

### Integration — `tests/integration/test_exchanges.py`
1. Full happy path: checkout w/ opt-in → initiate → complete; verify item statuses, `bill_history` has 3 rows in order (`purchase`, `exchange_initiated`, `exchange_completed`).
2. Anonymous sale → initiate fails 422 → `POST /sales/{ref}/link-customer` → initiate succeeds.
3. Item with `exchange_eligible=false` → 422 `NOT_ELIGIBLE`.
4. Exchange outside window → 422 `WINDOW_EXPIRED` (set `exchange_window_days=0`).
5. Complete with out-of-stock item → 422.
6. Analytics: seed 5 items, 1 marked `is_exchange_item`; verify `get_trends`, `get_dead_stock`, `get_velocity`, `get_cv_performance` exclude it; verify `get_summary.revenue` includes its sale price.
7. Receipt for sale w/ exchange fee shows `exchange_fee_total > 0`.
8. `GET /sales/{sale_ref}/history` returns events chronologically.

---

## 14. Risk Assessment

| Risk | Existing surface | Mitigation |
|---|---|---|
| Adding enum value mid-transaction breaks migration on managed Postgres that disallows mid-DDL `COMMIT`. | Migration 008. | Document Option B (`transactional_ddl = False`). Test on Docker postgres 16 first. |
| `validate_exchange_eligibility` window check using `system_settings` is read at call time. If admin shrinks the window mid-flight, in-flight initiations may fail. | `system_settings`. | Acceptable; document. |
| Existing `routes/sales.py` total computation may double-add tax+fee. | `routes/sales.py`. | Add explicit unit test for sale total math; `exchange_fee_total` is **not taxed**. |
| Existing `get_summary` queries are raw SQL strings — adding `is_exchange_item = false` to wrong line could silently drop revenue. | `analytics_service.py`. | The Analytics Exclusion Checklist (§9) is precise: do not modify lines 28-34 main row aggregates. Add a test asserting revenue includes exchange items. |
| Returns flow already places `ReturnItem` UNIQUE on `item_id`. If a returned item is later exchanged-eligible, both could fire — but `exchange_eligible` is set at original sale, returns roll status back to `in_stock`. Possible to have an item that was returned and is also exchange_eligible=true. | `returns` + `items`. | Decision: once an item is returned (via returns flow), `exchange_eligible` should be cleared. Add this clearing to existing return-completion handler. **Document in plan as a small required change to `services/return_service.py` / wherever return completion lives** — implementer must locate and add `item.exchange_eligible = False` on return completion. |
| CV `is_exchange_marker` accidentally activated before cards printed → false positives flag legitimate items as exchange items, removing them from analytics. | `cv_service.py`, `routes/items.py`. | `EXCHANGE_MARKER_ENABLED = False` gate; explicit TODO; gated test. |
| `chk_exchanges_image_confirmed` CHECK is strict — any test that builds a row directly without setting `true` will fail. | `tests/integration/test_exchanges.py`. | Document in fixture helpers. |
| `Exchange.original_item_id` UNIQUE prevents accidental double-exchange but also prevents a re-cancellation pattern. | `exchanges` table. | Document — cancellation in v1 deletes the pending row; future v2 will need a soft-cancel column. |
| `bill_history.return_id` FK references `returns` table; ensure that table is named `returns` (reserved word concern in some Postgres versions). | `returns` table. | Existing model uses it already; safe. Quote identifiers in SQL only if needed. |
| Frontend `Checkout.tsx` modifications could ship without backend update if deploy ordering is wrong, causing 422s on legacy sale POSTs. | `Checkout.tsx` + `routes/sales.py`. | Backend must default `exchange_eligible=False` in schema (already specified). Deploy backend first. |

### Specific findings from existing code that the implementer must know

1. **`services/analytics_service.py` line 28-34**: the main aggregate row in `get_summary` uses `FILTER (WHERE status='sold' ...)`. Do not add the `is_exchange_item=false` filter here. Only add it to the inner `top_labels` query and other functions. There is **no separate revenue subquery** to update — leave the main row untouched.
2. **`routes/__init__.py` shows existing routers**: `auth, items, sales, analytics, jobs, customers, returns`. `main.py` must `include_router` the new `exchanges` router (and the package import block in `__init__.py` if it re-exports).
3. **No existing `_append_history` helper** — `bill_history` is brand new. The implementer must:
   - Decide where the helper lives (recommended: `services/exchange_service.py` exports `append_bill_history`).
   - Call it from `routes/sales.py` (purchase + item_added), `services/return_service` or `routes/returns.py` (return_initiated, return_completed), and `services/exchange_service.py` (exchange_initiated, exchange_completed).
   - There is **no existing return-side hook** for history — the implementer must locate the return completion code (likely in `routes/returns.py`) and add `append_bill_history` calls there too. This is *out of the original prompt scope* but required to make the timeline complete; flag it for the user if it expands the change set.
4. **`services/receipt_service.py` `_advisory_key`** (referenced in spec) — verify the helper's actual name; if it is `_advisory_key("rcp")` then re-use it via import. If private, copy the same pattern locally in `exchange_service.py` rather than reaching into a private name.
5. **Returned item clearing** — when an item goes through the *returns* pipeline (existing flow), the implementer **must** also set `exchange_eligible = false` so a returned item cannot then be exchanged. This is a small but easy-to-miss edit in the return-completion handler.

---

## 15. Security Checklist (8 items)

1. **Auth on every new endpoint.** All `/exchanges/*`, `/sales/{ref}/history`, `/sales/{ref}/link-customer` require `Depends(get_current_user)` with `role >= staff`. `/customers/{uid}/exchanges` is `role == admin`.
2. **Pydantic validation on every body.** `condition` is constrained to `ReturnedItemCondition`; `reason` `min_length=3, max_length=2000`; `new_item_barcode` regex matches existing barcode pattern; `image_confirmed` must be `True` (validator).
3. **No raw SQL interpolation.** Analytics changes append a literal predicate (`AND is_exchange_item = false`) — no user input. All new queries in `exchange_service.py` use bound parameters or ORM.
4. **No hardcoded secrets / config.** `exchange_window_days` and `exchange_fee_amount` come from `system_settings` only.
5. **Audit logging.** Existing audit middleware will record exchanges automatically (since `Exchange` is a SQLAlchemy model on the audited engine). Add `Exchange` and `BillHistory` to the audit allow-list if it is opt-in. Do not skip.
6. **Server-side enforcement of immutable fields.** No PATCH route for `exchange_eligible`, `is_exchange_item`, `original_item_id`, `exchanged_at`, `exchange_fee_paid`. Existing `PATCH /items/{id}` schema must explicitly **forbid** these (add `Field(exclude=True)` or strip in route before applying updates). Implementer must verify.
7. **Image-confirmation enforcement is dual.** CHECK constraint at DB level + Pydantic validator + service-level `if not confirmed_by_image: raise`.
8. **Tenant isolation.** All new queries scope by `tenant_id` like the existing customers/returns code does. `bill_history` and `exchanges` carry `tenant_id` columns.

---

## 16. Step-by-Step Execution Plan

1. **Migration**
   - Write `backend/migrations/versions/008_exchange_system.py` per §5.
   - `make migrate` against dev DB; verify `\d items`, `\d sales`, `\d exchanges`, `\d bill_history`, `SELECT enum_range(NULL::item_status)`.
   - Run downgrade then upgrade once to ensure idempotency (note: enum value persists after downgrade — documented).

2. **Models**
   - Update `backend/models/item.py`, `backend/models/sale.py`.
   - Create `backend/models/exchange.py`.
   - Wire `__init__.py`.

3. **Schemas**
   - Update `backend/schemas/item.py`, `backend/schemas/sale.py`.
   - Create `backend/schemas/exchange.py` (`ExchangeInitiate`, `ExchangeComplete`, `ExchangeResponse`, `BillHistoryEvent`).

4. **Service + unit tests**
   - Create `backend/services/exchange_service.py` per §7.
   - Write `tests/unit/test_exchange_service.py` per §13.
   - Run `pytest tests/unit/test_exchange_service.py -q`.

5. **Routes**
   - Create `backend/routes/exchanges.py` per §8.
   - Modify `backend/routes/sales.py`: `POST /` accepts `exchange_eligible`; emit `bill_history` row; new `GET /sales/{ref}/history`, `POST /sales/{ref}/link-customer`.
   - Modify `backend/routes/customers.py`: `GET /customers/{uid}/exchanges`.
   - Modify `backend/routes/items.py`: CV marker gate.
   - Register router in `backend/main.py`.

6. **Returns integration**
   - Locate return-completion handler. Add `item.exchange_eligible = False` on completion.
   - Add `bill_history` `return_initiated` / `return_completed` calls.

7. **Analytics**
   - Update `backend/services/analytics_service.py` per §9.
   - Add `exchange_stats` block to `get_summary`.

8. **Integration tests**
   - Write `tests/integration/test_exchanges.py` per §13.
   - `make test-integration`.

9. **Frontend**
   - `frontend/src/components/BillHistoryTimeline.tsx`.
   - `frontend/src/pages/Exchange.tsx`.
   - Modify `frontend/src/pages/Checkout.tsx` (per-item toggle, fee total, receipt).
   - Modify `frontend/src/App.tsx` (route + nav).
   - `npm run test` and `npm run typecheck`.

10. **Security pass**
    - Walk through the 8 items in §15 against the implementation. Specifically grep `PATCH` on items route for forbidden fields.

11. **CV gating**
    - Verify `EXCHANGE_MARKER_ENABLED = False`.
    - Add unit test that with the flag false, `is_exchange_marker=true` in cv output does **not** flag the item.

12. **Docs**
    - Update `CHANGELOG.md`.
    - Move exchange entry out of `PLANNING.md` open questions.
    - Append SESSION NOTES (2026-05-09) to `CLAUDE.md` describing the new model, the marker-card protocol, and the `exchange_eligible` immutability rule.

13. **Final**
    - `make test` (full).
    - `make lint`.
    - Manual smoke: full intake → checkout w/ exchange opt-in → exchange initiate → complete → analytics dashboard.

---

## 17. API Request/Response Cheat Sheet

```
POST /exchanges/initiate
{
  "sale_ref": "SALE-20260415-007",
  "item_id": 1234,
  "customer_uid": "CUS-000123",
  "reason": "Wrong size",
  "condition": "good",
  "image_confirmed": true
}
→ 200 {
  "exchange_ref": "EXC-20260509-0001",
  "status": "pending",
  "original_item_id": 1234,
  "exchange_fee": "0.00",
  "created_at": "...",
  ...
}

POST /exchanges/EXC-20260509-0001/complete
{ "new_item_barcode": "TS-098765" }
→ 200 { "status": "completed", "new_item_id": 9876, "completed_at": "...", ... }

GET /sales/SALE-20260415-007/history
→ 200 [
  { "event_type": "purchase",            "created_at": "...", "description": "..." },
  { "event_type": "exchange_initiated",  "created_at": "...", "exchange_id": 1, "item_id": 1234 },
  { "event_type": "exchange_completed",  "created_at": "...", "exchange_id": 1, "item_id": 9876 }
]

POST /sales/SALE-20260415-007/link-customer
{ "customer_uid": "CUS-000123" }
→ 200 { "sale_ref": "...", "customer_id": 123 }
```

---

## 18. Hard Rules — Restated

1. `exchange_eligible` is **set only at sale POST**. No PATCH. (§15.6)
2. An item is exchanged at most once. UNIQUE on `exchanges.original_item_id` enforces it. (§5.5)
3. Exchange requires a customer. Anonymous sale → use `link-customer` first. (§8)
4. `image_confirmed = true` is enforced by Pydantic, service, and DB CHECK. (§15.7)
5. `is_exchange_item = true` is one-way. Never cleared. (§1.6)
6. Replacement items cannot be re-exchanged unless their own purchase opts in again. (§1.7)
