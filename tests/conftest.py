"""Test fixtures.

The schema is built by running the real Alembic migrations, never by
`create_all`, so every run also exercises the migrations.

Database: SQLite in a temp directory by default. Set TEST_DATABASE_URL to a
PostgreSQL URL to run the same suite against PostgreSQL (CI does this).
The target database is wiped: point it only at a throwaway database.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def alembic_config(database_url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = database_url
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    url = os.environ.get("TEST_DATABASE_URL") or (
        f"sqlite:///{tmp_path_factory.mktemp('db') / 'test.db'}"
    )
    cfg = alembic_config(url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield url
    command.downgrade(cfg, "base")


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(environment="test", database_url=database_url, _env_file=None)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM items"))
    engine.dispose()
    with TestClient(create_app(settings)) as c:
        yield c
