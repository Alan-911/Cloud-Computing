"""Engine construction. No server is contacted: engines connect lazily."""

from app.core.config import Settings
from app.database.session import Database, build_engine


def settings(url: str, **overrides: object) -> Settings:
    return Settings(database_url=url, _env_file=None, **overrides)


def test_postgres_engine_uses_pool_settings() -> None:
    engine = build_engine(
        settings("postgresql+psycopg://u:p@db.invalid/app", db_pool_size=3, db_max_overflow=2)
    )
    assert engine.pool.size() == 3
    assert engine.pool._max_overflow == 2
    assert engine.pool._pre_ping is True
    engine.dispose()


def test_sqlite_engine_skips_pool_options() -> None:
    engine = build_engine(settings("sqlite://"))
    assert engine.dialect.name == "sqlite"
    engine.dispose()


def test_ping_reports_unreachable_database() -> None:
    db = Database(settings("postgresql+psycopg://u:p@127.0.0.1:1/app", db_connect_timeout=1))
    assert db.ping() is False
    db.dispose()


def test_ping_reports_reachable_database() -> None:
    db = Database(settings("sqlite://"))
    assert db.ping() is True
    db.dispose()
