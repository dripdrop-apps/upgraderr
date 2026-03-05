from pydantic import HttpUrl, DirectoryPath
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=".env")

    sonarr_url: HttpUrl | None = None
    sonarr_api_key: str | None = None

    radarr_url: HttpUrl | None = None
    radarr_api_key: str | None = None

    dry_run: bool = True
    data_directory: DirectoryPath = "/data"  # type: ignore
    log_level: str = "INFO"
    logs_directory: DirectoryPath = "/logs"  # type: ignore
    max_search_limit: int = 20
    notification_url: HttpUrl | None = None
    one_shot: bool = False
    search_interval: int = 5  # minutes
    search_state_reset: int = 86400  # minutes


settings = Settings()  # type: ignore
