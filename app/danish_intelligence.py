from typing import Any

import httpx

from app.config import Settings
from app.models import Release, SearchRequest
from app.prowlarr import release_from_item, release_sort_key


class DanishIntelligenceClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.danish_intelligence_url.rstrip("/")
        self.api_key = settings.prowlarr_api_key
        self.timeout = settings.request_timeout_seconds

    def search(self, request: SearchRequest) -> list[Release]:
        if not self.api_key:
            raise RuntimeError("PROWLARR_API_KEY is not set")
        params = search_params(request)
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/search/v1",
                params=params,
                headers={"X-Api-Key": self.api_key},
            )
            response.raise_for_status()
            data = response.json()
        items = data.get("results") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise RuntimeError("Unexpected Danish Intelligence search response")
        releases = [
            release_from_item(
                item,
                request.query,
                request.min_resolution,
                request.expected_year,
            )
            for item in items
            if isinstance(item, dict)
        ]
        releases.sort(key=release_sort_key, reverse=True)
        return releases


def search_params(request: SearchRequest) -> dict[str, Any]:
    params: dict[str, Any] = {
        "query": request.query,
        "media_type": request.media_type,
        "limit": request.limit,
    }
    if request.tmdb_id:
        params["tmdb_id"] = request.tmdb_id
    if request.tvdb_id:
        params["tvdb_id"] = request.tvdb_id
    if request.imdb_id:
        params["imdb_id"] = request.imdb_id
    return params
