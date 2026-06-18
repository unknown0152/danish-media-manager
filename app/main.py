import asyncio
import contextlib
import json
import re

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.altmount import AltMountClient
from app.arr import ArrClient
from app.config import Settings, get_settings
from app.danish_intelligence import DanishIntelligenceClient
from app.import_health import check_import_health
from app.metadata import MetadataClient
from app.models import (
    DownloadStatus,
    GrabRequest,
    GrabResponse,
    ImportHealth,
    IndexerSearchSummary,
    MediaTarget,
    MediaRequest,
    MediaRequestCreate,
    MediaRequestResponse,
    MetadataResult,
    ProwlarrDiagnostics,
    QualitySearchSummary,
    Release,
    SearchRequest,
    SearchResponse,
    SeerrSyncResult,
    WantedRetryResult,
)
from app.prowlarr import ProwlarrClient
from app.seerr import SeerrClient, seerr_media_type, seerr_request_id
from app.store import Store
from app.targets import all_targets, exact_target_for_path, target_for_path

app = FastAPI(title="Danish Media Manager", version="0.30.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

TV_EPISODE_RE = re.compile(r"\bS\d{1,2}E\d{1,3}\b", re.IGNORECASE)
TV_SEASON_RE = re.compile(r"\bS\d{1,2}\b|\bSeason[ ._-]?\d{1,2}\b", re.IGNORECASE)
WANTED_RETRY_STATUSES = {"no_results", "search_failed", "grab_failed"}


@app.on_event("startup")
async def start_seerr_sync_worker() -> None:
    settings = get_settings()
    if not settings.seerr_sync_enabled or not settings.seerr_api_key:
        return
    app.state.seerr_sync_task = asyncio.create_task(_seerr_sync_worker())


@app.on_event("shutdown")
async def stop_seerr_sync_worker() -> None:
    task = getattr(app.state, "seerr_sync_task", None)
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _seerr_sync_worker() -> None:
    await asyncio.sleep(20)
    while True:
        settings = get_settings()
        try:
            await asyncio.to_thread(
                sync_seerr_requests,
                take=20,
                filter_name="all",
                auto_grab=settings.seerr_auto_grab,
                settings=settings,
                seerr_client=SeerrClient(settings),
                di_client=DanishIntelligenceClient(settings),
                prowlarr_client=ProwlarrClient(settings),
                altmount_client=AltMountClient(settings),
                arr_client=ArrClient(settings),
                request_store=Store(settings.database_path),
            )
            if settings.wanted_search_enabled:
                await asyncio.to_thread(
                    retry_wanted_requests,
                    limit=settings.wanted_search_max_per_cycle,
                    auto_grab=settings.seerr_auto_grab,
                    settings=settings,
                    metadata_client=MetadataClient(settings),
                    di_client=DanishIntelligenceClient(settings),
                    prowlarr_client=ProwlarrClient(settings),
                    altmount_client=AltMountClient(settings),
                    arr_client=ArrClient(settings),
                    request_store=Store(settings.database_path),
                )
        except Exception as exc:
            print(f"[DMM] Seerr background sync failed: {exc}", flush=True)
        await asyncio.sleep(max(30, settings.seerr_sync_interval_seconds))


def prowlarr(settings: Settings = Depends(get_settings)) -> ProwlarrClient:
    return ProwlarrClient(settings)


def danish_intelligence(settings: Settings = Depends(get_settings)) -> DanishIntelligenceClient:
    return DanishIntelligenceClient(settings)


def altmount(settings: Settings = Depends(get_settings)) -> AltMountClient:
    return AltMountClient(settings)


def arr(settings: Settings = Depends(get_settings)) -> ArrClient:
    return ArrClient(settings)


def store(settings: Settings = Depends(get_settings)) -> Store:
    return Store(settings.database_path)


def metadata(settings: Settings = Depends(get_settings)) -> MetadataClient:
    return MetadataClient(settings)


def seerr(settings: Settings = Depends(get_settings)) -> SeerrClient:
    return SeerrClient(settings)


def create_scored_request(
    *,
    query: str,
    media_type: str,
    min_resolution: str,
    limit: int,
    target_path: str | None,
    settings: Settings,
    metadata_result: MetadataResult,
    di_client: DanishIntelligenceClient,
    prowlarr_client: ProwlarrClient,
    request_store: Store,
    external_source: str | None = None,
    external_id: str | None = None,
) -> MediaRequestResponse:
    target = target_for_path(settings, media_type, target_path)
    row = request_store.create_media_request(
        query,
        media_type,
        min_resolution,
        target_path=target.path if target else None,
        target_label=target.label if target else None,
        metadata=metadata_result,
        external_source=external_source,
        external_id=external_id,
    )
    request_id = int(row["id"])
    search_request = SearchRequest(
        query=query,
        media_type=media_type,  # type: ignore[arg-type]
        limit=limit,
        min_resolution=min_resolution,  # type: ignore[arg-type]
    )
    search_request = enrich_search_request(search_request, metadata_result)
    try:
        releases = search_releases(
            search_request,
            di_client=di_client,
            prowlarr_client=prowlarr_client,
        )
    except Exception as exc:
        request_store.set_media_request_status(request_id, "search_failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    search_response = build_search_response(
        query=query,
        media_type=media_type,
        releases=releases,
        request_store=request_store,
        metadata_result=metadata_result,
        request_id=request_id,
    )
    best = best_release(releases)
    updated = request_store.update_media_request_search(
        request_id,
        status="ready" if best else "no_results",
        best_result_id=best.result_id if best else None,
        best_title=best.title if best else None,
        best_score=best.score.score if best else None,
        total=search_response.total,
        accepted=search_response.accepted,
        rejected=search_response.rejected,
    )
    if not updated:
        raise HTTPException(status_code=500, detail="Request disappeared after creation")
    return MediaRequestResponse(
        request=MediaRequest.model_validate(updated),
        search=search_response,
    )


def rerun_stored_request_search(
    row: dict,
    *,
    metadata_client: MetadataClient,
    di_client: DanishIntelligenceClient,
    prowlarr_client: ProwlarrClient,
    request_store: Store,
) -> MediaRequestResponse:
    request_id = int(row["id"])
    media_type = str(row["media_type"])
    search_request = SearchRequest(
        query=str(row["query"]),
        media_type=media_type,  # type: ignore[arg-type]
        min_resolution=str(row.get("min_resolution") or "any"),  # type: ignore[arg-type]
        expected_year=row.get("metadata_year") if isinstance(row.get("metadata_year"), int) else None,
    )
    metadata_result = metadata_client.lookup(search_request.query, search_request.media_type)
    if not metadata_result:
        metadata_result = _metadata_from_row(row)
    if metadata_result:
        search_request = enrich_search_request(search_request, metadata_result)
    try:
        releases = search_releases(
            search_request,
            di_client=di_client,
            prowlarr_client=prowlarr_client,
        )
    except Exception as exc:
        request_store.set_media_request_status(request_id, "search_failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    search_response = build_search_response(
        query=str(row["query"]),
        media_type=search_request.media_type,
        releases=releases,
        request_store=request_store,
        metadata_result=metadata_result,
        request_id=request_id,
    )
    best = best_release(releases)
    updated = request_store.update_media_request_search(
        request_id,
        status="ready" if best else "no_results",
        best_result_id=best.result_id if best else None,
        best_title=best.title if best else None,
        best_score=best.score.score if best else None,
        total=search_response.total,
        accepted=search_response.accepted,
        rejected=search_response.rejected,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Request not found")
    return MediaRequestResponse(
        request=MediaRequest.model_validate(updated),
        search=search_response,
    )


def build_search_response(
    *,
    query: str,
    media_type: str,
    releases: list[Release],
    request_store: Store,
    metadata_result: MetadataResult | None = None,
    request_id: int | None = None,
) -> SearchResponse:
    for release in releases:
        request_store.cache_release(query, media_type, release, request_id=request_id)
    accepted = sum(1 for release in releases if release.decision.accepted)
    return SearchResponse(
        query=query,
        media_type=media_type,  # type: ignore[arg-type]
        metadata=metadata_result,
        total=len(releases),
        accepted=accepted,
        rejected=len(releases) - accepted,
        indexers=indexer_summaries(releases),
        quality=quality_summary(releases),
        rejection_summary=reason_summary(
            reason
            for release in releases
            for reason in release.decision.rejections
        ),
        warning_summary=reason_summary(
            reason
            for release in releases
            for reason in release.decision.warnings
        ),
        releases=releases,
    )


def indexer_summaries(releases: list[Release]) -> list[IndexerSearchSummary]:
    grouped: dict[tuple[int | None, str], IndexerSearchSummary] = {}
    for release in releases:
        key = (release.indexer_id, release.indexer or "Unknown")
        summary = grouped.setdefault(
            key,
            IndexerSearchSummary(id=release.indexer_id, name=release.indexer or "Unknown"),
        )
        summary.total += 1
        if release.decision.accepted:
            summary.accepted += 1
        if summary.best_score is None or release.score.score > summary.best_score:
            summary.best_score = release.score.score
    return sorted(grouped.values(), key=lambda item: (item.accepted, item.total), reverse=True)


def quality_summary(releases: list[Release]) -> QualitySearchSummary:
    summary = QualitySearchSummary()
    best: Release | None = None
    for release in releases:
        resolution = release.quality.resolution or "unknown"
        source = release.quality.source or "unknown"
        verdict = release.score.verdict or "unknown"
        summary.resolutions[resolution] = summary.resolutions.get(resolution, 0) + 1
        summary.sources[source] = summary.sources.get(source, 0) + 1
        summary.verdicts[verdict] = summary.verdicts.get(verdict, 0) + 1
        if release.decision.accepted:
            summary.accepted_by_resolution[resolution] = (
                summary.accepted_by_resolution.get(resolution, 0) + 1
            )
        if best is None or release.score.score > best.score.score:
            best = release

    if best:
        summary.best_score = best.score.score
        summary.best_resolution = best.quality.resolution
        summary.best_source = best.quality.source
    summary.resolutions = _sort_count_map(summary.resolutions)
    summary.sources = _sort_count_map(summary.sources)
    summary.verdicts = _sort_count_map(summary.verdicts)
    summary.accepted_by_resolution = _sort_count_map(summary.accepted_by_resolution)
    return summary


def _sort_count_map(values: dict[str, int]) -> dict[str, int]:
    return dict(sorted(values.items(), key=lambda item: item[1], reverse=True))


def reason_summary(reasons) -> dict[str, int]:
    counts: dict[str, int] = {}
    for reason in reasons:
        counts[str(reason)] = counts.get(str(reason), 0) + 1
    return _sort_count_map(counts)


def _str_or_none(value) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def best_release(releases: list[Release]) -> Release | None:
    for release in releases:
        if release.decision.accepted:
            return release
    return None


def desired_profile_name(settings: Settings, target: MediaTarget) -> str:
    haystack = f"{target.label} {target.path}".lower()
    if any(token in haystack for token in ("danish", "kids", "christmas", "classics")):
        return settings.danish_audio_profile_name
    return settings.danish_subtitles_profile_name


def should_mark_seerr_available(media_type: str, title: str | None) -> bool:
    if media_type == "movie":
        return True
    if media_type != "tv" or not title:
        return False
    return bool(TV_SEASON_RE.search(title)) and not TV_EPISODE_RE.search(title)


def enrich_search_request(request: SearchRequest, metadata_result: MetadataResult) -> SearchRequest:
    search_query = metadata_result.title or request.query
    if metadata_result.year and str(metadata_result.year) not in search_query:
        search_query = f"{search_query} {metadata_result.year}"
    return request.model_copy(
        update={
            "query": search_query,
            "expected_year": metadata_result.year or request.expected_year,
            "tmdb_id": metadata_result.tmdb_id,
            "tvdb_id": metadata_result.tvdb_id,
            "imdb_id": metadata_result.imdb_id,
        }
    )


def search_releases(
    request: SearchRequest,
    *,
    di_client: DanishIntelligenceClient,
    prowlarr_client: ProwlarrClient,
) -> list[Release]:
    try:
        releases = di_client.search(request)
    except Exception:
        releases = []
    if releases:
        return releases
    return prowlarr_client.search(request)


def grab_cached_result(
    request: GrabRequest,
    *,
    altmount_client: AltMountClient,
    request_store: Store,
    settings: Settings,
) -> GrabResponse:
    if request.result_id:
        cached = request_store.get_cached_release(request.result_id)
        if not cached:
            raise HTTPException(status_code=404, detail="Search result expired; search again")
        release_payload = json.loads(str(cached["release_json"]))
        decision = release_payload.get("decision") if isinstance(release_payload, dict) else {}
        if isinstance(decision, dict) and decision.get("grab_allowed") is False:
            reasons = decision.get("rejections") if isinstance(decision.get("rejections"), list) else []
            detail = "Release is not grabbable"
            if reasons:
                detail = f"{detail}: {'; '.join(str(reason) for reason in reasons)}"
            raise HTTPException(status_code=409, detail=detail)
        request.download_url = (
            cached.get("download_url") if isinstance(cached.get("download_url"), str) else None
        )
        request.title = str(cached.get("title") or request.title)
        request.media_type = str(cached.get("media_type") or request.media_type)  # type: ignore[assignment]
    elif request.download_url and not settings.allow_direct_download_urls:
        raise HTTPException(
            status_code=403,
            detail="Direct download URLs are disabled; grab a cached search result instead",
        )
    try:
        response = altmount_client.add_uri(request)
        request_store.record_grab(request, response)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return GrabResponse(ok=True, message="Sent to AltMount", altmount_response=response)


def auto_grab_seerr_request(
    *,
    row: dict,
    media_type: str,
    target: MediaTarget,
    metadata_result: MetadataResult,
    settings: Settings,
    altmount_client: AltMountClient,
    arr_client: ArrClient,
    request_store: Store,
) -> GrabResponse:
    best_result_id = row.get("best_result_id")
    if not isinstance(best_result_id, str) or not best_result_id:
        raise RuntimeError("Request has no best result")
    repaired = arr_client.ensure_media_target(
        media_type=media_type,
        metadata=metadata_result,
        target_path=target.path,
        profile_name=desired_profile_name(settings, target),
    )
    if not repaired:
        raise RuntimeError("Arr item was not ready for target repair")
    response = grab_cached_result(
        GrabRequest(
            title=str(row.get("best_title") or row.get("query") or "request"),
            media_type=media_type,  # type: ignore[arg-type]
            result_id=best_result_id,
        ),
        altmount_client=altmount_client,
        request_store=request_store,
        settings=settings,
    )
    request_store.set_media_request_status(int(row["id"]), "grabbed")
    return response


def retry_wanted_requests(
    *,
    limit: int,
    auto_grab: bool,
    settings: Settings,
    metadata_client: MetadataClient,
    di_client: DanishIntelligenceClient,
    prowlarr_client: ProwlarrClient,
    altmount_client: AltMountClient,
    arr_client: ArrClient,
    request_store: Store,
) -> WantedRetryResult:
    result = WantedRetryResult()
    rows = request_store.wanted_media_requests(limit=max(1, min(limit, 50)))
    for row in rows:
        request_id = int(row["id"])
        if str(row.get("status") or "") not in WANTED_RETRY_STATUSES:
            result.skipped += 1
            continue
        try:
            response = rerun_stored_request_search(
                row,
                metadata_client=metadata_client,
                di_client=di_client,
                prowlarr_client=prowlarr_client,
                request_store=request_store,
            )
            result.requests.append(response.request)
            if not response.request.best_result_id:
                result.skipped += 1
                continue
            if not auto_grab:
                result.updated += 1
                continue
            target = target_for_path(
                settings,
                response.request.media_type,
                response.request.target_path,
            )
            metadata_result = response.search.metadata or _metadata_from_row(response.request.model_dump())
            if not target or not metadata_result:
                result.grab_failed += 1
                result.errors.append(f"Request {request_id}: missing target or metadata")
                continue
            auto_grab_seerr_request(
                row=response.request.model_dump(),
                media_type=response.request.media_type,
                target=target,
                metadata_result=metadata_result,
                settings=settings,
                altmount_client=altmount_client,
                arr_client=arr_client,
                request_store=request_store,
            )
            result.grabbed += 1
        except Exception as exc:
            result.failed += 1
            result.errors.append(f"Request {request_id}: {exc}")
    return result


@app.get("/")
def index() -> FileResponse:
    return FileResponse("app/static/index.html")


@app.get("/api/status")
def status(
    settings: Settings = Depends(get_settings),
    prowlarr_client: ProwlarrClient = Depends(prowlarr),
    altmount_client: AltMountClient = Depends(altmount),
) -> dict[str, object]:
    return {
        "app": settings.app_name,
        "prowlarr_url": settings.prowlarr_url,
        "prowlarr_ready": prowlarr_client.ready(),
        "altmount_url": settings.altmount_url,
        "altmount_ready": altmount_client.ready(),
    }


@app.post("/api/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    metadata_client: MetadataClient = Depends(metadata),
    di_client: DanishIntelligenceClient = Depends(danish_intelligence),
    prowlarr_client: ProwlarrClient = Depends(prowlarr),
    request_store: Store = Depends(store),
) -> SearchResponse:
    metadata_result = metadata_client.lookup(request.query, request.media_type)
    search_request = enrich_search_request(request, metadata_result)
    try:
        releases = search_releases(
            search_request,
            di_client=di_client,
            prowlarr_client=prowlarr_client,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return build_search_response(
        query=request.query,
        media_type=request.media_type,
        releases=releases,
        request_store=request_store,
        metadata_result=metadata_result,
    )


@app.post("/api/requests", response_model=MediaRequestResponse)
def create_request(
    request: MediaRequestCreate,
    settings: Settings = Depends(get_settings),
    metadata_client: MetadataClient = Depends(metadata),
    di_client: DanishIntelligenceClient = Depends(danish_intelligence),
    prowlarr_client: ProwlarrClient = Depends(prowlarr),
    request_store: Store = Depends(store),
) -> MediaRequestResponse:
    metadata_result = metadata_client.lookup(request.query, request.media_type)
    return create_scored_request(
        query=request.query,
        media_type=request.media_type,
        limit=request.limit,
        min_resolution=request.min_resolution,
        target_path=request.target_path,
        settings=settings,
        metadata_result=metadata_result,
        di_client=di_client,
        prowlarr_client=prowlarr_client,
        request_store=request_store,
    )


@app.get("/api/releases/{result_id}")
def release_detail(result_id: str, request_store: Store = Depends(store)) -> dict[str, object]:
    cached = request_store.get_cached_release(result_id)
    if not cached:
        raise HTTPException(status_code=404, detail="Search result expired; search again")
    return {
        "result_id": cached["result_id"],
        "created_at": cached["created_at"],
        "release": json.loads(str(cached["release_json"])),
    }


@app.post("/api/grab", response_model=GrabResponse)
def grab(
    request: GrabRequest,
    settings: Settings = Depends(get_settings),
    altmount_client: AltMountClient = Depends(altmount),
    request_store: Store = Depends(store),
) -> GrabResponse:
    return grab_cached_result(
        request,
        altmount_client=altmount_client,
        request_store=request_store,
        settings=settings,
    )


@app.get("/api/requests", response_model=list[MediaRequest])
def requests(request_store: Store = Depends(store)) -> list[MediaRequest]:
    return [MediaRequest.model_validate(row) for row in request_store.recent_media_requests()]


@app.get("/api/requests/{request_id}", response_model=MediaRequest)
def request_detail(request_id: int, request_store: Store = Depends(store)) -> MediaRequest:
    row = request_store.get_media_request(request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    return MediaRequest.model_validate(row)


@app.post("/api/requests/{request_id}/search", response_model=MediaRequestResponse)
def rerun_request_search(
    request_id: int,
    metadata_client: MetadataClient = Depends(metadata),
    di_client: DanishIntelligenceClient = Depends(danish_intelligence),
    prowlarr_client: ProwlarrClient = Depends(prowlarr),
    request_store: Store = Depends(store),
) -> MediaRequestResponse:
    row = request_store.get_media_request(request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    return rerun_stored_request_search(
        row,
        metadata_client=metadata_client,
        di_client=di_client,
        prowlarr_client=prowlarr_client,
        request_store=request_store,
    )


@app.post("/api/wanted/retry", response_model=WantedRetryResult)
def retry_wanted_now(
    limit: int = 10,
    auto_grab: bool | None = None,
    settings: Settings = Depends(get_settings),
    metadata_client: MetadataClient = Depends(metadata),
    di_client: DanishIntelligenceClient = Depends(danish_intelligence),
    prowlarr_client: ProwlarrClient = Depends(prowlarr),
    altmount_client: AltMountClient = Depends(altmount),
    arr_client: ArrClient = Depends(arr),
    request_store: Store = Depends(store),
) -> WantedRetryResult:
    return retry_wanted_requests(
        limit=limit,
        auto_grab=settings.seerr_auto_grab if auto_grab is None else auto_grab,
        settings=settings,
        metadata_client=metadata_client,
        di_client=di_client,
        prowlarr_client=prowlarr_client,
        altmount_client=altmount_client,
        arr_client=arr_client,
        request_store=request_store,
    )


@app.post("/api/requests/{request_id}/grab-best", response_model=GrabResponse)
def grab_best_for_request(
    request_id: int,
    settings: Settings = Depends(get_settings),
    altmount_client: AltMountClient = Depends(altmount),
    request_store: Store = Depends(store),
) -> GrabResponse:
    row = request_store.get_media_request(request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    best_result_id = row.get("best_result_id")
    if not isinstance(best_result_id, str) or not best_result_id:
        raise HTTPException(status_code=409, detail="Request has no best result yet")
    response = grab_cached_result(
        GrabRequest(
            title=str(row.get("best_title") or row.get("query") or "request"),
            media_type=row["media_type"],
            result_id=best_result_id,
        ),
        altmount_client=altmount_client,
        request_store=request_store,
        settings=settings,
    )
    request_store.set_media_request_status(request_id, "grabbed")
    return response


@app.post("/api/seerr/sync", response_model=SeerrSyncResult)
def sync_seerr_requests(
    take: int = 20,
    filter_name: str = "all",
    auto_grab: bool | None = None,
    settings: Settings = Depends(get_settings),
    seerr_client: SeerrClient = Depends(seerr),
    di_client: DanishIntelligenceClient = Depends(danish_intelligence),
    prowlarr_client: ProwlarrClient = Depends(prowlarr),
    altmount_client: AltMountClient = Depends(altmount),
    arr_client: ArrClient = Depends(arr),
    request_store: Store = Depends(store),
) -> SeerrSyncResult:
    try:
        items = seerr_client.requests(take=max(1, min(take, 100)), filter_name=filter_name)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    result = SeerrSyncResult()
    should_auto_grab = settings.seerr_auto_grab if auto_grab is None else auto_grab
    for item in items:
        request_id = seerr_request_id(item)
        media_type = seerr_media_type(item)
        if not request_id or media_type not in {"movie", "tv"}:
            result.skipped += 1
            continue
        root_folder = _str_or_none(item.get("rootFolder"))
        target = exact_target_for_path(settings, media_type, root_folder)
        if not target:
            result.skipped += 1
            if root_folder:
                result.errors.append(f"Seerr request {request_id}: unconfigured rootFolder {root_folder}")
            else:
                result.errors.append(f"Seerr request {request_id}: missing rootFolder")
            continue
        existing = request_store.get_media_request_by_external("seerr", request_id)
        if existing:
            if should_auto_grab and existing.get("status") == "grab_failed" and existing.get("best_result_id"):
                try:
                    metadata_result = seerr_client.metadata_for_request(item)
                    if metadata_result:
                        auto_grab_seerr_request(
                            row=existing,
                            media_type=media_type,
                            target=target,
                            metadata_result=metadata_result,
                            settings=settings,
                            altmount_client=altmount_client,
                            arr_client=arr_client,
                            request_store=request_store,
                        )
                        if should_mark_seerr_available(media_type, _str_or_none(existing.get("best_title"))):
                            seerr_client.mark_available(item)
                        result.grabbed += 1
                except Exception as exc:
                    result.grab_failed += 1
                    result.errors.append(f"Seerr request {request_id} grab failed: {exc}")
            result.skipped += 1
            continue
        try:
            metadata_result = seerr_client.metadata_for_request(item)
            if not metadata_result:
                result.skipped += 1
                continue
            query = metadata_result.title
            if metadata_result.year:
                query = f"{query} {metadata_result.year}"
            response = create_scored_request(
                query=query,
                media_type=media_type,
                min_resolution="1080p",
                limit=100,
                target_path=target.path,
                settings=settings,
                metadata_result=metadata_result,
                di_client=di_client,
                prowlarr_client=prowlarr_client,
                request_store=request_store,
                external_source="seerr",
                external_id=request_id,
            )
            if should_auto_grab:
                try:
                    auto_grab_seerr_request(
                        row=response.request.model_dump(),
                        media_type=media_type,
                        target=target,
                        metadata_result=metadata_result,
                        settings=settings,
                        altmount_client=altmount_client,
                        arr_client=arr_client,
                        request_store=request_store,
                    )
                    if should_mark_seerr_available(media_type, response.request.best_title):
                        seerr_client.mark_available(item)
                    result.grabbed += 1
                except Exception as exc:
                    request_store.set_media_request_status(response.request.id, "grab_failed")
                    result.grab_failed += 1
                    result.errors.append(f"Seerr request {request_id} grab failed: {exc}")
        except Exception as exc:
            result.failed += 1
            result.errors.append(f"Seerr request {request_id}: {exc}")
            continue
        result.imported += 1
        result.requests.append(response)
    return result


@app.get("/api/queue")
def queue(altmount_client: AltMountClient = Depends(altmount)) -> dict[str, object] | str:
    try:
        return altmount_client.queue()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/downloads", response_model=DownloadStatus)
def downloads(altmount_client: AltMountClient = Depends(altmount)) -> DownloadStatus:
    try:
        return altmount_client.downloads()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/import-health", response_model=ImportHealth)
def import_health(settings: Settings = Depends(get_settings)) -> ImportHealth:
    return check_import_health(settings)


@app.get("/api/targets", response_model=dict[str, list[MediaTarget]])
def targets(settings: Settings = Depends(get_settings)) -> dict[str, list[MediaTarget]]:
    return all_targets(settings)


@app.get("/api/indexers")
def indexers(prowlarr_client: ProwlarrClient = Depends(prowlarr)) -> list[dict[str, object]]:
    try:
        return [indexer.model_dump() for indexer in prowlarr_client.indexers()]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/prowlarr-diagnostics", response_model=ProwlarrDiagnostics)
def prowlarr_diagnostics(
    prowlarr_client: ProwlarrClient = Depends(prowlarr),
) -> ProwlarrDiagnostics:
    try:
        return prowlarr_client.diagnostics()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/grabs")
def grabs(request_store: Store = Depends(store)) -> list[dict[str, object]]:
    return request_store.recent_grabs()


def _metadata_from_row(row: dict[str, object]) -> MetadataResult | None:
    title = row.get("metadata_title")
    if not isinstance(title, str) or not title:
        return None
    year = row.get("metadata_year")
    return MetadataResult(
        title=title,
        year=year if isinstance(year, int) else None,
        poster_url=row.get("metadata_poster_url")
        if isinstance(row.get("metadata_poster_url"), str)
        else None,
        source="stored",
    )
