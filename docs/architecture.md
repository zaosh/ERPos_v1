# ThriftOS Architecture

## Overview

ThriftOS is a local-first inventory and POS system for a physical thrift store. All components run on a single server on-premises. There is no cloud dependency in the hot path — CV runs locally, storage is local filesystem, auth is JWT (stateless).

## Request Flow

### Intake

```
Browser (Intake page)
  │  getUserMedia → live video feed
  │
  ├─ POST /items/capture (multipart image)
  │    ├─ validate magic bytes (JPEG/PNG only)
  │    ├─ save /data/images/temp/{uuid}.jpg
  │    ├─ store Redis key temp_image:{uuid} TTL 600s
  │    ├─ run CLIP classification + K-means color
  │    └─ return { cv_result, temp_image_id }
  │
  │  Worker edits form, confirms
  │
  └─ POST /items/ (JSON body)
       ├─ generate barcode: Redis INCR barcode_seq:{date}
       ├─ INSERT items row
       ├─ claim temp image → move to /data/images/{YYYY}/{MM}/{id}.jpg
       ├─ generate thumbnail (300x300)
       ├─ write audit_log entry
       ├─ COMMIT
       ├─ attempt ZPL print (3s timeout)
       │    └─ on failure: push to Redis print_queue list
       └─ return { item_id, barcode, label_printed }
```

### Checkout

```
Browser (Checkout page)
  │  ZXing barcode scanner (camera) or manual entry
  │
  ├─ GET /items/?barcode=THR-... (lookup)
  │    └─ verify status=in_stock
  │
  │  Cashier adds items to cart, sets payment type
  │
  └─ POST /sales/ (JSON body)
       ├─ fetch all items by barcode (verify all in_stock)
       ├─ INSERT sales row
       ├─ INSERT sale_items rows
       ├─ UPDATE items SET status=sold, sold_at=NOW()
       ├─ write audit_log entries
       └─ COMMIT (all atomic in one transaction)
```

## Data Model

```
users
  └─ creates → items (created_by FK)
  └─ processes → sales (cashier_id FK)

items
  └─ referenced by → sale_items (item_id FK)
  └─ soft-deleted via deleted_at (never hard-deleted)

sales
  └─ has many → sale_items
  └─ voided via voided_at (never hard-deleted)

audit_log
  └─ append-only, references users and any table by name+id
```

## CV Pipeline

1. Image uploaded to backend as multipart form
2. Magic bytes checked (JPEG: `FF D8 FF`, PNG: `89 50 4E 47`)
3. Written to temp file
4. CLIP model (loaded once at startup, cached on disk) scores image against category prompts
5. K-means (k=3) on 100×100 resized image maps dominant colors to named colors
6. If max CLIP score < 0.4 → `needs_review: true`
7. Full raw output stored in `cv_raw_output` JSONB for future training data

CLIP model loaded once at startup via `load_cv_model()` in lifespan context. Cached in Docker named volume `clip_cache:/root/.cache/clip` to avoid 350MB download on each container start.

## Image Storage

```
/data/images/
  temp/           ← captures awaiting confirmation (Redis TTL 600s)
  2026/
    04/
      1.jpg       ← item 1 full image
      1_thumb.jpg ← 300×300 thumbnail
      2.jpg
      ...
```

Nginx serves `/data/images/` directly — never routed through Python. This prevents path traversal to the API and is significantly faster.

## Authentication

- JWT tokens, HS256, 8h expiry
- bcrypt cost factor 12
- Logout blacklists token in Redis (key: `blacklist:{token_hash}`, TTL = remaining token lifetime)
- Rate limit: 5 login attempts per IP per 15 minutes (Redis sliding window)

## Background Tasks (ARQ)

| Task | Schedule | Purpose |
|------|----------|---------|
| `drain_print_queue` | Every 30s | Retry failed label prints |
| `cleanup_expired_temp_images` | Every 5min | Belt-and-suspenders temp file cleanup |

## Key Design Decisions

See PLANNING.md for full rationale. Summary:

| Decision | Why |
|----------|-----|
| PostgreSQL | JSONB for CV output, ENUMs, window functions for analytics |
| Async SQLAlchemy | FastAPI is async — sync ORM deadlocks under load |
| CLIP local | No per-call cost, no internet dependency, runs on CPU |
| Redis rate limiting | O(1), doesn't pollute PostgreSQL |
| JWT (not sessions) | Stateless — works if Redis goes down |
| Soft deletes | Items are evidence — never lose the record |
| Barcode via Redis INCR | Atomic counter, no DB lock, collision-safe |
| Print queue in Redis | Printer offline doesn't block item creation |

## Performance Targets

| Operation | Target |
|-----------|--------|
| CV processing | < 800ms |
| Full item creation | < 1500ms |
| Analytics query | < 500ms |
| Barcode scan → cart | < 300ms |

Analytics queries use indexes: `idx_items_status`, `idx_items_sold_at`, `idx_items_label`. Dead stock query filters on `status` + `created_at` (both indexed). Velocity query joins `sale_items` on `item_id` with index on `sale_id`.

## Security Boundaries

- API: `0.0.0.0:8000` (internal only, Nginx terminates SSL externally)
- Images: served by Nginx from `/data/images/`, isolated from API process
- File uploads: stored at `/data/images/` which is outside the Python working directory
- No raw SQL: SQLAlchemy ORM only, no f-string queries anywhere
- Secrets: `.env` only, never committed, `python-dotenv` via pydantic-settings
