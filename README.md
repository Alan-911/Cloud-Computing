# Cloud-Native Backend Infrastructure

A FastAPI items service behind an Nginx reverse proxy, being developed in
phases from a graded cloud-computing assignment into a production-oriented
backend: tested, containerized, automated, observable and secure.

- **Roadmap and status:** [`docs/ROADMAP.md`](docs/ROADMAP.md)
- **Requirements and architecture:** [`docs/architecture/requirements.md`](docs/architecture/requirements.md)
- **Original academic submission:** tag `v1.0-academic`, files in [`docs/academic-submission/`](docs/academic-submission/NOTE.md)

```
client ──▶ :80 nginx ──▶ api:8000 FastAPI ──▶ /data named volume (SQLite → PostgreSQL in Phase 02)
           (published)    (internal only, non-root)
```

## Status

| Phase | State |
|---|---|
| 00 Repository preparation | Done (project board pending) |
| 01 Backend engineering | Done |
| 02–10 | Planned |

## API

Base path `/api`. Interactive docs at `/api/docs` (disabled when
`APP_ENVIRONMENT=production` unless `APP_DEBUG=true`).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Status, version, database reachability (503 if the database is down) |
| GET | `/api/v1/items?limit=&offset=` | Paginated list with `total` |
| POST | `/api/v1/items` | Create (201, `Location` header) |
| GET | `/api/v1/items/{id}` | Read one |
| PUT | `/api/v1/items/{id}` | Replace |
| PATCH | `/api/v1/items/{id}` | Partial update |
| DELETE | `/api/v1/items/{id}` | Delete (204) |

Names are 1–100 characters after trimming and unique regardless of case.
Every error has the same shape:

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
  database/     engine and session lifecycle
  models/       SQLAlchemy tables
  schemas/      Pydantic request/response models
  services/     business rules
  main.py       application factory
  Dockerfile
tests/          unit and integration tests
nginx/          reverse proxy config
docs/           roadmap, architecture, academic submission
```

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload   # http://127.0.0.1:8000/api/docs
pytest --cov                    # tests with coverage
ruff check . && ruff format --check .
```

Configuration is read from `APP_*` environment variables or a `.env` file;
see [`.env.example`](.env.example).

## Run with Docker Compose

```bash
docker compose up -d --build
curl -i http://localhost/api/health
curl -i -X POST http://localhost/api/v1/items -H "Content-Type: application/json" -d '{"name":"alpha"}'
curl -s http://localhost/api/v1/items
```

Only Nginx publishes a port. The API runs as UID 10001 with no reload, and its
data lives in the `appdata` volume, which survives `docker compose down` / `up`.
Set `APP_DEBUG=true` to expose `/api/docs` through the proxy.

## Breaking changes from `v1.0-academic`

- Item routes moved from `/api/items` to `/api/v1/items`.
- `POST` returns the created item (201) instead of `{"message": "added"}`.
- `GET` returns `{"items": [...], "total", "limit", "offset"}` with full item objects instead of a list of names.
- The SQLite schema changed; remove the old `appdata` volume (`docker compose down -v`) before the first run.
