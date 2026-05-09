# Technical Review — ERPos
> Date: 2026-05-09 | Reviewer: Claude Sonnet (session review)
> Status: READ-ONLY — no code was written or modified in this session

---

## 1. Complexity Scores

| Area | Score | Reasoning |
|---|---|---|
| Data model | **Medium** | 14 tables, clean FK discipline, but `items` is accumulating columns across unrelated concerns |
| Job queue | **Low–Medium** | Single table for 5 job types works; un-typed JSONB payloads are the only real risk |
| CV pipeline | **Medium** | 3 models + exchange branch is manageable but the worker function has 5 code paths |
| Exchange system | **Medium–High** | 5–6 tables touched per complete lifecycle; bill_history coupling is the main structural risk |
| Analytics exclusion pattern | **High** | No enforcement mechanism; every future query is one forgotten WHERE clause away from wrong data |
| Overall | **Medium** | Clean in most places, with two specific patterns that will cause pain as the system grows |

---

## 2. Entity Relationship Map

```
users
  id PK
  username UNIQUE
  password_hash
  role (user_role enum)
  is_active
  created_at, updated_at

items
  id PK
  barcode UNIQUE
  category (item_category enum)
  color, secondary_color
  type (item_type enum)
  label, size
  condition (item_condition enum)
  price NUMERIC(10,2)
  cv_confidence, cv_raw_output JSONB
  cv_color_correct, cv_type_correct
  cv_phase_b_complete
  fashion_attributes JSONB
  image_path, image_thumb_path
  status (item_status enum)  ← in_stock | sold | reserved | archived | exchanged
  notes
  bulk_group_id UUID, bulk_sequence
  created_by → users.id
  sold_at, deleted_at
  exchange_eligible BOOL
  exchange_fee_paid NUMERIC(10,2)
  is_exchange_item BOOL              ← one-way flag, never cleared
  exchange_marker_detected BOOL
  original_item_id → items.id       ← self-reference: replacement → original
  exchanged_at

sales
  id PK
  sale_ref UNIQUE
  receipt_number UNIQUE
  customer_id → customers.id (nullable)
  subtotal, discount_amount, tax_rate, tax_amount, total_amount NUMERIC
  exchange_fee_total NUMERIC
  payment_type (payment_type enum)
  cashier_id → users.id
  notes
  voided_at, voided_by → users.id
  created_at, updated_at

sale_items
  id PK
  sale_id → sales.id ON DELETE RESTRICT
  item_id → items.id ON DELETE RESTRICT
  price NUMERIC

customers
  id PK (BigInteger)
  customer_uid UNIQUE
  first_name, last_name, phone (E.164), email, notes
  is_active, deleted_at, gdpr_erased_at
  tenant_id
  created_at, updated_at

returns
  id PK (BigInteger)
  return_ref UNIQUE
  original_sale_id → sales.id ON DELETE RESTRICT
  customer_id → customers.id (nullable)
  return_reason, notes
  processed_by → users.id
  refund_amount NUMERIC
  refund_method (refund_method_enum)
  status (return_status_enum)        ← pending|approved|completed|rejected
  completed_at, tenant_id
  created_at, updated_at

return_items
  id PK
  return_id → returns.id ON DELETE CASCADE
  item_id → items.id ON DELETE RESTRICT (UNIQUE constraint)
  original_price, refund_price NUMERIC
  tenant_id

exchanges
  id PK (BigInteger)
  exchange_ref UNIQUE
  original_sale_id → sales.id
  original_item_id → items.id (UNIQUE)
  new_item_id → items.id (UNIQUE, nullable)
  customer_id → customers.id
  exchange_reason, notes
  returned_item_condition (returned_item_condition_enum)
  returned_item_image_confirmed BOOL (CHECK = TRUE)
  exchange_fee NUMERIC
  status (exchange_status_enum)      ← pending|completed|cancelled
  processed_by → users.id
  completed_at, tenant_id
  created_at, updated_at

bill_history
  id PK (BigInteger)
  sale_id → sales.id
  event_type (bill_event_type_enum)  ← purchase|exchange_initiated|exchange_completed|return_initiated|return_completed|item_added
  item_id → items.id (nullable)
  exchange_id → exchanges.id (nullable)
  return_id → returns.id (nullable)
  description TEXT
  created_by → users.id
  created_at, tenant_id

job_queue
  id PK (BigInteger)
  job_type (job_type_enum)           ← cv_phase_a|cv_phase_b|fashion_attributes|print_label|print_retry
  status (job_status_enum)           ← pending|processing|complete|failed|cancelled
  priority, attempts, max_attempts
  item_id → items.id (nullable)
  payload JSONB                      ← shape varies by job_type; no schema enforcement
  result JSONB, error_message
  next_retry_at, created_at, started_at, completed_at
  created_by → users.id

audit_log
  id PK (BigInteger)
  table_name, record_id, action
  old_values JSONB, new_values JSONB  ← PII masked before write
  user_id → users.id
  ip_address INET
  created_at

system_settings
  key PK (String 64)
  value TEXT
  description TEXT
  updated_by → users.id
  updated_at, tenant_id
```

