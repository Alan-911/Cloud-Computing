#!/usr/bin/env bash
#
# Start (or update) the stack on the app host from a published image, then run the
# smoke test. Used by the EC2 first-boot script and by the Deploy workflow (via SSM).
#
#   IMAGE_TAG=1.3.0 scripts/deploy-on-host.sh
#
# Expects to run from a checkout of the repository at the matching commit, with .env
# (POSTGRES_PASSWORD) present. Appends each successful deploy to /data/deploy-history.log.

set -euo pipefail
cd "$(dirname "$0")/.."

: "${IMAGE_TAG:?set IMAGE_TAG to a published image tag}"
export IMAGE_TAG

compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

echo "==> Deploying ghcr.io/alan-911/cloud-computing:${IMAGE_TAG} at $(git rev-parse --short HEAD)"
"${compose[@]}" pull --quiet migrate api
"${compose[@]}" up -d --remove-orphans --wait --wait-timeout 180
"${compose[@]}" ps

# The write key is in a root-only file on the data volume (created on first boot).
if [ -z "${API_KEY:-}" ] && [ -r /data/secrets/api.key ]; then
    API_KEY="$(cat /data/secrets/api.key)"
fi
API_KEY="${API_KEY:-}" bash scripts/smoke-test.sh http://localhost

history_dir=/data
[ -w "$history_dir" ] || history_dir="$HOME"
echo "$(date -u +%FT%TZ) ${IMAGE_TAG} $(git rev-parse HEAD)" >> "${history_dir}/deploy-history.log"
echo "==> Deployed ${IMAGE_TAG}"
