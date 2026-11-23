"""Application factory. `uvicorn app.main:app` serves the default instance."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.observability import (
    APP_INFO,
    DB_POOL_IN_USE,
    LoadSheddingMiddleware,
    ObservabilityMiddleware,
    metrics_endpoint,
)
from app.core.security import SecurityHeadersMiddleware
from app.database.session import Database

DESCRIPTION = """
Items service for the Cloud-Native Backend Infrastructure project.

Every error uses one envelope:

    {"error": {"code": "not_found", "message": "Item 42 was not found.", "details": {"id": 42}}}
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    db = Database(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Schema comes from `alembic upgrade head`, run before the app starts.
        yield
        db.dispose()

    prefix = settings.api_prefix
    docs = settings.docs_enabled
    app = FastAPI(
        title=settings.name,
        version=settings.version,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url=f"{prefix}/docs" if docs else None,
        redoc_url=f"{prefix}/redoc" if docs else None,
        openapi_url=f"{prefix}/openapi.json" if docs else None,
        openapi_tags=[
            {"name": "health", "description": "Liveness and dependency status."},
            {"name": "items", "description": "Create, read, update and delete items."},
        ],
    )
    app.state.settings = settings
    app.state.db = db
    register_error_handlers(app)
    app.include_router(api_router, prefix=prefix)

    # Security headers on every response, then observability (outermost) so the
    # access log and metrics also cover responses produced by inner layers.
    # Starlette runs the last-added middleware outermost. Outer to inner:
    # observability (logs and counts everything, shed requests included) ->
    # security headers (on every response, 503s included) -> load shedding (rejects
    # excess before any work is done) -> the app.
    app.add_middleware(LoadSheddingMiddleware, limit=settings.max_concurrent_requests)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(ObservabilityMiddleware)
    app.add_route("/metrics", metrics_endpoint, include_in_schema=False)
    APP_INFO.labels(settings.version, settings.environment).set(1)
    pool = db.engine.pool
    if hasattr(pool, "checkedout"):
        DB_POOL_IN_USE.set_function(pool.checkedout)
    return app


app = create_app()
