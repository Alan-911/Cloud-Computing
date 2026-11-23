# Threat model — Items API

Method: STRIDE per trust boundary. Reviewed 2026-11-23 (Phase 08).
Scope: the API, its database, the Compose/EC2 and Kubernetes deployments, and the
CI/CD supply chain. Out of scope: the developer workstation, and GitHub's and AWS's
own infrastructure.

## System and trust boundaries

```
 Internet ──(B1)──▶ nginx / Envoy Gateway ──(B2)──▶ API pods ──(B3)──▶ PostgreSQL
 (anonymous          TLS, rate limits,           auth on writes,      internal only,
  clients)           request IDs                  validation           NetworkPolicy

 Operators ──(B4)──▶ AWS (SSM, IAM)        GitHub Actions ──(B5)──▶ GHCR images ──▶ hosts
 (yves-admin, MFA)                         (OIDC, no stored keys)    (SBOM, provenance)
```

| Asset | Why it matters |
|---|---|
| Item data in PostgreSQL | Integrity: only authorised clients may change it |
| API write keys | They grant write access. Only SHA-256 hashes are stored server-side |
| Database password | Generated in the cluster or on the host, never in git or Terraform state |
| Container images | Everything that runs comes from them |
| AWS account | Billing, and the blast radius of a compromise |

## STRIDE analysis

