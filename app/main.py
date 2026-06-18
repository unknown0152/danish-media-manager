from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.altmount import AltMountClient
from app.config import Settings, get_settings
from app.models import GrabRequest, GrabResponse, SearchRequest, SearchResponse
from app.prowlarr import ProwlarrClient
from app.store import Store
import json

app = FastAPI(title="Danish Media Manager", version="0.1.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

def prowlarr(settings: Settings = Depends(get_settings)) -> ProwlarrClient:
    return ProwlarrClient(settings)


def altmount(settings: Settings = Depends(get_settings)) -> AltMountClient:
    return AltMountClient(settings)


def store(settings: Settings = Depends(get_settings)) -> Store:
    return Store(settings.database_path)


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
    for release in releases:
        request_store.cache_release(request.query, request.media_type, release)
    accepted = sum(1 for release in releases if release.decision.accepted)
    return SearchResponse(
        query=request.query,
        media_type=request.media_type,
        total=len(releases),
        accepted=accepted,
        rejected=len(releases) - accepted,
        releases=releases,
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


@app.get("/api/queue")
def queue(altmount_client: AltMountClient = Depends(altmount)) -> dict[str, object] | str:
    try:
        return altmount_client.queue()
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
