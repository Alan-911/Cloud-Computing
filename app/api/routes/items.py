from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, Response, status

from app.api.deps import ItemServiceDep, SettingsDep
from app.core.security import WriteAccess
from app.schemas.common import error_responses
from app.schemas.item import ItemCreate, ItemPage, ItemPatch, ItemRead

router = APIRouter(prefix="/items", tags=["items"])

ItemId = Annotated[int, Path(ge=1, description="Item identifier")]


@router.get(
    "",
    response_model=ItemPage,
    summary="List items",
    description="Items ordered by id, paginated with `limit` and `offset`.",
    responses=error_responses(422),
)
def list_items(
    service: ItemServiceDep,
    settings: SettingsDep,
    limit: Annotated[
        int | None, Query(ge=1, description="Page size. Default 20, capped at 100.")
    ] = None,
    offset: Annotated[int, Query(ge=0, description="Number of items to skip")] = 0,
) -> ItemPage:
    limit = min(limit or settings.default_page_size, settings.max_page_size)
    items, total = service.list(limit=limit, offset=offset)
    return ItemPage(
        items=[ItemRead.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=ItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an item",
    responses=error_responses(401, 409, 422),
    dependencies=[WriteAccess],
)
def create_item(
    body: ItemCreate, service: ItemServiceDep, request: Request, response: Response
) -> ItemRead:
    item = service.create(body)
    response.headers["Location"] = str(request.url_for("get_item", item_id=item.id).path)
    return ItemRead.model_validate(item)


@router.get(
    "/{item_id}",
    response_model=ItemRead,
    summary="Get an item",
    responses=error_responses(404, 422),
)
def get_item(item_id: ItemId, service: ItemServiceDep) -> ItemRead:
    return ItemRead.model_validate(service.get(item_id))


@router.put(
    "/{item_id}",
    response_model=ItemRead,
    summary="Replace an item",
    dependencies=[WriteAccess],
    description="Replaces every field. Omitted optional fields are cleared.",
    responses=error_responses(401, 404, 409, 422),
)
def replace_item(item_id: ItemId, body: ItemCreate, service: ItemServiceDep) -> ItemRead:
    return ItemRead.model_validate(service.replace(item_id, body))


@router.patch(
    "/{item_id}",
    response_model=ItemRead,
    summary="Update an item",
    dependencies=[WriteAccess],
    description="Changes only the fields present in the body.",
    responses=error_responses(401, 404, 409, 422),
)
def update_item(item_id: ItemId, body: ItemPatch, service: ItemServiceDep) -> ItemRead:
    return ItemRead.model_validate(service.update(item_id, body))


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an item",
    dependencies=[WriteAccess],
    responses=error_responses(401, 404, 422),
)
def delete_item(item_id: ItemId, service: ItemServiceDep) -> Response:
    service.delete(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
