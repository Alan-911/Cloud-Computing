# Runbook — failure recovery

How the service behaves when a part fails, what recovers on its own, and what to do
when it doesn't. Every scenario below has been tested by injecting the failure
under live traffic (`scripts/resilience-drill.sh`, run weekly by the Performance
workflow). Measured results are in [benchmarks](../benchmarks/README.md).

## What recovers on its own

| Failure | Automatic behaviour | Expected impact |
|---|---|---|
| **An API pod crashes** (Kubernetes) | The Deployment replaces it. Envoy retries requests that never reached a pod (connect failure, refused stream) on a healthy one. Passive health checks eject a pod that keeps failing. | A handful of failed requests, well inside the 99.5% SLO. No other pod restarts. |
| **PostgreSQL restarts or is briefly down** | The API returns **503 `database_unavailable`** with `Retry-After: 2`, never a 500. Readiness fails, so the gateway stops routing. Liveness doesn't check the database, so API pods are **not** restarted. The pool's pre-ping reconnects as soon as the database is back. | Requests fail during the outage, and the API serves again within seconds of the database being ready (SLO: 30 s). Committed data survives (persistent volume or named volume). |
| **More traffic than one replica can serve** | Load shedding: requests beyond `APP_MAX_CONCURRENT_REQUESTS` (64 per process) get an immediate **503 `overloaded`** with `Retry-After: 1`. Admitted requests keep normal latency. On Kubernetes the HPA adds replicas (3 → 6) on CPU. | Some clients get fast 503s and should retry. No queue collapse, no timeouts. |
| **One client floods the API** | nginx returns 429 above 300 req/s per IP (100 writes/s). Envoy caps a route at 2,000 req/s per proxy. | Only that client is throttled. |
| **The node or instance is replaced** | On Kubernetes, the PodDisruptionBudget keeps 2 replicas during drains. On EC2, the data volume is separate, so `terraform apply -replace=aws_instance.app` keeps it. | No data loss. |

Clients should retry 503 and 429 after `Retry-After`, with jitter. They should not
blindly retry 500 or other non-idempotent failures.

## When it doesn't recover: diagnosis

Start from the symptom:

1. **Dashboard** ([observability runbook](observability.md)). Check *API up*, the 5xx ratio, the latency percentiles, the in-flight requests, and DB pool use.
2. **Status codes tell you the layer:**

   | Response | Meaning |
   |---|---|
   | `503 database_unavailable` | The database is unreachable |
   | `503 overloaded` | The API is at capacity |
   | `503` with no envelope, from Envoy | No ready pods |
   | `429` | Rate limited |
   | `500` | A bug; look up the traceback by `request_id` |

3. **Logs:** follow one request with `grep '"request_id": *"<id>"'` across the nginx and API logs.

### Database down and staying down

```bash
# Compose
docker compose ps db && docker compose logs --tail=100 db
docker compose restart db
# Kubernetes
kubectl -n items get pod postgres-0 && kubectl -n items logs postgres-0 --tail=100
kubectl -n items describe pod postgres-0   # PVC, scheduling and image problems
```

- **The volume is lost or corrupt:** restore from backup ([database runbook](database.md#restore)).
- **The API stays at 503 after the database is healthy:** the pool reconnects on its own through pre-ping. If not, roll the API with `kubectl -n items rollout restart deploy/api` or `docker compose restart api`.

### API pods crash-looping

```bash
kubectl -n items get pods -l app.kubernetes.io/name=api
kubectl -n items logs deploy/api --previous --tail=100
kubectl -n items describe deploy/api
```

- **A bad deploy:** roll back with `kubectl -n items rollout undo deploy/api` (same schema), or redeploy the previous tag ([CI/CD runbook](ci-cd.md#deploy-and-roll-back)).
- **A migration failed:** the API wasn't updated. Read `kubectl -n items logs job/migrate`.

### Sustained overload (503 `overloaded` or high latency)

1. **Confirm it's load:** in-flight requests at the limit, `http_requests_shed_total` rising, and CPU near one core per pod.
2. **Scale out** (`kubectl -n items scale deploy/api --replicas=N`), or let the HPA do it. Raise `maxReplicas` if it's pinned at 6.
3. **Check the pool:** keep `replicas × (pool + overflow)` below PostgreSQL's `max_connections`.
4. **If one client is causing it,** tighten the nginx or Envoy limits.

## Drills

Run them against a test environment, never production:

```bash
scripts/resilience-drill.sh compose-db-restart   # Compose stack on localhost
scripts/resilience-drill.sh k8s-pod-kill         # kind cluster (scripts/k8s-up.sh)
scripts/resilience-drill.sh k8s-db-outage
```

Each one:
1. Writes a sentinel row.
2. Runs mixed traffic.
3. Injects the failure.
4. Measures the failure window and recovery time.
5. Checks the pass criteria.

It exits non-zero if any criterion fails. The Performance workflow runs all three
every Sunday on clean runners.
