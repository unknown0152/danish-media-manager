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
