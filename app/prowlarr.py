import hashlib
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.config import Settings
from app.decision import decide_release
from app.models import (
    DiagnosticHint,
    HealthIssue,
    IndexerFailure,
    IndexerStatus,
    ProwlarrDiagnostics,
    Release,
    SearchRequest,
)
from app.quality import parse_quality
from app.scoring import score_release
from app.titlematch import match_title

ApiCallRecorder = Callable[[dict[str, Any]], None]


class ProwlarrClient:
    def __init__(
        self,
        settings: Settings,
        *,
        api_call_recorder: ApiCallRecorder | None = None,
        context: str = "generic",
        request_id: int | None = None,
    ):
        self.settings = settings
        self.base_url = settings.prowlarr_url.rstrip("/")
        self.api_key = settings.prowlarr_api_key
        self.timeout = settings.request_timeout_seconds
        self.api_call_recorder = api_call_recorder
        self.context = context
        self.request_id = request_id

    def scoped(self, context: str, request_id: int | None = None) -> "ProwlarrClient":
        return ProwlarrClient(
            self.settings,
            api_call_recorder=self.api_call_recorder,
            context=context,
            request_id=request_id,
        )

    def ready(self) -> bool:
        if not self.api_key:
            return False
        started = time.perf_counter()
        status_code: int | None = None
        error: str | None = None
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(
                    f"{self.base_url}/api/v1/system/status",
                    headers={"X-Api-Key": self.api_key},
                )
                status_code = resp.status_code
                return resp.status_code == 200
        except httpx.HTTPError as exc:
            error = _error_text(exc)
            return False
        finally:
            self._record_api_call(
                operation="status",
                endpoint="/api/v1/system/status",
                method="GET",
                started=started,
                status_code=status_code,
                error=error,
            )

    def search(self, request: SearchRequest) -> list[Release]:
        if not self.api_key:
            raise RuntimeError("PROWLARR_API_KEY is not set")

        params = search_params(request)

        started = time.perf_counter()
        status_code: int | None = None
        result_count: int | None = None
        error: str | None = None
        with httpx.Client(timeout=self.timeout) as client:
            try:
                resp = client.get(
                    f"{self.base_url}/api/v1/search",
                    params=params,
                    headers={"X-Api-Key": self.api_key},
                )
                status_code = resp.status_code
                resp.raise_for_status()
                data = resp.json()
                result_count = len(data) if isinstance(data, list) else None
            except Exception as exc:
                error = _error_text(exc)
                raise
            finally:
                self._record_api_call(
                    operation="active_search",
                    endpoint="/api/v1/search",
                    method="GET",
                    media_type=request.media_type,
                    query=request.query,
                    limit=request.limit,
                    started=started,
                    status_code=status_code,
                    result_count=result_count,
                    error=error,
                )

        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected Prowlarr search response: {type(data).__name__}")

        releases = [
            release_from_item(
                item,
                request.query,
                request.min_resolution,
                request.expected_year,
            )
            for item in data
            if isinstance(item, dict)
        ]
        releases.sort(key=release_sort_key, reverse=True)
        return releases

    def recent(self, media_type: str, limit: int = 500) -> list[dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("PROWLARR_API_KEY is not set")

        safe_limit = max(1, min(limit, 500))
        started = time.perf_counter()
        status_code: int | None = None
        result_count: int | None = None
        error: str | None = None
        with httpx.Client(timeout=self.timeout) as client:
            try:
                resp = client.get(
                    f"{self.base_url}/api/v1/search",
                    params=recent_search_params(media_type, safe_limit),
                    headers={"X-Api-Key": self.api_key},
                )
                status_code = resp.status_code
                resp.raise_for_status()
                data = resp.json()
                result_count = len(data) if isinstance(data, list) else None
            except Exception as exc:
                error = _error_text(exc)
                raise
            finally:
                self._record_api_call(
                    operation="recent_feed",
                    endpoint="/api/v1/search",
                    method="GET",
                    media_type=media_type,
                    query="",
                    limit=safe_limit,
                    started=started,
                    status_code=status_code,
                    result_count=result_count,
                    error=error,
                )

        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected Prowlarr recent response: {type(data).__name__}")
        return [item for item in data if isinstance(item, dict)][:safe_limit]

    def indexers(self) -> list[IndexerStatus]:
        if not self.api_key:
            raise RuntimeError("PROWLARR_API_KEY is not set")

        started = time.perf_counter()
        status_code: int | None = None
        result_count: int | None = None
        error: str | None = None
        with httpx.Client(timeout=self.timeout) as client:
            try:
                resp = client.get(
                    f"{self.base_url}/api/v1/indexer",
                    headers={"X-Api-Key": self.api_key},
                )
                status_code = resp.status_code
                resp.raise_for_status()
                data = resp.json()
                result_count = len(data) if isinstance(data, list) else None
            except Exception as exc:
                error = _error_text(exc)
                raise
            finally:
                self._record_api_call(
                    operation="indexer_list",
                    endpoint="/api/v1/indexer",
                    method="GET",
                    started=started,
                    status_code=status_code,
                    result_count=result_count,
                    error=error,
                )

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

    def diagnostics(self) -> ProwlarrDiagnostics:
        if not self.api_key:
            raise RuntimeError("PROWLARR_API_KEY is not set")

        indexers = self.indexers()
        statuses = self._get_list("/api/v1/indexerstatus")
        health = self._get_list("/api/v1/health")
        return diagnostics_from_payloads(indexers, statuses, health)

    def _get_list(self, path: str) -> list[dict[str, Any]]:
        started = time.perf_counter()
        status_code: int | None = None
        result_count: int | None = None
        error: str | None = None
        with httpx.Client(timeout=self.timeout) as client:
            try:
                resp = client.get(
                    f"{self.base_url}{path}",
                    headers={"X-Api-Key": self.api_key},
                )
                status_code = resp.status_code
                resp.raise_for_status()
                data = resp.json()
                result_count = len(data) if isinstance(data, list) else None
            except Exception as exc:
                error = _error_text(exc)
                raise
            finally:
                self._record_api_call(
                    operation="diagnostics",
                    endpoint=path,
                    method="GET",
                    started=started,
                    status_code=status_code,
                    result_count=result_count,
                    error=error,
                )

        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected Prowlarr response for {path}: {type(data).__name__}")
        return [item for item in data if isinstance(item, dict)]

    def _record_api_call(
        self,
        *,
        operation: str,
        endpoint: str,
        method: str,
        started: float,
        media_type: str | None = None,
        query: str | None = None,
        limit: int | None = None,
        status_code: int | None = None,
        result_count: int | None = None,
        error: str | None = None,
    ) -> None:
        if not self.api_call_recorder:
            return
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        try:
            self.api_call_recorder(
                {
                    "context": self.context,
                    "operation": operation,
                    "endpoint": endpoint,
                    "method": method,
                    "media_type": media_type,
                    "query": query,
                    "limit": limit,
                    "request_id": self.request_id,
                    "status_code": status_code,
                    "result_count": result_count,
                    "duration_ms": elapsed_ms,
                    "error": error,
                }
            )
        except Exception:
            pass


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


def _error_text(exc: Exception) -> str:
    text = str(exc)
    if not text:
        text = type(exc).__name__
    return text[:500]


def release_from_item(
    item: dict[str, Any],
    query: str,
    min_resolution: str,
    expected_year: int | None,
) -> Release:
    title = str(item.get("title") or item.get("releaseTitle") or "<untitled>")
    size = _int_or_none(item.get("size"))
    download_url = _str_or_none(item.get("downloadUrl") or item.get("downloadUrlMagnet"))
    result_id = _result_id(title, _str_or_none(item.get("guid")), download_url)
    quality = parse_quality(title)
    score = score_release(title, size)
    title_match = match_title(query, title, expected_year=expected_year)
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
        indexer_attrs=_attrs_from_item(item),
        quality=quality,
        title_match=title_match,
        raw=item,
        score=score,
        decision=decide_release(
            score=score,
            quality=quality,
            title_match=title_match,
            size=size,
            download_url=download_url,
            min_resolution=min_resolution,
        ),
    )


