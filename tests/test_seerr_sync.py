from app.config import Settings
from app.main import sync_seerr_requests


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
