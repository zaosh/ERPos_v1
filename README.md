# ERPos

Inventory and point-of-sale system for a physical thrift store. Computer-vision intake, barcode printing, POS checkout, customer management, returns, and analytics. All currency in INR.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + SQLAlchemy 2.0 async + asyncpg |
| Database | PostgreSQL 16 — JSONB, native ENUMs, SKIP LOCKED |
| Auth | JWT 8h + bcrypt cost-12 + Redis rate limiting |
| CV — Color | K-means clustering (local, ~50ms) |
| CV — Type | GPT-4o-mini via OpenAI (background job, Phase A) |
| CV — Deep | GPT-4o (Phase B, nightly on sold items) |
| CV — Fashion | FashionCLIP via HuggingFace Inference API |
| Job Queue | PostgreSQL `job_queue` + 2 async workers (SKIP LOCKED) |
| Printer | ZPL over TCP socket — Zebra-compatible |
| Cache | Redis 7 — rate limiting, barcode sequence, image TTL |
| Frontend | React 18 + TypeScript + Vite + TanStack Query v5 |
| Styling | Inline styles, dark terminal theme (`IBM Plex Sans/Mono`) |
| Infra | Docker Compose + Nginx |

---

## Features

### Intake
- Webcam capture with motion detection (auto-fires when garment is still)
- K-means color detection runs instantly on capture (~50ms, local)
- GPT-4o-mini fills item type in the background (Phase A job)
- Manual form: category, color, size, condition, price (INR)
- Bulk intake mode — queue multiple items, confirm all at end
- Barcode label prints automatically on confirm (ZPL → Zebra printer)
- Queue retries print if printer offline (exponential backoff)
- CV confidence shown; items below 0.4 confidence flagged `needs_review`

### Checkout (POS)
- Scan or type barcode → items added to cart
- Thermal receipt (off-white paper, perforated edges, IBM Plex Mono) rendered live as items are added
- Customer lookup by phone — auto-fills name, shows returning customer badge on receipt
- Discount: flat ₹ or % with quick chips (10 / 15 / 20%)
- Payment: Cash / Card / Other
- Cash tendered: quick-amount buttons (₹100 / ₹500 / ₹1000 / ₹2000) with change-due callout
- Price override — click any price on the live receipt to edit inline
- Keyboard shortcuts: `F2` customer · `F3` discount · `F12` complete · `Backspace` remove last · `Esc` void
- Sale complete screen: receipt fetched from DB, print button, "Another for [customer]" shortcut
- Customer auto-created in DB if name + phone provided and not already linked

### Sales History & Returns (`/sales`)
- Search by `SALE-YYYYMMDD-NNN` or `RCP-YYYYMMDD-NNNN`
- Renders receipt in the same thermal-paper format as live checkout
- Days-since-purchase banner: green (within window) / amber (≤3 days left) / red (expired)
- Return flow (admin only):
  - Checklist of returnable items — already-returned items struck through and disabled
  - Reason text, refund method (Cash / Card / Store Credit)
  - Resellable toggle: `ON` → item returns to `in_stock` at original barcode; `OFF` → archived
  - Backend enforces `return_window_days` from `system_settings`
  - Duplicate return prevented by `uq_return_items_item_id` constraint

### Inventory
- Grid (card) and table views
- Filter by status, category; search by label or barcode (searches both fields)
- Quick inline status change per item
- `↩ returned` badge on items that have ever been through a return
- Image thumbnails in grid view

### Analytics (admin)
- Today's revenue hero strip with 7-day sparkline
- Revenue / sold count / avg price stat cards (configurable period: 7d / 30d / 90d)
- Sales trend line chart grouped by label, color, or category
- Category sell-through heatmap
- Dead stock alerts — items unsold for N days
- Avg days-to-sell by category and condition
- CV model performance: overall accuracy, needs-review %, per-type breakdown, top mistakes
- Admin job queue monitor — see pending / failed jobs, retry from UI

### Customers
- Created at checkout (name + phone) or via `/customers/` API
- Phone-based lookup (debounced, 7+ digits) with returning-customer detection
- `total_purchases` tracked per customer
- Linked to sales and returns by `customer_uid`
- GDPR erase support (`gdpr_erased_at`)

### System
- `system_settings` table — store name, receipt footer, return window, tax rate, all runtime-editable
- Audit log on every write: table, record, action, old values, new values, user, IP
- Soft deletes on items (`deleted_at`) — never lose a record
- All monetary values: `NUMERIC(10,2)`, never float
- All images archived permanently even after sale