def _attrs_from_item(item: dict[str, Any]) -> dict[str, list[Any]]:
    attrs = item.get("attrs") or item.get("attributes")
    if not isinstance(attrs, dict):
        return {}
    normalized: dict[str, list[Any]] = {}
    for key, value in attrs.items():
        name = str(key)
        if isinstance(value, list):
            normalized[name] = value
        elif value is not None:
            normalized[name] = [value]
    return normalized


def search_params(request: SearchRequest) -> dict[str, Any]:
    return {
        "query": request.query,
        "type": request.media_type,
        "limit": request.limit,
        "categories": "2000" if request.media_type == "movie" else "5000",
    }


def recent_search_params(media_type: str, limit: int) -> dict[str, Any]:
    if media_type == "movie":
        search_type = "movie"
        category = "2000"
    elif media_type == "tv":
        search_type = "tvsearch"
        category = "5000"
    else:
        raise ValueError(f"Unsupported media type for recent feed: {media_type}")
    return {
        "query": "",
        "type": search_type,
        "limit": max(1, min(limit, 500)),
        "categories": category,
    }


RESOLUTION_RANK = {
    "2160p": 4,
    "1080p": 3,
    "720p": 2,
    "sd": 1,
    "unknown": 0,
}

SOURCE_RANK = {
    "remux": 6,
    "bluray": 5,
    "web-dl": 4,
    "webrip": 3,
    "hdtv": 2,
    "dvd": 1,
    "cam": -10,
    "unknown": 0,
}


