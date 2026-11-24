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
- [x] `CBE-P05-005` Create and destroy the environment from Terraform alone (as IAM user `yves-admin`)

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

**Evidence (bootstrap applied, 2026-11-22, as IAM user `yves-admin`, not root):**
- **Apply:** `terraform apply` added 11 resources. A follow-up `plan` showed no changes.
- **State bucket:** versioning is on, encryption is AES256, all four public-access blocks are on, and plain HTTP is refused (403).
- **First CI plan failed:** the trust policy rejected the token, because the repo uses GitHub immutable OIDC subjects.
- **Trust fix:** both trust policies now use the immutable subject (an in-place change to one resource).
- **Keyless CI plan:** Infrastructure run 44977505706 assumed the read-only role through OIDC and planned the app stack: 18 to add, 0 to change, 0 to destroy.

**Evidence (app stack create → deploy → destroy, 2026-11-22):**
- **Created:** `terraform apply` added 18 resources at 02:51:32Z. Host `i-0549fd1b713b43ad7` was a t4g.small (arm64) at 100.50.238.252.
- **First boot:** healthy about 70 s later. `/api/health` returned `{"version":"1.4.0","database":"ok"}`.
- **Public smoke test:** `scripts/smoke-test.sh http://100.50.238.252` passed 10/10.
- **Port isolation:** ports 22, 8000 and 5432 were closed from the internet. Only nginx on port 80 answered.
- **Host checks via SSM:** the agent was online, and a read-only Run Command showed:
  - `/data` mounted on its own XFS volume, with `/data/docker` as Docker's data root
  - all three services healthy
  - `.env` with mode `600 root`
  - the first-boot deploy logged as 1.4.0 at `56792f7`
- **Keyless deploy:** Deploy run 44978233395, started from `v1.4.0`, did the following:
  - assumed the deploy role through OIDC
  - checked out `56792f7` on the host and redeployed `sha-56792f7` via SSM Run Command `ce362623…`
  - passed the smoke test on the host and the public health check
- **Destroyed:** `terraform destroy` removed 18 resources by 02:57:07Z, and the state is empty.
- **Independent check in AWS:** the instance is terminated, and no volumes, Elastic IPs, 10.20 VPC, app roles or instance profiles are left.
- **Untouched:** the bootstrap stack and the pre-existing DA510 instances and VPCs.
- **Cost:** about 6 minutes of runtime, a fraction of a cent.

### Phase 06 — Kubernetes
- [x] `CBE-P06-001` Kustomize manifests (`kubernetes/`) for the database, migrations and API:
  - PostgreSQL as a StatefulSet with a PVC
  - the migration Job
  - the API: a Deployment (3 replicas, startup/readiness/liveness probes), its Service, a ConfigMap, and a Secret generated in the cluster
- [x] `CBE-P06-002` Traffic through the **Gateway API**:
  - Envoy Gateway v1.10 serves a `Gateway` plus an `HTTPRoute`
  - ingress-nginx was archived upstream in March 2026, so it isn't used
- [x] `CBE-P06-003` Resilience:
  - rolling update with `maxUnavailable: 0`
  - `preStop` drain and graceful shutdown
  - a PodDisruptionBudget (`minAvailable: 2`) and an HPA (3–6 replicas on CPU)
  - topology spread across nodes
- [x] `CBE-P06-004` Security:
  - Pod Security `restricted` enforced on the namespace (non-root, read-only root filesystem, no capabilities, seccomp)
  - default-deny NetworkPolicies
  - no service-account tokens mounted
  - no secrets in git
- [x] `CBE-P06-005` Automation:
  - `scripts/k8s-up.sh` deploys in a safe order: database, then migrations, then API
  - `scripts/k8s-rolling-update.sh` with `tests/performance/rolling_update_probe.py` checks zero downtime
  - the `kubernetes.yml` workflow runs kubeconform, then a kind deploy, the network-policy check and the zero-downtime rollout on pull requests

**Acceptance:** rolling update with zero failed requests on a local cluster.

**Evidence (local kind v0.33, 3 nodes, 2026-11-22):**
- **Deploy:** PostgreSQL, then the migration Job (Complete), then 3 API replicas spread over both workers.
- **Smoke test:** 10/10 through the Gateway at `127.0.0.1:8088`.
- **Zero-downtime rollout:**

  | | Value |
  |---|---|
  | Change | Rollback `sha-5ac5db8` → `1.4.0`, then a forced `rollout restart`; every pod replaced twice |
  | Traffic | 4 threads of mixed reads and writes for 165 s |
  | Requests | **28,633, 0 failed** (14,316 list, 7,157 create, 7,160 health) |
  | Latency | p50 18.5 ms, p95 45.2 ms, p99 86.3 ms, max 498 ms |