**Foreign key counts (tables with 4+):**

| Table | FK count |
|---|---|
| `items` | 2 (created_by, original_item_id self-ref) |
| `sales` | 3 (customer_id, cashier_id, voided_by) |
| `sale_items` | 2 |
| `returns` | 3 (original_sale_id, customer_id, processed_by) |
| `return_items` | 2 |
| `exchanges` | **5** (original_sale_id, original_item_id, new_item_id, customer_id, processed_by) |
| `bill_history` | **5** (sale_id, item_id, exchange_id, return_id, created_by) |
| `job_queue` | 2 |
| `audit_log` | 1 |
| `system_settings` | 1 |

Exchanges and bill_history are the most connected tables. They are also the newest. This is expected — events naturally reference more things than entities.

---

## 3. The Critical Chain: Customer → Interaction History

**Question: "What is the full history of this customer's interaction with the store?"**

```
customers.id
  └─ sales.customer_id              [1 hop: customer's sales]
      └─ sale_items.sale_id         [2 hops: items on each sale]
          └─ items.id               [3 hops: item details + status]
      └─ returns.original_sale_id   [2 hops: returns from each sale]
          └─ return_items.return_id [3 hops: which items returned]
      └─ exchanges.original_sale_id [2 hops: exchanges from each sale]
          └─ exchanges.new_item_id  [3 hops: replacement items]
      └─ bill_history.sale_id       [2 hops: event timeline]
```

**Hop count to reconstruct a complete picture: 3 hops, 6 tables.**

This is reasonable. The chain is not circular. The most expensive reconstruction (all sales + all items + all returns + all exchanges + all bill_history) requires 5 JOINs but is scoped to one customer's data.

**The bill_history table is an important observation here**: it theoretically makes this query easier (one table with all events), but it is only complete if every code path that modifies a bill correctly writes to it. Currently:
- `routes/sales.py` writes `purchase` events ✓
- `routes/returns.py` writes `return_initiated` + `return_completed` ✓
- `services/exchange_service.py` writes `exchange_initiated` + `exchange_completed` ✓

The coupling is hidden and informal. If a future developer adds a sale void handler and forgets to write to `bill_history`, the timeline becomes silently incomplete. There is no test that asserts bill_history completeness.

---

## 4. Red Flags

### RF-1: Analytics Exclusion Has No Enforcement Mechanism

**Where:** `services/analytics_service.py`, all query functions.

**What:** Exchange items (`is_exchange_item = TRUE`) must be excluded from trend, velocity, dead stock, sell-through, and CV accuracy queries, but included in revenue totals. This rule is enforced by manually adding `AND is_exchange_item = false` to 6 separate raw SQL query blocks in one service file.

**The risk:** Every future analytics query that a developer writes must independently remember this rule. There is nothing in the database, schema, or code architecture that prevents a new query from silently including exchange items. In 6 months, when someone adds "most exchanged color" or "pricing trend by category" without the filter, the analytics will be wrong and the store owner will make pricing decisions based on recycled inventory data.

**Evidence of how easily this gets missed:** The same `is_exchange_item` filter was introduced as part of this session and the pattern already has to be applied to 7 separate locations (including the calibration and mistakes sub-queries within `get_cv_performance`). The developer got them all, but only because they were working on it in one session. A future developer adding a new query weeks later will have less context.

### RF-2: `bill_history` Coupling Across Three Unrelated Route Files

**Where:** `routes/sales.py`, `routes/returns.py`, `services/exchange_service.py`.

