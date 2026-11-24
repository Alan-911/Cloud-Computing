# Benchmarks

Measured on GitHub-hosted runners by the [Performance workflow](../../.github/workflows/performance.yml)
(`ubuntu-24.04`, 4 vCPU, 16 GB RAM, k6 2.4.0). The whole stack runs on the runner:
nginx, one API process, PostgreSQL 17, and for drills a 3-node kind cluster. That
makes these numbers about the **software**, not a production fleet. They're
repeatable, and the workflow reruns them weekly.

Why not on the development laptop: Docker Desktop's VM disk measured ~6 ms p50
`fsync` (10–50× a Linux NVMe), and etcd logged `slow fdatasync` stalls over 1 s
under concurrent load. That skewed latency there (Phase 07's 5–7 s stalls), and
none of it appeared on the Linux runners.

## Defined workload (the SLO test)

`tests/performance/k6/load.js`. **100 req/s** (constant arrival rate) for **3 min**
after a 30 s ramp, through nginx, with **60% read, 25% list (20 rows), 10% create,
5% update**. Writes carry the API key. Gate: p95 < 200 ms, p99 < 500 ms, failed < 0.5%.

| Run | Commit | Requests | p50 | p95 | p99 | Max | Failed | Result |
|---|---|---|---|---|---|---|---|---|
| 1 | `0334988` | 18,001 | 2.2 ms | **3.1 ms** | 3.4 ms | 10.0 ms | 0.000% | Pass |
| 2 | `28bc90c` | 18,000 | 2.1 ms | **3.0 ms** | 3.3 ms | 9.0 ms | 0.000% | Pass |
| 3 | `b45b523` | 18,001 | 3.0 ms | **4.2 ms** | 4.7 ms | 26.5 ms | 0.000% | Pass |

p95 by operation in run 2: read 2.3 ms, list 3.0 ms, create 3.1 ms, update 3.3 ms.
**48–65× headroom against the 200 ms target** at this load across three runs.
The spread between runs is runner variance (shared cloud hardware), not the code.

## Capacity (one API process)

`tests/performance/k6/stress.js`. The arrival rate steps up in 45 s plateaus against
the API directly, bypassing nginx's deliberate 300 req/s per-client cap.

**Before load shedding** (`0334988`):

| Target | p95 | Failed |
|---|---|---|
| 50–300/s | 2.5–3.0 ms | 0% |
| 400/s | 3.4 ms | 0% |
| 600/s | **60 s (timeout)** | **100%** |
| 800/s | **60 s (timeout)** | **100%** |

Past capacity, requests queued without bound and *every* request waited until the
client timed out: a collapse, not a slowdown.

**After load shedding** (`28bc90c`, `APP_MAX_CONCURRENT_REQUESTS=64`):

| Target | Requests | p50 | p95 | p99 | Shed (503) | Served |
|---|---|---|---|---|---|---|
| 50/s | 2,250 | 2.2 ms | 3.2 ms | 3.6 ms | 0% | 50/s |
| 100/s | 4,500 | 2.1 ms | 3.0 ms | 3.3 ms | 0% | 100/s |
| 200/s | 9,000 | 1.8 ms | 2.6 ms | 3.1 ms | 0% | 200/s |
| 300/s | 13,500 | 1.7 ms | 2.6 ms | 3.1 ms | 0% | 300/s |
| 400/s | 18,000 | 2.1 ms | 3.5 ms | 6.7 ms | 0% | 400/s |
| 600/s | 26,999 | 126.9 ms | 197.6 ms | 254.8 ms | 23.2% | **461/s** |
| 800/s | 36,000 | 76.6 ms | 202.1 ms | 235.9 ms | 47.4% | **421/s** |

Run 3 (`b45b523`), a different runner on unchanged code, saturated earlier:

| Target | p95 | Shed (503) | Served |
|---|---|---|---|
| 300/s | 7.5 ms | 0% | 300/s |
| 400/s | 274.2 ms | 16.0% | 336/s |
| 600/s | 269.4 ms | 48.7% | 308/s |
| 800/s | 254.0 ms | 66.4% | 269/s |

- **Capacity:** one process (one CPU core) sustains **~300–460 req/s** of this mix,
  depending on the runner. **Plan on ~300 req/s per replica.**
- **Past capacity:** the API rejects the excess **immediately** (`503 overloaded`,
  `Retry-After: 1`) and keeps serving at full throughput. There are no timeouts, and
  every request gets an answer within about a third of a second (worst band p99:
  350 ms).
- **Every "failed" request was a deliberate 503.** There were no errors and no
  timeouts.
- **Scaling:** capacity scales with replicas. On Kubernetes the HPA adds pods (3–6)
  on CPU; on Compose, run more API containers behind nginx.

## Failure drills

`scripts/resilience-drill.sh`, at a fixed 100 req/s of mixed traffic. Criteria and
procedures are in the [recovery runbook](../runbooks/recovery.md).

| Drill | Commit | Requests | Failed | Failure window | Recovered after dependency ready | Other checks | Result |
|---|---|---|---|---|---|---|---|
| **Compose: PostgreSQL restarted** | `b45b523` | 4,950 | 16 (0.32%), all `503` | **0.10 s** | immediately (DB healthy after 5.5 s) | sentinel row survived | Pass |
| **Kubernetes: API pod killed** (1 s grace, then SIGKILL) | `b45b523` | 5,241 | **0** | — | replacement Ready in 8.4 s | no other pod restarts, sentinel survived | Pass |
| **Kubernetes: PostgreSQL pod killed** | `b45b523` | 4,507 | 108 (2.4%): 104 × `503`, 4 timeouts | **3.95 s** | **2.8 s** (SLO 30 s) | API pods **not** restarted, sentinel survived | Pass |

What these show:
- **Losing an API pod costs nothing.** Envoy retries requests that hit a dead pod
  (connect failure, which is safe for every method), and the pod leaves the endpoints
  as soon as it starts terminating.
- **A database outage is short and honest.** Clients get `503 database_unavailable`
  with `Retry-After`, never `500`. Liveness doesn't depend on the database, so no API
  pod is restarted. The pool reconnects within seconds of PostgreSQL being back.
  Committed data survives on its volume.

**Drill-design lessons (both found from CI output, not from green ticks):**
1. **The traffic probe must be open-loop.** A closed-loop probe sends again as soon as
   a reply arrives. When the service started failing fast, it fired thousands of
   requests per second, hit nginx's 300 req/s per-client limit, and reported 85%
   failures while the drill still "passed". Drills now send at a fixed 100 req/s.
2. **Never `kubectl delete --force` to simulate a crash.** It deletes only the API
   object while the container keeps serving, which produced an impossible "0
   failures" database outage. With PostgreSQL it can also start a second instance on
   the same volume. Drills now use `--grace-period=1` and wait for the old pod to be
   gone.

## How to reproduce

```bash
# Locally (numbers are only indicative on Docker Desktop)
docker compose up -d --build --wait
docker run --rm --network host -v "$PWD/tests/performance/k6:/k6" \
  -e BASE_URL=http://localhost -e API_KEY="$API_KEY" grafana/k6:2.4.0 run /k6/load.js
scripts/resilience-drill.sh compose-db-restart

# Authoritative: Actions -> Performance -> Run workflow (results in the job summary and artifacts)
```
