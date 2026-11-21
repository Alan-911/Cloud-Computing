"""Business rules for items. Knows nothing about HTTP."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.item import Item
from app.schemas.item import ItemCreate, ItemPatch


class ItemService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, *, limit: int, offset: int) -> tuple[list[Item], int]:
        total = self.session.scalar(select(func.count()).select_from(Item)) or 0
        rows = self.session.scalars(
            select(Item).order_by(Item.id).limit(limit).offset(offset)
        ).all()
        return list(rows), total

    def get(self, item_id: int) -> Item:
        item = self.session.get(Item, item_id)
        if item is None:
            raise NotFoundError(f"Item {item_id} was not found.", {"id": item_id})
        return item

    def create(self, data: ItemCreate) -> Item:
        item = Item(name=data.name, description=data.description)
        self.session.add(item)
        self._commit(data.name)
        return item

    def replace(self, item_id: int, data: ItemCreate) -> Item:
        item = self.get(item_id)
        item.name = data.name
        item.description = data.description
        self._commit(data.name)
        return item

    def update(self, item_id: int, data: ItemPatch) -> Item:
        item = self.get(item_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(item, field, value)
        self._commit(item.name)
        return item

    def delete(self, item_id: int) -> None:
        item = self.get(item_id)
        self.session.delete(item)
        self.session.commit()

    def _commit(self, name: str) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(f"An item named '{name}' already exists.", {"name": name}) from exc
