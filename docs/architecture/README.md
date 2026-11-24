# Architecture

The same container image runs in three environments. The Compose and Kubernetes
setups are exercised on every pull request, and the AWS one was created, deployed to
and destroyed from Terraform. Requirements are in [requirements.md](requirements.md).

## 1. The application

```mermaid
flowchart LR
    C([Client]) -->|HTTPS / HTTP| P[nginx or Envoy Gateway<br/>TLS, rate limits, request IDs]
    P -->|/api/*| M

    subgraph API["FastAPI process (non-root, read-only FS)"]
        direction TB
        M[Middleware<br/>observability → security headers → load shedding] --> R[Routes<br/>/api/health, /api/v1/items]
        R -->|writes| A{API key<br/>SHA-256 hash}
        R --> S[Services<br/>business rules]
        A --> S
        S --> O[SQLAlchemy models<br/>pooled connections]
    end

    O -->|5432| D[(PostgreSQL 17)]
    MIG[migrate job<br/>alembic upgrade head] -->|before every rollout| D
    PR[Prometheus] -.->|scrapes /metrics<br/>internal only| M
```

| Layer | Responsibility |
|---|---|
| Middleware | Request IDs, JSON access logs, RED metrics; security headers; load shedding (fast 503 beyond 64 in flight) |
| Routes (`app/api`) | HTTP only: validation by Pydantic schemas, API-key check on writes, documented error responses |
| Services (`app/services`) | Business rules: case-insensitive uniqueness, not-found, conflicts |
| Data (`app/models`, `app/database`) | ORM models, pooled engine with pre-ping and timeouts; schema owned by Alembic |
| Errors (`app/core/errors.py`) | One envelope `{"error": {code, message, details}}`; DB outage → 503, never 500 |

## 2. Request lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant N as nginx
    participant A as API
    participant D as PostgreSQL
    C->>N: POST /api/v1/items (X-API-Key)
    N->>N: per-IP rate limit (300/s, writes 100/s)
    N->>A: proxy + X-Request-ID
    A->>A: in-flight < 64? else 503 overloaded
    A->>A: API key hash matches? else 401 (before body validation)
    A->>A: validate body (Pydantic) else 422
    A->>D: INSERT (unique lower(name)) 
    alt name taken
        D-->>A: IntegrityError
        A-->>C: 409 conflict
    else database down
        D-->>A: OperationalError
        A-->>C: 503 database_unavailable, Retry-After: 2
    else ok
        D-->>A: row
        A-->>C: 201 + Location + X-Request-ID + security headers
    end
    Note over N,A: nginx and API log the same request_id as JSON,<br/>metrics recorded by route template
```

## 3. Local stack (Docker Compose)

```mermaid
flowchart LR
    U([Browser / curl]) -->|80, 443| NG[nginx<br/>read-only, 4 caps]
    subgraph net[Compose network]
        NG --> API[api<br/>read-only, 0 caps]
        API --> DB[(db<br/>pgdata volume)]
        MG[migrate<br/>one-shot] --> DB
        PR[prometheus] --> API
        GF[grafana] --> PR
    end
    U -.->|127.0.0.1:3000| GF
    U -.->|127.0.0.1:9090| PR
```

`docker-compose.yml` is the base; overlays add HTTPS (`docker-compose.tls.yml`),
Prometheus and Grafana (`docker-compose.observability.yml`), and the published image
for servers (`docker-compose.prod.yml`). Start order: `db` healthy → `migrate`
completed → `api` healthy → `nginx`.

## 4. Kubernetes (kind locally and in CI)

```mermaid
flowchart TB
    U([Client]) -->|localhost:8088| GW
    subgraph egs[envoy-gateway-system]
        GW["Gateway: public<br/>Envoy: rate limit 2000/s, retry on connect-failure,<br/>outlier ejection"]
    end
    subgraph items["namespace items: Pod Security restricted, default-deny NetworkPolicy"]
        RT[HTTPRoute /api] --> SVC[Service api]
        SVC --> P1[api pod] & P2[api pod] & P3[api pod]
        HPA["HPA: 3 to 6 on CPU"] -.-> P1
        PDB["PDB: minAvailable 2"] -.-> P2
        P1 & P2 & P3 -->|NetworkPolicy| PG[("postgres-0<br/>StatefulSet + PVC")]
        JOB[migrate Job] --> PG
    end
    GW --> RT
