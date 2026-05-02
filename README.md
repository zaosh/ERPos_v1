# ThriftOS

Inventory and point-of-sale system for a physical thrift store.

**Core workflow:** place garment → camera captures → K-means color detection → confirm form → barcode prints → item in inventory. Checkout by scanning barcode. Analytics dashboard for sell-through, dead stock, and velocity.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI + SQLAlchemy 2.0 async + PostgreSQL 16 |
| CV | K-means (local) + GPT-4o-mini (type) + GPT-4o (deep analysis) + FashionCLIP |
| Queue | PostgreSQL job_queue table + 2 parallel async workers |
| Auth | JWT (8h) + bcrypt + Redis rate limiting |
| Frontend | React 18 + TypeScript + Vite + TanStack Query |
| Infra | Docker Compose + Nginx |

---

## Quick start

```bash
cp .env.example .env
# Edit .env — set SECRET_KEY, DATABASE_URL, OPENAI_API_KEY (optional)

make setup   # first-time: creates .env, installs deps, runs migrations, seeds DB
make dev     # start full stack
```

Open http://localhost — login with `admin / admin1234` (seeded).

---

## Environment variables

Copy `.env.example` to `.env`. Required fields:

| Variable | Description |
|---|---|
| `SECRET_KEY` | 64+ char random string. `openssl rand -hex 32` |
| `DATABASE_URL` | asyncpg connection string |
| `OPENAI_API_KEY` | For CV type analysis (Phase A/B). Optional — system works without it, CV returns fallback |
| `HUGGINGFACE_API_KEY` | For FashionCLIP attributes. Optional |

---

## CV pipeline

Three-phase analysis. All phases run as background jobs — intake never blocks on a CV API call.

| Phase | Model | When | What |
|---|---|---|---|
| Color | K-means (local) | At capture, ~50ms | Dominant color |
| Phase A | GPT-4o-mini | Job after item creation | Type: plain/band/graphic/anime/etc |
| Phase B | GPT-4o | Nightly on sold items | Label, era, resale interest, condition |
| Fashion | FashionCLIP/HuggingFace | Alongside Phase B | Fit, sleeve, neckline, style decade |

---

## Job queue

All CV analysis and label printing go through the `job_queue` PostgreSQL table. Two worker processes run in parallel with `SELECT FOR UPDATE SKIP LOCKED` to prevent conflicts. Failed jobs retry with exponential backoff (2ⁿ × 30s, capped at 1h).

```bash
# Workers start automatically in docker-compose
# Monitor via the admin queue panel in the nav bar
```

---

## Printer

Zebra-compatible thermal printer via ZPL over TCP socket. Set `PRINTER_HOST` and `PRINTER_PORT` in `.env`. When offline, the print job is retried automatically by the queue worker. Reprint any item via the Inventory page.

---

## Commands

```bash
make dev              # Start full stack
make test             # Backend tests
make test-frontend    # Frontend tests
make migrate          # Run pending Alembic migrations
make migrate-create msg="add column"
make seed             # Seed test data
make deploy           # Build + deploy production stack
make logs             # Tail all service logs
make backup           # pg_dump database
```

---

## Roles

| Role | Access |
|---|---|
| `staff` | Intake, Checkout, Inventory |
| `admin` | All above + Analytics, Queue monitor, Void sales |
| `superadmin` | All above + User management |

---

## Project structure

```
backend/
  routes/          FastAPI route handlers
  services/        Business logic (cv, queue, printer, barcode, image)
  models/          SQLAlchemy models
  schemas/         Pydantic request/response schemas
  migrations/      Alembic migration files

frontend/src/
  pages/           Intake, Checkout, Inventory, Analytics, Login
  components/      Shared UI components
  hooks/           React Query hooks
  styles/          Theme tokens (dark terminal design)
```

---

## Production deploy

```bash
cp .env.example .env.prod
# fill in production values

make deploy   # builds images, starts docker-compose.prod.yml, runs migrations
```

See `docs/deployment.md` for full production checklist.
