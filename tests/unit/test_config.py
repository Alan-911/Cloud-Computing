import pytest

from app.core.config import Settings


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_DATABASE_URL", "sqlite:////tmp/x.db")
    monkeypatch.setenv("APP_MAX_PAGE_SIZE", "50")
    s = Settings(_env_file=None)
    assert s.database_url == "sqlite:////tmp/x.db"
    assert s.max_page_size == 50


def test_docs_hidden_in_production() -> None:
    assert Settings(environment="production", _env_file=None).docs_enabled is False
    assert Settings(environment="production", debug=True, _env_file=None).docs_enabled is True
