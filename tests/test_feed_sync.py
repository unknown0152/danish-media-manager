from app.config import Settings
from app.main import sync_recent_releases
from app.models import GrabRequest, MetadataResult
from app.store import Store


class FakeProwlarr:
    def __init__(self, items_by_type: dict[str, list[dict]]) -> None:
        self.items_by_type = items_by_type
        self.calls: list[tuple[str, int]] = []

    def recent(self, media_type: str, limit: int = 500) -> list[dict]:
        self.calls.append((media_type, limit))
        return self.items_by_type.get(media_type, [])


class RecordingAltMount:
    def __init__(self) -> None:
        self.requests: list[GrabRequest] = []

    def add_uri(self, request: GrabRequest) -> dict[str, str]:
        self.requests.append(request)
        return {"status": "ok"}


class ReadyArr:
    def ensure_media_target(self, **kwargs):
        return True


def test_recent_feed_sync_marks_matching_request_ready(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    request = store.create_media_request(
        "The Batman 2022",
        "movie",
        "1080p",
        target_path="/media/movies",
        target_label="Movies",
        metadata=MetadataResult(title="The Batman", year=2022),
    )
    store.set_media_request_status(request["id"], "no_results")
    prowlarr = FakeProwlarr(
        {
            "movie": [
                {
                    "title": "The.Batman.2022.NORDiC.1080p.BluRay.x265-GROUP",
                    "downloadUrl": "http://example.invalid/batman.nzb",
                    "indexer": "TestIndexer",
                    "size": 12_000_000_000,
                }
            ]
        }
    )

    result = sync_recent_releases(
        limit=20,
        feed_limit=500,
        auto_grab=False,
        settings=Settings(MOVIE_TARGETS="Movies=/media/movies"),
        prowlarr_client=prowlarr,  # type: ignore[arg-type]
        altmount_client=RecordingAltMount(),  # type: ignore[arg-type]
        arr_client=ReadyArr(),  # type: ignore[arg-type]
        request_store=store,
    )

    updated = store.get_media_request(request["id"])
    assert prowlarr.calls == [("movie", 500)]
    assert result.movies_seen == 1
    assert result.run_id is not None
    assert result.requests_checked == 1
    assert result.matched == 1
    assert result.updated == 1
    assert updated is not None
    assert updated["status"] == "ready"
    assert updated["best_title"] == "The.Batman.2022.NORDiC.1080p.BluRay.x265-GROUP"
    assert updated["last_feed_checked_at"] is not None
    assert updated["last_feed_matched_at"] is not None


def test_recent_feed_sync_ignores_wrong_year(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    request = store.create_media_request(
        "The Batman 2022",
        "movie",
        "1080p",
        metadata=MetadataResult(title="The Batman", year=2022),
    )
    store.set_media_request_status(request["id"], "no_results")
    prowlarr = FakeProwlarr(
        {
            "movie": [
                {
                    "title": "The.Batman.1989.NORDiC.1080p.BluRay.x265-GROUP",
                    "downloadUrl": "http://example.invalid/wrong.nzb",
                    "indexer": "TestIndexer",
                    "size": 12_000_000_000,
                }
            ]
        }
    )

    result = sync_recent_releases(
        limit=20,
        feed_limit=500,
        auto_grab=False,
        settings=Settings(),
        prowlarr_client=prowlarr,  # type: ignore[arg-type]
        altmount_client=RecordingAltMount(),  # type: ignore[arg-type]
        arr_client=ReadyArr(),  # type: ignore[arg-type]
        request_store=store,
    )

    updated = store.get_media_request(request["id"])
    assert result.matched == 0
    assert result.updated == 0
    assert updated is not None
    assert updated["status"] == "no_results"
    assert updated["best_title"] is None


def test_recent_feed_sync_respects_tv_season_scope(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    request = store.create_media_request(
        "The Last of Us",
        "tv",
        "1080p",
        metadata=MetadataResult(title="The Last of Us", year=2023),
        tv_season=2,
    )
    store.set_media_request_status(request["id"], "no_results")
    prowlarr = FakeProwlarr(
        {
            "tv": [
                {
                    "title": "The.Last.of.Us.S01.NORDiC.1080p.WEB-DL-GROUP",
                    "downloadUrl": "http://example.invalid/s01.nzb",
                    "indexer": "TestIndexer",
                    "size": 20_000_000_000,
                },
                {
                    "title": "The.Last.of.Us.S02.NORDiC.1080p.WEB-DL-GROUP",
                    "downloadUrl": "http://example.invalid/s02.nzb",
                    "indexer": "TestIndexer",
                    "size": 20_000_000_000,
                },
            ]
        }
    )

    result = sync_recent_releases(
        limit=20,
        feed_limit=500,
        auto_grab=False,
        settings=Settings(),
        prowlarr_client=prowlarr,  # type: ignore[arg-type]
        altmount_client=RecordingAltMount(),  # type: ignore[arg-type]
        arr_client=ReadyArr(),  # type: ignore[arg-type]
        request_store=store,
    )

    updated = store.get_media_request(request["id"])
    items = store.monitored_items_for_request(request["id"])
    assert prowlarr.calls == [("tv", 500)]
    assert result.tv_seen == 2
    assert result.matched == 1
    assert updated is not None
    assert updated["best_title"] == "The.Last.of.Us.S02.NORDiC.1080p.WEB-DL-GROUP"
    assert items[0]["item_type"] == "season"
    assert items[0]["status"] == "ready"
    assert items[0]["best_title"] == "The.Last.of.Us.S02.NORDiC.1080p.WEB-DL-GROUP"


def test_recent_feed_sync_can_auto_grab_best_release(tmp_path) -> None:
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
    altmount = RecordingAltMount()

    result = sync_recent_releases(
        limit=20,
        feed_limit=500,
        auto_grab=True,
        settings=Settings(MOVIE_TARGETS="Movies=/media/movies"),
        prowlarr_client=FakeProwlarr(
            {
                "movie": [
                    {
                        "title": "Primer.2004.NORDiC.1080p.BluRay.x265-GROUP",
                        "downloadUrl": "http://example.invalid/primer.nzb",
                        "indexer": "TestIndexer",
                        "size": 8_000_000_000,
                    }
                ]
            }
        ),  # type: ignore[arg-type]
        altmount_client=altmount,  # type: ignore[arg-type]
        arr_client=ReadyArr(),  # type: ignore[arg-type]
        request_store=store,
    )

    updated = store.get_media_request(request["id"])
    assert result.grabbed == 1
    assert updated is not None
    assert updated["status"] == "grabbed"
    assert len(altmount.requests) == 1
    assert altmount.requests[0].result_id == updated["best_result_id"]
