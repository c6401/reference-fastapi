# app

FastAPI + SQLModel (async SQLite) + Alembic.

## Setup

```sh
uv sync                     # install deps
cp .env.example .env        # local config
uv run alembic upgrade head # create/migrate db
```

## Run

```sh
uv run uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs
```

## Test

```sh
uv run pytest               # in-memory SQLite, schema built by migrations
```

## Migrations

```sh
uv run alembic revision --autogenerate -m "msg"   # after changing app/models.py
uv run alembic upgrade head
uv run alembic downgrade -1
```

Data migration: empty revision, fill `upgrade()`/`downgrade()` by hand. Use `sa.table()`, not app models (they change, migrations must not).

```sh
uv run alembic revision -m "seed items"
```

```python
items = sa.table("item", sa.column("name", sa.String))

def upgrade() -> None:
    op.bulk_insert(items, [{"name": "Widget"}])

def downgrade() -> None:
    op.execute(items.delete().where(items.c.name == "Widget"))
```

## Layout

- `app/main.py`: routes
- `app/models.py`: SQLModel models
- `app/db.py`: engine, session
- `app/config.py`: settings (`.env`)
- `app/proxy.py`: `/proxy/*` → `PROXY_UPSTREAM_URL`, auth header swap in `upstream_headers()`
- `alembic/`: migrations
- `tests/`: tests
