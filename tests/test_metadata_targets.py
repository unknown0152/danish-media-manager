from app.config import Settings
from app.metadata import (
    local_metadata,
    metadata_from_radarr_item,
    metadata_from_seerr_item,
    metadata_from_sonarr_item,
)
from app.targets import parse_targets, target_for_path


def test_local_metadata_extracts_title_and_year() -> None:
    metadata = local_metadata("The Batman 2022")

    assert metadata.title == "The Batman"
    assert metadata.year == 2022
    assert metadata.source == "local"
    assert metadata.poster_url is None


def test_parse_targets_supports_labels_and_plain_paths() -> None:
    targets = parse_targets("Danish=/media/danish-movies,/media/classics", "movie")

    assert [(target.label, target.path) for target in targets] == [
        ("Danish", "/media/danish-movies"),
        ("classics", "/media/classics"),
    ]


def test_target_for_path_defaults_to_first_target() -> None:
    settings = Settings(MOVIE_TARGETS="Movies=/media/movies,Danish=/media/danish-movies")

    assert target_for_path(settings, "movie", "/media/danish-movies").label == "Danish"
    assert target_for_path(settings, "movie", None).path == "/media/movies"
    assert target_for_path(settings, "movie", "/not/allowed").path == "/media/movies"


def test_radarr_metadata_payload_maps_to_common_metadata() -> None:
    metadata = metadata_from_radarr_item(
        {
            "title": "The Batman",
            "releaseDate": "2022-03-04",
            "overview": "Vengeance.",
            "tmdbId": 414906,
            "imdbId": "tt1877830",
            "images": [
                {"coverType": "fanart", "remoteUrl": "https://example.invalid/fanart.jpg"},
                {"coverType": "poster", "remoteUrl": "https://example.invalid/poster.jpg"},
            ],
        },
        "The Batman",
    )

    assert metadata.source == "radarr"
    assert metadata.title == "The Batman"
    assert metadata.year == 2022
    assert metadata.external_id == "414906"
    assert metadata.tmdb_id == "414906"
    assert metadata.imdb_id == "tt1877830"
    assert metadata.poster_url == "https://example.invalid/poster.jpg"


def test_sonarr_metadata_payload_maps_to_common_metadata() -> None:
    metadata = metadata_from_sonarr_item(
        {
            "title": "The Last of Us",
            "firstAired": "2023-01-15",
            "overview": "After a global pandemic.",
            "tmdbId": 100088,
            "tvdbId": 392256,
            "imdbId": "tt3581920",
            "images": [{"coverType": "poster", "remoteUrl": "https://example.invalid/tv.jpg"}],
        },
        "The Last of Us",
    )

    assert metadata.source == "sonarr"
    assert metadata.title == "The Last of Us"
    assert metadata.year == 2023
    assert metadata.external_id == "100088"
    assert metadata.tmdb_id == "100088"
    assert metadata.tvdb_id == "392256"
    assert metadata.imdb_id == "tt3581920"
    assert metadata.poster_url == "https://example.invalid/tv.jpg"


def test_seerr_metadata_payload_maps_to_common_metadata() -> None:
    metadata = metadata_from_seerr_item(
        {
            "id": 414906,
            "mediaType": "movie",
            "title": "The Batman",
            "releaseDate": "2022-03-04",
            "overview": "Vengeance.",
            "posterPath": "/abc123.jpg",
        },
        "The Batman",
    )

    assert metadata.source == "seerr"
    assert metadata.title == "The Batman"
    assert metadata.year == 2022
    assert metadata.external_id == "414906"
    assert metadata.poster_url == "https://image.tmdb.org/t/p/w342/abc123.jpg"
