# Cloud-Native Backend Infrastructure & Reliability Engineering — Roadmap

This project grows the DA510 Assignment 2 submission (preserved at tag
`v1.0-academic`, see [`academic-submission/`](academic-submission/NOTE.md))
into a production-oriented backend: designed, tested, deployed, monitored,
secured and maintained.

**Rule:** a phase is done only when its acceptance criteria are verified and
the evidence is recorded. Targets below are goals, not results; nothing is
claimed until it has been measured.

Ticket convention: `CBE-P<phase>-<nnn>`, e.g. `CBE-P01-002 — Implement CRUD endpoints`.
Each ticket carries: objective, technical requirements, implementation tasks,
acceptance criteria, test evidence, documentation updates.

## Current state vs. target state

| Capability | Baseline (`v1.0-academic`) | Target |
|---|---|---|
| Backend | Single-file FastAPI | Modular package: api / services / models / schemas / core |
| Database | SQLite | PostgreSQL with migrations |
| Containers | Docker, non-root | Optimized, versioned images |
| Orchestration | Docker Compose | Compose and Kubernetes |
| Cloud | Manual EC2 | Terraform-managed AWS |
| Reverse proxy | Nginx, HTTP | Nginx with HTTPS |
| Testing | Manual curl | Automated unit and integration tests |
| CI/CD | None | GitHub Actions |
| Monitoring | Health check | Prometheus and Grafana |
| Logging | Container stdout | Structured JSON logs, centralized |
| Security | Non-root container | Automated scanning, access controls |
| Scalability | Single instance | Replicas, load-tested |
| Docs | Academic report | Engineering docs, runbooks |

## Phases

### Phase 00 — Repository preparation
- [x] `CBE-P00-001` Preserve the academic submission with tag `v1.0-academic`
- [x] `CBE-P00-002` Create `develop` branch *(GitHub project board: pending)*
- [x] `CBE-P00-003` Define architecture, requirements, acceptance criteria (this file, [`architecture/requirements.md`](architecture/requirements.md))
- [x] `CBE-P00-004` Move reports, screenshots and build scripts to `docs/academic-submission/`

**Acceptance:** original project preserved; backlog established.

### Phase 01 — Backend engineering
- [x] `CBE-P01-001` Restructure into `api`, `services`, `models`, `schemas`, `core`, `database`
- [x] `CBE-P01-002` Full CRUD for items
- [x] `CBE-P01-003` Validation, pagination, consistent error envelope
- [x] `CBE-P01-004` Environment-based configuration (`APP_*` variables, `.env.example`)
- [x] `CBE-P01-005` OpenAPI metadata, tags, examples, documented error responses

**Acceptance:** every endpoint works and appears in `/api/docs` with its error responses.

### Phase 02 — Database engineering
- [x] `CBE-P02-001` PostgreSQL 17 service in Compose, internal only, health-gated
- [x] `CBE-P02-002` Alembic migrations in `migrations/`; one-shot `migrate` service runs before the API; the app no longer creates tables
- [x] `CBE-P02-003` Connection pooling (size, overflow, pre-ping, recycle, connect and statement timeouts); separate liveness and readiness endpoints
- [x] `CBE-P02-004` Database-enforced constraints: `CHECK` on blank names, unique index on `lower(name)`
- [x] `CBE-P02-005` Backup and restore scripts with a [runbook](runbooks/database.md)

**Acceptance:** data persists across restarts; schema changes only via migrations.

**Evidence (2026-11-21):**
- An item created, then `docker compose down` and `up`, was still returned.
- `test_models_match_migrations` passes on PostgreSQL. It compares the ORM models against the migrated schema, including the expression index.
- The suite passed 18/18 on SQLite and on PostgreSQL 17, with 99% coverage.
- Backup → delete → restore returned the deleted item.
- From the host, port 8000 and port 5432 were both unreachable.

### Phase 03 — Automated testing
Unit tests for services, integration tests against PostgreSQL, coverage
reporting, test fixtures, `ruff` lint.
**Acceptance:** coverage ≥ 85%; suite runs with one command.

### Phase 04 — CI/CD
`ci.yml` (lint, test, build), `security.yml` (dependency and image scan),
image push to GHCR with version tags, branch protection, `deploy.yml`.
**Acceptance:** every PR runs the required checks; images are reproducible and tagged.

### Phase 05 — Infrastructure as Code
Terraform for VPC, security groups, EC2 (or ECS), remote state, `plan` in CI.
**Acceptance:** environment created and destroyed from Terraform alone.

### Phase 06 — Kubernetes
Manifests (Deployment, Service, ConfigMap, Secret, Ingress, probes, HPA),
run on kind/minikube first.
**Acceptance:** rolling update with zero failed requests on a local cluster.

### Phase 07 — Observability and SRE
`/metrics` endpoint, Prometheus, Grafana dashboards, structured logs with
request IDs, alert rules, SLOs.
**Acceptance:** latency, error rate and saturation visible; one alert fires in a drill.

### Phase 08 — Security engineering
Dependency and image scanning, secret management, HTTPS, rate limiting,
security headers, authentication for write endpoints, threat model.
**Acceptance:** zero unresolved critical findings; threat model documented.

### Phase 09 — Performance and reliability
Load tests (`tests/performance/`), p95 baseline, replica scaling, failure
injection and recovery runbook.
**Acceptance:** p95 under 200 ms at a defined workload; recovery tested and documented.

### Phase 10 — Portfolio release
Architecture diagrams, benchmark report, runbooks, README polish, `v2.0.0` release.
**Acceptance:** a reviewer can clone, run and understand the system in 15 minutes.

## Success metrics (targets)

| Metric | Target |
|---|---|
| Test coverage | ≥ 85% |
| API p95 latency | < 200 ms under a defined workload |
| CI | All required checks passing |
| Critical vulnerabilities | 0 unresolved |
| API docs | All public endpoints |
| Deployment | Reproducible and automated |
| Persistence | Verified across restarts |
| Recovery | Tested and documented |
| Provisioning | Reproducible through Terraform |

Cost policy: use local Kubernetes and monitoring before provisioning paid AWS resources.
