#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="thrift_store_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "Backing up thrift_store → ${BACKUP_DIR}/${FILENAME}"

docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
  pg_dump -U thrift_user thrift_store \
  | gzip > "${BACKUP_DIR}/${FILENAME}"

SIZE=$(du -sh "${BACKUP_DIR}/${FILENAME}" | cut -f1)
echo "Backup complete: ${FILENAME} (${SIZE})"

# Keep only last 30 backups
find "$BACKUP_DIR" -name "thrift_store_*.sql.gz" -mtime +30 -delete
echo "Cleaned up backups older than 30 days"
