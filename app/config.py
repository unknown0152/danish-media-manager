from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Danish Media Manager"
    database_path: str = Field(default="/data/danish-media-manager.db", alias="DATABASE_PATH")

    prowlarr_url: str = Field(default="http://prowlarr:9696", alias="PROWLARR_URL")
    prowlarr_api_key: str = Field(default="", alias="PROWLARR_API_KEY")

    altmount_url: str = Field(
        default="http://danish-intelligence:9699/altmount",
        alias="ALTMOUNT_URL",
    )
    altmount_api_key: str = Field(default="", alias="ALTMOUNT_API_KEY")
    altmount_import_dir: str = Field(
        default="/mnt/altmount-import",
        alias="ALTMOUNT_IMPORT_DIR",
    )
    altmount_mount_path: str = Field(default="/mnt/altmount", alias="ALTMOUNT_MOUNT_PATH")
    media_root: str = Field(default="/media", alias="MEDIA_ROOT")

    request_timeout_seconds: float = Field(default=20.0, alias="REQUEST_TIMEOUT_SECONDS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
