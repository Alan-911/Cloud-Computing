"""Application factory. `uvicorn app.main:app` serves the default instance."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.database.session import Database

DESCRIPTION = """
Items service for the Cloud-Native Backend Infrastructure project.

Every error uses one envelope:

    {"error": {"code": "not_found", "message": "Item 42 was not found.", "details": {"id": 42}}}
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
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
    return app


app = create_app()
