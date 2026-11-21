from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas.item import ItemCreate, ItemPatch, ItemRead


class TestItemCreate:
    def test_trims_whitespace(self) -> None:
        item = ItemCreate(name="  alpha  ", description="  text  ")
        assert item.name == "alpha" and item.description == "text"

    @pytest.mark.parametrize("name", ["x", "x" * 100, "名前", "a b c"])
    def test_accepts_valid_names(self, name: str) -> None:
        assert ItemCreate(name=name).name == name

    @pytest.mark.parametrize("name", ["", "   ", "\t\n", "x" * 101])
    def test_rejects_invalid_names(self, name: str) -> None:
        with pytest.raises(ValidationError):
            ItemCreate(name=name)

    def test_description_limit(self) -> None:
        assert ItemCreate(name="a", description="d" * 500).description == "d" * 500
        with pytest.raises(ValidationError):
            ItemCreate(name="a", description="d" * 501)

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            ItemCreate(name="a", colour="red")

    def test_rejects_non_string_name(self) -> None:
        with pytest.raises(ValidationError):
            ItemCreate(name=123)


class TestItemPatch:
    def test_tracks_only_sent_fields(self) -> None:
        patch = ItemPatch(description="new")
        assert patch.model_dump(exclude_unset=True) == {"description": "new"}

    def test_allows_clearing_description(self) -> None:
        assert ItemPatch(description=None).model_dump(exclude_unset=True) == {"description": None}

    def test_requires_a_field(self) -> None:
        with pytest.raises(ValidationError, match="at least one field"):
            ItemPatch()

    def test_name_cannot_be_null(self) -> None:
        with pytest.raises(ValidationError, match="name cannot be null"):
            ItemPatch(name=None)


class TestItemRead:
    def test_naive_timestamps_are_treated_as_utc(self) -> None:
        naive = datetime(2026, 1, 1, 12, 0)
        item = ItemRead(id=1, name="a", description=None, created_at=naive, updated_at=naive)
        assert item.created_at.tzinfo == UTC

    def test_aware_timestamps_are_kept(self) -> None:
        plus2 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone(timedelta(hours=2)))
        item = ItemRead(id=1, name="a", description=None, created_at=plus2, updated_at=plus2)
        assert item.created_at == plus2 and item.created_at.utcoffset() == timedelta(hours=2)
