from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app import proxy
from app.db import get_session
from app.models import Item, ItemIn, ItemOut


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    async with proxy.make_http_client() as client:
        app.state.http_client = client
        yield


app = FastAPI(lifespan=lifespan)
app.include_router(proxy.router)

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
