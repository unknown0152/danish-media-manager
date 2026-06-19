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
    CompletionSyncResult,
    DownloadItem,
    DownloadStatus,
    FeedSyncResult,
    GrabRequest,
    GrabResponse,
    ImportHealth,
    IndexerSearchSummary,
    MediaTarget,
    MediaRequest,
    MediaRequestCreate,
    MediaRequestResponse,
    MetadataResult,
    MonitoredItem,
    ProwlarrDiagnostics,
    QualitySearchSummary,
    Release,
    SearchRequest,
    SearchResponse,
    SeerrSyncResult,
    WantedRetryResult,
)
from app.prowlarr import ProwlarrClient, release_from_item, release_sort_key
from app.seerr import SeerrClient, seerr_media_type, seerr_request_id
from app.store import Store
from app.targets import all_targets, exact_target_for_path, target_for_path

app = FastAPI(title="Danish Media Manager", version="0.36.1")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

TV_EPISODE_RE = re.compile(r"\bS\d{1,2}E\d{1,3}\b", re.IGNORECASE)
TV_SEASON_RE = re.compile(r"\bS\d{1,2}\b|\bSeason[ ._-]?\d{1,2}\b", re.IGNORECASE)
TV_EPISODE_NUM_RE = re.compile(r"\bS(?P<season>\d{1,2})E(?P<episode>\d{1,3})\b", re.IGNORECASE)
TV_SEASON_NUM_RE = re.compile(r"\bS(?P<season>\d{1,2})\b|\bSeason[ ._-]?(?P<word_season>\d{1,2})\b", re.IGNORECASE)
WANTED_RETRY_STATUSES = {"no_results", "search_failed", "grab_failed"}


@app.on_event("startup")
async def start_background_monitor_worker() -> None:
    settings = get_settings()
    if not background_monitor_enabled(settings):
        return
    app.state.background_monitor_task = asyncio.create_task(_background_monitor_worker())


@app.on_event("shutdown")
async def stop_background_monitor_worker() -> None:
    task = getattr(app.state, "background_monitor_task", None)
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def background_monitor_enabled(settings: Settings) -> bool:
    seerr_ready = settings.seerr_sync_enabled and bool(settings.seerr_api_key)
    return seerr_ready or settings.recent_feed_sync_enabled or settings.wanted_search_enabled


