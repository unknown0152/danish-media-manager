import pytest
from fastapi import HTTPException

from app.config import Settings
from app.decision import decide_release
from app.main import (
    best_release,
    create_scored_request,
    grab_cached_result,
    rerun_stored_request_search,
    retry_wanted_requests,
    sync_altmount_completions,
)
from app.models import (
    Decision,
    DownloadItem,
    DownloadStatus,
    GrabRequest,
    MetadataResult,
    Release,
    ScoreBreakdown,
)
from app.prowlarr import release_sort_key
from app.quality import QualityInfo
from app.quality import parse_quality
from app.scoring import score_release
from app.store import Store
from app.titlematch import match_title


class FailingAltMount:
    def add_uri(self, request: GrabRequest):  # pragma: no cover - should not be called
        raise AssertionError("rejected release was sent to AltMount")


class RecordingAltMount:
    def __init__(self) -> None:
        self.requests: list[GrabRequest] = []

    def add_uri(self, request: GrabRequest) -> dict[str, str]:
        self.requests.append(request)
        return {"status": "ok", "nzo_id": "download-1", "name": request.title}


class StaticDownloadsAltMount:
    def __init__(self, downloads: DownloadStatus) -> None:
        self._downloads = downloads

    def downloads(self) -> DownloadStatus:
        return self._downloads


class StaticMetadata:
    def lookup(self, query: str, media_type: str) -> MetadataResult:
        return MetadataResult(title=query.rsplit(" ", 1)[0], year=2004, tmdb_id="123")


class EmptySearchClient:
    def search(self, request):
        return []


class StaticSearchClient:
    def __init__(self, releases: list[Release]) -> None:
        self.releases = releases

    def search(self, request):
        return self.releases


class RecordingSearchClient(StaticSearchClient):
    def __init__(self, releases: list[Release]) -> None:
        super().__init__(releases)
        self.requests = []

    def search(self, request):
        self.requests.append(request)
        return self.releases


class WrongYearMetadata:
    def lookup(self, query: str, media_type: str) -> MetadataResult:
        return MetadataResult(title="Big Hero 6", year=2015, tmdb_id="177572")


class ReadyArr:
    def ensure_media_target(self, **kwargs):
        return True


class RecordingArr(ReadyArr):
    def __init__(self) -> None:
        self.rescans: list[tuple[str, MetadataResult]] = []

    def rescan_for_metadata(self, media_type: str, metadata: MetadataResult) -> bool:
        self.rescans.append((media_type, metadata))
        return True


def test_best_release_returns_none_when_all_results_rejected() -> None:
    rejected = _release(
        "The.Batman.2022.NORDiC.1080p.BluRay.x265",
        min_resolution="2160p",
    )

    assert best_release([rejected]) is None


