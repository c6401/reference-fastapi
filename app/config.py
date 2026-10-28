from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./app.db"

    proxy_upstream_url: str | None = None
    proxy_upstream_authorization: str | None = None
    proxy_timeout: float = 30.0


settings = Settings()
