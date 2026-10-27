import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Item, ItemIn, ItemOut

pytestmark = pytest.mark.anyio


async def test_item_persists_and_gets_id(session: AsyncSession) -> None:
    item = Item(name="Widget", description="A widget")
    session.add(item)
    await session.commit()

    assert item.id is not None
    stored = await session.get(Item, item.id)
    assert stored is not None
    assert (stored.name, stored.description) == ("Widget", "A widget")


async def test_item_description_is_optional(session: AsyncSession) -> None:
    session.add(Item(name="Gadget"))
    await session.commit()

    stored = (await session.exec(select(Item))).one()
    assert stored.description is None


async def test_item_ids_are_unique(session: AsyncSession) -> None:
    session.add_all([Item(name="A"), Item(name="B")])
    await session.commit()

    ids = (await session.exec(select(Item.id))).all()
    assert len(ids) == len(set(ids)) == 2


async def test_item_name_is_not_null_in_database(session: AsyncSession) -> None:
    # Table models skip validation, so this reaches the DB and hits the NOT NULL constraint.
    session.add(Item(name=None))
    with pytest.raises(IntegrityError):
        await session.commit()


def test_item_create_validates_lengths() -> None:
    with pytest.raises(ValidationError):
        ItemIn(name="x" * 256)
    with pytest.raises(ValidationError):
        ItemIn(name="ok", description="x" * 1001)


def test_item_create_requires_name() -> None:
    with pytest.raises(ValidationError):
        ItemIn.model_validate({"description": "No name"})


def test_item_public_from_item() -> None:
    public = ItemOut.model_validate(Item(id=1, name="Widget"))
    assert public.model_dump() == {"id": 1, "name": "Widget", "description": None}
