from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.altmount import AltMountClient
from app.config import Settings, get_settings
from app.models import (
    DownloadStatus,
    GrabRequest,
    GrabResponse,
    MediaRequest,
    MediaRequestCreate,
    MediaRequestResponse,
    Release,
    SearchRequest,
    SearchResponse,
)
from app.prowlarr import ProwlarrClient
from app.store import Store
import json

app = FastAPI(title="Danish Media Manager", version="0.5.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

def prowlarr(settings: Settings = Depends(get_settings)) -> ProwlarrClient:
    return ProwlarrClient(settings)


def altmount(settings: Settings = Depends(get_settings)) -> AltMountClient:
    return AltMountClient(settings)


def store(settings: Settings = Depends(get_settings)) -> Store:
    return Store(settings.database_path)


def build_search_response(
    *,
    query: str,
    media_type: str,
    releases: list[Release],
    request_store: Store,
    request_id: int | None = None,
) -> SearchResponse:
    for release in releases:
        request_store.cache_release(query, media_type, release, request_id=request_id)
    accepted = sum(1 for release in releases if release.decision.accepted)
    return SearchResponse(
        query=query,
        media_type=media_type,  # type: ignore[arg-type]
        total=len(releases),
        accepted=accepted,
        rejected=len(releases) - accepted,
        releases=releases,
    )


def best_release(releases: list[Release]) -> Release | None:
    for release in releases:
        if release.decision.accepted:
            return release
    return releases[0] if releases else None


def grab_cached_result(
    request: GrabRequest,
    *,
    altmount_client: AltMountClient,
    request_store: Store,
) -> GrabResponse:
    if request.result_id and not request.download_url:
        cached = request_store.get_cached_release(request.result_id)
        if not cached:
            raise HTTPException(status_code=404, detail="Search result expired; search again")
        request.download_url = (
            cached.get("download_url") if isinstance(cached.get("download_url"), str) else None
        )
        request.title = str(cached.get("title") or request.title)
        request.media_type = str(cached.get("media_type") or request.media_type)  # type: ignore[assignment]
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
    prowlarr_client: ProwlarrClient = Depends(prowlarr),
    request_store: Store = Depends(store),
) -> SearchResponse:
    try:
        releases = prowlarr_client.search(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return build_search_response(
        query=request.query,
        media_type=request.media_type,
        releases=releases,
        request_store=request_store,
    )


@app.post("/api/requests", response_model=MediaRequestResponse)
def create_request(
    request: MediaRequestCreate,
    prowlarr_client: ProwlarrClient = Depends(prowlarr),
    request_store: Store = Depends(store),
) -> MediaRequestResponse:
    row = request_store.create_media_request(request.query, request.media_type)
    request_id = int(row["id"])
    search_request = SearchRequest(
        query=request.query,
        media_type=request.media_type,
        limit=request.limit,
    )
    try:
        releases = prowlarr_client.search(search_request)
    except Exception as exc:
        request_store.set_media_request_status(request_id, "search_failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    search_response = build_search_response(
        query=request.query,
        media_type=request.media_type,
        releases=releases,
        request_store=request_store,
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
    altmount_client: AltMountClient = Depends(altmount),
    request_store: Store = Depends(store),
) -> GrabResponse:
    return grab_cached_result(
        request,
        altmount_client=altmount_client,
        request_store=request_store,
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
    prowlarr_client: ProwlarrClient = Depends(prowlarr),
    request_store: Store = Depends(store),
) -> MediaRequestResponse:
    row = request_store.get_media_request(request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    search_request = SearchRequest(query=str(row["query"]), media_type=row["media_type"])
    try:
        releases = prowlarr_client.search(search_request)
    except Exception as exc:
        request_store.set_media_request_status(request_id, "search_failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    search_response = build_search_response(
        query=search_request.query,
        media_type=search_request.media_type,
        releases=releases,
        request_store=request_store,
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


@app.get("/api/indexers")
def indexers(prowlarr_client: ProwlarrClient = Depends(prowlarr)) -> list[dict[str, object]]:
    try:
        return [indexer.model_dump() for indexer in prowlarr_client.indexers()]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/grabs")
def grabs(request_store: Store = Depends(store)) -> list[dict[str, object]]:
    return request_store.recent_grabs()
