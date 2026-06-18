from app.seerr import (
    SeerrClient,
    metadata_from_seerr_detail,
    seerr_media_type,
    seerr_request_id,
    seerr_tmdb_id,
    seerr_tvdb_id,
)
from app.config import Settings


def test_seerr_request_mapping_from_nested_media() -> None:
    item = {
        "id": 123,
        "media": {
            "mediaType": "tv",
            "tmdbId": 456,
            "tvdbId": 789,
        },
    }

    assert seerr_request_id(item) == "123"
    assert seerr_media_type(item) == "tv"
    assert seerr_tmdb_id(item) == "456"
    assert seerr_tvdb_id(item) == "789"


def test_seerr_detail_maps_to_metadata() -> None:
    metadata = metadata_from_seerr_detail(
        {
            "id": 414906,
            "title": "The Batman",
            "releaseDate": "2022-03-01",
            "posterPath": "/poster.jpg",
            "overview": "A detective story.",
            "imdbId": "tt1877830",
        },
        "movie",
        fallback_id="414906",
    )

    assert metadata.title == "The Batman"
    assert metadata.year == 2022
    assert metadata.tmdb_id == "414906"
    assert metadata.imdb_id == "tt1877830"
    assert metadata.poster_url == "https://image.tmdb.org/t/p/w342/poster.jpg"


def test_mark_available_posts_media_status_with_tv_seasons(monkeypatch) -> None:
    calls = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeHttpClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, *, json, headers):
            calls.append((url, json, headers))
            return FakeResponse()

    monkeypatch.setattr("app.seerr.httpx.Client", FakeHttpClient)
    client = SeerrClient(Settings(SEERR_API_KEY="secret"))

    assert client.mark_available({
        "is4k": False,
        "media": {"id": 42, "mediaType": "tv"},
        "seasons": [{"seasonNumber": 1}, {"seasonNumber": 2}],
    })

    assert calls == [
        (
            "http://seerr:5055/api/v1/media/42/available",
            {"is4k": False, "seasons": [{"seasonNumber": 1}, {"seasonNumber": 2}]},
            {"X-Api-Key": "secret"},
        )
    ]
