from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from app.api.deps import ItemServiceDep
from app.schemas.item import ItemCreate, ItemRead, ItemUpdate

router = APIRouter(prefix="/items", tags=["items"])


class ItemPage(BaseModel):
    items: list[ItemRead]
    total: int


@router.get("", response_model=ItemPage)
async def list_items(
    service: ItemServiceDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> ItemPage:
    items, total = await service.list_items(offset=offset, limit=limit)
    return ItemPage(items=[ItemRead.model_validate(i) for i in items], total=total)


@router.get("/{item_id}", response_model=ItemRead)
async def get_item(item_id: int, service: ItemServiceDep):
    return await service.get_item(item_id)


@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
async def create_item(data: ItemCreate, service: ItemServiceDep):
    return await service.create_item(data)


@router.patch("/{item_id}", response_model=ItemRead)
async def update_item(item_id: int, data: ItemUpdate, service: ItemServiceDep):
    return await service.update_item(item_id, data)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: int, service: ItemServiceDep) -> None:
    await service.delete_item(item_id)
