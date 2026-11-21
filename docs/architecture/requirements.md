# Technical requirements

## Functional

| ID | Requirement |
|---|---|
| FR-1 | Create, read, list, update (full and partial) and delete items. |
| FR-2 | List endpoint is paginated (`limit`, `offset`) and returns the total count. |
| FR-3 | Item names are unique (case-insensitive) and 1–100 characters after trimming. |
| FR-4 | Health endpoint reports service status, version and database reachability. |

## Non-functional

| ID | Requirement |
|---|---|
| NFR-1 | All errors use one envelope: `{"error": {"code", "message", "details"}}`. |
| NFR-2 | Configuration comes from environment variables (`APP_*`); no secrets in code or images. |
| NFR-3 | The API container runs as a non-root user and is reachable only through the proxy. |
| NFR-4 | Every public endpoint is documented in OpenAPI with its error responses. |
| NFR-5 | Data persists across container restarts. |
| NFR-6 | The database backend is swappable by URL (SQLite now, PostgreSQL in Phase 02). |

## Architecture (current, Phase 01)

```
client ─▶ nginx :80 ─▶ api:8000 (FastAPI)
                          │
                          ├─ api/        HTTP routes, request/response mapping
                          ├─ services/   business rules (uniqueness, not-found)
                          ├─ models/     SQLAlchemy ORM tables
                          ├─ schemas/    Pydantic request/response models
                          ├─ database/   engine and session lifecycle
                          └─ core/       settings, error types and handlers
                          ▼
                     /data/app.db (named volume)
```

Dependencies point inward: routes call services, services use models and the
session; nothing below `api/` imports FastAPI routing.

## Proposed final architecture (not yet implemented)

```
client ─HTTPS─▶ nginx / ingress ─▶ api replicas ─▶ PostgreSQL
                                        │
                                        ├─▶ /metrics ─▶ Prometheus ─▶ Grafana
                                        └─▶ JSON logs ─▶ log aggregation
CI (GitHub Actions) ─▶ GHCR image ─▶ Kubernetes / EC2 (Terraform)
```
