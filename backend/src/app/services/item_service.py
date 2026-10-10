from app.models import Item
from app.repositories.item_repository import ItemRepository
from app.schemas.item import ItemCreate, ItemUpdate
from app.services.exceptions import ConflictError, NotFoundError


class ItemService:
    """Business rules for items. Works with repositories, never with HTTP or SQL directly."""

    def __init__(self, repository: ItemRepository) -> None:
        self.repository = repository

    async def list_items(self, *, offset: int, limit: int) -> tuple[list[Item], int]:
        items = await self.repository.list(offset=offset, limit=limit)
        return list(items), await self.repository.count()

    async def get_item(self, item_id: int) -> Item:
        item = await self.repository.get(item_id)
        if item is None:
            raise NotFoundError(f"Item {item_id} not found")
        return item

    async def create_item(self, data: ItemCreate) -> Item:
        if await self.repository.get_by_name(data.name):
            raise ConflictError(f"Item named '{data.name}' already exists")
        return await self.repository.add(Item(**data.model_dump()))

    async def update_item(self, item_id: int, data: ItemUpdate) -> Item:
        item = await self.get_item(item_id)
        changes = data.model_dump(exclude_unset=True)
        if "name" in changes and changes["name"] != item.name:
            if await self.repository.get_by_name(changes["name"]):
                raise ConflictError(f"Item named '{changes['name']}' already exists")
        for field, value in changes.items():
            setattr(item, field, value)
        return await self.repository.save(item)

    async def delete_item(self, item_id: int) -> None:
        await self.repository.delete(await self.get_item(item_id))