---

## API routes

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/login` | — | Get JWT |
| POST | `/auth/refresh` | staff | Refresh token |
| POST | `/items/capture` | staff | Upload image → CV → temp_image_id |
| POST | `/items/` | staff | Confirm item, print label |
| GET | `/items/` | staff | List/search items (`status`, `category`, `search`) |
| PATCH | `/items/{barcode}` | staff | Update item fields |
| POST | `/sales/` | staff | Create sale (checkout) |
| GET | `/sales/` | admin | List sales (`sale_ref`, `receipt_number` filters) |
| GET | `/sales/{sale_ref}/receipt` | staff | Full receipt with line items |
| GET | `/sales/by-receipt/{receipt_number}` | staff | Receipt lookup by RCP number |
| POST | `/sales/{sale_id}/void` | admin | Void sale, restore items |
| POST | `/returns/` | admin | Process return |
| GET | `/returns/{return_ref}` | staff | Return details |
| GET | `/customers/lookup` | staff | Phone lookup |
| POST | `/customers/` | staff | Create customer |
| GET | `/analytics/summary` | admin | Revenue, stock, CV stats |
| GET | `/analytics/trends` | admin | Time-series by group |
| GET | `/analytics/dead_stock` | admin | Items unsold N+ days |
| GET | `/analytics/velocity` | admin | Avg days-to-sell |
| GET | `/jobs/` | admin | Job queue list |
| POST | `/jobs/{id}/retry` | admin | Retry failed job |
| GET | `/health` | — | Uptime check |

---

## Data model

```
users
items          ← barcode, category, color, type, label, size, condition, price, status, image_path, cv_raw_output (JSONB)
  └─ sale_items  ← sale_id, item_id, price (at time of sale)
sales          ← sale_ref, receipt_number, customer_id, subtotal, discount_amount, tax_rate, tax_amount, total_amount, payment_type
customers      ← customer_uid, first_name, last_name, phone, total_purchases
returns        ← return_ref, original_sale_id, customer_id, return_reason, refund_method, refund_amount, status
  └─ return_items ← return_id, item_id, original_price, refund_price (item_id unique — one return per item)
