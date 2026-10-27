from typing import Annotated

from fastapi import Depends, FastAPI, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db import get_session
from app.models import Item, ItemIn, ItemOut

app = FastAPI()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@app.get("/ping")
async def ping() -> str:
    return "ping"


@app.post("/items", status_code=status.HTTP_201_CREATED)
async def create_item(item_in: ItemIn, session: SessionDep) -> ItemOut:
    item = Item.model_validate(item_in)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return ItemOut.model_validate(item)
