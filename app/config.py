from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Danish Media Manager"
    database_path: str = Field(default="/data/danish-media-manager.db", alias="DATABASE_PATH")

    prowlarr_url: str = Field(default="http://prowlarr:9696", alias="PROWLARR_URL")
    prowlarr_api_key: str = Field(default="", alias="PROWLARR_API_KEY")
    danish_intelligence_url: str = Field(
        default="http://danish-intelligence:9699",
        alias="DANISH_INTELLIGENCE_URL",
    )
    radarr_url: str = Field(default="http://radarr:7878", alias="RADARR_URL")
    radarr_api_key: str = Field(default="", alias="RADARR_API_KEY")
    sonarr_url: str = Field(default="http://sonarr:8989", alias="SONARR_URL")
    sonarr_api_key: str = Field(default="", alias="SONARR_API_KEY")
    seerr_url: str = Field(default="http://seerr:5055", alias="SEERR_URL")
    seerr_api_key: str = Field(default="", alias="SEERR_API_KEY")

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
    allow_direct_download_urls: bool = Field(default=False, alias="ALLOW_DIRECT_DOWNLOAD_URLS")
    tmdb_api_key: str = Field(default="", alias="TMDB_API_KEY")
    tmdb_base_url: str = Field(default="https://api.themoviedb.org/3", alias="TMDB_BASE_URL")
    movie_targets: str = Field(
        default=(
            "Movies=/media/movies,"
            "Danish Movies=/media/danish-movies,"
            "Kids Movies=/media/kids-movies,"
            "Documentaries=/media/documentaries,"
            "Christmas Movies=/media/christmas-movies,"
            "Classics=/media/classics"
        ),
        alias="MOVIE_TARGETS",
    )
    tv_targets: str = Field(
        default=(
            "TV=/media/tv,"
            "Danish TV=/media/danish-tv,"
            "Kids TV=/media/kids-tv,"
            "Documentary Series=/media/documentary-series,"
            "Christmas TV=/media/christmas-tv"
        ),
        alias="TV_TARGETS",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
