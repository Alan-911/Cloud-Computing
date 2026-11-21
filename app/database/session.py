"""Engine and session lifecycle. The engine is built from settings so tests
and environments can point at any database URL.

The schema is owned by Alembic (`migrations/`); the application never creates
or alters tables itself."""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def build_engine(settings: Settings) -> Engine:
    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite":
        return create_engine(url, connect_args={"check_same_thread": False})

    connect_args: dict = {"connect_timeout": settings.db_connect_timeout}
    if url.get_backend_name() == "postgresql":
        # Server-side guard against runaway queries holding a pooled connection.
        connect_args["options"] = f"-c statement_timeout={settings.db_statement_timeout_ms}"
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        connect_args=connect_args,
    )


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine = build_engine(settings)
        self._sessionmaker = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def session(self) -> Iterator[Session]:
        with self._sessionmaker() as session:
            yield session

    def ping(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def dispose(self) -> None:
        self.engine.dispose()
