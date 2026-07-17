from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(strict=True)

    WEBSITE_PROVIDER: str = "mock"
    WEBSITE_BRIDGE_PORT: int = 8100
    WEBSITE_FETCH_TIMEOUT: float = 10.0
    WEBSITE_MAX_BYTES: int = 2_000_000
    WEBSITE_MAX_REDIRECTS: int = 3
    WEBSITE_CACHE_TTL: int = 86400
    WEBSITE_USER_AGENT: str = "LeadForgeBot/1.0 (+https://github.com/KVM1L03/lead-ia)"


settings = Settings()
