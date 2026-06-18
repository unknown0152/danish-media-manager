from app.config import Settings
from app.main import should_mark_seerr_available, sync_seerr_requests


class FakeSeerrClient:
    def __init__(self, items):
        self._items = items
        self.metadata_calls = 0

    def requests(self, *, take: int = 20, filter_name: str = "all"):
        return self._items

    def metadata_for_request(self, item):
        self.metadata_calls += 1
        raise AssertionError("metadata lookup should not run for invalid Seerr target paths")


class FakeStore:
    def get_media_request_by_external(self, external_source: str, external_id: str):
        return None


def test_seerr_sync_skips_requests_without_exact_target_path() -> None:
    seerr_client = FakeSeerrClient([
        {"id": 10, "mediaType": "movie", "rootFolder": None},
        {"id": 11, "mediaType": "movie", "rootFolder": "/media/not-configured"},
    ])

    result = sync_seerr_requests(
        settings=Settings(MOVIE_TARGETS="Movies=/media/movies,Danish=/media/danish-movies"),
        seerr_client=seerr_client,
        di_client=object(),
        prowlarr_client=object(),
        altmount_client=object(),
        arr_client=object(),
        request_store=FakeStore(),
    )

    assert result.imported == 0
    assert result.skipped == 2
    assert result.failed == 0
    assert seerr_client.metadata_calls == 0
    assert result.errors == [
        "Seerr request 10: missing rootFolder",
        "Seerr request 11: unconfigured rootFolder /media/not-configured",
    ]


def test_tv_episode_release_does_not_mark_whole_show_available() -> None:
    assert should_mark_seerr_available("movie", "Primer.2004.NORDiC.1080p.BluRay") is True
    assert should_mark_seerr_available("tv", "The.Last.of.Us.2023.S02E07.NORDiC.2160p") is False
    assert should_mark_seerr_available("tv", "The.Chestnut.Man.2021.S01.2160p.WEB-DL") is True
