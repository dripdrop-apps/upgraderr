from pydantic import HttpUrl, DirectoryPath
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=".env")

    sonarr_url: HttpUrl | None = None
    sonarr_api_key: str | None = None

    radarr_url: HttpUrl | None = None
    radarr_api_key: str | None = None

    dry_run: bool = True
    log_level: str = "INFO"
    logs_directory: DirectoryPath = "/logs"  # type: ignore
    max_search_limit: int = 20
    notification_url: str | None = None
    one_shot: bool = False
    search_interval: int = 5  # minutes
    search_refresh_interval: int = 86400  # minutes
    sonarr_search: Literal["release", "command"] = "command"


settings = Settings()  # type: ignore
