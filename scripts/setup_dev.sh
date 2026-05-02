#!/usr/bin/env bash
set -euo pipefail

echo "=== ThriftOS Dev Setup ==="

# Check dependencies
command -v docker >/dev/null 2>&1 || { echo "ERROR: Docker is required"; exit 1; }
command -v docker compose >/dev/null 2>&1 || { echo "ERROR: Docker Compose is required"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: Python 3 is required"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "ERROR: Node.js is required"; exit 1; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# .env setup
if [ ! -f .env ]; then
  echo "Creating .env from .env.example..."
  cp .env.example .env
  SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s|<64+ char random string>|${SECRET_KEY}|" .env
  else
    sed -i "s|<64+ char random string>|${SECRET_KEY}|" .env
  fi
  echo ".env created with a random SECRET_KEY"
else
  echo ".env already exists — skipping"
fi

# Create data directories
mkdir -p data/images/temp
echo "Created data/images/temp/"

# Backend Python venv
if [ ! -d backend/.venv ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv backend/.venv
fi
echo "Installing Python dependencies..."
backend/.venv/bin/pip install -q -r backend/requirements.txt

# Frontend node_modules
echo "Installing frontend dependencies..."
cd frontend && npm install --silent && cd "$ROOT"

# Start services
echo "Starting Docker services (postgres + redis)..."
docker compose up -d postgres redis

# Wait for postgres (use postgres superuser — thrift_user exists only after init.sql runs)
echo "Waiting for PostgreSQL..."
for i in $(seq 1 30); do
  docker compose exec -T postgres pg_isready -U postgres >/dev/null 2>&1 && break
  sleep 1
done
# Give init.sql a moment to finish creating thrift_user and databases
sleep 2
echo "PostgreSQL ready"

# Run migrations
echo "Running Alembic migrations..."
cd backend
source .venv/bin/activate 2>/dev/null || true
DATABASE_URL=$(grep DATABASE_URL "$ROOT/.env" | cut -d= -f2-)
export DATABASE_URL
python -m alembic upgrade head
cd "$ROOT"

# Seed database
echo "Seeding database..."
cd backend
python "$ROOT/scripts/seed_db.py"
cd "$ROOT"

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Start development:"
echo "  make dev          # Start full stack"
echo "  make backend      # Backend only (http://localhost:8000)"
echo "  make frontend     # Frontend only (http://localhost:5173)"
echo ""
echo "Test credentials:"
echo "  admin / admin1234  (admin role)"
echo "  staff1 / staff1234 (staff role)"
