import sqlite3

from app.decision import decide_release
from app.main import _expand_tv_items_from_metadata
from app.models import MetadataResult, Release, TVSeasonMetadata
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


def test_store_creates_default_monitored_items(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    movie = store.create_media_request("Primer 2004", "movie")
    season = store.create_media_request("The Last of Us", "tv", tv_season=2)
    episode = store.create_media_request("The Last of Us S02E07", "tv", tv_season=2, tv_episode=7)

    movie_items = store.monitored_items_for_request(movie["id"])
    season_items = store.monitored_items_for_request(season["id"])
    episode_items = store.monitored_items_for_request(episode["id"])

    assert movie_items[0]["item_type"] == "movie"
    assert season_items[0]["item_type"] == "season"
    assert season_items[0]["season_number"] == 2
    assert episode_items[0]["item_type"] == "episode"
    assert episode_items[0]["season_number"] == 2
    assert episode_items[0]["episode_number"] == 7


def test_tv_season_metadata_expands_monitored_episode_items(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    request = store.create_media_request("The Last of Us", "tv", tv_season=2)
    added = _expand_tv_items_from_metadata(
        request_store=store,
        request_id=request["id"],
        media_type="tv",
        metadata_result=MetadataResult(
            title="The Last of Us",
            year=2023,
            tv_seasons=[TVSeasonMetadata(season_number=2, episode_count=3)],
        ),
        seasons=[2],
    )

    items = store.monitored_items_for_request(request["id"])
    assert added == 3
    assert [item["item_type"] for item in items] == ["season", "episode", "episode", "episode"]
    assert [item["episode_number"] for item in items if item["item_type"] == "episode"] == [1, 2, 3]


def test_store_marks_matching_monitored_item(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    request = store.create_media_request("The Last of Us", "tv", tv_season=2)
    item = store.monitored_items_for_request(request["id"])[0]

    store.mark_monitored_item_feed_checked(item["id"])
    store.mark_monitored_item_feed_matched(
        item["id"],
        result_id="release-1",
        title="The.Last.of.Us.S02.NORDiC.1080p",
    )

    updated = store.monitored_items_for_request(request["id"])[0]
    assert updated["status"] == "ready"
    assert updated["best_result_id"] == "release-1"
    assert updated["best_title"] == "The.Last.of.Us.S02.NORDiC.1080p"
    assert updated["last_feed_checked_at"] is not None
    assert updated["last_feed_matched_at"] is not None


def test_store_migrates_old_grabs_table_without_non_constant_defaults(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            create table grabs (
                id integer primary key autoincrement,
                created_at text not null default current_timestamp,
                title text not null,
                media_type text not null,
                category text,
                response_json text not null
            )
            """
        )
        conn.execute(
            """
            insert into grabs (title, media_type, category, response_json)
            values ('Primer.2004.NORDiC.1080p', 'movie', 'movies', '{}')
            """
        )

    store = Store(str(db_path))
    grabs = store.active_grabs()

    assert grabs[0]["status"] == "grabbed"
    assert grabs[0]["updated_at"] is not None


def test_store_records_and_resets_prowlarr_api_call_summary(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    first_id = store.record_prowlarr_api_call(
        {
            "context": "seerr_sync",
            "operation": "active_search",
            "endpoint": "/api/v1/search",
            "method": "GET",
            "media_type": "movie",
            "query": "The Batman 2022",
            "request_id": 12,
            "limit": 100,
            "status_code": 200,
            "result_count": 77,
            "duration_ms": 42,
        }
    )
    store.record_prowlarr_api_call(
        {
            "context": "recent_feed_sync",
            "operation": "recent_feed",
            "endpoint": "/api/v1/search",
            "method": "GET",
            "media_type": "tv",
            "limit": 500,
            "status_code": 200,
            "result_count": 500,
            "duration_ms": 101,
        }
    )

    summary = store.prowlarr_api_call_summary()
    recent_only = store.prowlarr_api_call_summary(since_id=first_id)
    calls = store.recent_prowlarr_api_calls(limit=10)

    assert summary["total"] == 2
    assert summary["active_search"] == 1
    assert summary["recent_feed"] == 1
    assert summary["results"] == 577
    assert recent_only["total"] == 1
    assert calls[0]["context"] == "recent_feed_sync"
    assert store.clear_prowlarr_api_calls() == 2
    assert store.prowlarr_api_call_summary()["total"] == 0
