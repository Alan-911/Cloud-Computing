#!/usr/bin/env bash
#
# Dump the Compose PostgreSQL database to backups/<db>-<UTC timestamp>.dump
# (pg_dump custom format: compressed, restorable with scripts/db-restore.sh).
#
#   scripts/db-backup.sh [output-dir]

set -euo pipefail
cd "$(dirname "$0")/.."

out_dir="${1:-backups}"
mkdir -p "$out_dir"

db="$(docker compose exec -T db sh -c 'echo "$POSTGRES_DB"')"
file="${out_dir}/${db}-$(date -u +%Y%m%dT%H%M%SZ).dump"

# Credentials come from the container's own environment, never this shell.
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$file"

# A dump that pg_restore cannot list is not a backup.
docker compose exec -T db pg_restore --list < "$file" > /dev/null

echo "Backup written: $file ($(wc -c < "$file") bytes)"
