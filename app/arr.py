from typing import Any

import httpx

from app.config import Settings
from app.models import MetadataResult, Release, SearchRequest
from app.prowlarr import release_from_item, release_sort_key
from app.titlematch import clean_title, parse_year


class ArrClient:
    def __init__(self, settings: Settings):
        self.radarr_url = settings.radarr_url.rstrip("/")
        self.radarr_api_key = settings.radarr_api_key
        self.sonarr_url = settings.sonarr_url.rstrip("/")
        self.sonarr_api_key = settings.sonarr_api_key
        self.timeout = settings.request_timeout_seconds

    def interactive_search(self, request: SearchRequest) -> list[Release] | None:
        if request.media_type == "movie":
            return self._radarr_interactive_search(request)
        return self._sonarr_interactive_search(request)

    def ensure_media_target(
        self,
        *,
        media_type: str,
        metadata: MetadataResult,
        target_path: str,
        profile_name: str,
    ) -> bool:
        request = SearchRequest(
            query=f"{metadata.title} {metadata.year}" if metadata.year else metadata.title,
            media_type="movie" if media_type == "movie" else "tv",
            expected_year=metadata.year,
            tmdb_id=metadata.tmdb_id,
            tvdb_id=metadata.tvdb_id,
            imdb_id=metadata.imdb_id,
        )
        if media_type == "movie":
            return self._ensure_radarr_target(request, target_path, profile_name)
        return self._ensure_sonarr_target(request, target_path, profile_name)

    def _radarr_interactive_search(self, request: SearchRequest) -> list[Release] | None:
        if not self.radarr_api_key:
            return None
        with httpx.Client(timeout=self.timeout) as client:
            movies = self._get_list(client, self.radarr_url, self.radarr_api_key, "/api/v3/movie")
            movie = find_radarr_movie(movies, request)
            if not movie:
                return None
            movie_id = _int_or_none(movie.get("id"))
            if movie_id is None:
                return None
            releases = self._get_list(
                client,
                self.radarr_url,
                self.radarr_api_key,
                "/api/v3/release",
                {"movieId": movie_id},
            )
        return _map_arr_releases(releases, request)

    def _sonarr_interactive_search(self, request: SearchRequest) -> list[Release] | None:
        if not self.sonarr_api_key:
            return None
        with httpx.Client(timeout=self.timeout) as client:
            series_items = self._get_list(
                client,
                self.sonarr_url,
                self.sonarr_api_key,
                "/api/v3/series",
            )
            series = find_sonarr_series(series_items, request)
            if not series:
                return None
            series_id = _int_or_none(series.get("id"))
            if series_id is None:
                return None
            releases = self._get_list(
                client,
                self.sonarr_url,
                self.sonarr_api_key,
                "/api/v3/release",
                {"seriesId": series_id},
            )
        return _map_arr_releases(releases, request)

    def _get_list(
        self,
        client: httpx.Client,
        base_url: str,
        api_key: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        response = client.get(
            f"{base_url}{path}",
            params=params,
            headers={"X-Api-Key": api_key},
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected Arr response for {path}: {type(data).__name__}")
        return [item for item in data if isinstance(item, dict)]

    def _ensure_radarr_target(
        self,
        request: SearchRequest,
        target_path: str,
        profile_name: str,
    ) -> bool:
        if not self.radarr_api_key:
            return False
        with httpx.Client(timeout=self.timeout) as client:
            movies = self._get_list(client, self.radarr_url, self.radarr_api_key, "/api/v3/movie")
            movie = find_radarr_movie(movies, request)
            profile_id = self._profile_id(client, self.radarr_url, self.radarr_api_key, profile_name)
            if not movie or profile_id is None:
                return False
            return self._update_arr_item(
                client,
                self.radarr_url,
                self.radarr_api_key,
                "/api/v3/movie",
                movie,
                target_path,
                profile_id,
            )

    def _ensure_sonarr_target(
        self,
        request: SearchRequest,
        target_path: str,
        profile_name: str,
    ) -> bool:
        if not self.sonarr_api_key:
            return False
        with httpx.Client(timeout=self.timeout) as client:
            series_items = self._get_list(
                client,
                self.sonarr_url,
                self.sonarr_api_key,
                "/api/v3/series",
            )
            series = find_sonarr_series(series_items, request)
            profile_id = self._profile_id(client, self.sonarr_url, self.sonarr_api_key, profile_name)
            if not series or profile_id is None:
                return False
            return self._update_arr_item(
                client,
                self.sonarr_url,
                self.sonarr_api_key,
                "/api/v3/series",
                series,
                target_path,
                profile_id,
            )

    def _profile_id(
        self,
        client: httpx.Client,
        base_url: str,
        api_key: str,
        profile_name: str,
    ) -> int | None:
        profiles = self._get_list(client, base_url, api_key, "/api/v3/qualityprofile")
        profile = next((item for item in profiles if item.get("name") == profile_name), None)
        return _int_or_none(profile.get("id")) if profile else None

    def _update_arr_item(
        self,
        client: httpx.Client,
        base_url: str,
        api_key: str,
        path: str,
        item: dict[str, Any],
        target_path: str,
        profile_id: int,
    ) -> bool:
        item_id = _int_or_none(item.get("id"))
        if item_id is None:
            return False
        old_path = str(item.get("path") or "")
        folder_name = old_path.rstrip("/").rsplit("/", 1)[-1] if old_path else str(item.get("title") or item_id)
        new_path = f"{target_path.rstrip('/')}/{folder_name}"
        changed = False
        if item.get("qualityProfileId") != profile_id:
            item["qualityProfileId"] = profile_id
            changed = True
        if item.get("rootFolderPath") != target_path:
            item["rootFolderPath"] = target_path
            changed = True
        if item.get("path") != new_path:
            item["path"] = new_path
            changed = True
        if not changed:
            return True
        response = client.put(
            f"{base_url}{path}/{item_id}",
            params={"moveFiles": "false"},
            headers={"X-Api-Key": api_key},
            json=item,
        )
        response.raise_for_status()
        return True


def find_radarr_movie(items: list[dict[str, Any]], request: SearchRequest) -> dict[str, Any] | None:
    return _find_arr_item(items, request, tmdb_key="tmdbId", tvdb_key=None)


def find_sonarr_series(items: list[dict[str, Any]], request: SearchRequest) -> dict[str, Any] | None:
    return _find_arr_item(items, request, tmdb_key="tmdbId", tvdb_key="tvdbId")


def _find_arr_item(
    items: list[dict[str, Any]],
    request: SearchRequest,
    *,
    tmdb_key: str,
    tvdb_key: str | None,
) -> dict[str, Any] | None:
    if request.tmdb_id:
        match = next((item for item in items if _same_id(item.get(tmdb_key), request.tmdb_id)), None)
        if match:
            return match
    if request.tvdb_id and tvdb_key:
        match = next((item for item in items if _same_id(item.get(tvdb_key), request.tvdb_id)), None)
        if match:
            return match
    if request.imdb_id:
        match = next((item for item in items if _same_id(item.get("imdbId"), request.imdb_id)), None)
        if match:
            return match

    wanted_title = clean_title(request.query)
    wanted_year = request.expected_year or parse_year(request.query)
    for item in items:
        title = clean_title(str(item.get("title") or ""))
        item_year = _int_or_none(item.get("year")) or parse_year(str(item.get("releaseDate") or ""))
        if title == wanted_title and (wanted_year is None or item_year == wanted_year):
            return item
    return None


def _map_arr_releases(items: list[dict[str, Any]], request: SearchRequest) -> list[Release]:
    releases = [
        release_from_item(
            item,
            request.query,
            request.min_resolution,
            request.expected_year,
        )
        for item in items
    ]
    releases.sort(key=release_sort_key, reverse=True)
    return releases


def _same_id(value: Any, expected: str) -> bool:
    return str(value or "").strip().lower() == str(expected or "").strip().lower()


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
