#!/usr/bin/env bash
#
# Failure-injection drills under continuous traffic. Each prints a JSON result and
# exits non-zero if its pass criterion is not met.
#
#   scripts/resilience-drill.sh k8s-pod-kill       # kind cluster from k8s-up.sh
#   scripts/resilience-drill.sh k8s-db-outage
#   scripts/resilience-drill.sh compose-db-restart # Compose stack on localhost
#
# Pass criteria
#   k8s-pod-kill        an API pod is force-killed (no grace period, like a crash):
#                       failed requests stay within the 99.5% availability SLO, the
#                       replacement pod becomes Ready, no other pod restarts.
#   k8s-db-outage       the PostgreSQL pod is force-killed: the API recovers within
#                       RECOVERY_SLO_S (30 s) of the database being Ready again,
#                       API pods are NOT restarted (liveness is independent of the
#                       database), and data written before the outage survives.
#   compose-db-restart  the database container is restarted: recovery within
#                       RECOVERY_SLO_S of PostgreSQL being healthy again.

set -euo pipefail
cd "$(dirname "$0")/.."

DRILL="${1:?usage: resilience-drill.sh <k8s-pod-kill|k8s-db-outage|compose-db-restart>}"
RECOVERY_SLO_S="${RECOVERY_SLO_S:-30}"
NS=items
if   [ -x .venv/bin/python ];         then py=.venv/bin/python
elif [ -x .venv/Scripts/python.exe ]; then py=.venv/Scripts/python.exe
else py=python3
fi

case "$DRILL" in
    k8s-*)    URL="${URL:-http://127.0.0.1:8088}"; [ -n "${API_KEY:-}" ] || API_KEY="$(cat .k8s-api-key 2>/dev/null || true)" ;;
    compose-*) URL="${URL:-http://127.0.0.1}" ;;
    *) echo "unknown drill: $DRILL" >&2; exit 2 ;;
esac
export API_KEY="${API_KEY:-}"

now() { "$py" -c 'import time; print(f"{time.time():.3f}")'; }
since() { "$py" -c "print(round($2 - $1, 2))"; }

stop_file=".drill.stop"; result_file=".drill.json"
rm -f "$stop_file" "$result_file"
trap 'rm -f "$stop_file"' EXIT

restarts() { # total container restarts of the API pods
    kubectl -n "$NS" get pods -l app.kubernetes.io/name=api \
        -o jsonpath='{range .items[*]}{.status.containerStatuses[0].restartCount}{"\n"}{end}' |
        awk '{s+=$1} END {print s+0}'
}

# Sentinel row written before the failure; must still be there afterwards.
sentinel="drill-sentinel-$(date +%s)"
curl -fsS -m 5 -X POST "$URL/api/v1/items" -H 'Content-Type: application/json' \
    -H "X-API-Key: $API_KEY" -d "{\"name\":\"$sentinel\"}" > .drill.sentinel
sentinel_id=$(sed -n 's/.*"id":\([0-9]*\).*/\1/p' .drill.sentinel)

t_start=$(now)
"$py" tests/performance/rolling_update_probe.py --url "$URL" --duration 300 --workers 4 \
    --timeout 3 --stop-file "$stop_file" > "$result_file" &
probe=$!
sleep 15 # baseline

event_at=""; ready_at=""; extra="{}"
case "$DRILL" in
    k8s-pod-kill)
        before=$(restarts)
        victim=$(kubectl -n "$NS" get pods -l app.kubernetes.io/name=api -o jsonpath='{.items[0].metadata.name}')
        event_at=$(now)
        kubectl -n "$NS" delete pod "$victim" --grace-period=0 --force --wait=false > /dev/null 2>&1
        kubectl -n "$NS" rollout status deploy/api --timeout=180s > /dev/null
        kubectl -n "$NS" wait --for=condition=Ready pod -l app.kubernetes.io/name=api --timeout=180s > /dev/null
        ready_at=$(now)
        after=$(restarts)
        extra="{\"killed_pod\":\"$victim\",\"other_pod_restarts\":$((after - before))}"
        ;;
    k8s-db-outage)
        before=$(restarts)
        event_at=$(now)
        kubectl -n "$NS" delete pod postgres-0 --grace-period=0 --force --wait=false > /dev/null 2>&1
        sleep 3
        kubectl -n "$NS" wait --for=condition=Ready pod/postgres-0 --timeout=240s > /dev/null
        ready_at=$(now)
        after=$(restarts)
        extra="{\"api_pod_restarts\":$((after - before))}"
        ;;
    compose-db-restart)
        event_at=$(now)
        docker restart items_db > /dev/null
        until [ "$(docker inspect -f '{{.State.Health.Status}}' items_db)" = healthy ]; do sleep 0.5; done
        ready_at=$(now)
        ;;
esac

sleep 30 # observe recovery
touch "$stop_file"; wait "$probe" || true

found=$(curl -fsS -m 5 "$URL/api/v1/items/$sentinel_id" | grep -c "$sentinel" || true)
"$py" - "$result_file" "$DRILL" "$t_start" "$event_at" "$ready_at" "$found" "$extra" "$RECOVERY_SLO_S" <<'PY'
import json, sys
path, drill, t0, ev, rd, found, extra, slo = sys.argv[1:]
t0, ev, rd, slo = float(t0), float(ev), float(rd), float(slo)
p = json.load(open(path))
extra = json.loads(extra)
event_s, ready_s = round(ev - t0, 2), round(rd - t0, 2)
last = p.get("last_failure_at_s")
recovered_after_ready = round(max(0.0, last - ready_s), 2) if last is not None else 0.0
failed_ratio = p["failed"] / max(p["requests"], 1)
res = {
    "drill": drill,
    "requests": p["requests"],
    "failed": p["failed"],
    "failed_pct": round(100 * failed_ratio, 3),
    "outcomes": p["outcomes"],
    "failure_event_at_s": event_s,
    "dependency_ready_at_s": ready_s,
    "time_to_ready_s": round(ready_s - event_s, 2),
    "first_failure_at_s": p.get("first_failure_at_s"),
    "last_failure_at_s": last,
    "failure_window_s": p.get("failure_window_s"),
    "recovered_s_after_ready": recovered_after_ready,
    "sentinel_row_survived": found != "0",
    "latency_ms": p["latency_ms"],
    **extra,
}
checks = {"sentinel_row_survived": res["sentinel_row_survived"]}
if drill == "k8s-pod-kill":
    checks["within_99.5pct_slo"] = failed_ratio <= 0.005
    # <= 0: the killed pod's own restart count disappears with it.
    checks["no_other_pod_restarts"] = extra.get("other_pod_restarts", 0) <= 0
else:
    checks[f"recovered_within_{int(slo)}s_of_ready"] = recovered_after_ready <= slo
if drill == "k8s-db-outage":
    checks["api_pods_not_restarted"] = extra.get("api_pod_restarts", 0) == 0
res["checks"] = checks
res["passed"] = all(checks.values())
print(json.dumps(res, indent=2))
sys.exit(0 if res["passed"] else 1)
PY
