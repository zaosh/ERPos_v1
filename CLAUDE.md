# THRIFT STORE INVENTORY SYSTEM — CLAUDE CODE MASTER CONTEXT

> **Last updated:** auto-update this date whenever a significant change is made
> **Version:** 1.0.0
> **Status:** Active Development

---

## CRITICAL RULES — READ FIRST, ALWAYS

1. **Never hardcode secrets.** All secrets come from `.env` via `python-dotenv`. If you see a secret hardcoded, stop and fix it.
2. **Never modify `auth.py` or `middleware/security.py` without being explicitly told to.** These are security-critical.
3. **Never run `alembic downgrade` in production context.** Always check which environment you're in.
4. **Every DB schema change requires an Alembic migration.** No raw `ALTER TABLE` ever.
5. **Every new API endpoint must have:** authentication check, input validation (Pydantic), error handling, and a test.
6. **Before any large refactor**, read `docs/architecture.md` first.
7. **When uncertain about a decision**, use Opus model to plan (`claude --model claude-opus-4-5`) before implementing.
8. **CV confidence below 0.4** = always flag `needs_review: true`. Never silently fail.
9. **Images are evidence.** Never delete item images even after sale. Archive only.
10. **Test before commit.** Run `make test` before marking anything done.

---

## PROJECT OVERVIEW

A production-grade inventory and analytics system for a physical thrift store.

**Core purpose:**
- Fast intake: place shirt → camera captures → CV pre-fills fields → human confirms → barcode prints
- Digital twin: every physical item has a database record + image
- Analytics: trend data on what sells, what sits, pricing signals
- POS checkout: scan barcode → add to cart → complete sale → item marked sold

**Business context:**
- Store is already operating and profitable
- System is an optimization layer, not a replacement for staff judgment
- Speed at intake is critical (target: <10 sec/item)
- Analytics are the long-term value — data quality at entry = query quality later

---

## TECH STACK

| Layer | Technology | Version | Notes |
|---|---|---|---|
| Backend framework | FastAPI | 0.111+ | Async, fast, typed |
| Database | PostgreSQL | 16 | Primary data store |
| ORM | SQLAlchemy 2.0 | async mode | Use `AsyncSession` everywhere |
| Migrations | Alembic | latest | Every schema change needs one |
| Auth | JWT (python-jose) + bcrypt | - | 8h token expiry (1 shift) |
| CV - Classification | CLIP (openai/clip-vit-base-patch32) | - | No training needed |
| CV - Color | K-means via scikit-learn | - | k=3, map to named colors |
| Image handling | Pillow | - | Resize, crop, save |
| Barcode | python-barcode + qrcode | - | Code128 for items |
| Thermal printer | ZPL via raw socket | - | Zebra-compatible |
| Task queue | Redis + ARQ | - | Async background tasks |
| Cache | Redis | 7+ | Session cache, rate limiting |
| Frontend | React 18 + Vite | - | TypeScript |
| UI components | shadcn/ui + Tailwind | - | Clean, fast |
| State management | Zustand | - | Lightweight |
| HTTP client | React Query (TanStack) | - | Caching + sync |
| Testing (backend) | pytest + pytest-asyncio | - | All async |
| Testing (frontend) | Vitest + Testing Library | - | Component + integration |
| Linting | ruff (backend), ESLint (frontend) | - | Strict mode |
| Container | Docker + Docker Compose | - | Dev and prod parity |
| Reverse proxy | Nginx | - | SSL termination, static files |

---

## DIRECTORY STRUCTURE

