from typing import Any

import httpx

from app.config import Settings
from app.models import MediaType, MetadataResult
from app.titlematch import clean_title, parse_year


class MetadataClient:
    def __init__(self, settings: Settings):
        self.api_key = settings.tmdb_api_key
        self.base_url = settings.tmdb_base_url.rstrip("/")
        self.timeout = settings.request_timeout_seconds

    def lookup(self, query: str, media_type: MediaType) -> MetadataResult:
        fallback = local_metadata(query)
        if not self.api_key:
            return fallback

        try:
            result = self._lookup_tmdb(query, media_type)
        except httpx.HTTPError:
            return fallback
        return result or fallback

    def _lookup_tmdb(self, query: str, media_type: MediaType) -> MetadataResult | None:
        year = parse_year(query)
        endpoint = "movie" if media_type == "movie" else "tv"
        params: dict[str, Any] = {
            "api_key": self.api_key,
            "query": clean_title(query),
            "include_adult": "false",
        }
        if year:
            params["year" if media_type == "movie" else "first_air_date_year"] = year
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/search/{endpoint}", params=params)
            response.raise_for_status()
            data = response.json()

        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list) or not results:
            return None
        item = next((entry for entry in results if isinstance(entry, dict)), None)
        if not item:
            return None

        title = str(item.get("title") or item.get("name") or fallback_title(query))
        date = str(item.get("release_date") or item.get("first_air_date") or "")
        poster_path = item.get("poster_path")
        poster_url = (
            f"https://image.tmdb.org/t/p/w342{poster_path}" if isinstance(poster_path, str) else None
        )
        return MetadataResult(
            title=title,
            year=parse_year(date) or year,
            overview=_str_or_none(item.get("overview")),
            poster_url=poster_url,
            source="tmdb",
            external_id=str(item.get("id")) if item.get("id") is not None else None,
        )


def local_metadata(query: str) -> MetadataResult:
    return MetadataResult(
        title=fallback_title(query),
        year=parse_year(query),
        source="local",
    )


def fallback_title(query: str) -> str:
    title = clean_title(query)
    return title.title() if title else query.strip()


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
