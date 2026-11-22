# Runbook — Kubernetes (local kind cluster)

The same published image runs on Kubernetes, on a local
[kind](https://kind.sigs.k8s.io/) cluster at no cloud cost.

```
localhost:8088 ──▶ kind control-plane :30080 (NodePort)
                     └─▶ Envoy Gateway proxy (Gateway API: Gateway "public")
                           └─▶ HTTPRoute /api ─▶ Service api ─▶ 3× api pods (Deployment, HPA 3–6)
                                                                   └─▶ postgres-0 (StatefulSet + PVC)
                     migrate Job (alembic upgrade head) runs before each API rollout
```

| Path | Contents |
|---|---|
| `kubernetes/cluster/kind.yaml` | 1 control-plane + 2 workers; host port 8088 → NodePort 30080 |
| `kubernetes/platform/gateway.yaml` | `EnvoyProxy` (NodePort, `externalTrafficPolicy: Cluster`), `GatewayClass`, `Gateway` |
| `kubernetes/base/` | Namespace, ConfigMap, PostgreSQL, API Deployment/Service/HTTPRoute/PDB/HPA, NetworkPolicies |
| `kubernetes/migrate/` | Migration Job (applied separately, before the API changes) |
| `scripts/k8s-up.sh [tag]` | Create the cluster if needed, install the platform, deploy `tag` |
| `scripts/k8s-rolling-update.sh <tag> [--restart]` | Update to `tag` under continuous traffic; fails on any failed request |
| `scripts/k8s-down.sh` | Delete the cluster |

**Why Gateway API, not Ingress.** ingress-nginx was archived upstream in March 2026.
The Gateway API is the maintained successor. Envoy Gateway (v1.10) implements it.

## Prerequisites

Docker Desktop, `kubectl` (ships with Docker Desktop), and `kind` v0.33.
Download kind from its [releases](https://github.com/kubernetes-sigs/kind/releases)
and check the `.sha256sum`. If kind isn't on your PATH, set `KIND=/path/to/kind`.

## Run it

```bash
scripts/k8s-up.sh 1.4.0                      # about 3–4 minutes on a fresh cluster
scripts/smoke-test.sh http://127.0.0.1:8088
kubectl -n items get pods,hpa,pdb
```

Use `127.0.0.1` rather than `localhost`. On Windows, `localhost` tries IPv6 first and
adds about 2 seconds to every request.

## How an update works

`scripts/k8s-up.sh <new-tag>` runs these steps in order:

1. Apply everything except the API Deployment: namespace, config, PostgreSQL, policies.
2. Wait for PostgreSQL. Generate the `db-credentials` Secret once, if it's missing. The
   password exists only in the cluster.
3. Replace the `migrate` Job with the new image and wait for **Complete**. If a migration
   fails, the API is never updated.
4. Apply the Deployment with the new image and wait for the rollout.

Zero downtime comes from four things working together:

| Setting | Effect |
|---|---|
| `maxUnavailable: 0`, `maxSurge: 1` | A new pod must be Ready before an old one is removed |
| `readinessProbe` → `/api/health` | A pod gets traffic only once it can reach the database |
| `preStop: sleep 10` | An old pod keeps serving while Envoy and endpoints drop it |
| Uvicorn graceful shutdown, `terminationGracePeriodSeconds: 40` | In-flight requests finish |

Roll back by running `scripts/k8s-up.sh <previous-tag>`, or with
`kubectl -n items rollout undo deploy/api` when the schema is unchanged.

## Security posture

- **Pod Security Standard `restricted`** is enforced on the namespace. Every pod:
  - runs as non-root, with a fixed UID
  - has a read-only root filesystem
  - drops all capabilities and can't escalate privileges
  - uses seccomp `RuntimeDefault`
  - doesn't mount a service-account token
- **NetworkPolicies:** inbound traffic is denied by default. The only allowed paths are:
  - the gateway namespace → `api:8000`
  - `api` and `migrate` → `postgres:5432`
- **No secrets in git:** the database password is generated in the cluster.

## Verified (2026-11-22, local kind, 3 nodes)

See the Phase 06 evidence in [`docs/ROADMAP.md`](../ROADMAP.md).

## Troubleshooting

| Symptom | Check |
|---|---|
| `localhost:8088` connects but never answers | `externalTrafficPolicy` on the Envoy Service must be `Cluster`. kind maps the host port to the control-plane node, and with `Local` only the node running the proxy answers. |
| Requests take about 2 s each | Use `127.0.0.1`, not `localhost` (Windows IPv6 fallback) |
| HPA shows `cpu: <unknown>` | `kubectl top pods -n items`. metrics-server needs `--kubelet-insecure-tls` on kind (the script adds it). Every pod the HPA selects needs a CPU request. |
| `migrate` Job fails | `kubectl -n items logs job/migrate`. The API stays on the old version. |
| Pod rejected with `violates PodSecurity "restricted"` | The pod spec is missing one of the security settings listed above |