```
thrift-store/
├── CLAUDE.md                    ← YOU ARE HERE — always read this first
├── PLANNING.md                  ← Architecture decisions and open questions
├── CHANGELOG.md                 ← What changed and when
├── Makefile                     ← All common commands
├── docker-compose.yml           ← Full stack local dev
├── docker-compose.prod.yml      ← Production overrides
├── .env.example                 ← Template — never commit .env
│
├── backend/
│   ├── main.py                  ← FastAPI app init, middleware registration
│   ├── config.py                ← Settings via pydantic-settings
│   ├── database.py              ← AsyncEngine, AsyncSession, get_db dependency
│   ├── auth.py                  ← JWT create/verify, password hash — DO NOT TOUCH
│   ├── dependencies.py          ← FastAPI dependency injection (current_user etc)
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py              ← SQLAlchemy Base, TimestampMixin
│   │   ├── user.py              ← User model
│   │   ├── item.py              ← Item model (core)
│   │   ├── sale.py              ← Sale + SaleItem models
│   │   └── audit.py             ← AuditLog model
│   │
│   ├── schemas/                 ← Pydantic models (request/response)
│   │   ├── item.py
│   │   ├── sale.py
│   │   ├── user.py
│   │   └── analytics.py
│   │
│   ├── routes/
│   │   ├── auth.py              ← /auth/login, /auth/refresh
│   │   ├── items.py             ← /items/* (intake, update, query)
│   │   ├── sales.py             ← /sales/* (checkout, history)
│   │   ├── analytics.py         ← /analytics/* (dashboard queries)
│   │   └── health.py            ← /health (no auth — uptime check)
│   │
│   ├── services/
│   │   ├── cv_service.py        ← CLIP + K-means — image analysis
│   │   ├── barcode_service.py   ← Generate Code128 barcodes
│   │   ├── printer_service.py   ← ZPL label printing
│   │   ├── image_service.py     ← Save, resize, archive images
│   │   └── analytics_service.py ← Complex query logic
│   │
│   ├── middleware/
│   │   ├── security.py          ← Rate limiting, CORS, headers — DO NOT TOUCH
│   │   ├── logging.py           ← Request/response structured logging
│   │   └── audit.py             ← Write audit log entries
│   │
│   └── migrations/
│       ├── env.py               ← Alembic config
│       └── versions/            ← Migration files (auto-named)
│
├── tests/
│   ├── conftest.py              ← Fixtures: test DB, test client, mock user
│   ├── unit/
│   │   ├── test_cv_service.py
│   │   ├── test_barcode_service.py
│   │   ├── test_auth.py
│   │   └── test_analytics.py
│   ├── integration/
│   │   ├── test_intake_flow.py  ← Full intake: image → DB → barcode
│   │   ├── test_checkout_flow.py
│   │   └── test_analytics_queries.py
│   └── e2e/
│       └── test_full_workflow.py
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Intake.tsx       ← Camera + CV + confirm form
│   │   │   ├── Checkout.tsx     ← POS / barcode scan + cart
│   │   │   ├── Analytics.tsx    ← Dashboard
│   │   │   ├── Inventory.tsx    ← Browse + search all items
│   │   │   └── Login.tsx
│   │   ├── components/
│   │   │   ├── Camera.tsx       ← Webcam capture component
│   │   │   ├── CVResultCard.tsx ← Show CV suggestions + edit fields
│   │   │   ├── BarcodeScanner.tsx
│   │   │   ├── Cart.tsx
│   │   │   └── charts/          ← Analytics chart components
│   │   ├── hooks/
│   │   │   ├── useCamera.ts
│   │   │   ├── useAuth.ts
│   │   │   └── useAnalytics.ts
│   │   ├── store/
│   │   │   └── authStore.ts     ← Zustand auth state
│   │   └── utils/
│   │       ├── api.ts           ← Axios instance with JWT interceptor
│   │       └── constants.ts
│   └── tests/
│       ├── Intake.test.tsx
│       └── Checkout.test.tsx
│
├── scripts/
│   ├── setup_dev.sh             ← First-time dev setup
│   ├── seed_db.py               ← Insert test data
│   ├── backup_db.sh             ← pg_dump to /backups
│   └── health_check.sh          ← Ping all services
│
├── docs/
│   ├── architecture.md          ← System design decisions
│   ├── cv_pipeline.md           ← How CV works, accuracy notes
│   ├── api_reference.md         ← All endpoints documented
│   ├── deployment.md            ← How to deploy / update prod
│   └── runbooks/
│       ├── printer_issues.md
│       └── db_recovery.md
│
└── infra/
    ├── nginx.conf
    ├── Dockerfile.backend
    ├── Dockerfile.frontend
    └── postgres/
        └── init.sql             ← DB user setup, extensions
```

---

## DATABASE SCHEMA

### Core Design Principles
- All tables have `created_at` / `updated_at` via `TimestampMixin`
- Soft deletes via `deleted_at` — never hard delete item records
- `audit_log` captures every write operation with user + before/after
- Use `ENUM` types in Postgres for constrained fields (not just varchar)
- All monetary values stored as `NUMERIC(10,2)` — never float