def release_sort_key(release: Release) -> tuple[int, int, int, int, int, int]:
    return (
        1 if release.decision.grab_allowed else 0,
        release.score.score,
        RESOLUTION_RANK.get(release.quality.resolution, 0),
        SOURCE_RANK.get(release.quality.source, 0),
        release.size or 0,
        -(release.age if release.age is not None else 999999),
    )


def diagnostics_from_payloads(
    indexers: list[IndexerStatus],
    statuses: list[dict[str, Any]],
    health: list[dict[str, Any]],
) -> ProwlarrDiagnostics:
    names = {indexer.id: indexer.name for indexer in indexers}
    indexer_failures = [
        IndexerFailure(
            id=_int_or_none(item.get("indexerId") or item.get("indexer_id")),
            name=names.get(
                _int_or_none(item.get("indexerId") or item.get("indexer_id")),
                str(item.get("indexer") or item.get("name") or "Unknown"),
            ),
            disabled_till=_str_or_none(item.get("disabledTill") or item.get("disabled_till")),
            initial_failure=_str_or_none(item.get("initialFailure") or item.get("initial_failure")),
            most_recent_failure=_str_or_none(
                item.get("mostRecentFailure") or item.get("most_recent_failure")
            ),
            level=_str_or_none(item.get("escalationLevel") or item.get("level")),
        )
        for item in statuses
    ]
    health_issues = [
        HealthIssue(
            source=_str_or_none(item.get("source")),
            type=_str_or_none(item.get("type")),
            message=str(item.get("message") or item.get("errorMessage") or item),
        )
        for item in health
    ]
    return ProwlarrDiagnostics(
        indexer_failures=indexer_failures,
        health=health_issues,
        hints=diagnostic_hints(indexers, health_issues, indexer_failures),
    )


def diagnostic_hints(
    indexers: list[IndexerStatus],
    health: list[HealthIssue],
    failures: list[IndexerFailure],
) -> list[DiagnosticHint]:
    hints: list[DiagnosticHint] = []
    health_text = " ".join(issue.message.lower() for issue in health)
    indexer_names = " ".join(indexer.name.lower() for indexer in indexers)
    if "all indexers are unavailable" in health_text:
        if "oldboys" in indexer_names:
            hints.append(
                DiagnosticHint(
                    level="error",
                    message=(
                        "Prowlarr only has OldBoys enabled and marks it failed. "
                        "Check Danish Intelligence logs for unsupported Newznab query types "
                        "such as t=tv or t=movieSearch, or proxy authentication failures."
                    ),
                )
            )
        else:
            hints.append(
                DiagnosticHint(
                    level="error",
                    message=(
                        "Prowlarr reports every enabled indexer as failed. Test each indexer "
                        "in Prowlarr and check recent indexer logs for HTTP/auth/DNS errors."
                    ),
                )
            )
    if failures:
        hints.append(
            DiagnosticHint(
                level="warn",
                message="One or more indexers have an active failure status in Prowlarr.",
            )
        )
    return hints


def _result_id(title: str, guid: str | None, download_url: str | None) -> str:
    source = "\n".join([title, guid or "", download_url or ""])
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]
