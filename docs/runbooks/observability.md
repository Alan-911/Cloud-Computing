# Runbook — observability

```
client ─▶ nginx ──X-Request-ID──▶ api ──▶ JSON logs (stdout, one object per line)
                                   │
                                   └─ /metrics (internal only) ◀── Prometheus ─▶ rules: SLIs + alerts
                                                                       ▲
                                                                  Grafana dashboard
```

## Run it

```bash
# .env needs POSTGRES_PASSWORD and GRAFANA_ADMIN_PASSWORD (see .env.example)
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --wait
```

| Tool | URL | Notes |
|---|---|---|
| Grafana | http://127.0.0.1:3000 | `admin` / `GRAFANA_ADMIN_PASSWORD`. The home dashboard is **Items API — SLOs and RED metrics** |
| Prometheus | http://127.0.0.1:9090 | Alerts: `/alerts`. Targets: `/targets` |

Both listen on localhost only. Prometheus scrapes `api:8000/metrics` over the
Compose network. nginx and the Kubernetes Gateway only route `/api/`, so `/metrics`
is never public.

## Signals

**Logs** are one JSON object per line on stdout, from the app (`app.access`,
application loggers, tracebacks) and from nginx (`nginx.access`).

- **Request IDs:** every line written while handling a request carries the same
  `request_id`. The ID is the client's `X-Request-ID` if it's safe
  (`[A-Za-z0-9._:-]{1,128}`). Otherwise nginx or the app generates one. The response
  echoes it back.
- **Follow one request:**

  ```bash
  docker compose logs api nginx | grep '"request_id": *"<id>"'
  ```

- **Readable logs locally:** set `APP_LOG_FORMAT=text`.

**Metrics** (Prometheus, labelled by route *template*, e.g. `/api/v1/items/{item_id}`,
so IDs never create new series):

| Metric | Meaning |
|---|---|
| `http_requests_total{method,route,status}` | Rate and errors |
| `http_request_duration_seconds{method,route}` | Latency histogram (5 ms … 5 s buckets, including 200 ms) |
| `http_requests_in_progress` | Concurrency |
| `db_pool_connections_in_use` | Pool saturation (limit is pool 5 + overflow 5) |
| `process_cpu_seconds_total`, `process_resident_memory_bytes` | CPU and memory |
| `app_info{version,environment}` | Which build is running |

## SLOs

| SLO | Target | SLI (recording rule) |
|---|---|---|
| Availability | 99.5% of requests are not 5xx | `job:http_error_ratio:rate{5m,30m,1h,6h}` |
| Latency | 95% of requests complete within 200 ms | `job:http_slow_ratio:rate{5m,1h}` |

Burn-rate alerts use the multi-window pattern: an alert fires only when the error
budget burns fast in **both** a long and a short window. A brief spike doesn't page,
and a fixed problem stops alerting quickly.

Rules: `monitoring/prometheus/rules/api-slo.yml`. Unit tests:
`monitoring/prometheus/tests/api-slo-test.yml`. CI runs `promtool test rules` on every
pull request.

## Alerts

### ApiDown
**Critical.** Prometheus couldn't scrape the API for 1 minute.
1. Run `docker compose ps api` and `docker compose logs --tail=100 api`.
2. If the container is restarting, look for the traceback. Common causes: the
   database is unreachable, or the `migrate` service failed (`docker compose logs migrate`).
3. Check the user-facing path: `curl -i http://127.0.0.1/api/health`.

### ApiErrorBudgetBurnFast
**Critical.** The 5xx ratio is above 7.2% (14.4× budget) over both 5 minutes and 1 hour.
1. On the dashboard, see which route and status are failing ("Responses by status").
2. Pull a failing request's ID from the API logs (`"level": "ERROR"`) and read the
   traceback with that `request_id`.
3. If it began with a deploy, roll back by redeploying the previous tag
   ([CI/CD runbook](ci-cd.md#deploy-and-roll-back)).

### ApiErrorBudgetBurnSlow
**Warning.** The 5xx ratio is above 3% (6× budget) over both 30 minutes and 6 hours.
Use the same diagnosis as the fast burn. Treat it within working hours.

### ApiLatencySLOBreach
**Warning.** More than 5% of requests took longer than 200 ms, over both 5 minutes and 1 hour.
1. Use "p95 latency by route" to find the slow route.
2. Check saturation: in-flight requests, DB pool use, CPU.
3. If the DB pool is saturated, see below.

### ApiDbPoolSaturated
**Warning.** 9 or 10 of 10 database connections have been in use for 5 minutes.
Requests queue for a connection (`APP_DB_POOL_TIMEOUT` is 10 s).
1. Look for slow queries in PostgreSQL:

   ```bash
   docker compose exec db psql -U app -c "select pid, now()-query_start as age, state, left(query,80) from pg_stat_activity where datname='app' order by age desc;"
   ```

2. Scale out API replicas (Kubernetes HPA) or raise `APP_DB_POOL_SIZE`. Keep
   `replicas × (pool + overflow)` below PostgreSQL's `max_connections`.

## Drill (verified 2026-11-22)

To confirm alerting works end to end:

```bash
docker stop items_api          # simulate an outage
# Prometheus /alerts: ApiDown goes pending, then firing after ~1 minute
docker start items_api         # recover; the alert clears once scrapes succeed
```

Observed:
- **Stopped** at 21:55:09Z.
- **Pending** at 21:55:52Z.
- **Firing** at 21:56:53Z (`severity=critical`, `instance=api:8000`).
- **Restarted** at 21:56:58Z.
- **Cleared** at 21:58:04Z, and the API answered 200 through nginx.

## Not covered yet

- **No alert delivery:** alerts show in Prometheus and Grafana, but no Alertmanager
  routes them to email or chat. That's a candidate for a later phase.
- **Kubernetes:** the cluster doesn't run Prometheus yet. The usual choice there is
  kube-prometheus-stack plus a `ServiceMonitor`, and the NetworkPolicy would need to
  allow the scraper to reach `api:8000`.
- **Logs** go to stdout and are read with `docker compose logs`. There's no central
  log store (such as Loki) yet.