def test_grab_cached_result_rejects_non_grabbable_release(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    release = _release(
        "The.Batman.2022.NORDiC.1080p.BluRay.x265",
        min_resolution="2160p",
    )
    store.cache_release("The Batman 2022", "movie", release)

    with pytest.raises(HTTPException) as exc_info:
        grab_cached_result(
            GrabRequest(title=release.title, media_type="movie", result_id=release.result_id),
            altmount_client=FailingAltMount(),  # type: ignore[arg-type]
            request_store=store,
            settings=Settings(),
        )

    assert exc_info.value.status_code == 409
    assert "Below requested minimum resolution" in str(exc_info.value.detail)


def test_grab_cached_result_validates_result_id_even_with_supplied_url(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    release = _release(
        "The.Batman.2022.NORDiC.1080p.BluRay.x265",
        min_resolution="2160p",
    )
    store.cache_release("The Batman 2022", "movie", release)

    with pytest.raises(HTTPException) as exc_info:
        grab_cached_result(
            GrabRequest(
                title=release.title,
                media_type="movie",
                result_id=release.result_id,
                download_url="http://example.invalid/bypass.nzb",
            ),
            altmount_client=FailingAltMount(),  # type: ignore[arg-type]
            request_store=store,
            settings=Settings(ALLOW_DIRECT_DOWNLOAD_URLS=True),
        )

    assert exc_info.value.status_code == 409
    assert "Below requested minimum resolution" in str(exc_info.value.detail)


def test_direct_download_urls_are_disabled_by_default(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))

    with pytest.raises(HTTPException) as exc_info:
        grab_cached_result(
            GrabRequest(
                title="Manual",
                media_type="movie",
                download_url="http://example.invalid/manual.nzb",
            ),
            altmount_client=FailingAltMount(),  # type: ignore[arg-type]
            request_store=store,
            settings=Settings(),
        )

    assert exc_info.value.status_code == 403
    assert "Direct download URLs are disabled" in str(exc_info.value.detail)


def test_direct_download_urls_can_be_explicitly_enabled(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    altmount = RecordingAltMount()

    response = grab_cached_result(
        GrabRequest(
            title="Manual",
            media_type="movie",
            download_url="http://example.invalid/manual.nzb",
        ),
        altmount_client=altmount,  # type: ignore[arg-type]
        request_store=store,
        settings=Settings(ALLOW_DIRECT_DOWNLOAD_URLS=True),
    )

    assert response.ok is True
    assert len(altmount.requests) == 1
    assert altmount.requests[0].download_url == "http://example.invalid/manual.nzb"


def test_grab_cached_result_links_grab_to_monitored_item(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    request = store.create_media_request(
        "The Last of Us",
        "tv",
        metadata=MetadataResult(title="The Last of Us", year=2023, tvdb_id="392256"),
        tv_season=2,
    )
    release = _manual_release(
        title="The.Last.of.Us.S02.NORDiC.1080p.WEB-DL",
        accepted=True,
        score=9000,
        resolution="1080p",
        source="web-dl",
        size=20_000_000_000,
    )
    store.cache_release("The Last of Us", "tv", release, request_id=request["id"])

    response = grab_cached_result(
        GrabRequest(title=release.title, media_type="tv", result_id=release.result_id),
        altmount_client=RecordingAltMount(),  # type: ignore[arg-type]
        request_store=store,
        settings=Settings(),
    )

    grabs = store.recent_grabs()
    items = store.monitored_items_for_request(request["id"])
    assert response.ok is True
    assert grabs[0]["result_id"] == release.result_id
    assert grabs[0]["monitored_item_id"] == items[0]["id"]
    assert grabs[0]["status"] == "grabbed"
    assert "payload" not in grabs[0]
    assert "response" not in grabs[0]
    assert items[0]["status"] == "grabbed"


def test_create_scored_request_marks_monitored_item_ready(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    release = _manual_release(
        title="Big.Hero.6.2014.NORDiC.ENG.2160p.WEB-DL.HDR.H.265-TWA",
        accepted=True,
        score=9000,
        resolution="2160p",
        source="web-dl",
        size=20_000_000_000,
    )

    response = create_scored_request(
        query="Big Hero 6 2014",
        media_type="movie",
        min_resolution="1080p",
        limit=100,
        target_path="/media/kids-movies",
        settings=Settings(),
        metadata_result=MetadataResult(title="Big Hero 6", year=2014, tmdb_id="177572"),
        di_client=StaticSearchClient([release]),  # type: ignore[arg-type]
        prowlarr_client=EmptySearchClient(),  # type: ignore[arg-type]
        request_store=store,
    )

    item = store.monitored_items_for_request(response.request.id)[0]
    assert response.request.status == "ready"
    assert response.request.target_path == "/media/kids-movies"
    assert item["status"] == "ready"
    assert item["best_result_id"] == release.result_id
    assert item["best_title"] == release.title


def test_rerun_stored_request_keeps_stored_metadata_year(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    row = store.create_media_request(
        "Big Hero 6 2014",
        "movie",
        min_resolution="1080p",
        metadata=MetadataResult(title="Big Hero 6", year=2014, tmdb_id="177572"),
        external_source="seerr",
        external_id="19",
    )
    release = _manual_release(
        title="Big.Hero.6.2014.NORDiC.ENG.2160p.WEB-DL.HDR.H.265-TWA",
        accepted=True,
        score=9000,
        resolution="2160p",
        source="web-dl",
        size=20_000_000_000,
    )
    di = RecordingSearchClient([release])

    response = rerun_stored_request_search(
        row,
        metadata_client=WrongYearMetadata(),  # type: ignore[arg-type]
        di_client=di,  # type: ignore[arg-type]
        prowlarr_client=EmptySearchClient(),  # type: ignore[arg-type]
        request_store=store,
    )

    item = store.monitored_items_for_request(row["id"])[0]
    assert di.requests[0].expected_year == 2014
    assert "2014" in di.requests[0].query
    assert response.request.status == "ready"
    assert response.search.metadata is not None
    assert response.search.metadata.year == 2014
    assert item["status"] == "ready"
    assert item["best_title"] == release.title


def test_completion_sync_marks_grab_import_pending_and_triggers_arr_rescan(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    request = store.create_media_request(
        "Primer 2004",
        "movie",
        metadata=MetadataResult(title="Primer", year=2004, tmdb_id="14337"),
    )
    item = store.monitored_items_for_request(request["id"])[0]
    release = _manual_release(
        title="Primer.2004.NORDiC.1080p.BluRay.x265",
        accepted=True,
        score=9000,
        resolution="1080p",
        source="bluray",
        size=8_000_000_000,
    )
    store.cache_release("Primer 2004", "movie", release, request_id=request["id"])
    grab_cached_result(
        GrabRequest(title=release.title, media_type="movie", result_id=release.result_id),
        altmount_client=RecordingAltMount(),  # type: ignore[arg-type]
        request_store=store,
        settings=Settings(),
    )
    arr = RecordingArr()

    result = sync_altmount_completions(
        settings=Settings(),
        altmount_client=StaticDownloadsAltMount(
            DownloadStatus(
                status="Idle",
                queue=[],
                history=[
                    DownloadItem(
                        id="done-1",
                        name=release.title,
                        status="Completed",
                        category="movies",
                    )
                ],
            )
        ),  # type: ignore[arg-type]
        arr_client=arr,  # type: ignore[arg-type]
        request_store=store,
    )

    grabs = store.recent_grabs()
    updated_item = store.get_monitored_item(item["id"])
    assert result.completed == 1
    assert result.rescans_triggered == 1
    assert grabs[0]["status"] == "import_pending"
    assert grabs[0]["completed_at"] is not None
    assert updated_item is not None
    assert updated_item["status"] == "import_pending"
    assert arr.rescans[0][0] == "movie"
    assert arr.rescans[0][1].title == "Primer"
    assert arr.rescans[0][1].tmdb_id == "14337"


def test_completion_sync_matches_altmount_history_by_download_id(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    request = store.create_media_request(
        "The Batman 2022",
        "movie",
        metadata=MetadataResult(title="The Batman", year=2022, tmdb_id="414906"),
    )
    item = store.monitored_items_for_request(request["id"])[0]
    release = _manual_release(
        title="The.Batman.2022.NORDiC.2160p.UHD.BluRay.x265",
        accepted=True,
        score=12000,
        resolution="2160p",
        source="bluray",
        size=40_000_000_000,
    )
    store.cache_release("The Batman 2022", "movie", release, request_id=request["id"])
    grab_cached_result(
        GrabRequest(title=release.title, media_type="movie", result_id=release.result_id),
        altmount_client=RecordingAltMount(),  # type: ignore[arg-type]
        request_store=store,
        settings=Settings(),
    )
    arr = RecordingArr()

    result = sync_altmount_completions(
        settings=Settings(),
        altmount_client=StaticDownloadsAltMount(
            DownloadStatus(
                status="Idle",
                queue=[],
                history=[
                    DownloadItem(
                        id="download-1",
                        name="AltMount renamed completed item",
                        status="Completed",
                        category="movies",
                    )
                ],
            )
        ),  # type: ignore[arg-type]
        arr_client=arr,  # type: ignore[arg-type]
        request_store=store,
    )

    grabs = store.recent_grabs()
    updated_item = store.get_monitored_item(item["id"])
    assert result.completed == 1
    assert result.missing == 0
    assert result.rescans_triggered == 1
    assert grabs[0]["status"] == "import_pending"
    assert updated_item is not None
    assert updated_item["status"] == "import_pending"
    assert arr.rescans[0][1].tmdb_id == "414906"


def test_release_sort_key_prefers_accepted_then_quality() -> None:
    rejected_high_score = _manual_release(
        title="Rejected 2160p",
        accepted=False,
        score=20000,
        resolution="2160p",
        source="remux",
        size=90_000_000_000,
    )
    accepted_1080p = _manual_release(
        title="Accepted 1080p",
        accepted=True,
        score=5000,
        resolution="1080p",
        source="web-dl",
        size=8_000_000_000,
    )
    accepted_2160p = _manual_release(
        title="Accepted 2160p",
        accepted=True,
        score=5000,
        resolution="2160p",
        source="bluray",
        size=40_000_000_000,
    )

    sorted_releases = sorted(
        [rejected_high_score, accepted_1080p, accepted_2160p],
        key=release_sort_key,
        reverse=True,
    )

    assert [release.title for release in sorted_releases] == [
        "Accepted 2160p",
        "Accepted 1080p",
        "Rejected 2160p",
    ]


def test_retry_wanted_requests_searches_and_auto_grabs_best(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    request = store.create_media_request(
        "Primer 2004",
        "movie",
        "1080p",
        target_path="/media/movies",
        target_label="Movies",
        metadata=MetadataResult(title="Primer", year=2004),
    )
    store.set_media_request_status(request["id"], "no_results")
    release = _manual_release(
        title="Primer.2004.NORDiC.1080p.BluRay.x265",
        accepted=True,
        score=9000,
        resolution="1080p",
        source="bluray",
        size=20_000_000_000,
    )
    altmount = RecordingAltMount()

    result = retry_wanted_requests(
        limit=10,
        auto_grab=True,
        settings=Settings(MOVIE_TARGETS="Movies=/media/movies"),
        metadata_client=StaticMetadata(),  # type: ignore[arg-type]
        di_client=EmptySearchClient(),  # type: ignore[arg-type]
        prowlarr_client=StaticSearchClient([release]),  # type: ignore[arg-type]
        altmount_client=altmount,  # type: ignore[arg-type]
        arr_client=ReadyArr(),  # type: ignore[arg-type]
        request_store=store,
    )

    updated = store.get_media_request(request["id"])
    assert result.grabbed == 1
    assert updated is not None
    assert updated["status"] == "grabbed"
    assert updated["best_title"] == release.title
    assert len(altmount.requests) == 1
    assert altmount.requests[0].result_id == release.result_id


def _release(title: str, min_resolution: str = "any") -> Release:
    quality = parse_quality(title)
    score = score_release(title, 20_000_000_000)
    return Release(
        result_id=title,
        title=title,
        download_url="http://example.invalid/file.nzb",
        quality=quality,
        score=score,
        decision=decide_release(
            score=score,
            quality=quality,
            title_match=match_title("The Batman 2022", title),
            size=20_000_000_000,
            download_url="http://example.invalid/file.nzb",
            min_resolution=min_resolution,
        ),
    )


def _manual_release(
    *,
    title: str,
    accepted: bool,
    score: int,
    resolution: str,
    source: str,
    size: int,
) -> Release:
    return Release(
        result_id=title,
        title=title,
        size=size,
        quality=QualityInfo(resolution=resolution, source=source),  # type: ignore[arg-type]
        score=ScoreBreakdown(score=score, verdict="good", reasons=["test"]),
        decision=Decision(accepted=accepted, grab_allowed=accepted),
    )