**What:** `append_bill_history()` is defined in `services/exchange_service.py` and is imported by `routes/returns.py` and `routes/sales.py`. The function belongs conceptually to a "bill" concern but is homed in the exchange service module.

**The risk:** Structural. Three different places write to the same table with no coordination layer. A developer modifying the returns flow has a non-obvious dependency on an exchange service function. If returns are ever refactored to a `services/return_service.py`, the import path creates confusion. More concretely: any new event type that should appear in the bill timeline (say, a "price adjustment" or "barcode reprint") requires knowing to call this function, which is not documented at the call sites.

### RF-3: `exchanges.new_item_id` UNIQUE Constraint Is Too Strict

**Where:** `backend/migrations/versions/008_exchange_system.py`, the `uq_exchanges_new_item` constraint.

**What:** The UNIQUE constraint on `exchanges.new_item_id` prevents the same item from being used as a replacement in two different exchanges.

**The real workflow that breaks this:** A customer receives replacement item B in exchange for item A. Customer B then returns item B via the returns flow (not exchange). Item B goes back to `in_stock`. A different customer then brings in item C for exchange. Staff scans item B as the replacement. The insert into `exchanges` fails with a uniqueness violation because `new_item_id = B.id` already exists from the first exchange, even though that exchange is complete and item B has been returned and is back in inventory.

**This will happen in a real store.** Replacement items are stock items like any other. They will be returned, they will be re-selected as replacements.

### RF-4: `items` Table Is a Mixing Bowl

**Where:** `backend/models/item.py`, 28 columns at last count.

**What:** The items table currently merges four concerns:
1. **Core product attributes** (barcode, category, color, type, label, size, condition, price, status, notes) — always populated
2. **CV metadata** (cv_confidence, cv_raw_output, cv_color_correct, cv_type_correct, cv_phase_b_complete, fashion_attributes) — filled asynchronously, NULL for most items initially
3. **Bulk intake coordination** (bulk_group_id, bulk_sequence) — NULL for ~95% of items
4. **Exchange provenance** (exchange_eligible, exchange_fee_paid, is_exchange_item, exchange_marker_detected, original_item_id, exchanged_at) — NULL or false for ~90%+ of items

**The consequence:** At any given time, roughly half the columns on any given item row are NULL. The `SELECT *` footprint is larger than necessary. More importantly, the table's conceptual surface is wide: a developer looking at the item model needs to mentally track 4 different subsystems.

**This is not yet a performance problem.** PostgreSQL handles NULL columns efficiently. But it is a readability and onboarding problem, and it will get worse with each new feature.

### RF-5: `ReturnStatus` Enum Has Dead Variants

**Where:** `models/return_.py`, `ReturnStatus` enum (`pending`, `approved`, `completed`, `rejected`).

**What:** `routes/returns.py` always sets `status=ReturnStatus.completed` at creation. `pending`, `approved`, and `rejected` are never written to. These states exist in the database schema, in the Python enum, and in the CHANGELOG, but have zero code paths that produce them.

**The risk:** Low in isolation, but it creates a false impression of system capability. A developer debugging a return-related issue in production will see `pending` in the schema and wonder if there's a background approval workflow they've missed. It's documented complexity with no value.

### RF-6: Job Payload Shapes Are Untyped

**Where:** `services/queue_service.py` (`enqueue()`), `services/queue_worker.py` (all `_run_*` functions).

**What:** Job payloads are inserted as arbitrary JSONB dicts. The queue worker reads them with `.get()` calls. There is no validation that a `cv_phase_a` job has an `image_path` key at enqueue time; if it's missing, the worker raises `PermanentError` after starting, consuming an attempt.

**The specific inconsistency:** A bulk `cv_phase_a` job has payload `{image_path, bulk_group_id, item_ids}`. A single-item `cv_phase_a` job has payload `{image_path}`. The worker handles both by checking `payload.get("bulk_group_id")`. This is an implicit protocol written in comments, not enforced by any type system.

**This is manageable at current scale.** If job types grow, or if print job payloads change format (e.g., adding printer target IP), the mismatch between enqueueing code and worker code will be invisible until runtime.

### RF-7: ZPL Label Currency Symbol Is Hardcoded as `$`

**Where:** `services/printer_service.py`, line `price_str = f"${item.price:.2f}"`.

