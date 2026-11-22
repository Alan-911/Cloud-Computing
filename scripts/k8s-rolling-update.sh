#!/usr/bin/env bash
#
# Zero-downtime check: send continuous traffic through the Gateway while the API
# is updated to NEW_TAG (migrations first, then a rolling update), and fail if
# any request fails.
#
#   scripts/k8s-rolling-update.sh <new-image-tag> [--restart]
#
# --restart additionally forces a second full rollout of the same image afterwards,
# so the check covers two complete replacements of every pod.

set -euo pipefail
cd "$(dirname "$0")/.."

NEW_TAG="${1:?usage: k8s-rolling-update.sh <new-image-tag> [--restart]}"
# 127.0.0.1, not localhost: on Windows, "localhost" tries IPv6 ::1 first and only
# falls back to IPv4 after ~2 s, which would make every request look 2 s slow.
URL="${URL:-http://127.0.0.1:8088}"
if   [ -x .venv/bin/python ];         then py=.venv/bin/python
elif [ -x .venv/Scripts/python.exe ]; then py=.venv/Scripts/python.exe
else py=python3
fi

# Relative paths in the repo, so the shell and a native Windows Python agree on them.
stop_file=".k8s-probe.stop"
result_file=".k8s-probe.json"
rm -f "$stop_file"
trap 'rm -f "$stop_file"' EXIT

echo "==> Starting traffic probe against $URL"
"$py" tests/performance/rolling_update_probe.py --url "$URL" --duration 900 \
    --workers 4 --stop-file "$stop_file" > "$result_file" &
probe=$!
sleep 5 # baseline traffic before anything changes

before=$(kubectl -n items get deploy api -o jsonpath='{.spec.template.spec.containers[0].image}')
echo "==> Updating API: $before -> ghcr.io/alan-911/cloud-computing:$NEW_TAG"
bash scripts/k8s-up.sh "$NEW_TAG"

if [ "${2:-}" = "--restart" ]; then
    echo "==> Forcing a second rollout (rollout restart)"
    kubectl -n items rollout restart deploy/api
    kubectl -n items rollout status deploy/api --timeout=300s
fi

sleep 10 # trailing traffic after the last old pod is gone
touch "$stop_file"
set +e
wait "$probe"
code=$?
set -e

echo "==> Probe result"
cat "$result_file"
echo "==> Running pods"
kubectl -n items get pods -l app.kubernetes.io/name=api \
    -o custom-columns=NAME:.metadata.name,IMAGE:.spec.containers[0].image,NODE:.spec.nodeName,READY:.status.containerStatuses[0].ready
if [ "$code" -ne 0 ]; then
    echo "Zero-downtime check FAILED"
    exit 1
fi
echo "Zero-downtime check passed"