### Items Table
```sql
CREATE TABLE items (
    id              SERIAL PRIMARY KEY,
    barcode         VARCHAR(20) UNIQUE NOT NULL,
    category        item_category NOT NULL,        -- ENUM: tshirt/pants/jacket/etc
    color           VARCHAR(30),
    secondary_color VARCHAR(30),
    type            item_type NOT NULL,             -- ENUM: plain/graphic/patterned/striped
    label           VARCHAR(100),                  -- band name, anime, brand, etc
    size            VARCHAR(10),
    condition       item_condition NOT NULL,        -- ENUM: excellent/good/fair/worn
    price           NUMERIC(10,2) NOT NULL,
    cv_confidence   FLOAT,
    cv_raw_output   JSONB,                         -- full CV response stored for debugging
    image_path      VARCHAR(500),
    image_thumb_path VARCHAR(500),
    status          item_status DEFAULT 'in_stock', -- ENUM: in_stock/sold/reserved/archived
    notes           TEXT,
    created_by      INTEGER REFERENCES users(id),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    sold_at         TIMESTAMP WITH TIME ZONE,
    deleted_at      TIMESTAMP WITH TIME ZONE      -- soft delete
);

CREATE INDEX idx_items_status ON items(status);
CREATE INDEX idx_items_category_color ON items(category, color);
CREATE INDEX idx_items_label ON items(label);
CREATE INDEX idx_items_created_at ON items(created_at);
CREATE INDEX idx_items_sold_at ON items(sold_at);
```

### Sales Tables
```sql
CREATE TABLE sales (
    id           SERIAL PRIMARY KEY,
    sale_ref     VARCHAR(20) UNIQUE NOT NULL,      -- human-readable: SALE-20240115-001
    total_amount NUMERIC(10,2) NOT NULL,
    discount     NUMERIC(10,2) DEFAULT 0,
    payment_type payment_type NOT NULL,             -- ENUM: cash/card/other
    cashier_id   INTEGER REFERENCES users(id),
    notes        TEXT,
    created_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    voided_at    TIMESTAMP WITH TIME ZONE,          -- if sale was voided
    voided_by    INTEGER REFERENCES users(id)
);

CREATE TABLE sale_items (
    id        SERIAL PRIMARY KEY,
    sale_id   INTEGER REFERENCES sales(id) ON DELETE RESTRICT,
    item_id   INTEGER REFERENCES items(id) ON DELETE RESTRICT,
    price     NUMERIC(10,2) NOT NULL               -- price at time of sale
);
```

### Audit Log
```sql
CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    table_name  VARCHAR(50) NOT NULL,
    record_id   INTEGER NOT NULL,
    action      VARCHAR(10) NOT NULL,               -- INSERT/UPDATE/DELETE
    old_values  JSONB,
    new_values  JSONB,
    user_id     INTEGER REFERENCES users(id),
    ip_address  INET,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_audit_table_record ON audit_log(table_name, record_id);
```

---

## API CONTRACTS

### Authentication
```
POST /auth/login
  Body: { username, password }
  Returns: { access_token, token_type, expires_in, user: { id, role } }

POST /auth/refresh
  Header: Authorization: Bearer <token>
  Returns: { access_token, expires_in }
```

### Intake Flow
```
POST /items/capture
  Multipart: image file
  Returns: { cv_result: { color, type, label, confidence, needs_review }, temp_image_id }

POST /items/
  Body: { temp_image_id, category, color, type, label, size, condition, price, notes? }
  Returns: { item_id, barcode, label_zpl }

GET /items/{id}
  Returns: full item record + image URL

PATCH /items/{id}
  Body: any editable fields
  Returns: updated item
```

### Checkout
```
POST /sales/
  Body: { items: [{ barcode }], payment_type, discount? }
  Returns: { sale_id, sale_ref, total, items: [...] }

GET /sales/{id}
  Returns: full sale record

POST /sales/{id}/void
  Admin only. Body: { reason }
```

### Analytics
```
GET /analytics/summary
  Query: ?period=7d|30d|90d
  Returns: { total_items, sold, revenue, avg_price, top_labels }

GET /analytics/trends
  Query: ?group_by=label|color|category&period=30d
  Returns: time-series data for charts

GET /analytics/dead_stock
  Query: ?days=21
  Returns: items unsold for N days

GET /analytics/velocity
  Returns: avg days-to-sell by category/condition
```

---

## CV PIPELINE DETAILS

See `docs/cv_pipeline.md` for full details.

**Quick reference:**
- Model: `openai/clip-vit-base-patch32` (loads once at startup)
- Color: K-means k=3 on resized (100x100) masked image
- Confidence threshold: 0.4 → below = `needs_review: true`
- Processing target: <800ms per image
- Raw output always stored in `cv_raw_output` JSONB column for debugging

**Category prompts (update in `cv_service.py`):**
```python
PROMPTS = [
    "a band or music graphic t-shirt",
    "an anime or manga graphic t-shirt",
    "a sports team t-shirt",
    "a plain solid color t-shirt",
    "a vintage or retro graphic t-shirt",
    "a holiday or novelty t-shirt",
    "a branded or logo t-shirt",
]
```

---

## SECURITY REQUIREMENTS

