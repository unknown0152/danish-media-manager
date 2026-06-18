from typing import Any

import httpx

from app.config import Settings
from app.models import MediaType, MetadataResult
from app.titlematch import clean_title, parse_year


class MetadataClient:
    def __init__(self, settings: Settings):
        self.tmdb_api_key = settings.tmdb_api_key
        self.tmdb_base_url = settings.tmdb_base_url.rstrip("/")
        self.radarr_url = settings.radarr_url.rstrip("/")
        self.radarr_api_key = settings.radarr_api_key
        self.sonarr_url = settings.sonarr_url.rstrip("/")
        self.sonarr_api_key = settings.sonarr_api_key
        self.seerr_url = settings.seerr_url.rstrip("/")
        self.seerr_api_key = settings.seerr_api_key
        self.timeout = settings.request_timeout_seconds

    def lookup(self, query: str, media_type: MediaType) -> MetadataResult:
        fallback = local_metadata(query)

        result = self._lookup_configured_services(query, media_type)
        if result:
            return result

        if not self.tmdb_api_key:
            return fallback

        try:
            result = self._lookup_tmdb(query, media_type)
        except httpx.HTTPError:
            return fallback
        return result or fallback

    def _lookup_configured_services(
        self,
        query: str,
        media_type: MediaType,
    ) -> MetadataResult | None:
        if self.seerr_api_key:
            try:
                result = self._lookup_seerr(query, media_type)
            except httpx.HTTPError:
                result = None
            if result:
                return result

        if media_type == "movie" and self.radarr_api_key:
            try:
                result = self._lookup_radarr(query)
            except httpx.HTTPError:
                result = None
            if result:
                return result

        if media_type == "tv" and self.sonarr_api_key:
            try:
                result = self._lookup_sonarr(query)
            except httpx.HTTPError:
                result = None
            if result:
                return result

        return None

    def _lookup_seerr(self, query: str, media_type: MediaType) -> MetadataResult | None:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.seerr_url}/api/v1/search",
                params={"query": query, "page": 1},
                headers={"X-Api-Key": self.seerr_api_key},
            )
            response.raise_for_status()
            data = response.json()

        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            return None
        wanted_type = "movie" if media_type == "movie" else "tv"
        item = next(
            (
                entry
                for entry in results
                if isinstance(entry, dict) and entry.get("mediaType") == wanted_type
            ),
            None,
        )
        return metadata_from_seerr_item(item, query) if item else None

    def _lookup_radarr(self, query: str) -> MetadataResult | None:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.radarr_url}/api/v3/movie/lookup",
                params={"term": query},
                headers={"X-Api-Key": self.radarr_api_key},
            )
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, list):
            return None
        item = next((entry for entry in data if isinstance(entry, dict)), None)
        return metadata_from_radarr_item(item, query) if item else None

    def _lookup_sonarr(self, query: str) -> MetadataResult | None:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.sonarr_url}/api/v3/series/lookup",
                params={"term": query},
                headers={"X-Api-Key": self.sonarr_api_key},
            )
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, list):
            return None
        item = next((entry for entry in data if isinstance(entry, dict)), None)
        return metadata_from_sonarr_item(item, query) if item else None

    def _lookup_tmdb(self, query: str, media_type: MediaType) -> MetadataResult | None:
        year = parse_year(query)
        endpoint = "movie" if media_type == "movie" else "tv"
        params: dict[str, Any] = {
            "api_key": self.tmdb_api_key,
            "query": clean_title(query),
            "include_adult": "false",
        }
        if year:
            params["year" if media_type == "movie" else "first_air_date_year"] = year
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.tmdb_base_url}/search/{endpoint}", params=params)
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


def metadata_from_radarr_item(item: dict[str, Any], query: str) -> MetadataResult:
    return MetadataResult(
        title=str(item.get("title") or fallback_title(query)),
        year=parse_year(str(item.get("releaseDate") or "")) or parse_year(query),
        overview=_str_or_none(item.get("overview")),
        poster_url=_poster_from_arr_images(item.get("images")) or _str_or_none(item.get("remotePoster")),
        source="radarr",
        external_id=str(item.get("tmdbId")) if item.get("tmdbId") is not None else None,
    )


def metadata_from_sonarr_item(item: dict[str, Any], query: str) -> MetadataResult:
    external_id = item.get("tmdbId") if item.get("tmdbId") is not None else item.get("tvdbId")
    return MetadataResult(
        title=str(item.get("title") or fallback_title(query)),
        year=parse_year(str(item.get("firstAired") or "")) or parse_year(query),
        overview=_str_or_none(item.get("overview")),
        poster_url=_poster_from_arr_images(item.get("images")) or _str_or_none(item.get("remotePoster")),
        source="sonarr",
        external_id=str(external_id) if external_id is not None else None,
    )


def metadata_from_seerr_item(item: dict[str, Any], query: str) -> MetadataResult:
    media_type = item.get("mediaType")
    title = item.get("title") if media_type == "movie" else item.get("name")
    date = item.get("releaseDate") if media_type == "movie" else item.get("firstAirDate")
    poster_path = item.get("posterPath")
    poster_url = (
        f"https://image.tmdb.org/t/p/w342{poster_path}" if isinstance(poster_path, str) else None
    )
    return MetadataResult(
        title=str(title or fallback_title(query)),
        year=parse_year(str(date or "")) or parse_year(query),
        overview=_str_or_none(item.get("overview")),
        poster_url=poster_url,
        source="seerr",
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


def _poster_from_arr_images(images: Any) -> str | None:
    if not isinstance(images, list):
        return None
    for image in images:
        if not isinstance(image, dict):
            continue
        if image.get("coverType") == "poster":
            return _str_or_none(image.get("remoteUrl") or image.get("url"))
    return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
