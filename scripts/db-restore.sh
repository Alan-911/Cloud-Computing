#!/usr/bin/env bash
#
# Restore a dump made by scripts/db-backup.sh into the Compose database.
# Replaces existing objects. The API is stopped during the restore so no
# requests write to a half-restored database.
#
#   scripts/db-restore.sh backups/app-20261121T000000Z.dump [--yes]

set -euo pipefail
cd "$(dirname "$0")/.."

file="${1:?usage: db-restore.sh <dump-file> [--yes]}"
[ -f "$file" ] || { echo "No such file: $file" >&2; exit 1; }

if [ "${2:-}" != "--yes" ]; then
    read -r -p "Replace the current database with ${file}? [y/N] " answer
    [ "$answer" = "y" ] || { echo "Aborted."; exit 1; }
fi

docker compose stop api
trap 'docker compose start api' EXIT

docker compose exec -T db sh -c \
    'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --single-transaction' \
    < "$file"

echo "Restored from $file"