| # | Threat | Boundary | Mitigation (status) | Residual risk |
|---|---|---|---|---|
| S1 | **Spoofing.** An anonymous client creates, changes or deletes data | B1–B2 | API keys required on POST/PUT/PATCH/DELETE. Keys are compared as SHA-256 hashes in constant time. Staging and production **fail closed** when no key is configured. Auth runs before body validation. (**Done**) | Keys are bearer tokens, so a leaked key works until rotated. Rotation: add a new hash, migrate clients, remove the old hash. |
| S2 | Spoofing the deploy pipeline to push code to hosts | B5 | GitHub OIDC with the immutable subject (`repo:Alan-911@136555079/Cloud-Computing@1400158294`). The deploy role is limited to `environment:production` and one instance. No stored AWS keys. (**Done**) | A compromised GitHub account with production-environment access. Mitigate with environment reviewers and 2FA. |
| S3 | Spoofing operators in AWS | B4 | IAM user `yves-admin` with MFA. Root not used for day-to-day work. (**Done**) Root access keys **still exist** (**Open**, owner action) | Root keys on a workstation. Delete them. |
| T1 | **Tampering** with data in transit | B1 | TLS 1.2/1.3 only (TLS 1.0/1.1 refused, verified), AEAD ciphers, HSTS, HTTP→HTTPS redirect (`docker-compose.tls.yml`). (**Done locally**) | The EC2 path serves HTTP only, because there's no domain for a public certificate yet. |
| T2 | Tampering with images or dependencies (supply chain) | B5 | Third-party actions pinned to commit SHAs. Images built only after CI passes, with SBOM and signed provenance. pip-audit, Trivy and dependency review on pull requests. Dependabot. Branch protection on `main`. (**Done**) | A compromised upstream package before it's flagged |
| T3 | SQL injection | B2–B3 | SQLAlchemy ORM with bound parameters only. CodeQL runs on every change. Pydantic validation with `extra="forbid"`. (**Done**) | — |
| T4 | Tampering with a running container | host | Read-only root filesystem, all capabilities dropped, `no-new-privileges`, non-root UID 10001. The Pod Security `restricted` standard is enforced on Kubernetes. (**Done**) | PostgreSQL keeps default capabilities, because its entrypoint switches user |
| R1 | **Repudiation.** Can't trace who did what | B2 | Every request has an ID (client or generated), logged as JSON by nginx and the API. Rejected keys are logged with an 8-character prefix, never the full key. (**Done**) | There's no per-key identity in logs yet (keys aren't named). No central, tamper-evident log store. |
| I1 | **Information disclosure** through errors | B2 | One error envelope. Unexpected errors return a generic 500. Tracebacks go only to server logs. Anonymous callers get 401 before any schema detail. (**Done**) | — |
| I2 | Disclosure through headers or banners | B1 | `server_tokens off`. Uvicorn sends no `Server` header. `X-Content-Type-Options`, `X-Frame-Options: DENY`, a strict CSP, `Referrer-Policy`, CORP, `Permissions-Policy`, `Cache-Control: no-store`. (**Done**) | nginx still identifies itself as `nginx`, without a version |
| I3 | Metrics or internals reachable from outside | B1 | `/metrics` is served only on the app port. nginx returns 404, and the Gateway routes `/api` only. PostgreSQL, Prometheus and Grafana are never public (Grafana and Prometheus bind 127.0.0.1). (**Done**) | — |
| I4 | Secrets in git, images or Terraform state | all | Generated in place (`.env`, k8s Secrets, the `/data/secrets` volume). git-ignored. Trivy secret scan and GitHub secret scanning show 0 open alerts. (**Done**) | Plaintext `.env` on hosts (root-only, 600) |
| D1 | **Denial of service** by request floods | B1 | nginx per-IP limits: 300 r/s, plus 100 r/s for writes, with bursts and a JSON 429 with `Retry-After` (verified). Connection cap and slow-client timeouts. Envoy local limit of 2,000 r/s per route. 64 KB body limit. (**Done**) | A distributed flood from many IPs needs an upstream WAF or CDN (not in scope) |
| D2 | Resource exhaustion inside | B2–B3 | DB pool limits and statement timeout (5 s). Kubernetes resource limits, PDB and HPA. A pool-saturation alert. (**Done**) | — |
| E1 | **Elevation of privilege** from the app process | host | Non-root, no capabilities, read-only filesystem, seccomp `RuntimeDefault` (k8s). IMDSv2 with hop limit 1, so containers can't reach instance credentials. The instance role allows SSM only. (**Done**) | — |
| E2 | Lateral movement in the cluster | B3 | Default-deny NetworkPolicies: only gateway→api:8000 and api/migrate→postgres:5432 (verified with a blocked pod and a positive control). No service-account tokens mounted. (**Done**) | — |

## Findings and decisions

Scanner state on `develop` (Phase 08):

| Source | Critical | High | Decision |
|---|---|---|---|
| Trivy image (current build) | **0** | 21 packages, **0 fixable** | See below |
| Trivy filesystem and IaC | 0 | 0 | Two accepted with inline reasons ([infrastructure runbook](../runbooks/infrastructure.md#accepted-scanner-findings)) |
| pip-audit | 0 | 0 | — |
| Secret scanning | 0 | 0 | — |

**Accepted: unfixed HIGH CVEs in Debian base-image packages.**
- **What:** every HIGH finding in the image is marked `affected` or `fix_deferred` by Debian, meaning no fixed package exists.
- **Packages the app never runs:** `util-linux`, `mount`, `login`, `bsdutils`, `ncurses`, `perl-base`. The container drops all capabilities and has a read-only filesystem, so these tools can't mount, log in or escalate.
- **Libraries the app does load:**
  - `libssl3`/`openssl`, used by psycopg's TLS (the database link is internal and doesn't use TLS).
  - `libsqlite3`, loaded by Python. The production path uses PostgreSQL.
- **Control:** the build runs `apt-get upgrade`, so fixes land on the next build once Debian publishes them. The Trivy gate (fixable HIGH/CRITICAL) fails CI as soon as a fix exists, and the weekly scheduled scan catches new ones.
- **Re-evaluate:** at each release, or sooner if any becomes fixable or is rated critical.
- **Option considered:** a distroless or minimal Python base. Deferred, because no maintained distroless image exists for Python 3.15 yet.

## Open items

| Item | Owner | Plan |
|---|---|---|
| Delete AWS root access keys | Account owner | IAM → Security credentials (root) |
| Public HTTPS on EC2 | Phase 10 or later | Needs a domain. Then ACM and an ALB, or Let's Encrypt on nginx; open 443 in the security group. |
| Named keys / per-client identity | Later | Key IDs in logs; consider OAuth2 client credentials if more clients appear |
| Alert delivery | Later | Alertmanager to email or chat (see the observability runbook) |
| Request stalls on Docker Desktop | Phase 09 | Performance investigation (not a security issue) |
