# ThriftOS — AWS Deployment Guide

## Architecture Overview

```
                          ┌─────────────────────────────────────────┐
Internet ──HTTPS──▶ Route 53 ──▶ ALB ──▶ ECS Fargate (backend)     │
                                   │         └─▶ ECS Fargate (worker)│
                                   │    ┌─── RDS PostgreSQL 16        │
                                   │    ├─── ElastiCache Redis         │
                                   │    └─── S3 + CloudFront (images) │
                                   └─────────────────────────────────┘
                          ECR ──▶ ECS pulls Docker images
                          Secrets Manager ──▶ all secrets at runtime
```

## AWS Services

| Service | Purpose | Notes |
|---|---|---|
| **RDS PostgreSQL 16** | Primary database | Encryption at rest **required** (PII stored) |
| **ElastiCache Redis** | Rate limiting, advisory locks, job state | Not publicly accessible |
| **ECS Fargate** | Backend API + queue_worker containers | 2 worker replicas |
| **S3** | Image storage | Replace local volume when `STORAGE_BACKEND=s3` |
| **CloudFront** | Image CDN / delivery | Never serve images directly from S3 |
| **Application Load Balancer** | HTTPS termination | Port 443 only externally |
| **ECR** | Docker image registry | One repo per service |
| **Secrets Manager** | All application secrets | Never use .env in production |
| **Route 53** | DNS management | A record → ALB |

## Security Requirements

### Database
- RDS encryption at rest: **enabled** (required for GDPR and PII compliance)
- RDS must be in a private VPC subnet — not publicly accessible
- Database user has CONNECT + DML permissions only; no SUPERUSER, no DDL in production
- SSL required for all RDS connections (`sslmode=require` in DATABASE_URL)

### Redis
- ElastiCache in private VPC subnet — not publicly accessible
- AUTH token enabled

### Images
- S3 bucket: **block all public access** enabled
- CloudFront distribution with origin access control (OAC) — images served via CF signed URLs or public CF only
- S3 bucket policy allows only CloudFront OAC principal

### API
- All traffic HTTPS only (ALB listener on 443, redirect 80→443)
- CORS: explicit allowed origins in `ALLOWED_ORIGINS` env var
- JWT secret: 64+ chars, stored in Secrets Manager

### Secrets
All secrets must come from AWS Secrets Manager, not `.env`, in production:
- `SECRET_KEY`
- `DATABASE_URL`
- `REDIS_URL`
- `OPENAI_API_KEY`
- `HUGGINGFACE_API_KEY`
- Redis AUTH token

## Tenant Isolation Strategy

**Current state:** Single tenant, single database/schema.

**Future path (one migration):** Every new table created from Phase 4 onwards has a `tenant_id INTEGER DEFAULT 1` column with an index. When multi-tenancy is needed:
1. Run migration: populate `tenant_id` for each tenant's data
2. Enable PostgreSQL Row Level Security (RLS) on all tenant-scoped tables
3. Set `SET app.current_tenant_id = :tid` on each connection
4. Add RLS policy: `USING (tenant_id = current_setting('app.current_tenant_id')::int)`

This is a one-migration upgrade path — no schema rebuild required.

**Tables with tenant_id:** customers, returns, return_items, system_settings

## Customer PII Handling

- Phone numbers stored as plaintext — protected by RDS encryption at rest
- Phone numbers are **never logged** (PIILogFilter + middleware scrubbing active)
- Full phone number returned only in `GET /customers/{uid}` (admin only)
- GDPR right to erasure: `POST /customers/{uid}/gdpr-erase` nulls PII, preserves row and FK integrity
- Audit log masks all PII fields (phone last 4 only, names first char + ***)

## Image Storage: Local → S3 Migration

Switch from local filesystem to S3 by setting:
```env
STORAGE_BACKEND=s3
S3_BUCKET_NAME=thrift-images-prod
AWS_REGION=us-east-1
IMAGE_BASE_URL=https://d1234.cloudfront.net
```

The `storage_service.py` abstraction handles the switch — no code changes required.

## Estimated Monthly Cost (Single Tenant, ~100 items/day)

| Service | Config | Est. Cost/mo |
|---|---|---|
| RDS db.t3.micro | Multi-AZ, 20GB | ~$30 |
| ElastiCache cache.t3.micro | Single node | ~$15 |
| ECS Fargate (backend) | 0.25 vCPU / 512MB, 2 tasks | ~$15 |
| ECS Fargate (worker) | 0.25 vCPU / 512MB, 2 tasks | ~$15 |
| S3 + CloudFront | ~3GB/mo images, 100k requests | ~$5 |
| ALB | 1 LCU | ~$18 |
| ECR | 2 repos, ~2GB | ~$1 |
| Route 53 | 1 hosted zone | ~$1 |
| **Total** | | **~$100/mo** |

## Deployment Checklist

### First Deploy
- [ ] RDS encryption at rest enabled on creation (cannot be changed after)
- [ ] RDS in private VPC subnet (no public accessibility)
- [ ] ElastiCache in private VPC subnet
- [ ] S3 bucket with block public access enabled
- [ ] CloudFront distribution with OAC configured
- [ ] All secrets in Secrets Manager (not .env)
- [ ] ALB HTTPS listener with valid SSL certificate (ACM)
- [ ] `APP_ENV=production` in ECS task definition
- [ ] `SECRET_KEY` is 64+ chars in Secrets Manager
- [ ] Run `alembic upgrade head` via ECS run-task before starting API
- [ ] Health check endpoint responding: `GET /health`
- [ ] Backup: RDS automated backups enabled (7-day retention)

### Every Deploy
- [ ] Push Docker images to ECR
- [ ] Run Alembic migrations via ECS run-task
- [ ] Update ECS service (rolling deployment)
- [ ] Health check passes after deploy
- [ ] `make test` passing on CI before deploy

## Environment Variables for Production

```env
APP_ENV=production
SECRET_KEY=<from Secrets Manager>
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<rds-endpoint>:5432/thrift_store?ssl=require
REDIS_URL=rediss://<auth-token>@<elasticache-endpoint>:6379/0
STORAGE_BACKEND=s3
S3_BUCKET_NAME=thrift-images-prod
AWS_REGION=us-east-1
IMAGE_BASE_URL=https://<cloudfront-domain>
OPENAI_API_KEY=<from Secrets Manager>
HUGGINGFACE_API_KEY=<from Secrets Manager>
ALLOWED_ORIGINS=https://app.yourdomain.com
```
