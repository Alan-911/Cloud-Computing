"""Shared test fixtures.

The schema is built by running the real Alembic migrations, never by
`create_all`, so every run also exercises the migrations.

Database: SQLite in a temp directory by default. Set TEST_DATABASE_URL to a
PostgreSQL URL to run the same suite against PostgreSQL (CI does this).
The target database is wiped: point it only at a throwaway database.

Layout:
    tests/unit/         no database: schemas, config, error handling, engine options
    tests/integration/  migrated database: services, HTTP API, migrations
"""

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.security import hash_key
from app.main import create_app
from app.models.item import Item

ROOT = Path(__file__).resolve().parents[1]

# A fixed key for tests only; the app is configured with its hash.
TEST_API_KEY = "cbe_test_key_for_pytest_only"


def alembic_config(database_url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = database_url
    cfg.attributes["configure_logger"] = False
    return cfg


def pytest_report_header() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    return f"database: {url.split('@')[-1] if url else 'SQLite (temp file)'}"


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


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    eng = create_engine(database_url)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def is_postgres(engine: Engine) -> bool:
    return engine.dialect.name == "postgresql"


@pytest.fixture
def clean_db(engine: Engine) -> None:
    """Empty every table so each test starts from a known state."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM items"))


@pytest.fixture
def session_factory(engine: Engine, clean_db: None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def item_factory(db_session: Session) -> Callable[..., Item]:
    """Insert an item directly, bypassing the API. Names default to item-1, item-2, ..."""
    counter = iter(range(1, 10_000))

    def make(name: str | None = None, description: str | None = None) -> Item:
        item = Item(name=name or f"item-{next(counter)}", description=description)
        db_session.add(item)
        db_session.commit()
        return item

    return make


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(
        environment="test",
        database_url=database_url,
        api_key_hashes=hash_key(TEST_API_KEY),
        _env_file=None,
    )


@pytest.fixture
def client(settings: Settings, clean_db: None) -> Iterator[TestClient]:
    # Sends a valid key by default; auth tests override or drop the header.
    with TestClient(create_app(settings), headers={"X-API-Key": TEST_API_KEY}) as c:
        yield c
