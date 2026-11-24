# Changelog

All notable changes. Versions follow [Semantic Versioning](https://semver.org/).
Evidence for every phase is in [docs/ROADMAP.md](docs/ROADMAP.md).

## [2.0.0] — 2026-11-24

Portfolio release: everything from v1.4.0 onward (Phases 06–10).

### Breaking

- **Writes need an API key.** `POST`, `PUT`, `PATCH` and `DELETE` need
  `X-API-Key: <key>` or `Authorization: Bearer <key>`. Generate one with
  `scripts/new-api-key.sh` and set its hash in `APP_API_KEY_HASHES`. In `staging` and
  `production`, writes are **refused if no key is configured** (fail closed).
- **New response codes:**
  - A database outage now returns `503 database_unavailable` with `Retry-After`,
    instead of `500`.
  - Requests beyond the per-process concurrency limit get `503 overloaded`.
  - nginx returns `429 rate_limited` above its per-client limits.

### Added

- **Kubernetes** (Phase 06):
  - Kustomize manifests for a kind cluster.
  - Gateway API through Envoy Gateway; ingress-nginx was archived upstream.
  - Probes, HPA, PDB, Pod Security `restricted`, default-deny NetworkPolicies.
  - A migration Job, plus `scripts/k8s-up.sh` and a zero-downtime rollout check
    that runs in CI.
- **Observability** (Phase 07):
  - JSON logs with request IDs, passed through nginx.
  - Prometheus RED metrics by route template.
  - SLO recording rules and multi-window burn-rate alerts, unit-tested with promtool.
  - A provisioned Grafana dashboard (`docker-compose.observability.yml`).
- **Security** (Phase 08):
  - Hashed API keys, security headers, and an HTTPS overlay (TLS 1.2/1.3, HSTS).
  - nginx and Envoy rate limits.
  - Read-only containers with all capabilities dropped.
  - CodeQL and dependency review, and every action pinned to a commit SHA.
  - A STRIDE threat model, a security guide and `SECURITY.md`.
- **Performance and reliability** (Phase 09):
  - A k6 SLO test (100 req/s, gated at p95 < 200 ms) and a capacity ramp.
  - Load shedding (`APP_MAX_CONCURRENT_REQUESTS`).
  - Envoy retries on connect failures, plus outlier ejection.
  - Failure drills (DB restart, pod kill, DB outage) and a weekly Performance workflow.
  - A benchmark report and a recovery runbook.
- **Portfolio release** (Phase 10):
  - Architecture docs with diagrams of each environment, the request lifecycle and
    the pipeline, plus design decisions.
  - `scripts/setup-env.sh` for a one-command local setup.
  - A rewritten README, this changelog, and an MIT licence.

### Changed

- Python 3.15 runtime image without pip, and nginx 1.29.
- `kind` keeps etcd on tmpfs, so local clusters survive slow Docker Desktop disks.
- `scripts/k8s-up.sh` replaces whatever tag the manifests pin, not one hard-coded
  version.

### Fixed

- **Overload:** one process collapsed to 100% timeouts at 600 req/s; load shedding
  now rejects the excess quickly.
- **Route labels:** metric and log labels lost router prefixes
  (`/items/{id}` → `/api/v1/items/{id}`).
- **Error ratio:** it was empty instead of 0 when there were no 5xx responses.
- **Windows scripts:** `openssl` CRLF output corrupted generated keys and passwords.
- **Dev CA:** the certificate lacked `keyUsage` and was rejected by strict TLS
  verification.

## [1.4.0] — 2026-11-22

- **Terraform:**
  - A bootstrap stack: S3 state, GitHub OIDC and a read-only plan role.
  - An app stack: VPC, EC2, data volume, IAM, budget.
  - Deploys over SSM through OIDC, with no SSH.
- Python 3.15 base image; pip removed from the runtime image.

## [1.3.0] — 2026-11-21

- **CI/CD:**
  - CI, Security, Release (multi-arch GHCR images with SBOM and provenance), and Deploy.
  - Branch protection and Dependabot.

## [1.2.0] — 2026-11-21

- PostgreSQL 17 with Alembic migrations, connection pooling, liveness and readiness
  probes, and backup and restore scripts.
- An automated test suite with a coverage gate.

## [1.1.0] — 2026-11-21

- Layered FastAPI package with full CRUD under `/api/v1/items`, validation,
  pagination, one error envelope, and environment configuration.

## [1.0-academic]

- The graded DA510 Assignment 2 submission, preserved unchanged: one FastAPI file,
  SQLite and a manual EC2 deploy.
