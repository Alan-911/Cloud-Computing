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
- [x] `CBE-P03-001` Unit tests with no database: schemas, error envelope, config, engine options
- [x] `CBE-P03-002` Integration tests: the service layer, the HTTP API, migrations, and concurrent duplicate creates
- [x] `CBE-P03-003` The same suite runs on SQLite or on PostgreSQL (`TEST_DATABASE_URL`)
- [x] `CBE-P03-004` Shared fixtures (`clean_db`, `db_session`, `item_factory`), branch coverage, an 85% gate, and any new warning fails the run
- [x] `CBE-P03-005` One command, `scripts/test.sh [--postgres]`, runs ruff, the format check, and pytest with coverage

**Acceptance:** coverage ≥ 85%; suite runs with one command.

**Evidence (2026-11-21):**
- `scripts/test.sh` passed 62/62 on SQLite.
- `scripts/test.sh --postgres` passed 62/62 on PostgreSQL 17.
- Branch coverage was 99.67%, with no warnings.
- With the gate raised to 100%, the run exits 1, so the gate is enforced.

### Phase 04 — CI/CD
- [x] `CBE-P04-001` `ci.yml`: lint, tests on SQLite and PostgreSQL, image build with a Compose smoke test (port isolation, persistence across restart)
- [x] `CBE-P04-002` `security.yml`: pip-audit, plus Trivy scans of the repo (vulnerabilities, secrets, misconfiguration) and the image. Fails on fixable HIGH/CRITICAL findings, reports to the Security tab, and runs weekly.
- [x] `CBE-P04-003` `release.yml`: only after CI passes, publishes multi-arch images to GHCR with branch, SHA and semver tags, an SBOM and signed provenance. Rejects a tag that doesn't match the code version.
- [x] `CBE-P04-004` Branch protection:
  - `main` requires a PR plus the four CI checks, admins included.
  - `develop` requires the checks and blocks force-push and deletion.
  - Details in the [runbook](runbooks/ci-cd.md).
- [x] `CBE-P04-005` `deploy.yml`: manual, through the `production` environment. Deploys the image for the selected commit over SSH, runs the smoke test, and rolls back by redeploying an earlier ref. Also adds Dependabot and a PR template.

**Acceptance:** every PR runs the required checks; images are reproducible and tagged.

**Evidence (local, 2026-11-21):**
- actionlint is clean on all workflows.
- `pip-audit` and Trivy (image and repo) are clean after the image build applies Debian security updates. The first image scan caught CVE-2026-85091 in zlib, which the update fixed.
- `docker compose up --wait` with the one-shot migrate service works, and `scripts/smoke-test.sh` passes 10/10.
- The production override refuses to run without `IMAGE_TAG`.

**Evidence (GitHub Actions, commit `e95860d`, 2026-11-21):**
- Release run 44938906150 passed every job:

  | Job | Time |
  |---|---|
  | Lint | 23 s |
  | Tests (sqlite) | 37 s |
  | Tests (postgres) | 38 s |
  | Image build and smoke test | 74 s |
  | Build and push image | 210 s |

- Security run 44938906271 passed pip-audit, Trivy fs and Trivy image.
- The image was published as `ghcr.io/alan-911/cloud-computing:develop` and `:sha-e95860d` for linux/amd64 and linux/arm64, with provenance and SBOM manifests. Its digest is `sha256:f6fb37f5…`.

### Phase 05 — Infrastructure as Code
- [x] `CBE-P05-001` Bootstrap stack:
  - an S3 remote state bucket (versioned, encrypted, private, TLS-only, S3 lock files)
  - the GitHub OIDC provider
  - a read-only plan role
- [x] `CBE-P05-002` App stack:
  - a dedicated VPC and public subnet
  - a security group allowing inbound 80 and outbound 443 only
  - an EC2 host (t4g.small arm64, Amazon Linux 2023, IMDSv2 only, encrypted)
  - a separate data volume and an Elastic IP
  - an optional budget alert
- [x] `CBE-P05-003` Deploy through SSM Run Command:
  - deploys assume a GitHub OIDC role scoped to the one instance and the `production` environment
  - no SSH and no stored keys
  - `scripts/deploy-on-host.sh` is shared by the first boot and the Deploy workflow
- [x] `CBE-P05-004` Infrastructure workflow:
  - `fmt`, `validate` and `tflint` on every change
  - a read-only `plan` once the bootstrap variables are set
  - Trivy checks the Terraform for misconfiguration
- [ ] `CBE-P05-005` Create and destroy the environment from Terraform alone *(needs owner approval and an administrator IAM identity; the account currently uses root keys)*

**Acceptance:** environment created and destroyed from Terraform alone.

**Evidence (local, 2026-11-21):**
- `terraform fmt`, `validate` and `tflint` (with the AWS ruleset) are clean on both stacks.
- Trivy config has no unaccepted HIGH or CRITICAL findings. The two it raised were handled as follows:
  - Outbound traffic narrowed to TCP 443.
  - The state bucket's AWS-managed encryption accepted with a documented reason.
- `terraform plan` against the account (read-only) gave:
  - bootstrap: 11 to add, 0 to change, 0 to destroy
  - app: 18 to add, 0 to change, 0 to destroy
- No existing resources are touched.
- The estimated cost is about $18.31/month: [runbook](runbooks/infrastructure.md).

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
