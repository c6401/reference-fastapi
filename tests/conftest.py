from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db import get_session
from app.main import app

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def alembic_config(connection: Connection) -> Config:
    config = Config(ALEMBIC_INI)
    config.attributes["connection"] = connection
    return config


def upgrade(connection: Connection, revision: str = "head") -> None:
    command.upgrade(alembic_config(connection), revision)


def downgrade(connection: Connection, revision: str = "base") -> None:
    command.downgrade(alembic_config(connection), revision)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """In-memory SQLite with the schema built by Alembic migrations, not create_all."""
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(upgrade)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.pop(get_session, None)
