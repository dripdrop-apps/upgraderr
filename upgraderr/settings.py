from pydantic import HttpUrl, DirectoryPath
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=".env")

    sonarr_url: HttpUrl | None
    sonarr_api_key: str | None

    radarr_url: HttpUrl | None
    radarr_api_key: str | None

    max_search_limit: int = 20
    search_interval: int = 24  # 24 hours
    data_directory: DirectoryPath = "/data"  # type: ignore
    dry_run: bool = True
    log_level: str = "INFO"


settings = Settings()  # type: ignore
