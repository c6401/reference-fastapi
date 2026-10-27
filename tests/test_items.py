import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Item

pytestmark = pytest.mark.anyio


async def test_create_item(client: AsyncClient, session: AsyncSession) -> None:
    response = await client.post("/items", json={"name": "Widget", "description": "A widget"})

    assert response.status_code == 201
    data = response.json()
    assert data == {"id": data["id"], "name": "Widget", "description": "A widget"}

    item = await session.get(Item, data["id"])
    assert item is not None
    assert item.name == "Widget"


async def test_create_item_without_description(client: AsyncClient, session: AsyncSession) -> None:
    response = await client.post("/items", json={"name": "Gadget"})

    assert response.status_code == 201
    assert response.json()["description"] is None
    items = (await session.exec(select(Item))).all()
    assert len(items) == 1


async def test_create_item_requires_name(client: AsyncClient) -> None:
    response = await client.post("/items", json={"description": "No name"})

    assert response.status_code == 422
