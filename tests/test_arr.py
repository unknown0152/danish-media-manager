from app.arr import find_radarr_movie, find_sonarr_series
from app.models import SearchRequest


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
