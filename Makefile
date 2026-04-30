.PHONY: dev backend frontend migrate migrate-create seed db-reset \
        test test-unit test-integration test-cov lint format typecheck \
        build deploy backup logs clean help

# ─── Dev ───────────────────────────────────────────────────────────────────────

dev:
	docker compose up

dev-build:
	docker compose up --build

backend:
	cd backend && uvicorn main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

# ─── Database ─────────────────────────────────────────────────────────────────

migrate:
	cd backend && alembic upgrade head

migrate-create:
	@if [ -z "$(msg)" ]; then echo "Usage: make migrate-create msg='your message'"; exit 1; fi
	cd backend && alembic revision --autogenerate -m "$(msg)"

migrate-down:
	@echo "WARNING: Only run in development. Use: make migrate-down steps=1"
	cd backend && alembic downgrade -$(steps)

migrate-history:
	cd backend && alembic history --verbose

seed:
	cd backend && python ../scripts/seed_db.py

db-reset:
	@echo "WARNING: This will destroy all data. Only for development."
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	docker compose exec postgres psql -U postgres -c "DROP DATABASE IF EXISTS thrift_store;"
	docker compose exec postgres psql -U postgres -c "CREATE DATABASE thrift_store;"
	$(MAKE) migrate
	$(MAKE) seed

db-shell:
	docker compose exec postgres psql -U thrift_user -d thrift_store

# ─── Testing ──────────────────────────────────────────────────────────────────

test:
	cd backend && pytest tests/ -v --tb=short

test-unit:
	cd backend && pytest tests/unit/ -v --tb=short

test-integration:
	cd backend && pytest tests/integration/ -v --tb=short

test-e2e:
	cd backend && pytest tests/e2e/ -v --tb=short

test-cov:
	cd backend && pytest tests/ --cov=. --cov-report=html --cov-report=term-missing --cov-fail-under=80
	@echo "Coverage report: backend/htmlcov/index.html"

test-watch:
	cd backend && pytest-watch tests/unit/ -- -v

test-frontend:
	cd frontend && npm run test

test-all: test test-frontend

# ─── Code Quality ─────────────────────────────────────────────────────────────

lint:
	cd backend && ruff check .
	cd frontend && npm run lint

lint-fix:
	cd backend && ruff check --fix .
	cd frontend && npm run lint:fix

format:
	cd backend && ruff format .
	cd frontend && npm run format

typecheck:
	cd backend && mypy . --ignore-missing-imports
	cd frontend && npm run typecheck

check: lint typecheck test
	@echo "All checks passed."

# ─── Production ───────────────────────────────────────────────────────────────

build:
	docker compose -f docker compose.prod.yml build

deploy:
	@echo "Deploying to production..."
	docker compose -f docker compose.prod.yml pull
	docker compose -f docker compose.prod.yml up -d
	$(MAKE) migrate
	@echo "Deploy complete."

backup:
	bash scripts/backup_db.sh

# ─── Utilities ────────────────────────────────────────────────────────────────

logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

logs-db:
	docker compose logs -f postgres

health:
	bash scripts/health_check.sh

setup:
	bash scripts/setup_dev.sh

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true

# ─── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "Thrift Store Inventory System — Available Commands"
	@echo "════════════════════════════════════════════════════"
	@echo ""
	@echo "Development:"
	@echo "  make dev              Start full stack (docker compose)"
	@echo "  make backend          Start backend only"
	@echo "  make frontend         Start frontend only"
	@echo ""
	@echo "Database:"
	@echo "  make migrate          Run pending migrations"
	@echo "  make migrate-create msg='description'"
	@echo "  make seed             Insert test data"
	@echo "  make db-reset         Drop + recreate + seed (DEV ONLY)"
	@echo ""
	@echo "Testing:"
	@echo "  make test             All backend tests"
	@echo "  make test-unit        Unit tests only"
	@echo "  make test-integration Integration tests"
	@echo "  make test-cov         Tests with coverage report"
	@echo ""
	@echo "Code quality:"
	@echo "  make lint             Lint all code"
	@echo "  make format           Format all code"
	@echo "  make check            lint + typecheck + test"
	@echo ""
	@echo "Production:"
	@echo "  make build            Build Docker images"
	@echo "  make deploy           Deploy to production"
	@echo "  make backup           Database backup"
	@echo ""