- **Autoscaling:** during that run the HPA scaled 3 → 4 → 5 → 6 replicas on CPU (198% of request against a 70% target), without dropping a request.
- **Earlier run:** the forward update `1.4.0` → `sha-5ac5db8` plus a restart also had 0 failures in 1,749 requests.
  - Its throughput and latency were distorted by Windows resolving `localhost` IPv6-first (2,048 ms against 8.4 ms for `127.0.0.1`).
  - The probe now defaults to `127.0.0.1`.
- **Network policy:**
  - an unlabelled pod could not reach `postgres:5432`
  - the same pod labelled `api` could (positive control)
- **Validation:**
  - kubeconform (strict, including the Gateway API and EnvoyProxy schemas): 16/16 valid
  - actionlint: clean
- **Bug found and fixed:** Envoy Gateway's default `externalTrafficPolicy: Local` meant the kind host port (on the control-plane node) never reached the proxy. It now uses `Cluster`.

### Phase 07 — Observability and SRE
- [x] `CBE-P07-001` Request IDs:
  - taken from the client's `X-Request-ID` (validated) or generated, then echoed back
  - nginx passes them through, so the proxy and app logs share one ID
  - a crash traceback keeps the ID of the request that crashed
- [x] `CBE-P07-002` Structured JSON logs (app and nginx):
  - one access log line per request, with route template, status, duration and client
  - uvicorn's duplicate access log is turned off
- [x] `CBE-P07-003` Prometheus metrics at `/metrics` (internal only):
  - RED by route template: rate, errors and latency histogram
  - saturation: requests in progress, DB pool use, process CPU and memory
  - `app_info` (which build is running)
- [x] `CBE-P07-004` SLOs: 99.5% availability and 95% of requests under 200 ms:
  - recording rules plus multi-window burn-rate alerts
  - `ApiDown` and DB-pool saturation alerts
  - every alert links to a [runbook](runbooks/observability.md) section
  - promtool unit tests, run in CI
- [x] `CBE-P07-005` Prometheus 3.16 and Grafana 13.3:
  - added through `docker-compose.observability.yml`, listening on localhost only
  - Grafana datasource and a 14-panel dashboard are provisioned as code

**Acceptance:** latency, error rate and saturation visible; one alert fires in a drill.

**Evidence (2026-11-22):**
- **Tests:**
  - 90 tests passed, with 99% branch coverage
  - new tests cover request IDs, JSON logs, metric labels by route template (no per-ID series), the 500 path, and logging set-up
  - `promtool test rules` passes 6 scenarios, including a regression test for the zero-errors case
- **Request tracing:** `X-Request-ID: demo-trace-001` was echoed in the response and appeared in both the nginx and API JSON log lines. `/metrics` isn't reachable through nginx.
- **Visibility:** after real traffic, Grafana returned data for **14/14 panels**, including:
  - availability 100%, with error budget 100% left
  - 98% of requests under 200 ms, p95 about 92 ms
  - request rate by route
  - DB pool use, CPU and RSS of about 98 MB
- **Alert drill:**

  | Time (UTC) | Event |
  |---|---|
  | 21:55:09 | API stopped |
  | 21:55:52 | `ApiDown` pending |
  | **21:56:53** | **`ApiDown` firing** |
  | 21:56:58 | API restarted |
  | 21:58:04 | Alert cleared; API returned 200 |

- **Bugs found and fixed:**
  - The route label dropped router prefixes (`/items/{item_id}` instead of `/api/v1/items/{item_id}`).
  - The error ratio showed no data instead of 0 when there were no 5xx responses.
  - `configure_logging` removed handlers it didn't own.
  - Healthchecks used `localhost`, which resolves to IPv6 on Alpine.
- **Open finding for Phase 09:**
  - **What:** on the Compose stack under Docker Desktop, 0.2% of requests (27/12,188) took over 1 s. They came in clusters of 5–7 s stalls in which the server still returned 200.
  - **Ruled out:** PostgreSQL checkpoints and memory pressure.
  - **Leads:** embedded DNS shows p99 lookups of 257 ms.
  - **Not seen on Kubernetes:** max 498 ms over 28,633 requests.