**What:** Every physical barcode label printed for every item in the store shows the price as `$250.00` instead of `₹250.00`. This is a small bug with a visible daily impact — every physical tag is wrong.

### RF-8: `get_receipt` Had a Scope Leak (Recently Fixed)

**Where:** `routes/sales.py`, `get_receipt()`.

**What:** The query `SELECT item_id FROM return_items WHERE item_id IN (...)` asked "has this item ever been returned?" instead of "was this item returned from this sale?" An item returned and then resold showed as RETURNED on its new receipt, blocking re-return. This was fixed in the current session but illustrates the architectural risk: whenever a query filters by item ID without scoping to the sale context, the same class of bug can recur. Any new endpoint that queries `return_items` by item ID needs to consciously join through `returns` and scope to `original_sale_id`.

---

## 5. Simplification Opportunities

### SO-1: Create a Database View for Organic Items

**Replaces:** RF-1 (analytics exclusion risk)

**Change:** Add to a migration:
```sql
CREATE VIEW organic_items AS
  SELECT * FROM items WHERE is_exchange_item = FALSE;
```

All analytics functions in `analytics_service.py` use `organic_items` instead of `items`. Revenue-total queries keep using `items` directly. A developer writing a new analytics query defaults to `organic_items` and is automatically correct. The comment block in `analytics_service.py` is replaced by the view definition.

**What it removes:** 7 `AND is_exchange_item = false` predicates scattered across the service file. More importantly: removes the future risk that a new query forgets the filter.

**Cost:** One migration line. Zero behavior change.

### SO-2: Move `append_bill_history` to `services/bill_service.py`

**Replaces:** RF-2 (coupling)

**Change:** Create `services/bill_service.py` with `append_bill_history()` and nothing else. Import it in sales, returns, and exchange_service.

**What it removes:** The confusion of routes/returns.py depending on a function defined in exchange_service.py. The function's home signals its scope clearly: bill history is a sale-level concern, not an exchange-level concern.

**Cost:** One new file, three import changes.

### SO-3: Remove the UNIQUE Constraint on `exchanges.new_item_id`

**Replaces:** RF-3 (workflow-breaking constraint)

**Change:** Drop `uq_exchanges_new_item`, keep a regular index on `new_item_id` for FK performance.

**What it removes:** The production bug where a staff member tries to use a previously-replaced item as a replacement again after it's been returned to inventory. No business rule requires that a replacement item can only ever appear in one exchange.

**Cost:** One migration line to drop the constraint.

### SO-4: Collapse `ReturnStatus` to `completed | rejected`

**Replaces:** RF-5 (dead variants)

**Change:** Remove `pending` and `approved` from the enum. If a two-stage approval workflow is needed later, add those variants back when implementing it.

**Caveat:** PostgreSQL enums cannot have values removed without recreating the type. This requires a migration that creates a new enum, alters the column, drops the old enum. At this stage (no production data using those states) it's cheap. In 6 months it won't be.

**Cost:** One non-trivial migration. If deferred, add a code comment.

### SO-5: Fix the ZPL Currency Symbol

**Replaces:** RF-7

**Change:** `price_str = f"₹{item.price:.2f}"` in `printer_service.py`.

**Cost:** One character.

---

## 6. Exchange System Evaluation: Build As Designed, Simplify First, or Break Into Pieces?

**The exchange system as designed is architecturally sound for a thrift store.** The business logic (opt-in at checkout, photo verification, single-use exchange) is correctly modelled. The state machine is clean. The database constraints do what they should.

**The concerns are operational, not structural:**

1. The `new_item_id` UNIQUE constraint will cause a real problem. Fix before going live (SO-3).

2. The exchange flow requires a customer record. The `link-customer` endpoint handles anonymous sales. This is correct but adds a step that staff will not intuit. The frontend Exchange page should surface this clearly (it currently does).

3. The image verification step (staff visually confirms photo) is a human process, not a technical one. The database enforces that `returned_item_image_confirmed = TRUE` before the exchange record can be created. This is the right approach — the system can't verify the item, but it can make staff confirm they did.

**The one thing that would improve the exchange system's long-term maintainability, without changing any business logic, is SO-1 (the organic_items view).** Exchange items feeding into analytics is the subtlest and most likely production bug.

