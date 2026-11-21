"""Engine and session lifecycle. The engine is built from settings so tests
and environments can point at any database URL."""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base


def build_engine(database_url: str) -> Engine:
    kwargs: dict = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url or database_url == "sqlite://":
            kwargs["poolclass"] = StaticPool
    return create_engine(database_url, **kwargs)


class Database:
    def __init__(self, database_url: str) -> None:
        self.engine = build_engine(database_url)
        self._sessionmaker = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def create_all(self) -> None:
        # Replaced by Alembic migrations in Phase 02.
        import app.models  # noqa: F401  (registers tables on Base.metadata)

        Base.metadata.create_all(self.engine)

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