def run_background_monitor_cycle(settings: Settings) -> None:
    if settings.seerr_sync_enabled and settings.seerr_api_key:
        try:
            sync_seerr_requests(
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
        except Exception as exc:
            print(f"[DMM] Seerr background sync failed: {exc}", flush=True)
    if settings.recent_feed_sync_enabled:
        try:
            sync_recent_releases(
                limit=settings.monitored_requests_max_per_cycle,
                feed_limit=settings.recent_feed_limit,
                auto_grab=settings.seerr_auto_grab,
                settings=settings,
                prowlarr_client=ProwlarrClient(settings),
                altmount_client=AltMountClient(settings),
                arr_client=ArrClient(settings),
                request_store=Store(settings.database_path),
            )
        except Exception as exc:
            print(f"[DMM] Recent feed sync failed: {exc}", flush=True)
    try:
        sync_altmount_completions(
            settings=settings,
            altmount_client=AltMountClient(settings),
            arr_client=ArrClient(settings),
            request_store=Store(settings.database_path),
        )
    except Exception as exc:
        print(f"[DMM] AltMount completion sync failed: {exc}", flush=True)
    if settings.wanted_search_enabled:
        try:
            retry_wanted_requests(
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
            print(f"[DMM] Wanted background search failed: {exc}", flush=True)


async def _background_monitor_worker() -> None:
    await asyncio.sleep(20)
    while True:
        settings = get_settings()
        await asyncio.to_thread(run_background_monitor_cycle, settings)
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
    origin_source: str | None = None,
    origin_details: str | None = None,
    tv_season: int | None = None,
    tv_episode: int | None = None,
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
        origin_source=origin_source,
        origin_details=origin_details,
        tv_season=tv_season,
        tv_episode=tv_episode,
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
    _mark_best_monitored_item(request_store, updated, best)
    _expand_tv_items_from_metadata(
        request_store=request_store,
        request_id=request_id,
        media_type=media_type,
        metadata_result=metadata_result,
        seasons=[tv_season] if tv_season is not None and tv_episode is None else [],
    )
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
    metadata_result = _stored_metadata_with_lookup(row, metadata_client, search_request)
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
    _mark_best_monitored_item(request_store, updated, best)
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
    monitored_item_id: int | None = None
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
        monitored_item_id = _monitored_item_id_for_cached_release(request_store, cached, request)
    elif request.download_url and not settings.allow_direct_download_urls:
        raise HTTPException(
            status_code=403,
            detail="Direct download URLs are disabled; grab a cached search result instead",
        )
    try:
        response = altmount_client.add_uri(request)
        request_store.record_grab(request, response, monitored_item_id=monitored_item_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return GrabResponse(ok=True, message="Sent to AltMount", altmount_response=response)


def _monitored_item_id_for_cached_release(
    request_store: Store,
    cached: dict[str, object],
    request: GrabRequest,
) -> int | None:
    request_id = _int_or_none(cached.get("request_id"))
    if request_id is None:
        return None
    release_payload = json.loads(str(cached["release_json"]))
    title = str(release_payload.get("title") or request.title) if isinstance(release_payload, dict) else request.title
    season_number, episode_number = (
        _parse_release_tv_scope(title) if request.media_type == "tv" else (None, None)
    )
    item = request_store.best_monitored_item_for_scope(
        request_id,
        media_type=request.media_type,
        season_number=season_number,
        episode_number=episode_number,
    )
    return int(item["id"]) if item else None


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


def sync_recent_releases(
    *,
    limit: int,
    feed_limit: int,
    auto_grab: bool,
    settings: Settings,
    prowlarr_client: ProwlarrClient,
    altmount_client: AltMountClient,
    arr_client: ArrClient,
    request_store: Store,
) -> FeedSyncResult:
    result = FeedSyncResult()
    rows = request_store.monitored_media_requests(limit=max(1, min(limit, 500)))
    result.requests_checked = len(rows)
    by_type: dict[str, list[dict]] = {"movie": [], "tv": []}
    for row in rows:
        media_type = str(row.get("media_type") or "")
        if media_type in by_type:
            by_type[media_type].append(row)
        else:
            result.skipped += 1

    recent_by_type: dict[str, list[dict[str, object]]] = {}
    for media_type, media_rows in by_type.items():
        if not media_rows:
            continue
        try:
            recent = prowlarr_client.recent(media_type, limit=max(1, min(feed_limit, 500)))
        except Exception as exc:
            result.errors.append(f"{media_type} recent feed failed: {exc}")
            continue
        recent_by_type[media_type] = recent
        if media_type == "movie":
            result.movies_seen = len(recent)
        else:
            result.tv_seen = len(recent)

    for media_type, media_rows in by_type.items():
        recent_items = recent_by_type.get(media_type, [])
        if not recent_items:
            result.skipped += len(media_rows)
            continue
        for row in media_rows:
            request_id = int(row["id"])
            try:
                request_store.mark_media_request_feed_checked(request_id)
                monitored_item = _monitored_item_for_row(request_store, row, None)
                if monitored_item:
                    request_store.mark_monitored_item_feed_checked(int(monitored_item["id"]))
                metadata_result = _metadata_from_row(row)
                query = _feed_match_query(row, metadata_result)
                min_resolution = str(row.get("min_resolution") or "any")
                expected_year = metadata_result.year if metadata_result else None
                releases = []
                for item in recent_items:
                    release = release_from_item(
                        item,
                        query,
                        min_resolution,
                        expected_year,
                    )
                    if _feed_title_candidate(release):
                        if not _feed_tv_scope_candidate(row, release):
                            continue
                        releases.append(release)
                releases.sort(key=release_sort_key, reverse=True)
                best = best_release(releases)
                if not best:
                    result.skipped += 1
                    continue
                result.matched += 1
                search_response = build_search_response(
                    query=str(row["query"]),
                    media_type=media_type,
                    releases=releases,
                    request_store=request_store,
                    metadata_result=metadata_result,
                    request_id=request_id,
                )
                updated = request_store.update_media_request_search(
                    request_id,
                    status="ready",
                    best_result_id=best.result_id,
                    best_title=best.title,
                    best_score=best.score.score,
                    total=search_response.total,
                    accepted=search_response.accepted,
                    rejected=search_response.rejected,
                )
                if not updated:
                    result.errors.append(f"Request {request_id}: disappeared during feed sync")
                    continue
                request_store.mark_media_request_feed_matched(request_id, best.title)
                matched_item = _monitored_item_for_row(request_store, updated, best)
                if matched_item:
                    request_store.mark_monitored_item_feed_matched(
                        int(matched_item["id"]),
                        result_id=best.result_id,
                        title=best.title,
                    )
                result.updated += 1
                if not auto_grab:
                    continue
                target = target_for_path(settings, media_type, _str_or_none(updated.get("target_path")))
                metadata_result = metadata_result or _metadata_from_row(updated)
                if not target or not metadata_result:
                    result.grab_failed += 1
                    result.errors.append(f"Request {request_id}: missing target or metadata")
                    continue
                auto_grab_seerr_request(
                    row=updated,
                    media_type=media_type,
                    target=target,
                    metadata_result=metadata_result,
                    settings=settings,
                    altmount_client=altmount_client,
                    arr_client=arr_client,
                    request_store=request_store,
                )
                result.grabbed += 1
            except Exception as exc:
                result.errors.append(f"Request {request_id}: {exc}")
    result.run_id = request_store.record_feed_sync_run(
        movies_seen=result.movies_seen,
        tv_seen=result.tv_seen,
        requests_checked=result.requests_checked,
        matched=result.matched,
        updated=result.updated,
        grabbed=result.grabbed,
        grab_failed=result.grab_failed,
        skipped=result.skipped,
        errors=result.errors,
    )
    return result


def sync_altmount_completions(
    *,
    settings: Settings,
    altmount_client: AltMountClient,
    arr_client: ArrClient,
    request_store: Store,
) -> CompletionSyncResult:
    result = CompletionSyncResult()
    grabs = request_store.active_grabs(limit=100)
    if not grabs:
        return result
    downloads = altmount_client.downloads()
    queue_by_id, queue_by_name = _download_maps(downloads.queue)
    history_by_id, history_by_name = _download_maps(downloads.history)
    for grab in grabs:
        result.checked += 1
        grab_id = int(grab["id"])
        try:
            queue_item = _download_for_grab(grab, by_id=queue_by_id, by_name=queue_by_name)
            if queue_item:
                request_store.update_grab_status(grab_id, status="downloading")
                _set_grab_item_status(request_store, grab, "downloading")
                result.downloading += 1
                continue
            history_item = _download_for_grab(grab, by_id=history_by_id, by_name=history_by_name)
            if history_item:
                status = history_item.status.lower()
                if any(token in status for token in ("fail", "error", "repair")):
                    request_store.update_grab_status(
                        grab_id,
                        status="failed",
                        completed=False,
                        last_error=history_item.status,
                    )
                    _set_grab_item_status(request_store, grab, "failed")
                    result.failed += 1
                    continue
                request_store.update_grab_status(grab_id, status="import_pending", completed=True)
                _set_grab_item_status(request_store, grab, "import_pending")
                if _trigger_arr_rescan_for_grab(
                    grab,
                    settings=settings,
                    arr_client=arr_client,
                    request_store=request_store,
                ):
                    result.rescans_triggered += 1
                result.completed += 1
                continue
            result.missing += 1
        except Exception as exc:
            result.errors.append(f"Grab {grab_id}: {exc}")
    return result


def _download_maps(items: list[DownloadItem]) -> tuple[dict[str, DownloadItem], dict[str, DownloadItem]]:
    by_id: dict[str, DownloadItem] = {}
    by_name: dict[str, DownloadItem] = {}
    for item in items:
        if item.id:
            by_id[item.id] = item
        name_key = _normalize_download_name(item.name)
        if name_key:
            by_name[name_key] = item
    return by_id, by_name


def _download_for_grab(
    grab: dict[str, object],
    *,
    by_id: dict[str, DownloadItem],
    by_name: dict[str, DownloadItem],
) -> DownloadItem | None:
    download_id = _str_or_none(grab.get("download_id"))
    if download_id and download_id in by_id:
        return by_id[download_id]
    title = str(grab.get("download_name") or grab.get("title") or "")
    return by_name.get(_normalize_download_name(title))


def _set_grab_item_status(request_store: Store, grab: dict[str, object], status: str) -> None:
    item_id = _int_or_none(grab.get("monitored_item_id"))
    if item_id is not None:
        request_store.set_monitored_item_status(item_id, status)


def _trigger_arr_rescan_for_grab(
    grab: dict[str, object],
    *,
    settings: Settings,
    arr_client: ArrClient,
    request_store: Store,
) -> bool:
    item_id = _int_or_none(grab.get("monitored_item_id"))
    if item_id is None:
        return False
    item = request_store.get_monitored_item(item_id)
    if not item:
        return False
    row = request_store.get_media_request(int(item["request_id"]))
    if not row:
        return False
    metadata_result = _metadata_from_row(row)
    if not metadata_result:
        return False
    return arr_client.rescan_for_metadata(str(row["media_type"]), metadata_result)


def _normalize_download_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _feed_match_query(row: dict[str, object], metadata_result: MetadataResult | None) -> str:
    if metadata_result:
        return metadata_result.title
    return str(row.get("query") or "")


def _feed_title_candidate(release: Release) -> bool:
    if not release.title_match:
        return False
    if release.title_match.year_matches is False:
        return False
    return release.title_match.token_overlap >= 0.6


def _feed_tv_scope_candidate(row: dict[str, object], release: Release) -> bool:
    if str(row.get("media_type") or "") != "tv":
        return True
    wanted_season = _int_or_none(row.get("tv_season"))
    wanted_episode = _int_or_none(row.get("tv_episode"))
    if wanted_season is None and wanted_episode is None:
        return True
    found_season, found_episode = _parse_release_tv_scope(release.title)
    if found_season is None:
        return True
    if wanted_season is not None and found_season != wanted_season:
        return False
    if wanted_episode is not None and found_episode is not None and found_episode != wanted_episode:
        return False
    return True


def _monitored_item_for_row(
    request_store: Store,
    row: dict[str, object],
    release: Release | None,
) -> dict[str, object] | None:
    media_type = str(row.get("media_type") or "")
    season_number = _int_or_none(row.get("tv_season"))
    episode_number = _int_or_none(row.get("tv_episode"))
    if media_type == "tv" and release is not None:
        parsed_season, parsed_episode = _parse_release_tv_scope(release.title)
        season_number = parsed_season if parsed_season is not None else season_number
        episode_number = parsed_episode if parsed_episode is not None else episode_number
    return request_store.best_monitored_item_for_scope(
        int(row["id"]),
        media_type=media_type,
        season_number=season_number,
        episode_number=episode_number,
    )


def _mark_best_monitored_item(
    request_store: Store,
    row: dict[str, object],
    release: Release | None,
) -> None:
    if release is None:
        return
    matched_item = _monitored_item_for_row(request_store, row, release)
    if matched_item:
        request_store.mark_monitored_item_feed_matched(
            int(matched_item["id"]),
            result_id=release.result_id,
            title=release.title,
        )


def _parse_release_tv_scope(title: str) -> tuple[int | None, int | None]:
    episode_match = TV_EPISODE_NUM_RE.search(title)
    if episode_match:
        return int(episode_match.group("season")), int(episode_match.group("episode"))
    season_match = TV_SEASON_NUM_RE.search(title)
    if season_match:
        season = season_match.group("season") or season_match.group("word_season")
        return int(season), None
    return None, None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


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
        origin_source="dmm",
        tv_season=request.tv_season,
        tv_episode=request.tv_episode,
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


@app.get("/api/requests/{request_id}/items", response_model=list[MonitoredItem])
def request_items(request_id: int, request_store: Store = Depends(store)) -> list[MonitoredItem]:
    if not request_store.get_media_request(request_id):
        raise HTTPException(status_code=404, detail="Request not found")
    return [
        MonitoredItem.model_validate(row)
        for row in request_store.monitored_items_for_request(request_id)
    ]


@app.get("/api/monitored-items", response_model=list[MonitoredItem])
def monitored_items(request_store: Store = Depends(store)) -> list[MonitoredItem]:
    return [MonitoredItem.model_validate(row) for row in request_store.monitored_items()]


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


@app.post("/api/feed/sync", response_model=FeedSyncResult)
def sync_recent_feed_now(
    limit: int = 100,
    feed_limit: int | None = None,
    auto_grab: bool | None = None,
    settings: Settings = Depends(get_settings),
    prowlarr_client: ProwlarrClient = Depends(prowlarr),
    altmount_client: AltMountClient = Depends(altmount),
    arr_client: ArrClient = Depends(arr),
    request_store: Store = Depends(store),
) -> FeedSyncResult:
    return sync_recent_releases(
        limit=limit,
        feed_limit=settings.recent_feed_limit if feed_limit is None else feed_limit,
        auto_grab=settings.seerr_auto_grab if auto_grab is None else auto_grab,
        settings=settings,
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
                origin_source="seerr",
                origin_details=json.dumps(_seerr_origin_details(item), ensure_ascii=False),
                **_seerr_tv_scope(item),
            )
            _create_seerr_monitored_items(
                request_store=request_store,
                request_id=response.request.id,
                media_type=media_type,
                item=item,
            )
            _expand_tv_items_from_metadata(
                request_store=request_store,
                request_id=response.request.id,
                media_type=media_type,
                metadata_result=metadata_result,
                seasons=_seerr_requested_seasons(item),
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


@app.post("/api/completions/sync", response_model=CompletionSyncResult)
def sync_completions_now(
    settings: Settings = Depends(get_settings),
    altmount_client: AltMountClient = Depends(altmount),
    arr_client: ArrClient = Depends(arr),
    request_store: Store = Depends(store),
) -> CompletionSyncResult:
    try:
        return sync_altmount_completions(
            settings=settings,
            altmount_client=altmount_client,
            arr_client=arr_client,
            request_store=request_store,
        )
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


@app.get("/api/feed/runs")
def feed_runs(request_store: Store = Depends(store)) -> list[dict[str, object]]:
    runs: list[dict[str, object]] = []
    for row in request_store.recent_feed_sync_runs():
        normalized = dict(row)
        errors_json = normalized.pop("errors_json", "[]")
        try:
            errors = json.loads(str(errors_json))
        except json.JSONDecodeError:
            errors = []
        normalized["errors"] = errors if isinstance(errors, list) else []
        runs.append(normalized)
    return runs


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
        tmdb_id=row.get("metadata_tmdb_id")
        if isinstance(row.get("metadata_tmdb_id"), str)
        else None,
        tvdb_id=row.get("metadata_tvdb_id")
        if isinstance(row.get("metadata_tvdb_id"), str)
        else None,
        imdb_id=row.get("metadata_imdb_id")
        if isinstance(row.get("metadata_imdb_id"), str)
        else None,
        external_id=row.get("external_id") if isinstance(row.get("external_id"), str) else None,
        source="stored",
    )


def _stored_metadata_with_lookup(
    row: dict[str, object],
    metadata_client: MetadataClient,
    search_request: SearchRequest,
) -> MetadataResult | None:
    stored = _metadata_from_row(row)
    looked_up = metadata_client.lookup(search_request.query, search_request.media_type)
    if not stored:
        return looked_up
    if not looked_up:
        return stored
    return MetadataResult(
        title=stored.title or looked_up.title,
        year=stored.year or looked_up.year,
        overview=looked_up.overview,
        poster_url=stored.poster_url or looked_up.poster_url,
        source=stored.source,
        external_id=stored.external_id or looked_up.external_id,
        tmdb_id=stored.tmdb_id or looked_up.tmdb_id,
        tvdb_id=stored.tvdb_id or looked_up.tvdb_id,
        imdb_id=stored.imdb_id or looked_up.imdb_id,
        tv_seasons=looked_up.tv_seasons or stored.tv_seasons,
    )


def _seerr_tv_scope(item: dict[str, object]) -> dict[str, int | None]:
    if seerr_media_type(item) != "tv":
        return {"tv_season": None, "tv_episode": None}
    seasons = _seerr_requested_seasons(item)
    if len(seasons) == 1:
        return {"tv_season": seasons[0], "tv_episode": None}
    return {"tv_season": None, "tv_episode": None}


def _seerr_origin_details(item: dict[str, object]) -> dict[str, object]:
    details: dict[str, object] = {}
    seasons = _seerr_requested_seasons(item)
    if seasons:
        details["seasons"] = seasons
    for key in ("requestedBy", "is4k", "serverId", "profileId", "rootFolder"):
        value = item.get(key)
        if value is not None:
            details[key] = value
    return details


def _create_seerr_monitored_items(
    *,
    request_store: Store,
    request_id: int,
    media_type: str,
    item: dict[str, object],
) -> None:
    if media_type != "tv":
        return
    seasons = _seerr_requested_seasons(item)
    if len(seasons) <= 1:
        return
    for season in seasons:
        request_store.create_monitored_item(
            request_id,
            media_type="tv",
            item_type="season",
            season_number=season,
        )


def _expand_tv_items_from_metadata(
    *,
    request_store: Store,
    request_id: int,
    media_type: str,
    metadata_result: MetadataResult,
    seasons: list[int],
) -> int:
    if media_type != "tv" or not seasons:
        return 0
    wanted = set(seasons)
    added = 0
    for season in metadata_result.tv_seasons:
        if season.season_number not in wanted:
            continue
        if not season.episode_count:
            continue
        added += request_store.create_monitored_episode_items(
            request_id,
            season_number=season.season_number,
            episode_count=season.episode_count,
        )
    return added


def _seerr_requested_seasons(item: dict[str, object]) -> list[int]:
    seasons: list[int] = []
    raw = item.get("seasons")
    if not isinstance(raw, list):
        return seasons
    for season in raw:
        if not isinstance(season, dict):
            continue
        value = season.get("seasonNumber")
        number = _int_or_none(value)
        if number is not None:
            seasons.append(number)
    return sorted(set(seasons))