- JWT secret: minimum 64 chars, stored in `.env` only
- Tokens expire: 8 hours (configurable via `ACCESS_TOKEN_EXPIRE_HOURS`)
- Password hashing: bcrypt with cost factor 12
- Rate limiting: 5 login attempts per IP per 15 minutes (Redis)
- CORS: explicit allowed origins only, no wildcard in production
- File uploads: validate mimetype + magic bytes, max 10MB, store outside webroot
- SQL: SQLAlchemy ORM only — no raw string interpolation ever
- Logs: never log passwords, tokens, or full credit card numbers
- Staff role: intake + checkout only
- Admin role: analytics, void sales, edit items, manage users
- Superadmin role: system config, user management

---

## ENVIRONMENT VARIABLES

```bash
# .env.example — copy to .env and fill in

# App
APP_ENV=development                   # development | production
SECRET_KEY=<64+ char random string>   # generate: openssl rand -hex 32
ACCESS_TOKEN_EXPIRE_HOURS=8

# Database
DATABASE_URL=postgresql+asyncpg://thrift_user:password@localhost:5432/thrift_store
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40

# Redis
REDIS_URL=redis://localhost:6379/0

# Storage
IMAGE_STORAGE_PATH=/data/images        # absolute path, outside webroot
IMAGE_BASE_URL=http://localhost:8000/images

# CV
CV_MODEL=openai/clip-vit-base-patch32
CV_CONFIDENCE_THRESHOLD=0.4
CV_PROCESSING_TIMEOUT=5.0

# Printer
PRINTER_HOST=192.168.1.100
PRINTER_PORT=9100
PRINTER_TIMEOUT=3.0
LABEL_WIDTH_MM=57
LABEL_HEIGHT_MM=32

# Frontend (Vite)
VITE_API_URL=http://localhost:8000
VITE_APP_NAME=ThriftOS
```

---

## COMMON COMMANDS

```bash
# Development
make dev              # Start full stack (docker-compose up)
make backend          # Start backend only
make frontend         # Start frontend only

# Database
make migrate          # Run pending migrations (alembic upgrade head)
make migrate-create msg="add condition field"  # New migration
make seed             # Seed test data
make db-reset         # Drop + recreate + seed (dev only)

# Testing
make test             # All tests
make test-unit        # Unit tests only
make test-integration # Integration tests (needs running DB)
make test-cov         # With coverage report

# Code quality
make lint             # ruff + ESLint
make format           # ruff format + prettier
make typecheck        # mypy + tsc

# Production
make build            # Build Docker images
make deploy           # Deploy to production
make backup           # Database backup
make logs             # Tail all service logs
```

---

## TESTING REQUIREMENTS

**Every feature needs:**
1. Unit test for service logic (mock DB)
2. Integration test for API endpoint (real test DB)
3. Edge cases: empty input, invalid data, auth failure, CV failure

**Test DB:** Separate PostgreSQL database `thrift_store_test`
- Recreated fresh for each test session via `conftest.py`
- Use `pytest-asyncio` for all async tests
- Use `httpx.AsyncClient` for API tests

**Coverage requirement:** 80% minimum. Check with `make test-cov`.

---

## KNOWN CONSTRAINTS & DECISIONS

| Decision | Reason |
|---|---|
| PostgreSQL over SQLite/MySQL | JSONB for CV output, native ENUMs, best analytics queries, production grade |
| Async SQLAlchemy | FastAPI is async — sync ORM causes connection pool issues under load |
| CLIP over Google Vision API | No per-call cost, runs locally, no internet dependency in-store |
| Redis for rate limiting | PostgreSQL-based rate limiting is slow and pollutes the DB |
| ZPL for labels | Industry standard for thermal printers, works with all Zebra-compatible printers |
| Soft deletes | Items are physical evidence — never lose the record |
| JSONB for cv_raw_output | Allows debugging CV issues without schema changes |
| JWT over sessions | Stateless — works if Redis goes down, simpler horizontal scaling |

---

## OPEN QUESTIONS / TODO

Track these in `PLANNING.md`. When resolved, move to CHANGELOG.md.

- [ ] Batch intake mode (multiple shirts queued)
- [ ] Cloud sync / backup strategy
- [ ] Mobile app for floor staff to look up items by barcode
- [ ] Supplier/wholesale intake tracking
- [ ] Price suggestion based on historical sale velocity
- [ ] Dead stock discount automation

---

## WHEN TO USE OPUS FOR PLANNING

Before implementing any of these, run `claude --model claude-opus-4-5` and ask for a plan:
- New database table or schema change
- New service with external dependency
- Security-related changes
- Performance optimization
- Anything touching auth or middleware
- Refactoring that touches >5 files

Use Sonnet for implementation once the plan is approved.

---

## UPDATE LOG

When you make changes, append to this section:

```
[DATE] - [WHAT CHANGED] - [WHO/WHY]
```
