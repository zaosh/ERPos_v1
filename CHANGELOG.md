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

## [Phase 2] — 2026-05-02

### Bug Fixes
- **Fix 1: PATCH /items/{barcode}** — Route was accepting `item_id` (integer) but Inventory page called it with barcode string. Changed `PATCH /{item_id}` → `PATCH /{barcode}` throughout backend route. Lookup now uses `Item.barcode == barcode` instead of `Item.id == item_id`. Added tests confirming 200 response and 404 for unknown barcode.
- **Fix 2: today_revenue and today_items** — `GET /analytics/summary` was missing these fields expected by the TodayStrip component. Added `today_items` (COUNT filtered to today) and `today_revenue` (SUM filtered to today) to the SQL query, service return dict, and `SummaryResponse` Pydantic schema. Added unit and integration tests.
- **Fix 3: days_in_stock field consistency** — Backend already returned `days_in_stock` from dead stock query; frontend was reading `item.days_unsold ?? item.days`. Fixed frontend to read `item.days_in_stock`. Added integration test confirming field name.

### Added — CV Accuracy Measurement
- Alembic migration `002_cv_accuracy_columns.py`: adds `cv_color_correct` and `cv_type_correct` boolean columns (nullable — null = pre-measurement era) to `items` table.
- `Item` SQLAlchemy model updated with both columns.
- `ItemCreate` schema gains optional `cv_confidence` and `cv_raw_output` fields.
- `POST /items/` computes `cv_color_correct` and `cv_type_correct` at confirmation time by comparing `cv_raw_output.color/type` against confirmed `color/type` values. Stores `cv_confidence` and `cv_raw_output` on item record.
- `Intake.tsx` now includes `cv_confidence` and `cv_raw_output: { color, type }` in the item creation payload.
- `GET /analytics/cv-performance` (admin only): returns `color_accuracy`, `type_accuracy`, `label_accuracy`, `overall_accuracy`, `confidence_calibration` (3 buckets), `top_mistakes` (top 10 field/cv_suggested/human_confirmed tuples), `total_items_analyzed`, `items_needing_review_pct`.
- CV Performance panel added to Analytics page following existing panel design system.