**The exchange marker card detection (`EXCHANGE_MARKER_ENABLED = False`)** is the right pattern. Build the infrastructure, gate it safely. The CV pipeline change needed for this is minimal (it's already written). It only needs the physical cards to exist and a test image to validate the prompt.

---

## 7. What to Build Next vs. Defer

### Build now (before taking more customers or more items)

1. **SO-3** — Drop `exchanges.new_item_id` UNIQUE. This is a real production bug waiting to happen. One migration, five minutes.

2. **SO-5** — Fix ZPL currency symbol. Every label is wrong today.

3. **SO-1** — Create the `organic_items` view. Prevent an entire class of future analytics bugs. One migration, one line. Then update `analytics_service.py` to reference it.

### Build next (within 2 weeks)

4. **SO-2** — Move `append_bill_history` to `bill_service.py`. Low urgency, medium-term maintenance value.

5. **Audit trail completeness test** — A test that creates a sale, return, and exchange and asserts that `bill_history` has exactly the right events in order. This exists implicitly in `tests/integration/test_exchanges.py` but should be more explicit.

### Defer (Phase 3 or later)

- **Batch intake mode** — useful, not urgent
- **Price suggestion** — requires 3 months of real data first
- **CV fine-tuning** — requires 500+ labeled images per category
- **SO-4 (ReturnStatus collapse)** — the dead states cause zero bugs, just confusion. Do it if doing other enum work, otherwise leave it.
- **items table splitting** — splitting CV metadata or exchange fields into a separate table is a valid long-term improvement but has zero benefit until the table performance is actually a problem. For a single thrift store with tens of thousands of items, it is not a problem.

---

## 8. The One Change That Helps Most

**Create the `organic_items` database view (SO-1).**

Here is the reasoning:

Every other red flag in this review is a bug that will manifest in an identifiable way — the ZPL label will show the wrong currency, the exchange with a reused item will fail with a constraint error, the bill_history import path will confuse a developer. These bugs announce themselves.

The analytics exclusion problem is silent. If someone queries velocity without `is_exchange_item = false`, the analytics dashboard will still render. It will show numbers. The owner will make purchasing decisions based on those numbers. The numbers will be slightly wrong in proportion to how many exchange items have been sold. Nobody will know.

A one-line SQL view costs nothing and makes the correct behavior the default behavior. Every developer who writes a new analytics query will reach for `organic_items` the same way they reach for the `items` table — and the filter is enforced without asking.

```sql
-- Add to next migration
CREATE VIEW organic_items AS
  SELECT * FROM items WHERE is_exchange_item = FALSE;
```

Then `analytics_service.py` becomes:
```python
# All trend/analytics queries: FROM organic_items
# Revenue total queries: FROM items (includes exchange items in revenue)
```

No logic changes. No behavioral changes. One fewer category of silent wrong answers.

---

## 9. What Is Actually Clean (Give Credit Where Due)

- **Auth module** — JWT + bcrypt + Redis blacklist. Clean, well-isolated, correct. The `DO NOT TOUCH` warning is appropriate.
- **Advisory lock pattern** — `pg_advisory_xact_lock` for receipt numbers and exchange refs. Correct, collision-safe under concurrency. Applied consistently in three places.
- **Queue worker with SKIP LOCKED** — Two worker instances, `FOR UPDATE SKIP LOCKED`, exponential backoff. This is production-grade.
- **Storage abstraction** — `StorageBackend` Protocol. Switching to S3 requires one config change. This was done right.
- **PII handling** — Phone masked in logs (PIILogFilter), masked in audit records, masked in staff-facing API responses, full erasure endpoint. Thorough.
- **Pydantic schema discipline** — Every route has proper input validation. No raw string interpolation in SQL. Validators on prices, item counts, discount amounts.
- **Soft deletes** — `deleted_at` on items. Images retained after sale. These are the right decisions for a store where physical items are the audit trail.
- **The `system_settings` approach** — Configurable window days, exchange fees, tax rates without code deploys. This is the right pattern for store-specific settings.
- **Middleware separation** — SecurityMiddleware, LoggingMiddleware, audit middleware are cleanly separated and each has a single responsibility.
- **The `require_staff` / `require_admin` dependency pattern** — Clean, composable. Role checks are centralized. `staff` sees intake + checkout, `admin` sees analytics + destructive operations. The line is well-drawn.
