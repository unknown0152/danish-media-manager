from app.config import Settings
from app.metadata import local_metadata
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
