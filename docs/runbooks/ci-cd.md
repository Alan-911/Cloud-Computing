# Runbook — CI/CD

## Pipeline at a glance

```
pull request ──▶ CI ─────────────────────────┐   required checks before merge
               ├─ Lint (ruff)                │
               ├─ Tests (sqlite)             │
               ├─ Tests (postgres)           │
               └─ Image build and smoke test ┘
             ──▶ Security (pip-audit, Trivy fs, Trivy image)

push develop / main / tag vX.Y.Z ──▶ Release: CI (same jobs) ──▶ build amd64+arm64
                                                              ──▶ push to GHCR + SBOM + provenance

manual ──▶ Deploy (environment: production) ──▶ SSH to EC2 ──▶ pull sha-<commit> ──▶ compose up --wait ──▶ smoke test
```

| Workflow | File | Trigger |
|---|---|---|
| CI | `.github/workflows/ci.yml` | Pull requests, manual, called by Release |
| Security | `.github/workflows/security.yml` | Push to main/develop, pull requests, Mondays 06:17 UTC, manual |
| Release | `.github/workflows/release.yml` | Push to main/develop, tags `v*.*.*`, manual |
| Deploy | `.github/workflows/deploy.yml` | Manual only |
| Dependabot | `.github/dependabot.yml` | Weekly PRs to develop |

## What each CI job proves

- **Lint:** `ruff check` and `ruff format --check`.
- **Tests (sqlite / postgres):** the full suite, with the schema built by the real migrations and an 85% branch-coverage gate. Coverage and JUnit reports are kept as artifacts for 14 days.
- **Image build and smoke test:** builds the image, then starts db, migrate, api and nginx with `--wait`. It then checks the following through nginx:
  - `scripts/smoke-test.sh` passes against every endpoint.
  - Ports 8000 and 5432 are not reachable from the host.
  - Data survives `down` / `up`.

## Image tags

Images live at `ghcr.io/alan-911/cloud-computing`.

| Event | Tags |
|---|---|
| Push to develop | `develop`, `sha-<short>` |
| Push to main | `main`, `sha-<short>` |
| Tag `v1.4.0` | `1.4.0`, `1.4`, `latest`, `sha-<short>` |

- **Deploy with `sha-<short>`:** branch tags move, but a SHA tag always names the same tested build.
- **Version:** `/api/health` reports the image version, set from the tag at build time.
- **Supply chain:** every image carries an SBOM and a signed build-provenance attestation. To verify one:

```bash
gh attestation verify oci://ghcr.io/alan-911/cloud-computing:1.4.0 --owner Alan-911
```

## Cut a release

1. Bump `version` in `pyproject.toml` and `app/core/config.py` (a unit test checks that they match).
2. Merge `develop` into `main` through a pull request.
3. Tag and push the tag. The workflow refuses a tag that doesn't match the code version.

```bash
git tag -a v1.4.0 -m "v1.4.0" && git push origin v1.4.0
```

## Deploy and roll back

Actions → **Deploy** → *Run workflow*, and pick the branch or tag. The workflow then:

1. Checks that the image for that exact commit exists.
2. Over SSH, checks out the same commit on the host.
3. Runs `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --wait`.
4. Runs the smoke test on the host and appends the deploy to `~/deploy-history.log`.

To roll back, run Deploy again from the previous tag or commit. Database migrations only move forward. Write them so the previous image still works with the new schema: expand first, contract in a later release.

One-time setup, in Settings → Environments → `production`:

- **Secrets:** `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`.
- **Variable:** `APP_URL`.
- **Approval (optional):** required reviewers, so every deploy needs a human.
- **Registry access:** if the GHCR package is private, run `docker login ghcr.io` once on the host with a read-only token, or make the package public.

## Branch protection (applied 2026-11-21)

Required checks on both branches: *Lint*, *Tests (sqlite)*, *Tests (postgres)*, *Image build and smoke test*.

| Branch | Pull request | Checks up to date | Applies to admins | Force-push / delete |
|---|---|---|---|---|
| `main` | Required (0 approvals: solo project), conversations resolved | Yes (strict) | **Yes**: nobody pushes to main directly | Blocked |
| `develop` | Not required | No | No: the owner can push directly; everyone else, including Dependabot, must pass CI | Blocked |

So code reaches `main` only through a pull request from `develop` whose checks
are green. To raise `develop` to the same bar later:

```bash
gh api -X PUT repos/Alan-911/Cloud-Computing/branches/develop/protection/enforce_admins
```

## When CI fails

| Job | First look |
|---|---|
| Lint | Run `ruff check --fix . && ruff format .` locally. |
| Tests | Download the `test-results-*` artifact and reproduce with `scripts/test.sh --postgres`. |
| Image smoke test | The failed run prints `docker compose logs`. Reproduce with `docker compose up -d --build --wait && scripts/smoke-test.sh`. |
| Trivy image | Usually an OS package fixed upstream: re-run (the build applies Debian updates), or bump the base image. |
| pip-audit | Bump the pinned package in `app/requirements.txt`, or wait for the Dependabot PR. |
