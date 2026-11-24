#!/usr/bin/env bash
#
# Create a ready-to-use .env for local runs: random database and Grafana passwords
# and a fresh API key (the server gets only its hash). Never overwrites an existing
# .env; delete it first to start over.
#
#   scripts/setup-env.sh
#
# On Windows, run it from Git Bash.

set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then
    echo ".env already exists; leaving it unchanged (delete it to regenerate)."
    exit 0
fi

rand() { openssl rand -hex "$1" | tr -d '\r\n'; }
keys="$(bash scripts/new-api-key.sh)"
key="$(printf '%s\n' "$keys" | sed -n 's/^API_KEY=//p')"
hash="$(printf '%s\n' "$keys" | sed -n 's/^APP_API_KEY_HASHES=//p')"

cp .env.example .env
sed -i \
    -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(rand 24)/" \
    -e "s/^GRAFANA_ADMIN_PASSWORD=.*/GRAFANA_ADMIN_PASSWORD=$(rand 12)/" \
    -e "s/^APP_API_KEY_HASHES=.*/APP_API_KEY_HASHES=${hash}/" \
    -e "s/^API_KEY=.*/API_KEY=${key}/" \
    -e "s/^APP_ENVIRONMENT=.*/APP_ENVIRONMENT=production/" \
    -e "s/^APP_DEBUG=.*/APP_DEBUG=true/" \
    .env
chmod 600 .env 2>/dev/null || true

echo "Created .env (git-ignored) with generated passwords and an API key."
echo "  API key for writes:   stored as API_KEY in .env (the server only knows its hash)"
echo "  Grafana admin password: GRAFANA_ADMIN_PASSWORD in .env"
echo "  Mode: production (writes need the key), APP_DEBUG=true so /api/docs is served"
