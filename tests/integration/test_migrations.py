"""The migrations are the only source of the schema. These tests check that
they apply cleanly in both directions and match the ORM models exactly."""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.database.base import Base
from tests.conftest import alembic_config


@pytest.fixture
def fresh_sqlite(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'fresh.db'}"


def test_upgrade_downgrade_upgrade(fresh_sqlite: str) -> None:
    cfg = alembic_config(fresh_sqlite)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    engine = create_engine(fresh_sqlite)
    assert "items" not in inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert "items" in inspect(engine).get_table_names()
    engine.dispose()


def test_single_head(database_url: str) -> None:
    heads = ScriptDirectory.from_config(alembic_config(database_url)).get_heads()
    assert len(heads) == 1, f"Multiple migration heads: {heads}"


# SQLite cannot reflect the lower(name) expression index, so it is only compared
# on PostgreSQL. Every other column, constraint and index is compared on both.
@pytest.mark.filterwarnings("ignore:.*expression-based index.*")
def test_models_match_migrations(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == [], f"Models and migrations differ; add a migration: {diff}"


def test_database_rejects_blank_names(database_url: str) -> None:
    engine = create_engine(database_url)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("INSERT INTO items (name) VALUES ('   ')"))
    engine.dispose()
