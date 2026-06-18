import hashlib
from typing import Any

import httpx

from app.config import Settings
from app.decision import decide_release
from app.models import IndexerStatus, Release, SearchRequest
from app.quality import parse_quality
from app.scoring import score_release


class ProwlarrClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.prowlarr_url.rstrip("/")
        self.api_key = settings.prowlarr_api_key
        self.timeout = settings.request_timeout_seconds

    def ready(self) -> bool:
        if not self.api_key:
            return False
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(
                    f"{self.base_url}/api/v1/system/status",
                    headers={"X-Api-Key": self.api_key},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def search(self, request: SearchRequest) -> list[Release]:
        if not self.api_key:
            raise RuntimeError("PROWLARR_API_KEY is not set")

        params: dict[str, Any] = {
            "query": request.query,
            "type": request.media_type,
            "limit": request.limit,
        }
        params["categories"] = "2000" if request.media_type == "movie" else "5000"

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(
                f"{self.base_url}/api/v1/search",
                params=params,
                headers={"X-Api-Key": self.api_key},
            )
            resp.raise_for_status()
            data = resp.json()

        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected Prowlarr search response: {type(data).__name__}")

        releases = [self._release_from_item(item) for item in data if isinstance(item, dict)]
        releases.sort(key=lambda release: release.score.score, reverse=True)
        return releases

    def indexers(self) -> list[IndexerStatus]:
        if not self.api_key:
            raise RuntimeError("PROWLARR_API_KEY is not set")

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(
                f"{self.base_url}/api/v1/indexer",
                headers={"X-Api-Key": self.api_key},
            )
            resp.raise_for_status()
            data = resp.json()

        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected Prowlarr indexer response: {type(data).__name__}")

        return [
            IndexerStatus(
                id=_int_or_none(item.get("id")),
                name=str(item.get("name") or "Unknown"),
                implementation=_str_or_none(item.get("implementation")),
                protocol=_str_or_none(item.get("protocol")),
                enable=item.get("enable") if isinstance(item.get("enable"), bool) else None,
                priority=_int_or_none(item.get("priority")),
                tags=item.get("tags") if isinstance(item.get("tags"), list) else [],
            )
            for item in data
            if isinstance(item, dict)
        ]

    def _release_from_item(self, item: dict[str, Any]) -> Release:
        title = str(item.get("title") or item.get("releaseTitle") or "<untitled>")
        size = _int_or_none(item.get("size"))
        download_url = _str_or_none(item.get("downloadUrl") or item.get("downloadUrlMagnet"))
        result_id = _result_id(title, _str_or_none(item.get("guid")), download_url)
        quality = parse_quality(title)
        score = score_release(title, size)
        return Release(
            result_id=result_id,
            title=title,
            indexer=str(item.get("indexer") or item.get("indexerName") or "Unknown"),
            protocol=item.get("protocol"),
            age=_int_or_none(item.get("age")),
            size=size,
            guid=_str_or_none(item.get("guid")),
            download_url=download_url,
            indexer_id=_int_or_none(item.get("indexerId")),
            categories=item.get("categories") if isinstance(item.get("categories"), list) else [],
            quality=quality,
            raw=item,
            score=score,
            decision=decide_release(
                score=score,
                quality=quality,
                size=size,
                download_url=download_url,
            ),
        )


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _result_id(title: str, guid: str | None, download_url: str | None) -> str:
    source = "\n".join([title, guid or "", download_url or ""])
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]
