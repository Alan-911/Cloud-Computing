# Security guide

What protects the API, how to operate it, and how to check it. The reasoning,
accepted risks and open items are in the [threat model](threat-model.md).

## API keys (write access)

Reads are public. `POST`, `PUT`, `PATCH` and `DELETE` need a key:

```bash
curl -X POST https://localhost/api/v1/items \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" -d '{"name":"x"}'
# or: -H "Authorization: Bearer $API_KEY"
```

**Issue a key:**

```bash
scripts/new-api-key.sh
# API_KEY=cbe_…              → give it to the client; shown once, store it in a secret manager
# APP_API_KEY_HASHES=…        → set it on the server
```

Where the server-side hash lives:

| Deployment | Location |
|---|---|
| Compose | `APP_API_KEY_HASHES` in `.env` |
| Kubernetes | Secret `api-auth`, created by `scripts/k8s-up.sh`, which writes the key to `.k8s-api-key` |
| EC2 | `/data/secrets/app.env`, generated on first boot. The key is in `/data/secrets/api.key` (root only) |

**Rotate without downtime:**
1. Add the new hash next to the old one: `APP_API_KEY_HASHES=<old>,<new>`. Then restart or roll the API.
2. Move clients to the new key.
3. Remove the old hash and roll again.

**Policy:**
- The server stores only SHA-256 hashes.
- Comparison takes the same time whether a key is wrong early or late.
- In `staging` and `production`, every write is **refused if no key is configured** (fail closed).
- In `development` and `test` without keys, writes are open for convenience.
- Rejected keys are logged with an 8-character prefix, never in full.

## HTTPS

```bash
scripts/dev-cert.sh   # local CA plus a certificate for localhost and 127.0.0.1, in nginx/certs/ (git-ignored)
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --wait
curl --cacert nginx/certs/dev-ca.pem https://localhost/api/health
# Windows curl (Schannel) also needs --ssl-no-revoke, because a local CA has no revocation list.
```

What the HTTPS setup does:
- **Port 80** only redirects to HTTPS.
- **Port 443** allows TLS 1.2 and 1.3 only, with forward-secret AEAD ciphers (Mozilla "intermediate" profile), and sends HSTS.
- **For a public deployment** you need a domain name, then either:
  - a Let's Encrypt certificate on nginx, with 443 opened in the Terraform security group, or
  - AWS Certificate Manager on a load balancer.

## Rate limits

| Layer | Limit | Over the limit |
|---|---|---|
| nginx (Compose, EC2) | 300 req/s per client IP (burst 600). Writes: 100 req/s per IP (burst 200). 100 connections per IP. | `429` with the JSON `rate_limited` error and `Retry-After: 1` |
| Envoy Gateway (Kubernetes) | 2,000 req/s per route per proxy replica (`BackendTrafficPolicy`) | `429` |

nginx also caps request bodies at 64 KB and drops slow clients after 10 s.

## Security headers

The API sets these on every response:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'`. Skipped on the docs pages, which load from a CDN and are disabled in production.
- `Referrer-Policy: no-referrer`
- `Cross-Origin-Resource-Policy: same-origin`
- `Permissions-Policy`
- `Cache-Control: no-store`

There's no `Server` header from the API, and nginx hides its version. nginx adds HSTS on HTTPS.

## Container hardening

| Container | Settings |
|---|---|
| API, migrate | Non-root (UID 10001), read-only root filesystem, **all capabilities dropped**, `no-new-privileges`, `/tmp` on tmpfs. No pip in the image. |
| nginx | Read-only root filesystem. Capabilities: only `NET_BIND_SERVICE`, `SETUID`, `SETGID`, `CHOWN`. `no-new-privileges`. |
| PostgreSQL | `no-new-privileges`. Not published to the host. |
| Kubernetes | Pod Security `restricted` enforced. Default-deny NetworkPolicies. No service-account tokens. |

## Automated checks

| Check | When | Fails on |
|---|---|---|
| CodeQL (Python and GitHub Actions) | Every push, pull request and weekly | Findings appear in the Security tab |
| Dependency review | Pull requests | New dependencies with HIGH+ vulnerabilities, or AGPL/GPL-3.0 licences |
| pip-audit | Every push, pull request and weekly | Any known vulnerability |
| Trivy filesystem (vulnerabilities, secrets, IaC misconfiguration) | Every push, pull request and weekly | Fixable HIGH or CRITICAL findings |
| Trivy image | Every push, pull request and weekly | Fixable HIGH or CRITICAL findings |
| CI image smoke test | Every pull request | Missing headers, server version shown, writable root filesystem, an anonymous write not getting 401 |

## Reporting a vulnerability

Open a private security advisory (Security → Advisories → Report a vulnerability).
Don't open a public issue.
