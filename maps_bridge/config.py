from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(strict=True)

    MAPS_PROVIDER: str = "mock"
    SERPAPI_API_KEY: str | None = None
    CACHE_DB_PATH: str = "./cache.db"


settings = Settings()
