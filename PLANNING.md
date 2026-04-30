# PLANNING.md — Architecture & Decision Log

> Use this file to document decisions BEFORE implementing them.
> For complex decisions, run `claude --model claude-opus-4-5` and paste the plan here.

---

## HOW TO USE THIS FILE

1. **Before starting any significant feature**, write a plan here first
2. **Mark status:** `[PLANNING]` → `[APPROVED]` → `[IN PROGRESS]` → `[DONE]`
3. **Link to relevant files** once implemented
4. **Never delete old plans** — they explain why things are the way they are

---

## SYSTEM ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────┐
│                     INTAKE STATION                       │
│  [USB Camera] → [Intake UI] → [CV Service] → [Confirm]  │
│                      ↓                                   │
│              [Barcode Printer]                           │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTPS
┌─────────────────────▼───────────────────────────────────┐
│                  FastAPI Backend                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │  /items  │  │  /sales  │  │/analytics│              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
│       │              │              │                    │
│  ┌────▼──────────────▼──────────────▼────┐              │
│  │           PostgreSQL 16               │              │
│  │  items / sales / users / audit_log    │              │
│  └───────────────────────────────────────┘              │
│  ┌────────────┐   ┌────────────────────┐                │
│  │   Redis    │   │  /data/images/     │                │
│  │ rate limit │   │  (local storage)   │                │
│  └────────────┘   └────────────────────┘                │
└─────────────────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                  CHECKOUT STATION                        │
│  [Barcode Scanner] → [Checkout UI] → [Cart] → [Confirm] │
└─────────────────────────────────────────────────────────┘
```

---

## DECISION: PostgreSQL as Primary Database

**Status:** `[APPROVED]`
**Date:** Project start

**Options considered:**
1. SQLite — rejected: no concurrent writes, no JSONB, no production path
2. MySQL — rejected: weaker JSONB support, less powerful analytics queries
3. MongoDB — rejected: thrift inventory is relational (sales → items), ACID matters
4. **PostgreSQL 16** — chosen

**Why PostgreSQL:**
- Native ENUM types for status/condition/category (data integrity)
- JSONB for CV raw output (flexible without schema changes)
- Window functions for analytics (ranking, moving averages)
- `pg_trgm` extension for fuzzy label search ("acdc" matches "AC/DC")
- ACID compliance — sale must atomically update item status
- Best async driver: `asyncpg`
- Proven at scale, excellent tooling

**Setup notes:**
```sql
-- Required extensions (run in init.sql)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;
```

---

## DECISION: CLIP for CV Classification

**Status:** `[APPROVED]`
**Date:** Project start

**Options considered:**
1. Google Vision API — rejected: per-call cost, internet dependency, privacy
2. AWS Rekognition — rejected: same as above
3. Custom trained model — rejected: needs thousands of labeled examples we don't have yet
4. **OpenAI CLIP** — chosen (runs locally, no cost per call)

**Why CLIP:**
- Zero-shot classification — works without training examples
- Describe categories in plain English, model understands context
- Runs on CPU acceptably (<800ms), GPU if available
- Accuracy is "good enough" — we always have human confirmation

**Accuracy expectations:**
- Color detection (K-means): ~85% accurate
- Category (plain/graphic/band/anime): ~70% accurate
- Specific label (ACDC, etc): ~40% accurate — mostly "unknown", human fills this

**Key insight:** CV accuracy doesn't need to be high — it needs to be *fast and consistent*. 
Human confirms in <5 sec. Wrong CV suggestion costs 2 seconds to correct. That's fine.

---

## DECISION: Redis for Rate Limiting + Cache

**Status:** `[APPROVED]`

**Why not DB-based rate limiting:**
- Rate limit checks happen on EVERY request — PostgreSQL adds latency
- Redis is O(1) for this operation
- Also used for: session blacklisting (logout), background task queue (ARQ)

**Rate limit rules:**
```
POST /auth/login     → 5 attempts per IP per 15 min
POST /items/capture  → 100 per minute per user (intake speed)
GET  /analytics/*    → 60 per minute per user (dashboard)
```

---

## DECISION: Image Storage Strategy

**Status:** `[APPROVED]`

**Storage path:** `/data/images/{YYYY}/{MM}/{item_id}.jpg`
- Year/month folders prevent single directory getting too large
- Served via Nginx directly (not through Python — much faster)
- Thumbnails at `{item_id}_thumb.jpg` (300x300px)
- Never served from the same port as API (security: no path traversal to API)

**Retention policy:**
- Item images: keep forever (they're evidence/history)
- Temp capture images: deleted after 10 minutes if not confirmed
- Sold item images: move to `archive/` folder after 1 year

---

## FEATURE PLAN: Intake Flow

**Status:** `[APPROVED]`

**Step-by-step:**
1. Worker places shirt on scanning surface
2. Camera feed shown live in browser (getUserMedia API)
3. Worker clicks "Capture" button
4. `POST /items/capture` — image uploaded to backend
5. Backend: save temp image → run CV service → return suggestions
6. Frontend shows: color swatch, type dropdown, label field, size, condition, price
7. CV pre-fills what it detected (color + type always; label if confidence > 0.6)
8. Worker edits anything wrong, sets price, clicks "Confirm & Print"
9. `POST /items/` — creates item record, generates barcode
10. Backend triggers label print via ZPL socket to printer
11. UI resets to camera view, ready for next item
12. Target total time: 8-12 seconds per item

**Error handling:**
- CV timeout (>5s): show form with empty fields, log timeout
- Printer offline: save item, show "Print later" queue
- Network error: retry 3x with backoff, then show error with retry button

---

## FEATURE PLAN: Analytics Dashboard

**Status:** `[IN PROGRESS]`

**Panels to build (priority order):**

1. **Today's snapshot** — items taken in, items sold, revenue
2. **Inventory by category** — stacked bar: in_stock vs sold
3. **Top labels** — ranked: "band tees" > "plain" > "sports" with sell-through rate
4. **Color trends** — what colors sell fastest vs sit longest
5. **Dead stock alert** — items unsold > 21 days (configurable)
6. **Price performance** — avg sale price by condition/category
7. **Velocity** — avg days-to-sell by category and condition

**Key queries:**
```sql
-- Sell-through rate by label
SELECT 
    label,
    COUNT(*) FILTER (WHERE status = 'sold') as sold,
    COUNT(*) as total,
    ROUND(COUNT(*) FILTER (WHERE status = 'sold') * 100.0 / COUNT(*), 1) as sell_through_pct
FROM items
WHERE created_at > NOW() - INTERVAL '90 days'
GROUP BY label
ORDER BY sell_through_pct DESC;

-- Dead stock with age
SELECT *, EXTRACT(DAY FROM NOW() - created_at) as days_in_stock
FROM items
WHERE status = 'in_stock' AND created_at < NOW() - INTERVAL '21 days'
ORDER BY created_at ASC;
```

---

## PHASE 1 IMPLEMENTATION DECISIONS (2026-04-29)

**Status:** `[APPROVED]` — decisions finalized via opus-planner, implementing now.

### Temp Image Storage
Filesystem + Redis key. `POST /items/capture` saves to `/data/images/temp/{uuid}.jpg`, stores `temp_image:{uuid}` in Redis with 600s TTL (value: `{path, uploaded_by}`). `POST /items/` looks up Redis key, verifies ownership, moves file to final path, creates thumbnail, deletes Redis key. Background ARQ task `cleanup_expired_temp_images` runs every 5 min as belt-and-suspenders.

### Barcode Format
`THR-{YYYYMMDD}-{5-digit sequence}` e.g. `THR-20260429-00047`. Redis INCR on `barcode_seq:{YYYYMMDD}` key (atomic, TTL 48h). DB UNIQUE constraint catches any collision edge case — retry once with INCR. 18 chars max, fits `VARCHAR(20)`.

### Print Queue
Redis list `print_queue` as lightweight queue. Printer service attempts direct ZPL socket (3s timeout). On failure: push job JSON to queue, return `label_printed: false` to client. ARQ task `drain_print_queue` runs every 30s. Max 5 attempts per job then permanent-fail log. Reprint available via `POST /items/{id}/reprint`. Redis `appendonly yes` for persistence.

### Alembic Strategy
Runs via Docker CMD: `sh -c "alembic upgrade head && uvicorn main:app ..."`. Idempotent on every start. First migration (`001_initial_schema.py`) is hand-written (not autogenerated) to ensure correct ENUM type creation order before tables.

### CV Model Caching
Mounted as named Docker volume (`clip_cache:/root/.cache/clip`). `make download-model` target pre-populates it. Avoids 350MB image bloat and slow cold start.

### Redis Persistence
`appendonly yes` in docker-compose for print queue and barcode counter durability.

---

## OPEN QUESTIONS

### Q1: Offline resilience
**Question:** What happens if the local server goes down during a busy intake session?
**Options:**
- A) Accept it — restart server, lose <5 min of data
- B) Local SQLite fallback that syncs when server comes back
- C) Browser-based IndexedDB queue
**Current thinking:** Start with A, plan B in v2

### Q2: Multi-station setup
**Question:** Can two intake stations run simultaneously?
**Answer:** Yes — backend handles concurrent requests. Camera/printer are per-station physical hardware. No code changes needed.

### Q3: Price guidance
**Question:** Should CV or system suggest a price?
**Current thinking:** Future feature — need 3+ months of sales data first. Add `suggested_price` field to items table when ready.

### Q4: Label accuracy improvement
**Question:** How do we get better logo detection over time?
**Plan:** Every confirmed item with a label = training data. After 500+ labeled images per category, fine-tune CLIP or train a small classifier. Store CV raw output in JSONB now so we have data to train with later.

---

## PERFORMANCE TARGETS

| Operation | Target | Alert threshold |
|---|---|---|
| CV processing | <800ms | >2000ms |
| Barcode print trigger | <200ms | >1000ms |
| Item creation (full) | <1500ms | >3000ms |
| Analytics query | <500ms | >2000ms |
| Barcode scan → cart add | <300ms | >1000ms |

---

## SECURITY THREAT MODEL

| Threat | Mitigation |
|---|---|
| Stolen JWT token | Short expiry (8h), logout blacklist in Redis |
| Brute force login | Rate limit 5/15min per IP |
| SQL injection | SQLAlchemy ORM only, no string interpolation |
| File upload exploit | Validate magic bytes, restrict to JPEG/PNG, store outside webroot |
| Path traversal | Nginx serves images from isolated directory |
| Insider threat | Audit log on all writes, admin-only destructive actions |
| Lost device with cached token | Logout endpoint blacklists token in Redis |

---

## DEPLOYMENT CHECKLIST

Before going to production:
- [ ] `APP_ENV=production` in .env
- [ ] `SECRET_KEY` is 64+ chars, randomly generated
- [ ] PostgreSQL user has minimal permissions (no SUPERUSER)
- [ ] Nginx SSL certificate configured
- [ ] Redis password set
- [ ] Image directory outside webroot, correct permissions
- [ ] Backup script scheduled (cron daily)
- [ ] Health check endpoint responding
- [ ] All tests passing (`make test`)
- [ ] Rate limits verified
- [ ] Audit log working (insert a test record)
