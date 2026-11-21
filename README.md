# Cloud-Native Backend Infrastructure

[![CI](https://github.com/Alan-911/Cloud-Computing/actions/workflows/release.yml/badge.svg?branch=develop)](https://github.com/Alan-911/Cloud-Computing/actions/workflows/release.yml)
[![Security](https://github.com/Alan-911/Cloud-Computing/actions/workflows/security.yml/badge.svg?branch=develop)](https://github.com/Alan-911/Cloud-Computing/actions/workflows/security.yml)

A FastAPI items service on PostgreSQL behind an Nginx reverse proxy, being
developed in phases from a graded cloud-computing assignment into a
production-oriented backend: tested, containerized, automated, observable and secure.

- **Roadmap and status:** [`docs/ROADMAP.md`](docs/ROADMAP.md)
- **Requirements and architecture:** [`docs/architecture/requirements.md`](docs/architecture/requirements.md)
- **Database runbook (migrations, backup, restore):** [`docs/runbooks/database.md`](docs/runbooks/database.md)
- **CI/CD runbook (pipeline, releases, deploy, rollback):** [`docs/runbooks/ci-cd.md`](docs/runbooks/ci-cd.md)
- **Original academic submission:** tag `v1.0-academic`, files in [`docs/academic-submission/`](docs/academic-submission/NOTE.md)

```
client ──▶ :80 nginx ──▶ api:8000 FastAPI ──▶ db:5432 PostgreSQL ──▶ pgdata volume
           (published)    (internal, non-root)   (internal)
                              ▲
             migrate ─────────┘  one-shot `alembic upgrade head` before api starts
```

## Status

| Phase | State |
|---|---|
| 00 Repository preparation | Done (project board pending) |
| 01 Backend engineering | Done |
| 02 Database engineering | Done |
| 03 Automated testing | Done |
| 04 CI/CD | Done (branch protection pending) |
| 05–10 | Planned |

## API

Base path `/api`. Interactive docs at `/api/docs` (disabled when
`APP_ENVIRONMENT=production` unless `APP_DEBUG=true`).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health/live` | Liveness: the process is up (never touches the database) |
| GET | `/api/health` | Readiness: version and database reachability, 503 if the database is down (also `/api/health/ready`) |
| GET | `/api/v1/items?limit=&offset=` | Paginated list with `total` |
| POST | `/api/v1/items` | Create (201, `Location` header) |
| GET | `/api/v1/items/{id}` | Read one |
| PUT | `/api/v1/items/{id}` | Replace |
| PATCH | `/api/v1/items/{id}` | Partial update |
| DELETE | `/api/v1/items/{id}` | Delete (204) |

Names are 1–100 characters after trimming and unique regardless of case. Both
rules are also enforced by the database (`CHECK` constraint and a unique index
on `lower(name)`). Every error has the same shape:

```json
{"error": {"code": "not_found", "message": "Item 42 was not found.", "details": {"id": 42}}}
```

Codes: `validation_error` (422), `not_found` (404), `conflict` (409),
`method_not_allowed` (405), `internal_error` (500).

## Project layout

```
app/
  api/          routes and dependencies (HTTP only)
  core/         settings and error handling
  database/     engine, connection pool, sessions
  models/       SQLAlchemy tables
  schemas/      Pydantic request/response models
  services/     business rules
  main.py       application factory
  Dockerfile    built from the repo root
migrations/     Alembic migrations (the only source of the schema)
tests/          unit and integration tests
scripts/        tests, smoke test, EC2 setup, database backup and restore
.github/        CI, security, release and deploy workflows; Dependabot
nginx/          reverse proxy config
docs/           roadmap, architecture, runbooks, academic submission
```

## Run with Docker Compose

```bash
cp .env.example .env          # then set POSTGRES_PASSWORD
docker compose up -d --build
curl -i http://localhost/api/health
curl -i -X POST http://localhost/api/v1/items -H "Content-Type: application/json" -d '{"name":"alpha"}'
curl -s http://localhost/api/v1/items
```

Only Nginx publishes a port; the API and PostgreSQL are reachable only on the
Compose network. Data lives in the `pgdata` volume and survives
`docker compose down` / `up`. Set `APP_DEBUG=true` in `.env` to expose `/api/docs`.

Back up and restore: `scripts/db-backup.sh`, `scripts/db-restore.sh <file>`.

## Run locally without Docker

```bash
python -m venv .venv
. .venv/bin/activate                     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export APP_DATABASE_URL=sqlite:///./app.db
alembic upgrade head
uvicorn app.main:app --reload            # http://127.0.0.1:8000/api/docs
```

## Tests

One command runs lint, the format check, and the suite with coverage
(run it from Git Bash on Windows):

```bash
scripts/test.sh              # SQLite, no Docker needed
scripts/test.sh --postgres   # starts and removes a throwaway PostgreSQL 17 container
scripts/test.sh -- -k service   # extra arguments go to pytest
```

| Folder | What it covers | Needs a database |
|---|---|---|
| `tests/unit/` | Validation rules, the error envelope, config, engine and pool options | No |
| `tests/integration/` | The service layer, every HTTP endpoint, migrations in both directions, model/migration drift, concurrent duplicate creates | Yes |

The schema is always built by the real migrations. The run fails if branch
coverage drops below 85% or if any test raises a warning. To point at your own
database, set `TEST_DATABASE_URL`. That database is wiped, so only use a throwaway one.

## Breaking changes from `v1.0-academic`

- Item routes moved from `/api/items` to `/api/v1/items`.
- `POST` returns the created item (201) instead of `{"message": "added"}`.
- `GET` returns `{"items": [...], "total", "limit", "offset"}` with full item objects instead of a list of names.
- Storage moved from SQLite in the `appdata` volume to PostgreSQL in `pgdata`. Old SQLite data is not migrated; remove the old volume with `docker volume rm cloud-computing_appdata`.
- Compose now requires a `.env` file with `POSTGRES_PASSWORD`.
