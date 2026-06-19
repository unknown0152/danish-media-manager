from typing import Any

import httpx

from app.config import Settings
from app.models import MetadataResult
from app.metadata import tv_seasons_from_tmdb
from app.titlematch import parse_year


class SeerrClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.seerr_url.rstrip("/")
        self.api_key = settings.seerr_api_key
        self.timeout = settings.request_timeout_seconds

    def ready(self) -> bool:
        if not self.api_key:
            return False
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/api/v1/status",
                    headers={"X-Api-Key": self.api_key},
                )
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def requests(self, *, take: int = 20, filter_name: str = "all") -> list[dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("SEERR_API_KEY is not set")
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/api/v1/request",
                params={
                    "take": take,
                    "skip": 0,
                    "filter": filter_name,
                    "sort": "added",
                    "sortDirection": "desc",
                    "mediaType": "all",
                },
                headers={"X-Api-Key": self.api_key},
            )
            response.raise_for_status()
            data = response.json()
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            raise RuntimeError("Unexpected Seerr request response")
        return [item for item in results if isinstance(item, dict)]

    def metadata_for_request(self, item: dict[str, Any]) -> MetadataResult | None:
        media_type = seerr_media_type(item)
        tmdb_id = seerr_tmdb_id(item)
        if not media_type or not tmdb_id:
            return None
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/api/v1/{'movie' if media_type == 'movie' else 'tv'}/{tmdb_id}",
                headers={"X-Api-Key": self.api_key},
            )
            response.raise_for_status()
            detail = response.json()
        if not isinstance(detail, dict):
            return None
        return metadata_from_seerr_detail(detail, media_type, fallback_id=tmdb_id)

    def mark_available(self, item: dict[str, Any]) -> bool:
        if not self.api_key:
            return False
        media = item.get("media") if isinstance(item.get("media"), dict) else {}
        media_id = media.get("id")
        if media_id is None:
            return False
        payload: dict[str, Any] = {"is4k": bool(item.get("is4k"))}
        if seerr_media_type(item) == "tv":
            seasons = [
                {"seasonNumber": season.get("seasonNumber")}
                for season in item.get("seasons") or []
                if isinstance(season, dict) and season.get("seasonNumber") is not None
            ]
            payload["seasons"] = seasons or [{"seasonNumber": 1}]
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/v1/media/{media_id}/available",
                json=payload,
                headers={"X-Api-Key": self.api_key},
            )
            response.raise_for_status()
        return True


def seerr_request_id(item: dict[str, Any]) -> str | None:
    value = item.get("id")
    return str(value) if value is not None else None


def seerr_media_type(item: dict[str, Any]) -> str | None:
    media = item.get("media") if isinstance(item.get("media"), dict) else {}
    value = item.get("mediaType") or media.get("mediaType") or media.get("media_type")
    if value in {"movie", "tv"}:
        return str(value)
    return None


def seerr_tmdb_id(item: dict[str, Any]) -> str | None:
    media = item.get("media") if isinstance(item.get("media"), dict) else {}
    value = media.get("tmdbId") or item.get("mediaId") or item.get("tmdbId")
    return str(value) if value is not None else None


def seerr_tvdb_id(item: dict[str, Any]) -> str | None:
    media = item.get("media") if isinstance(item.get("media"), dict) else {}
    value = media.get("tvdbId") or item.get("tvdbId")
    return str(value) if value is not None else None


def metadata_from_seerr_detail(
    detail: dict[str, Any],
    media_type: str,
    *,
    fallback_id: str,
) -> MetadataResult:
    title = detail.get("title") if media_type == "movie" else detail.get("name")
    date = detail.get("releaseDate") if media_type == "movie" else detail.get("firstAirDate")
    poster_path = detail.get("posterPath")
    poster_url = (
        f"https://image.tmdb.org/t/p/w342{poster_path}" if isinstance(poster_path, str) else None
    )
    tmdb_id = detail.get("id") or fallback_id
    return MetadataResult(
        title=str(title or fallback_id),
        year=parse_year(str(date or "")),
        overview=_str_or_none(detail.get("overview")),
        poster_url=poster_url,
        source="seerr",
        external_id=str(tmdb_id),
        tmdb_id=str(tmdb_id) if tmdb_id is not None else None,
        tvdb_id=_str_or_none(detail.get("tvdbId")),
        imdb_id=_str_or_none(detail.get("imdbId")),
        tv_seasons=tv_seasons_from_tmdb(detail.get("seasons")),
    )


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None