job_queue      ← type, status, payload, attempts, next_retry_at
audit_log      ← table_name, record_id, action, old_values, new_values, user_id, ip_address
system_settings ← key/value pairs (store_name="qstar", tax_rate, return_window_days, receipt_footer)
```

---

## Project layout

```
erpos/
├── backend/
│   ├── main.py                  FastAPI app init, middleware registration
│   ├── config.py                Settings via pydantic-settings + .env
│   ├── auth.py                  JWT create/verify, bcrypt — do not modify
│   ├── dependencies.py          FastAPI DI: current_user, require_staff, require_admin
│   ├── models/
│   │   ├── item.py              Item + enums (ItemCategory, ItemCondition, ItemStatus, ItemType)
│   │   ├── sale.py              Sale, SaleItem, PaymentType
│   │   ├── customer.py          Customer
│   │   ├── return_.py           Return, ReturnItem, RefundMethod, ReturnStatus
│   │   ├── job_queue.py         JobQueue, JobType, JobStatus
│   │   ├── user.py              User, Role
│   │   ├── audit.py             AuditLog
│   │   └── system_settings.py   SystemSettings
│   ├── schemas/                 Pydantic request/response models (mirrors models/)
│   ├── routes/
│   │   ├── items.py             Capture, confirm, list, patch
│   │   ├── sales.py             Checkout, receipt, void, list, by-receipt
│   │   ├── returns.py           Create return, get return
│   │   ├── customers.py         Lookup, create
│   │   ├── analytics.py         Summary, trends, dead stock, velocity, CV perf
│   │   ├── jobs.py              Queue monitor, retry
│   │   ├── auth.py              Login, refresh
│   │   └── health.py            /health
│   ├── services/
│   │   ├── cv_service.py        K-means color + GPT calls + FashionCLIP
│   │   ├── queue_service.py     Enqueue, poll, complete, fail, retry
│   │   ├── queue_worker.py      Standalone worker process (run 2 instances)
│   │   ├── printer_service.py   ZPL generation + TCP send
│   │   ├── barcode_service.py   Code128 barcode image generation
│   │   ├── receipt_service.py   next_receipt_number() with advisory lock
│   │   ├── customer_service.py  Phone normalisation, lookup/create
│   │   ├── image_service.py     Temp image lifecycle, thumbnail, URL
│   │   ├── settings_service.py  get/set system_settings key-value
│   │   ├── storage_service.py   File storage paths
│   │   └── analytics_service.py Complex query logic
│   ├── middleware/
│   │   ├── security.py          Rate limiting, CORS, headers — do not modify
│   │   ├── logging.py           Structured request/response logging
│   │   └── audit.py             write_audit_log()
│   └── migrations/versions/     001 → 006 (Alembic)
│
├── frontend/src/
│   ├── pages/
│   │   ├── Intake.tsx           Camera + CV + confirm form
│   │   ├── Checkout.tsx         POS — live receipt, cart, payment
│   │   ├── Sales.tsx            Bill search + receipt view + returns
│   │   ├── Inventory.tsx        Browse, filter, status change
│   │   ├── Analytics.tsx        Dashboard — revenue, trends, dead stock, CV perf
│   │   └── Login.tsx
│   ├── components/
│   │   ├── ui/index.tsx         Shared primitives: Card, Btn, Badge, Spinner, etc.
│   │   ├── Camera.tsx           Webcam capture, motion detection
│   │   ├── CVResultCard.tsx     CV result display + form
│   │   ├── Cart.tsx             Legacy cart component
│   │   └── charts/              SalesTrendChart, DeadStockTable, VelocityTable, CategoryBreakdownChart
│   ├── hooks/                   useAnalytics, useCamera, useAuth
│   ├── store/authStore.ts       Zustand — JWT token + user
│   ├── utils/
│   │   ├── api.ts               Axios instance + JWT interceptor + apiErrorMessage
│   │   ├── currency.ts          money() — Intl.NumberFormat en-IN INR (single source of truth)
│   │   └── constants.ts         ITEM_CATEGORIES, ITEM_STATUSES, PAYMENT_TYPES, etc.
│   └── styles/theme.ts          Theme tokens (dark / stone / indigo) + useTheme()
│
├── scripts/
│   ├── seed_db.py               Basic test data
│   └── stress_seed.py           2-month realistic dataset (3k customers, 15k items, 6k sales). Prefix: SS-
│
├── tests/
│   ├── unit/                    cv_service, barcode, auth, billing, phone, logging PII
│   └── integration/             intake flow, checkout flow, billing, customers, returns, bulk intake
│
├── infra/                       Dockerfiles, nginx.conf, postgres/init.sql
├── docs/                        architecture.md, cv_pipeline.md, api_reference.md, deployment.md, runbooks/
├── docker-compose.yml           Dev stack
├── docker-compose.prod.yml      Prod stack (gunicorn + uvicorn workers, resource limits)
├── Makefile                     All commands
└── .env.example                 Config template
```

---

## Setup

```bash
cp .env.example .env
# Set SECRET_KEY (required): openssl rand -hex 32
# Set OPENAI_API_KEY (optional — CV type detection degrades gracefully without it)
# Set PRINTER_HOST if using a thermal printer

make dev         # starts postgres, redis, backend, frontend, nginx
make migrate     # run pending migrations
make seed        # insert basic test data
```

Default credentials after seed:

| Username | Password | Role |
|---|---|---|
| `admin` | `admin1234` | admin |
| `staff1` | `staff1234` | staff |

Stress-test data (60 days, 6k sales): `cd backend && python ../scripts/stress_seed.py`

---

## Commands

```bash
make dev                       # Full stack
make migrate                   # Alembic upgrade head
make migrate-create msg="..."  # New migration
make seed                      # Basic seed
make db-reset                  # Drop + recreate + seed (dev only)
make test                      # All backend tests
make test-cov                  # Tests + coverage (80% minimum)
make lint                      # ruff + ESLint
make typecheck                 # mypy + tsc
make build                     # Build Docker images
make deploy                    # Build + start prod stack + migrate
make backup                    # pg_dump with 30-day retention
make logs                      # Tail all service logs
```

---

## Roles

| Role | Access |
|---|---|
| `staff` | Intake, Checkout, Sales history, Inventory |
| `admin` | All above + Analytics, Returns, Void sales, Job queue |
| `superadmin` | All above + User management, system config |

---

## Key constraints

- Barcodes are permanent — items soft-deleted via `deleted_at`, never hard-deleted
- Images are permanent — archived even after sale
- Monetary values: `NUMERIC(10,2)` everywhere, never `float`
- An item can only appear in one `return_items` record (`uq_return_items_item_id`)
- `auth.py` and `middleware/security.py` — do not modify without explicit reason
- Every schema change requires an Alembic migration
- `system_settings` controls runtime config (store name, tax rate, return window)
