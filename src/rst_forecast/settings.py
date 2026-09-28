from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RST Forecast"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    model_version: str = "sarimax-1.0"
    max_model_iterations: int = 100
    # When non-empty, require matching X-API-Key on all routes except /health.
    api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RST_FORECAST_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
