from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.session import Database
from app.services.item_service import ItemService


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_database(request: Request) -> Database:
    return request.app.state.db


def get_session(db: Annotated[Database, Depends(get_database)]) -> Iterator[Session]:
    yield from db.session()


def get_item_service(session: Annotated[Session, Depends(get_session)]) -> ItemService:
    return ItemService(session)


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DatabaseDep = Annotated[Database, Depends(get_database)]
ItemServiceDep = Annotated[ItemService, Depends(get_item_service)]
