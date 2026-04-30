#!/usr/bin/env bash
# start.sh — run this once to set up and start ThriftOS
# Usage: bash start.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}▶ $*${NC}"; }
success() { echo -e "${GREEN}✓ $*${NC}"; }
warn()    { echo -e "${YELLOW}⚠ $*${NC}"; }
die()     { echo -e "${RED}✗ $*${NC}"; exit 1; }

echo ""
echo "╔══════════════════════════════════════╗"
echo "║         ThriftOS — Starting up       ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Check Docker ─────────────────────────────────────────────────────────
info "Checking prerequisites..."
command -v docker >/dev/null 2>&1 || die "Docker is not installed. Install it from https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1       || die "Docker is not running. Start Docker Desktop (or: sudo systemctl start docker)"

# docker compose v2 check
if ! docker compose version >/dev/null 2>&1; then
  die "Docker Compose v2 not found. Update Docker Desktop or install the compose plugin."
fi
success "Docker is running"

# ── 2. .env setup ───────────────────────────────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
  info "Creating .env from .env.example..."
  cp "$ROOT/.env.example" "$ROOT/.env"

  # Generate a real SECRET_KEY
  if command -v openssl >/dev/null 2>&1; then
    SECRET_KEY=$(openssl rand -hex 32)
  else
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  fi
  sed -i "s|change_me_generate_with_openssl_rand_hex_32_minimum_64_chars_required|${SECRET_KEY}|" "$ROOT/.env"
  success ".env created with generated SECRET_KEY"
else
  success ".env already exists"
fi

# ── 3. Image storage directory ──────────────────────────────────────────────
mkdir -p "$ROOT/data/images/temp"
success "Image storage: $ROOT/data/images/"

# ── 4. Frontend npm install ─────────────────────────────────────────────────
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  info "Installing frontend dependencies (first run — takes ~1 min)..."
  command -v node >/dev/null 2>&1 || die "Node.js not installed. Install from https://nodejs.org"
  cd "$ROOT/frontend" && npm install --silent && cd "$ROOT"
  success "Frontend dependencies installed"
else
  success "Frontend node_modules already present"
fi

# ── 5. Start infrastructure (postgres + redis) ───────────────────────────────
info "Starting PostgreSQL and Redis..."
docker compose up -d postgres redis

# ── 6. Wait for PostgreSQL to be ready ───────────────────────────────────────
info "Waiting for PostgreSQL to be ready..."
TRIES=0
until docker compose exec -T postgres pg_isready -U postgres >/dev/null 2>&1; do
  TRIES=$((TRIES + 1))
  [ $TRIES -ge 60 ] && die "PostgreSQL did not become ready after 60s. Run: docker compose logs postgres"
  sleep 1
done
# Give init.sql a moment to finish creating thrift_user/thrift_store
sleep 2
success "PostgreSQL is ready"

# ── 7. Run Alembic migrations ─────────────────────────────────────────────────
info "Running database migrations..."
# Run inside a one-shot backend container so we don't need local Python
docker compose run --rm --no-deps \
  -e DATABASE_URL=postgresql+asyncpg://thrift_user:thrift_pass@postgres:5432/thrift_store \
  -e SECRET_KEY=seed_only_not_used \
  backend \
  sh -c "cd /app && alembic -c migrations/alembic.ini upgrade head" 2>&1 | tail -5
success "Migrations applied"

# ── 8. Seed the database ──────────────────────────────────────────────────────
info "Seeding database with test data..."
docker compose run --rm --no-deps \
  -e DATABASE_URL=postgresql+asyncpg://thrift_user:thrift_pass@postgres:5432/thrift_store \
  -e SECRET_KEY=seed_only_not_used \
  -v "$ROOT/scripts:/scripts:z" \
  backend \
  sh -c "cd /app && python /scripts/seed_db.py" 2>&1 | tail -5
success "Database seeded"

# ── 9. Start all services ─────────────────────────────────────────────────────
info "Starting all services (backend + frontend + nginx)..."
docker compose up -d

# ── 10. Wait for backend health ───────────────────────────────────────────────
info "Waiting for backend to be ready..."
TRIES=0
until curl -sf http://localhost:8000/health >/dev/null 2>&1; do
  TRIES=$((TRIES + 1))
  [ $TRIES -ge 60 ] && {
    warn "Backend not ready after 60s — check logs: docker compose logs backend"
    break
  }
  sleep 2
done
[ $TRIES -lt 60 ] && success "Backend is ready"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ThriftOS is running!                ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  App:      ${CYAN}http://localhost:3000${NC}"
echo -e "  API docs: ${CYAN}http://localhost:8000/docs${NC}"
echo ""
echo -e "  Login credentials:"
echo -e "    ${YELLOW}admin${NC}  / admin1234   (admin — analytics + everything)"
echo -e "    ${YELLOW}staff1${NC} / staff1234   (staff — intake + checkout)"
echo ""
echo -e "  Useful commands:"
echo -e "    docker compose logs -f          # tail all logs"
echo -e "    docker compose logs -f backend  # backend only"
echo -e "    docker compose down             # stop everything"
echo -e "    bash start.sh                   # restart / re-seed"
echo ""
