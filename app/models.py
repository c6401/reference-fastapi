# Import SQLModel table models here so Alembic autogenerate can see them.
from sqlmodel import Field, SQLModel


class ItemBase(SQLModel):
    name: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class Item(ItemBase, table=True):
    id: int | None = Field(default=None, primary_key=True)


class ItemIn(ItemBase):
    pass


class ItemOut(ItemBase):
    id: int