### Added — Production Infrastructure
- `docker-compose.prod.yml`: backend runs gunicorn+uvicorn workers (not dev reload), frontend served as static build, all ports except 80 internal, restart always, memory limits per service.
- `infra/nginx.prod.conf`: production nginx with gzip, security headers, no directory traversal on images, proper cache headers for static assets.
- `Makefile`: fixed `deploy` target (had space in filename `docker compose.prod.yml` → `docker-compose.prod.yml`), added frontend build step, health check after deploy.
- `scripts/setup_dev.sh`: fixed postgres wait to use `postgres` superuser instead of `thrift_user` (which doesn't exist until init.sql runs).

### Added — Tests
- `tests/integration/test_intake_flow.py`: added PATCH by barcode tests, CV accuracy storage tests, null cv_raw_output edge case.
- `tests/integration/test_analytics_queries.py`: added today_revenue/today_items tests, days_in_stock field test, cv-performance admin-only test, cv-performance structure test, cv-performance with known seed data test.
- `tests/unit/test_analytics.py`: updated summary structure and counts tests to assert today_revenue and today_items.
- `frontend/tests/Intake.test.tsx`: added page-level API flow tests (capture endpoint, review warning, success state with barcode, cv payload passthrough).
- `frontend/tests/Checkout.test.tsx`: added page-level API flow tests (barcode lookup, duplicate prevention, not-found error, POST /sales/ payload verification).

---

## [Phase 3] — 2026-05-02

### Removed
- CLIP / torch / torchvision / ftfy / opencv-python from requirements.txt — these ~1.5GB deps are gone. Backend image is significantly smaller.
- `load_cv_model()` removed from main.py lifespan
- `_model_loaded`, `analyze_image()`, `_classify_type()`, `_remove_background()`, `_mock_result()` removed from cv_service.py
- Redis print queue (`_PRINT_QUEUE_KEY`, `drain_print_queue`, `_queue_print_job`) removed from printer_service.py — all retry logic is now in job_queue table

### Added — Multi-model CV Pipeline
- **cv_service.py rewritten**: three async functions for three models
  - `detect_color(image_path)` — K-means color detection (numpy+sklearn, unchanged algorithm). Called synchronously at POST /items/capture. ~50ms, no API cost.
  - `quick_analyze(image_path) → PhaseAResult` — GPT-4o-mini type classification. Called by queue worker after item creation. Falls back gracefully if OPENAI_API_KEY not set.
  - `deep_analyze(image_path) → PhaseBResult` — GPT-4o deep analysis (label, era, resale interest, condition notes). Called nightly on sold items.
  - `analyze_fashion(image_path) → FashionResult` — FashionCLIP via HuggingFace Inference API. Never raises — returns null FashionResult on any failure.
- `prepare_for_cv()` removed (inlined into each function using Pillow resize+pad+base64)
- All model responses stored in `cv_raw_output` JSONB (phase_a/phase_b keys)
- `_TYPE_MAP` maps GPT's "pattern" → "patterned", "vintage" → "vintage_graphic"

### Added — Job Queue System
- **Alembic migration 004**: adds `cv_phase_b_complete` (bool), `fashion_attributes` (JSONB) to items; creates `job_type_enum`, `job_status_enum`, and `job_queue` table with 3 indexes
- **models/job_queue.py**: `JobQueue`, `JobType`, `JobStatus` SQLAlchemy model
- **services/queue_service.py**: `enqueue`, `get_next_job` (SKIP LOCKED), `complete_job`, `fail_job` (exponential backoff 2^n×30s, cap 3600s), `retry_job`, `get_job_status`, `get_item_jobs`, `get_queue_summary`, `get_failed_jobs`, `get_recent_completed`
- **services/queue_worker.py**: standalone async process (`python services/queue_worker.py`). Routes by job_type to cv_phase_a/phase_b/fashion/print dispatchers. RetryableError → backoff, PermanentError → fail permanently.
- **routes/jobs.py**: `GET /jobs/summary` (admin), `GET /jobs/failed` (admin), `GET /jobs/recent` (admin), `GET /jobs/{id}/status` (staff+), `POST /jobs/{id}/retry` (admin), `GET /jobs/config/public` (staff+)

### Changed — Intake Route
- `POST /items/capture`: no longer calls analyze_image; now calls `detect_color` (K-means, ~50ms); returns `{temp_image_id, color}` — no type/confidence in capture response
- `POST /items/`: `type` field now optional (defaults to `"unknown"`); no longer calls print_label directly; after commit, enqueues `cv_phase_a` (priority 1) and `print_label` (priority 1) jobs; response includes `cv_job_id` and `print_job_id` for frontend polling
- `POST /items/{id}/reprint`: now enqueues a `print_retry` job instead of direct socket call

### Added — Production Infrastructure
- **docker-compose.yml**: `queue_worker` service added with `deploy.replicas: 2` (two workers run in parallel, SKIP LOCKED prevents conflicts). `clip_cache` volume removed.
- **docker-compose.prod.yml**: updated to match (queue_worker service added)
- **routes/health.py**: removed `cv_model_loaded` from health response

### Added — Frontend
- **Intake.tsx**: CaptureResult interface simplified to `{temp_image_id, color}`; motion detection added to CameraPanel (Auto vs Rapid modes, localStorage persistence, 10×10 pixel grid sampling via canvas, configurable thresholds); IntakeSuccess polls `cv_job_id` and `print_job_id` every 500ms and updates status in real time; ConfidenceRing removed (no confidence at capture time)
- **App.tsx**: `QueueIndicator` component added to NavBar (admin-only); shows pending count (amber) or failed count (red); inline panel with pending by type, failed jobs + retry button, recent completed; polls every 5s when open, 30s when closed

### Added — Config
- New settings: `OPENAI_API_KEY`, `HUGGINGFACE_API_KEY`, `CV_PHASE_A_MODEL`, `CV_PHASE_B_MODEL`, `CV_FASHION_MODEL`, `CV_IMAGE_SIZE_PHASE_A`, `CV_IMAGE_SIZE_PHASE_B`, `CV_STILLNESS_THRESHOLD_MS`, `CV_MOTION_THRESHOLD_PCT`, `CV_PHASE_B_TRIGGER_DAYS`
- Removed: `CV_MODEL` (CLIP model name)
- `PRINT_QUEUE_MAX_ATTEMPTS` increased to 10 (label retry is critical)
- `CV_PROCESSING_TIMEOUT` increased to 30.0 (API calls need more time than CLIP)

### Added — Tests
- `tests/unit/test_cv_service.py`: rewritten for new three-function API (mocked OpenAI/HuggingFace). Tests fallback behavior, type mapping (pattern→patterned), null FashionResult on timeout.
- `tests/unit/test_queue_service.py`: enqueue, backoff at attempts 1/10, permanent failure, max_attempts exceeded, retry reset, SKIP LOCKED concurrency test.
- `tests/integration/test_intake_flow.py`: updated for new capture response shape, job_id in create response, jobs admin-only endpoints.

---

## Unreleased / Phase 2 candidates

- Batch intake mode (multiple items queued)
- Price suggestion from historical velocity
- Mobile floor app for barcode lookup
- Cloud sync / backup strategy
- Dead stock discount automation
- CLIP fine-tuning once 500+ labeled images per category
