from app.decision import decide_release
from app.models import MetadataResult, Release
from app.quality import parse_quality
from app.scoring import score_release
from app.store import Store
from app.titlematch import match_title


def test_store_persists_request_and_cached_release(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    request = store.create_media_request(
        "The Batman 2022",
        "movie",
        "2160p",
        target_path="/media/danish-movies",
        target_label="Danish Movies",
        metadata=MetadataResult(
            title="The Batman",
            year=2022,
            poster_url="https://image.tmdb.org/t/p/w342/example.jpg",
        ),
        origin_source="dmm",
        origin_details='{"note":"manual"}',
    )
    title = "The.Batman.2022.NORDiC.2160p.BluRay.x265"
    quality = parse_quality(title)
    score = score_release(title, 20_000_000_000)
    release = Release(
        result_id="abc123",
        title=title,
        download_url="http://prowlarr/1/download?apikey=secret",
        quality=quality,
        score=score,
        decision=decide_release(
            score=score,
            quality=quality,
            title_match=match_title("The Batman 2022", title),
            size=20_000_000_000,
            download_url="http://prowlarr/1/download?apikey=secret",
        ),
    )

    store.cache_release("The Batman 2022", "movie", release, request_id=request["id"])
    cached = store.get_cached_release("abc123")
    updated = store.update_media_request_search(
        request["id"],
        status="ready",
        best_result_id="abc123",
        best_title=release.title,
        best_score=release.score.score,
        total=1,
        accepted=1,
        rejected=0,
    )

    assert cached is not None
    assert cached["download_url"].endswith("apikey=secret")
    assert '"download_url"' not in cached["release_json"]
    assert updated is not None
    assert updated["best_result_id"] == "abc123"
    assert updated["min_resolution"] == "2160p"
    assert updated["target_path"] == "/media/danish-movies"
    assert updated["target_label"] == "Danish Movies"
    assert updated["metadata_title"] == "The Batman"
    assert updated["metadata_year"] == 2022
    assert updated["origin_source"] == "dmm"
    assert updated["origin_details"] == '{"note":"manual"}'
    assert updated["last_search_at"] is not None


def test_store_lists_wanted_requests_oldest_first(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    first = store.create_media_request("Older Missing", "movie")
    grabbed = store.create_media_request("Already Grabbed", "movie")
    second = store.create_media_request("Failed Later", "tv")

    store.set_media_request_status(first["id"], "no_results")
    store.set_media_request_status(grabbed["id"], "grabbed")
    store.set_media_request_status(second["id"], "search_failed")

    wanted = store.wanted_media_requests(limit=10)

    assert [row["id"] for row in wanted] == [first["id"], second["id"]]


def test_store_persists_tv_scope_and_feed_run(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    request = store.create_media_request(
        "The Last of Us",
        "tv",
        tv_season=2,
        tv_episode=7,
    )
    store.mark_media_request_feed_checked(request["id"])
    store.mark_media_request_feed_matched(request["id"], "The.Last.of.Us.S02E07.NORDiC.1080p")
    run_id = store.record_feed_sync_run(
        movies_seen=0,
        tv_seen=50,
        requests_checked=1,
        matched=1,
        updated=1,
        grabbed=0,
        grab_failed=0,
        skipped=0,
        errors=[],
    )

    updated = store.get_media_request(request["id"])
    runs = store.recent_feed_sync_runs()
    assert updated is not None
    assert updated["tv_season"] == 2
    assert updated["tv_episode"] == 7
    assert updated["last_feed_checked_at"] is not None
    assert updated["last_feed_matched_at"] is not None
    assert updated["last_feed_match_title"] == "The.Last.of.Us.S02E07.NORDiC.1080p"
    assert runs[0]["id"] == run_id
    assert runs[0]["tv_seen"] == 50
