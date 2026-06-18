from app.seerr import (
    metadata_from_seerr_detail,
    seerr_media_type,
    seerr_request_id,
    seerr_tmdb_id,
    seerr_tvdb_id,
)


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
