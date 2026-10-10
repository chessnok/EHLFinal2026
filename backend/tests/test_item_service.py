import pytest

from app.models import Item
from app.schemas.item import ItemCreate, ItemUpdate
from app.services.exceptions import ConflictError, NotFoundError
from app.services.item_service import ItemService


class FakeItemRepository:
    """In-memory stand-in: the service layer is tested without a database."""

    def __init__(self) -> None:
        self.items: dict[int, Item] = {}

    async def list(self, *, offset: int = 0, limit: int = 50):
        return list(self.items.values())[offset : offset + limit]

    async def count(self) -> int:
        return len(self.items)

    async def get(self, item_id: int):
        return self.items.get(item_id)

    async def get_by_name(self, name: str):
        return next((i for i in self.items.values() if i.name == name), None)

    async def add(self, item: Item) -> Item:
        item.id = len(self.items) + 1
        self.items[item.id] = item
        return item

    async def save(self, item: Item) -> Item:
        return item

    async def delete(self, item: Item) -> None:
        self.items.pop(item.id)


@pytest.fixture
def service() -> ItemService:
    return ItemService(FakeItemRepository())  # type: ignore[arg-type]


async def test_create_rejects_duplicate_name(service: ItemService) -> None:
    await service.create_item(ItemCreate(name="A"))
    with pytest.raises(ConflictError):
        await service.create_item(ItemCreate(name="A"))


async def test_rename_to_existing_name_conflicts(service: ItemService) -> None:
    await service.create_item(ItemCreate(name="A"))
    b = await service.create_item(ItemCreate(name="B"))
    with pytest.raises(ConflictError):
        await service.update_item(b.id, ItemUpdate(name="A"))


async def test_missing_item_raises(service: ItemService) -> None:
    with pytest.raises(NotFoundError):
        await service.get_item(42)
