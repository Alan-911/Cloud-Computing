"""ItemService against a migrated database, without the HTTP layer."""

import threading
import time
from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ConflictError, NotFoundError
from app.models.item import Item
from app.schemas.item import ItemCreate, ItemPatch
from app.services.item_service import ItemService

ItemFactory = Callable[..., Item]


@pytest.fixture
def service(db_session: Session) -> ItemService:
    return ItemService(db_session)


class TestList:
    def test_empty(self, service: ItemService) -> None:
        assert service.list(limit=10, offset=0) == ([], 0)

    def test_orders_by_id_and_pages(self, service: ItemService, item_factory: ItemFactory) -> None:
        made = [item_factory() for _ in range(5)]
        page, total = service.list(limit=2, offset=1)
        assert total == 5
        assert [i.id for i in page] == [made[1].id, made[2].id]

    def test_offset_past_end(self, service: ItemService, item_factory: ItemFactory) -> None:
        item_factory()
        assert service.list(limit=10, offset=50) == ([], 1)


class TestCreate:
    def test_persists(self, service: ItemService, db_session: Session) -> None:
        item = service.create(ItemCreate(name="alpha", description="d"))
        db_session.expire_all()
        stored = db_session.get(Item, item.id)
        assert stored is not None and stored.name == "alpha" and stored.description == "d"
        assert stored.created_at is not None and stored.updated_at is not None

    def test_duplicate_differs_only_by_case(
        self, service: ItemService, item_factory: ItemFactory
    ) -> None:
        item_factory("Alpha")
        with pytest.raises(ConflictError) as exc:
            service.create(ItemCreate(name="ALPHA"))
        assert exc.value.details == {"name": "ALPHA"}

    def test_session_usable_after_conflict(
        self, service: ItemService, item_factory: ItemFactory
    ) -> None:
        item_factory("taken")
        with pytest.raises(ConflictError):
            service.create(ItemCreate(name="taken"))
        assert service.create(ItemCreate(name="free")).id is not None


class TestGetAndDelete:
    def test_get_missing(self, service: ItemService) -> None:
        with pytest.raises(NotFoundError) as exc:
            service.get(12345)
        assert exc.value.details == {"id": 12345}

    def test_delete(self, service: ItemService, item_factory: ItemFactory) -> None:
        item = item_factory()
        service.delete(item.id)
        with pytest.raises(NotFoundError):
            service.get(item.id)

    def test_delete_missing(self, service: ItemService) -> None:
        with pytest.raises(NotFoundError):
            service.delete(12345)


class TestUpdate:
    def test_patch_changes_only_sent_fields(
        self, service: ItemService, item_factory: ItemFactory
    ) -> None:
        item = item_factory("keep", "old")
        updated = service.update(item.id, ItemPatch(description="new"))
        assert (updated.name, updated.description) == ("keep", "new")

    def test_patch_can_clear_description(
        self, service: ItemService, item_factory: ItemFactory
    ) -> None:
        item = item_factory("keep", "old")
        assert service.update(item.id, ItemPatch(description=None)).description is None

    def test_replace_clears_omitted_fields(
        self, service: ItemService, item_factory: ItemFactory
    ) -> None:
        item = item_factory("old", "old")
        updated = service.replace(item.id, ItemCreate(name="new"))
        assert (updated.name, updated.description) == ("new", None)

    def test_rename_to_own_name_in_other_case(
        self, service: ItemService, item_factory: ItemFactory
    ) -> None:
        item = item_factory("alpha")
        assert service.update(item.id, ItemPatch(name="ALPHA")).name == "ALPHA"

    def test_update_bumps_updated_at_only(
        self, service: ItemService, item_factory: ItemFactory
    ) -> None:
        item = item_factory()
        created, before = item.created_at, item.updated_at
        time.sleep(0.01)
        updated = service.update(item.id, ItemPatch(description="x"))
        assert updated.created_at == created
        assert updated.updated_at > before

    def test_missing(self, service: ItemService) -> None:
        with pytest.raises(NotFoundError):
            service.update(12345, ItemPatch(description="x"))
        with pytest.raises(NotFoundError):
            service.replace(12345, ItemCreate(name="x"))


def test_concurrent_duplicate_creates_yield_one_winner(
    session_factory: sessionmaker[Session],
) -> None:
    """Uniqueness must hold under concurrency, not just in a check-then-insert.
    Several sessions race to create the same name; the database lets one through."""
    workers = 8
    barrier = threading.Barrier(workers)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt(i: int) -> None:
        with session_factory() as session:
            barrier.wait()
            try:
                # Mixed case: the unique index is on lower(name).
                ItemService(session).create(ItemCreate(name="Race" if i % 2 else "race"))
                result = "created"
            except ConflictError:
                result = "conflict"
            except Exception as exc:  # pragma: no cover - surfaced in the assertion
                result = f"error: {exc!r}"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(outcomes) == ["conflict"] * (workers - 1) + ["created"], outcomes
