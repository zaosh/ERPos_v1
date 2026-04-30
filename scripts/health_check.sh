#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:5173}"

PASS=0
FAIL=0

check() {
  local name="$1"
  local cmd="$2"
  if eval "$cmd" >/dev/null 2>&1; then
    echo "  ✓ $name"
    PASS=$((PASS + 1))
  else
    echo "  ✗ $name"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== ThriftOS Health Check ==="
echo ""

echo "[ API ]"
check "Backend reachable" "curl -sf ${API_URL}/health"
check "Health endpoint OK" "curl -sf ${API_URL}/health | grep -q 'ok'"

echo ""
echo "[ Database ]"
check "PostgreSQL running" "docker compose exec -T postgres pg_isready -U thrift_user -d thrift_store"

echo ""
echo "[ Redis ]"
check "Redis running" "docker compose exec -T redis redis-cli ping | grep -q PONG"

echo ""
echo "[ Frontend ]"
check "Frontend reachable" "curl -sf ${FRONTEND_URL} -o /dev/null"

echo ""
echo "[ Image Storage ]"
check "Image dir exists" "test -d ./data/images"
check "Image dir writable" "test -w ./data/images"

echo ""
if [ $FAIL -eq 0 ]; then
  echo "All checks passed ($PASS/$((PASS + FAIL)))"
  exit 0
else
  echo "$FAIL check(s) failed ($PASS/$((PASS + FAIL)) passed)"
  exit 1
fi