### Phase 08 — Security engineering
- [x] `CBE-P08-001` [Threat model](security/threat-model.md):
  - STRIDE analysis per trust boundary
  - every control, accepted risk and open item recorded
  - plus a [security guide](security/README.md) and a `SECURITY.md` reporting policy
- [x] `CBE-P08-002` API-key authentication on writes:
  - reads stay public; POST, PUT, PATCH and DELETE need a key
  - only SHA-256 hashes are stored, compared in constant time
  - production and staging **fail closed** without keys
  - the key is checked before the request body
  - `scripts/new-api-key.sh` generates keys; rotation is documented
- [x] `CBE-P08-003` Security headers and banner:
  - headers: CSP, `X-Frame-Options`, nosniff, `Referrer-Policy`, CORP, `Permissions-Policy`, `no-store`
  - no `Server` header from the API; nginx `server_tokens off`
- [x] `CBE-P08-004` HTTPS and rate limiting:
  - TLS overlay: TLS 1.2/1.3 only, HSTS, redirect from HTTP
  - nginx per-IP limits: 300 r/s, plus 100 r/s for writes, with a JSON 429 and `Retry-After`
  - body, connection and timeout limits
  - Envoy `BackendTrafficPolicy` on Kubernetes
- [x] `CBE-P08-005` Hardening and scanning:
  - containers run read-only, drop all capabilities, and block privilege escalation
  - CodeQL (Python and Actions) and dependency review on pull requests
  - CI checks the headers, the hardening, and that an anonymous write gets 401

**Acceptance:** zero unresolved critical findings; threat model documented.

**Evidence (2026-11-23):**
- **Findings:**
  - Trivy image: **0 critical**; all 21 HIGH have no upstream fix (`affected` / `fix_deferred`), and each is recorded with a decision in the threat model
  - pip-audit 0, secret scanning 0, Trivy IaC: no unaccepted HIGH or CRITICAL
- **Tests:** 111 pass, with 99.48% branch coverage. New tests cover:
  - all four write methods returning 401 without a key
  - Bearer and header keys, and key rotation
  - fail-closed in staging and production
  - rejected keys logged without the key itself
  - headers on every path, and the docs page exempted from CSP
- **TLS:** with `openssl s_client`, TLS 1.0 and 1.1 were refused and TLS 1.2 and 1.3 negotiated. HTTP gave a 301 to HTTPS, and HSTS was present.
- **Smoke test over HTTPS with a key:** 11/11, including the anonymous write getting 401.
- **Rate limit:** a burst of 4,000 requests at 1,807 req/s gave 1,252 × 200 (≈ 600 burst + 300/s × 2.2 s) and 2,748 × 429 with JSON and `Retry-After`. Service recovered within 3 s.
- **Hardening, inside the running containers:**
  - API: read-only root filesystem, `CapEff` = 0, `NoNewPrivs` = 1, uid 10001
  - nginx: 4 capabilities only
- **Kubernetes:**
  - On kind, the smoke test with the key passed through the Gateway (including the anonymous-write 401), and the `BackendTrafficPolicy` was accepted.
  - The full zero-downtime rollout with auth enabled could not finish locally. The Docker Desktop VM's disk stalls etcd (`slow fdatasync` over 1 s), and the scheduler and controller-manager then crash-loop.
  - `kind.yaml` now keeps etcd on tmpfs. The rollout check runs in the Kubernetes CI workflow on GitHub's Linux runners.
- **Bugs found and fixed:**
  - On Windows, the key script hashed a value ending in `
`.
  - The dev CA lacked `keyUsage`, so Python's strict TLS verification rejected it.
  - nginx needed `CHOWN` to run with a read-only root filesystem.
- **Open, owner action:** delete the AWS root access keys.

### Phase 09 — Performance and reliability
- [x] `CBE-P09-001` Defined workload `tests/performance/k6/load.js`:
  - 100 req/s for 3 min through nginx: 60% read, 25% list, 10% create, 5% update
  - gates on p95 < 200 ms, p99 < 500 ms, and < 0.5% failed requests
- [x] `CBE-P09-002` Capacity ramp `k6/stress.js` (50 → 800 req/s): per-band latency, shed share and served throughput
- [x] `CBE-P09-003` Load shedding:
  - found by the capacity ramp: one process collapsed to 100% timeouts at 600 req/s
  - in-flight cap (64) with an immediate `503 overloaded` + `Retry-After`
  - health checks and `/metrics` exempt; shed requests counted in `http_requests_shed_total`
