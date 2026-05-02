# ThriftOS

A production inventory and point-of-sale system built for a physical thrift store. Fast item intake with computer vision, barcode printing, POS checkout, and a full analytics dashboard.

![Stack](https://img.shields.io/badge/backend-FastAPI-009688?style=flat-square) ![Stack](https://img.shields.io/badge/frontend-React%2018-61dafb?style=flat-square) ![Stack](https://img.shields.io/badge/database-PostgreSQL%2016-336791?style=flat-square) ![Stack](https://img.shields.io/badge/queue-PostgreSQL%20workers-336791?style=flat-square)

---

## What it does

**Intake** — place a shirt in front of a webcam, click capture (or let auto-mode fire when the garment stops moving). K-means color detection runs instantly in the backend. GPT-4o-mini analyzes the type in the background. You fill in size, price, condition — click confirm — barcode label prints on the Zebra printer. Under 10 seconds per item.

**Checkout** — scan or type a barcode. Items go into a cart. Set payment type, apply a discount, complete sale. Items marked sold instantly.

**Inventory** — browse and filter everything in stock. Change status directly from the grid or table view.

**Analytics** — sell-through rates by label, revenue trends, dead stock alerts, avg days to sell by category, CV model performance over time.

**Job Queue** — every CV analysis and print job is managed. If the printer is offline it retries automatically with exponential backoff. You can see the queue state and retry failed jobs from the admin panel in the nav bar.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + SQLAlchemy 2.0 async + asyncpg |
| Database | PostgreSQL 16 (JSONB, native ENUMs, SKIP LOCKED) |
| Auth | JWT 8h + bcrypt cost 12 + Redis rate limiting |
| CV — Color | K-means clustering (local, ~50ms, no API cost) |
| CV — Type | GPT-4o-mini via OpenAI API (Phase A, background job) |
| CV — Deep | GPT-4o (Phase B, runs nightly on sold items) |
| CV — Fashion | FashionCLIP via HuggingFace Inference API |
| Job Queue | PostgreSQL `job_queue` table + 2 async workers (SKIP LOCKED) |
| Printer | ZPL over TCP socket to Zebra-compatible thermal printer |
| Cache | Redis 7 (rate limiting, barcode sequence, temp image TTL) |
| Frontend | React 18 + TypeScript + Vite + TanStack Query v5 |
| Styling | Inline styles + dark terminal theme (no Tailwind in pages) |
| Infra | Docker Compose + Nginx reverse proxy |

---

## Getting started

### Prerequisites

- Docker + Docker Compose
- Node 18+ (for local frontend dev only)
- Python 3.11+ (for local backend dev only)

### First run

```bash
git clone https://github.com/zaosh/thrift.git
cd thrift

cp .env.example .env
# Open .env and set SECRET_KEY (required) and optionally OPENAI_API_KEY
```

Generate a secret key:

```bash
openssl rand -hex 32
```

Start everything:

```bash
make dev
```

Open **http://localhost** — the full app is behind Nginx.

Default credentials (seeded):

| Username | Password | Role |
|---|---|---|
| `admin` | `admin1234` | admin |
| `staff1` | `staff1234` | staff |

---

## Environment variables

Copy `.env.example` to `.env`. The only required variable is `SECRET_KEY`. Everything else has a working default for local development.

```bash
# Required
SECRET_KEY=<64+ char random string>   # openssl rand -hex 32

# Database (default works with docker-compose)
DATABASE_URL=postgresql+asyncpg://thrift_user:thrift_pass@localhost:5432/thrift_store

# CV — optional. System works without these; CV returns sensible fallbacks.
OPENAI_API_KEY=         # enables GPT-4o-mini type detection and GPT-4o deep analysis
HUGGINGFACE_API_KEY=    # enables FashionCLIP garment attribute extraction

# Printer
PRINTER_HOST=192.168.1.100   # IP of your Zebra-compatible thermal printer
PRINTER_PORT=9100
```

Full reference in `.env.example`.

---

## CV pipeline

Three phases. The intake flow never blocks on an API call — everything after the initial color detection runs as a background job.

```
Capture image
    │
    ├─ detect_color()        K-means, local, ~50ms → pre-fills color field
    │
    └─ [item saved to DB]
           │
           ├─ cv_phase_a job  GPT-4o-mini → fills item.type within seconds
           │
           └─ [item sold]
                  │
                  ├─ cv_phase_b job   GPT-4o → label, era, resale interest, condition notes
                  └─ fashion job      FashionCLIP → fit, sleeve, neckline, style, decade
```

All results land in `cv_raw_output` JSONB on the item. Phase B and fashion jobs run nightly on sold items — they're enrichment data for analytics, not required for operations.

---

## Job queue

All CV and print operations go through a PostgreSQL `job_queue` table. Two worker processes run in parallel.

```
job_queue table
├── priority 1: cv_phase_a, print_label  (intake — run immediately)
├── priority 2: print_retry              (reprint requests)
└── priority 8: cv_phase_b, fashion      (nightly enrichment)
```

Workers use `SELECT FOR UPDATE SKIP LOCKED` — they never step on each other. Failed jobs retry with exponential backoff (`2ⁿ × 30s`, capped at 1 hour). After `max_attempts`, a job is marked failed and visible in the admin queue panel.

Admins can see the queue state and manually retry failed jobs from the nav bar without touching the terminal.

---

## Printer setup

Any Zebra-compatible thermal printer (ZPL over raw TCP). Labels include a Code128 barcode, item description, price, and intake date.

1. Set `PRINTER_HOST` and `PRINTER_PORT` in `.env`
2. Make sure the printer is on the same network
3. Labels print automatically on item creation. If the printer is offline, the queue retries it.
4. Reprint any item from the Inventory page.

Tested with Zebra ZD420 and ZD220 on 57×32mm labels.

---

## Roles

| Role | Can do |
|---|---|
| `staff` | Intake, Checkout, Inventory |
| `admin` | All above + Analytics, Queue monitor, Void sales |
| `superadmin` | All above + User management, system config |

---

## Commands

```bash
# Development
make dev                          # Start full stack (postgres, redis, backend, frontend, nginx)
make backend                      # Backend only on :8000
make frontend                     # Frontend dev server on :5173

# Database
make migrate                      # Run pending Alembic migrations
make migrate-create msg="..."     # Generate new migration
make seed                         # Insert realistic test data (90 days of history)
make db-reset                     # Drop + recreate + seed (dev only)

# Testing
make test                         # All backend tests
make test-unit                    # Unit tests only
make test-integration             # Integration tests (needs running DB)
make test-cov                     # Tests + coverage report (80% minimum)
make test-frontend                # Frontend Vitest tests

# Code quality
make lint                         # ruff + ESLint
make format                       # ruff format + prettier
make typecheck                    # mypy + tsc

# Production
make deploy                       # Build images + start docker-compose.prod.yml + migrate
make backup                       # pg_dump to /backups with 30-day retention
make logs                         # Tail all service logs
make health                       # Ping all services
```

---

## Project layout

```
thrift/
├── backend/
│   ├── routes/          # FastAPI route handlers (items, sales, analytics, jobs, auth)
│   ├── services/
│   │   ├── cv_service.py        # K-means color + GPT-4o-mini/4o + FashionCLIP
│   │   ├── queue_service.py     # Enqueue, poll, complete, fail, retry
│   │   ├── queue_worker.py      # Standalone worker process (run 2 in docker-compose)
│   │   ├── printer_service.py   # ZPL generation + TCP socket send
│   │   ├── barcode_service.py   # THR-YYYYMMDD-NNNNN via Redis INCR
│   │   └── image_service.py     # Temp image lifecycle, thumbnail, URL
│   ├── models/          # SQLAlchemy models (Item, Sale, JobQueue, AuditLog, User)
│   ├── schemas/         # Pydantic request/response models
│   ├── middleware/       # Auth, rate limiting, CORS, structured logging, audit log
│   └── migrations/      # Alembic migrations (001–004)
│
├── frontend/src/
│   ├── pages/           # Intake, Checkout, Inventory, Analytics, Login
│   ├── components/      # Camera, Cart, CVResultCard, BarcodeScanner, UI primitives
│   ├── hooks/           # useAnalytics, useCamera, useAuth, useQueueSummary
│   └── styles/          # Dark terminal theme tokens
│
├── tests/
│   ├── unit/            # cv_service, queue_service, barcode, auth, analytics
│   └── integration/     # Full intake flow, checkout, analytics queries
│
├── infra/               # Dockerfiles, nginx configs, postgres init.sql
├── scripts/             # setup_dev.sh, seed_db.py, backup_db.sh, health_check.sh
├── docs/                # Architecture, CV pipeline, API reference, deployment, runbooks
├── docker-compose.yml       # Development stack
└── docker-compose.prod.yml  # Production stack (gunicorn workers, resource limits)
```

---

## Production deploy

```bash
cp .env.example .env.prod
# Set APP_ENV=production, strong SECRET_KEY, real DB credentials, API keys

make deploy
```

The production stack uses gunicorn + uvicorn workers for the API, serves the frontend as a static Nginx build, and keeps all internal ports off the host except 80/443. See `docs/deployment.md` for the full checklist.

---

## Data model highlights

- Every item has a permanent image even after sale (evidence, never deleted)
- Soft deletes via `deleted_at` — no hard deletes on item records
- All monetary values stored as `NUMERIC(10,2)` — never float
- `cv_raw_output` JSONB stores the full CV result for every phase, indexed for future fine-tuning
- `audit_log` captures every write with user, IP, old values, and new values
- `job_queue` table with `status`, `attempts`, `next_retry_at` for full job observability

---

## License

Private — not licensed for redistribution.