```

Rollouts are zero-downtime (`maxUnavailable: 0`, readiness on DB health, `preStop`
drain); verified under load in CI. Details: [Kubernetes runbook](../runbooks/kubernetes.md).

## 5. AWS (Terraform)

```mermaid
flowchart LR
    GH[GitHub Actions] -->|OIDC, no stored keys| IAM[IAM roles<br/>plan: read-only<br/>deploy: SSM on one instance]
    IAM -->|SSM Run Command| EC2
    subgraph vpc["VPC 10.20.0.0/16 (one public subnet)"]
        EC2[EC2 t4g.small, AL2023<br/>IMDSv2, encrypted root<br/>Compose stack] --- EBS[(EBS /data<br/>Docker data + secrets)]
    end
    NET([Internet]) -->|80 only| EIP[Elastic IP] --> EC2
    EC2 -->|443 out| GHCR[(GHCR images)]
    S3[(S3 state bucket<br/>versioned, TLS-only)] -.- TF[Terraform]
```

Bootstrap stack: state bucket, GitHub OIDC provider, read-only plan role. App stack:
network, instance, data volume, deploy role, optional budget alarm. No SSH (port 22
closed; shell via Session Manager). Cost ≈ $18/month while it exists. Details:
[infrastructure runbook](../runbooks/infrastructure.md).

## 6. Delivery pipeline

```mermaid
flowchart LR
    PRQ[Pull request] --> CI["CI: lint, tests on SQLite and PostgreSQL,<br/>image build, smoke and hardening checks,<br/>promtool"]
    PRQ --> SEC["Security: CodeQL, pip-audit,<br/>Trivy fs and image, dependency review"]
    PRQ --> K8S["Kubernetes: kubeconform,<br/>kind deploy, zero-downtime rollout"]
    PRQ --> INF["Infrastructure: fmt, validate,<br/>tflint, read-only plan"]
    CI & SEC & K8S & INF --> MAIN{{"main: PR + 4 required checks"}}
    MAIN --> REL["Release: CI again, then multi-arch image<br/>to GHCR with SBOM and provenance"]
    REL --> DEP["Deploy: manual, environment gate<br/>OIDC, then SSM, then smoke test"]
    PERF["Performance, weekly:<br/>k6 SLO test, capacity, failure drills"] -.-> MAIN
```

Every action is pinned to a commit SHA; Dependabot keeps them current.
Details: [CI/CD runbook](../runbooks/ci-cd.md).

## 7. Design decisions

| Decision | Why | Trade-off |
|---|---|---|
| Alembic owns the schema; app never calls `create_all` | Reviewable, reversible schema changes; a drift test fails CI if models and migrations differ | One more step on deploy (the `migrate` job) |
| API keys stored as SHA-256 hashes | Keys are 256-bit random, so a fast hash is safe; no plaintext secrets on servers | Key rotation is manual (documented) |
| Fail closed in production without keys | A missing secret can never open writes | Misconfiguration blocks writes until fixed |
| Load shedding at 64 in flight per process | Overload degrades gracefully instead of collapsing (measured: 100% timeouts → fast 503s) | Some requests rejected at peak; clients must honour `Retry-After` |
| Gateway API (Envoy) instead of Ingress | ingress-nginx was archived in March 2026 | Extra CRDs on the cluster |
| Liveness independent of the database | A DB outage must not restart API pods (verified in drills) | Readiness carries the DB signal |
| One host on AWS, no NAT gateway | Lowest cost for a portfolio environment (~$18/month) | No HA; Kubernetes covers replicas |
| SSM instead of SSH | No open port 22, no keys to leak; access is IAM-audited | Needs the SSM agent and IAM setup |
| Numbers measured on GitHub runners | Reproducible; the dev laptop's Docker VM has slow fsync | Runner-to-runner variance (reported as ranges) |