- [x] `CBE-P09-004` Failure drills `scripts/resilience-drill.sh` (DB restart, API pod kill, DB outage):
  - each drill has pass criteria
  - DB outages now return `503 database_unavailable` instead of `500`
  - Envoy retries connect failures only and ejects failing pods
  - [recovery runbook](runbooks/recovery.md)
- [x] `CBE-P09-005` Performance workflow:
  - runs on clean Linux runners: on dispatch, weekly, and when performance code changes
  - [benchmark report](benchmarks/README.md)

**Acceptance:** p95 under 200 ms at a defined workload; recovery tested and documented.

**Evidence (GitHub runners, 4 vCPU, 2026-11-23/24):**
- **Defined workload, 3 runs:** 18,000 requests each, **0 failed**, p95 **3.0–4.2 ms** (p99 ≤ 4.7 ms).
- **Capacity of one process:** ~300–460 req/s served.
  - Before shedding: 100% timeouts at 600 req/s.
  - After: excess requests got a fast 503, there were zero timeouts, and worst p99 was 350 ms.
- **Drills (all pass):**

  | Drill | Failed | Failure window | Recovery |
  |---|---|---|---|
  | Compose DB restart | 16 of 4,950, all 503 | 0.10 s | — |
  | API pod killed (real kill) | **0** of 5,241 | — | — |
  | DB pod killed | 108 of 4,507 | 3.95 s | 2.8 s after the DB was Ready (SLO 30 s); no API pod restarts, data survived |

- **Bugs found and fixed during the phase:**
  - throughput collapse with no load shedding
  - DB errors returned as 500 instead of 503
  - a closed-loop probe tripped the rate limiter and faked an 85% failure rate
  - `kubectl delete --force` faked a zero-failure DB outage and risked two PostgreSQL instances on one volume
- **Phase 07 open finding, closed:** the 5–7 s stalls didn't occur on Linux (max 26.5 ms over 18,001 requests).
  - On Docker Desktop, fsync p50 is ~6 ms, and etcd logged `slow fdatasync` over 1 s, which points to VM storage.
  - kind now keeps etcd on tmpfs.

### Phase 10 — Portfolio release
- [x] `CBE-P10-001` [Architecture docs](architecture/README.md): diagrams of the application, request lifecycle, Compose, Kubernetes, AWS and the pipeline, plus a design-decision table. Every diagram is checked with mermaid-cli.
- [x] `CBE-P10-002` Benchmark report and runbooks (database, CI/CD, infrastructure, Kubernetes, observability, recovery, security)
- [x] `CBE-P10-003` README rewritten for reviewers:
  - what it demonstrates, with evidence
  - a quick start, measured results and a documentation index
  - `scripts/setup-env.sh` for one-command local setup
- [x] `CBE-P10-004` `CHANGELOG.md`, MIT `LICENSE`, version 2.0.0
- [x] `CBE-P10-005` Release `v2.0.0`: pull request to `main`, tag, GitHub release
  - PR #7 merged to `main` as `6699309` with every check passing; tag `v2.0.0` pushed.
  - The Release workflow published `ghcr.io/alan-911/cloud-computing` `2.0.0`, `2.0` and `latest` (one digest, `sha256:333a60f2…`).
  - The pulled `2.0.0` image reports `version: 2.0.0` on `/api/health` and in `app_info`; `gh attestation verify` passes.
  - GitHub Release published: https://github.com/Alan-911/Cloud-Computing/releases/tag/v2.0.0

**Acceptance:** a reviewer can clone, run and understand the system in 15 minutes.

**Evidence (2026-11-24):**
- A fresh clone of `761bcc3` was run following the README word for word.
- Timeline:

  | Step | Elapsed |
  |---|---|
  | `git clone` | 3 s |
  | `scripts/setup-env.sh` | 4 s |
  | `docker compose up -d --build --wait` | 54 s |
  | `scripts/smoke-test.sh`, 11/11 | 55 s |

- The README's "try it" commands worked: health 200 (v2.0.0), create with key 201, without key 401, `/api/docs` 200.
- **55 s from clone to a verified system.** Base images were cached locally; a cold machine adds about 2–5 min of image pulls, still within 15 min.
- The test ran under its own Compose project (`qs-review`) so it couldn't touch the existing stack's volume.
- All 7 Mermaid diagrams (6 architecture, 1 README) render with mermaid-cli 11.4.2.

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
