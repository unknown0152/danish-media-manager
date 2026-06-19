from app.arr import ArrClient, find_radarr_movie, find_sonarr_series
from app.config import Settings
from app.models import MetadataResult, SearchRequest


def test_find_radarr_movie_prefers_tmdb_id() -> None:
    request = SearchRequest(query="The Batman 2022", media_type="movie", tmdb_id="414906")
    movie = find_radarr_movie(
        [
            {"id": 1, "title": "The Batman", "year": 2022, "tmdbId": 414906},
            {"id": 2, "title": "The Batman", "year": 1943, "tmdbId": 125249},
        ],
        request,
    )

    assert movie
    assert movie["id"] == 1


def test_find_radarr_movie_matches_title_and_year_without_ids() -> None:
    request = SearchRequest(query="The Batman 2022", media_type="movie", expected_year=2022)
    movie = find_radarr_movie(
        [
            {"id": 1, "title": "The Batman", "year": 1943},
            {"id": 2, "title": "The Batman", "year": 2022},
        ],
        request,
    )

    assert movie
    assert movie["id"] == 2


def test_find_sonarr_series_prefers_tvdb_id() -> None:
    request = SearchRequest(query="The Last of Us 2023", media_type="tv", tvdb_id="392256")
    series = find_sonarr_series(
        [
            {"id": 10, "title": "The Last of Us", "year": 2023, "tvdbId": 392256},
            {"id": 11, "title": "The Traitors (US)", "year": 2023, "tvdbId": 428163},
        ],
        request,
    )

    assert series
    assert series["id"] == 10


def test_arr_rescan_posts_radarr_command(monkeypatch) -> None:
    requests: list[tuple[str, dict | None]] = []

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, **kwargs):
            requests.append((url, kwargs.get("params")))
            return FakeResponse([{"id": 42, "title": "Primer", "year": 2004, "tmdbId": 14337}])

        def post(self, url, **kwargs):
            requests.append((url, kwargs.get("json")))
            return FakeResponse({"id": 99})

    monkeypatch.setattr("app.arr.httpx.Client", FakeHttpClient)
    client = ArrClient(Settings(RADARR_API_KEY="radarr-key"))

    assert client.rescan_for_metadata(
        "movie",
        MetadataResult(title="Primer", year=2004, tmdb_id="14337"),
    )
    assert requests[-1] == (
        "http://radarr:7878/api/v3/command",
        {"name": "RescanMovie", "movieId": 42},
    )
