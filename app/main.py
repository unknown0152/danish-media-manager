from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.arr import ArrClient
from app.altmount import AltMountClient
from app.config import Settings, get_settings
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
)
from app.prowlarr import ProwlarrClient
from app.store import Store
from app.targets import all_targets, target_for_path
import json

app = FastAPI(title="Danish Media Manager", version="0.20.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

def prowlarr(settings: Settings = Depends(get_settings)) -> ProwlarrClient:
    return ProwlarrClient(settings)


def altmount(settings: Settings = Depends(get_settings)) -> AltMountClient:
    return AltMountClient(settings)


def arr(settings: Settings = Depends(get_settings)) -> ArrClient:
    return ArrClient(settings)


def store(settings: Settings = Depends(get_settings)) -> Store:
    return Store(settings.database_path)


def metadata(settings: Settings = Depends(get_settings)) -> MetadataClient:
    return MetadataClient(settings)


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


def best_release(releases: list[Release]) -> Release | None:
    for release in releases:
        if release.decision.accepted:
            return release
    return None


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
    arr_client: ArrClient,
    prowlarr_client: ProwlarrClient,
) -> list[Release]:
    releases = arr_client.interactive_search(request)
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
    arr_client: ArrClient = Depends(arr),
    prowlarr_client: ProwlarrClient = Depends(prowlarr),
    request_store: Store = Depends(store),
) -> SearchResponse:
    metadata_result = metadata_client.lookup(request.query, request.media_type)
    search_request = enrich_search_request(request, metadata_result)
    try:
        releases = search_releases(
            search_request,
            arr_client=arr_client,
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
    arr_client: ArrClient = Depends(arr),
    prowlarr_client: ProwlarrClient = Depends(prowlarr),
    request_store: Store = Depends(store),
) -> MediaRequestResponse:
    metadata_result = metadata_client.lookup(request.query, request.media_type)
    target = target_for_path(settings, request.media_type, request.target_path)
    row = request_store.create_media_request(
        request.query,
        request.media_type,
        request.min_resolution,
        target_path=target.path if target else None,
        target_label=target.label if target else None,
        metadata=metadata_result,
    )
    request_id = int(row["id"])
    search_request = SearchRequest(
        query=request.query,
        media_type=request.media_type,
        limit=request.limit,
        min_resolution=request.min_resolution,
    )
    search_request = enrich_search_request(search_request, metadata_result)
    try:
        releases = search_releases(
            search_request,
            arr_client=arr_client,
            prowlarr_client=prowlarr_client,
        )
    except Exception as exc:
        request_store.set_media_request_status(request_id, "search_failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    search_response = build_search_response(
        query=request.query,
        media_type=request.media_type,
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
    arr_client: ArrClient = Depends(arr),
    prowlarr_client: ProwlarrClient = Depends(prowlarr),
    request_store: Store = Depends(store),
) -> MediaRequestResponse:
    row = request_store.get_media_request(request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    search_request = SearchRequest(
        query=str(row["query"]),
        media_type=row["media_type"],
        min_resolution=str(row.get("min_resolution") or "any"),  # type: ignore[arg-type]
        expected_year=row.get("metadata_year") if isinstance(row.get("metadata_year"), int) else None,
    )
    metadata_result = metadata_client.lookup(search_request.query, search_request.media_type)
    search_request = enrich_search_request(search_request, metadata_result)
    try:
        releases = search_releases(
            search_request,
            arr_client=arr_client,
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
