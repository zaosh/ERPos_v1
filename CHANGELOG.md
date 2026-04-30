# CHANGELOG

All notable changes to ThriftOS are documented here.

---

## [Phase 1] — 2026-04-30

### Added — Backend
- FastAPI application with async SQLAlchemy 2.0 (AsyncSession throughout)
- JWT authentication (8h expiry, bcrypt cost 12, Redis logout blacklist)
- Rate limiting via Redis: 5 login attempts/15min/IP, 100 captures/min/user
- User model with roles: staff / admin / superadmin
- Item model with ENUM types: category, type, condition, status
- Sale + SaleItem models with atomic status update on checkout
- AuditLog model — every write captured with old/new values and IP
- Pydantic schemas for all request/response contracts
- Routes: /auth, /items, /sales, /analytics, /health
- CV service: CLIP (openai/clip-vit-base-patch32) + K-means color detection
- Barcode service: THR-YYYYMMDD-NNNNN format via Redis INCR (atomic, collision-safe)
- Image service: magic byte validation, resize to thumbnail, temp → final path workflow
- Printer service: ZPL label generation, graceful offline handling via Redis print queue
- Analytics service: summary, trends, dead stock, velocity queries (index-aware)
- Alembic migrations: hand-written first migration with ENUM creation order correct
- Security middleware: CORS, security headers, rate limiting
- Logging middleware: structured request/response logging

### Added — Frontend
- React 18 + Vite + TypeScript project
- Tailwind CSS + shadcn/ui component pattern
- Zustand auth store (persisted to localStorage)
- React Query for all API data fetching with stale-time caching
- Login page with error handling
- Intake page: live camera feed → capture → CV suggestions → confirm form → print
- Checkout page: barcode scanner (ZXing) + manual entry + cart + sale completion
- Analytics dashboard: summary cards, sales trend chart, label sell-through, dead stock table, velocity table
- Inventory page: filterable/paginated item list
- JWT interceptor: auto-attaches token, redirects to /login on 401
- Role-based navigation: staff sees intake/checkout/inventory; admin also sees analytics

### Added — Infrastructure
- Docker Compose: backend, frontend, PostgreSQL 16, Redis 7 (appendonly yes)
- Nginx config: reverse proxy, static image serving outside webroot
- Dockerfile.backend (multi-stage), Dockerfile.frontend (nginx)
- Named volume for CLIP model cache (avoids 350MB re-download)

### Added — Scripts & Tests
- seed_db.py: 90 days of realistic inventory + sales history
- setup_dev.sh: first-time dev environment setup
- backup_db.sh: pg_dump with 30-day retention
- health_check.sh: validates all services
- Unit tests: auth, cv_service, barcode_service, analytics
- Integration tests: intake flow, checkout flow, analytics queries
- E2E test: full intake → checkout → analytics workflow
- Frontend component tests: CVResultCard, Cart

### Architecture decisions recorded in PLANNING.md
- Temp image lifecycle: filesystem + Redis key (600s TTL), ARQ cleanup task
- Barcode format: THR-YYYYMMDD-NNNNN via Redis INCR
- Print queue: Redis list, ARQ drain every 30s, max 5 attempts
- Alembic runs in Docker CMD before uvicorn (idempotent)

---

## Unreleased / Phase 2 candidates

- Batch intake mode (multiple items queued)
- Price suggestion from historical velocity
- Mobile floor app for barcode lookup
- Cloud sync / backup strategy
- Dead stock discount automation
- CLIP fine-tuning once 500+ labeled images per category
