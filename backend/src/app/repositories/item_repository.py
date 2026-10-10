from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item


class ItemRepository:
    """Data access for items. Knows SQL, knows nothing about HTTP or business rules."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, offset: int = 0, limit: int = 50) -> Sequence[Item]:
        result = await self.session.scalars(
            select(Item).order_by(Item.id).offset(offset).limit(limit)
        )
        return result.all()

    async def count(self) -> int:
        return await self.session.scalar(select(func.count()).select_from(Item)) or 0

    async def get(self, item_id: int) -> Item | None:
        return await self.session.get(Item, item_id)

    async def get_by_name(self, name: str) -> Item | None:
        return await self.session.scalar(select(Item).where(Item.name == name))

    async def add(self, item: Item) -> Item:
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def save(self, item: Item) -> Item:
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def delete(self, item: Item) -> None:
        await self.session.delete(item)
        await self.session.flush()
