import pytest
from fastapi import HTTPException

from app.config import Settings
from app.decision import decide_release
from app.main import best_release, grab_cached_result
from app.models import GrabRequest, Release
from app.quality import parse_quality
from app.scoring import score_release
from app.store import Store
from app.titlematch import match_title


class FailingAltMount:
    def add_uri(self, request: GrabRequest):  # pragma: no cover - should not be called
        raise AssertionError("rejected release was sent to AltMount")


class RecordingAltMount:
    def __init__(self) -> None:
        self.requests: list[GrabRequest] = []

    def add_uri(self, request: GrabRequest) -> dict[str, str]:
        self.requests.append(request)
        return {"status": "ok"}


def test_best_release_returns_none_when_all_results_rejected() -> None:
    rejected = _release(
        "The.Batman.2022.NORDiC.1080p.BluRay.x265",
        min_resolution="2160p",
    )

    assert best_release([rejected]) is None


def test_grab_cached_result_rejects_non_grabbable_release(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    release = _release(
        "The.Batman.2022.NORDiC.1080p.BluRay.x265",
        min_resolution="2160p",
    )
    store.cache_release("The Batman 2022", "movie", release)

    with pytest.raises(HTTPException) as exc_info:
        grab_cached_result(
            GrabRequest(title=release.title, media_type="movie", result_id=release.result_id),
            altmount_client=FailingAltMount(),  # type: ignore[arg-type]
            request_store=store,
            settings=Settings(),
        )

    assert exc_info.value.status_code == 409
    assert "Below requested minimum resolution" in str(exc_info.value.detail)


def test_grab_cached_result_validates_result_id_even_with_supplied_url(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    release = _release(
        "The.Batman.2022.NORDiC.1080p.BluRay.x265",
        min_resolution="2160p",
    )
    store.cache_release("The Batman 2022", "movie", release)

    with pytest.raises(HTTPException) as exc_info:
        grab_cached_result(
            GrabRequest(
                title=release.title,
                media_type="movie",
                result_id=release.result_id,
                download_url="http://example.invalid/bypass.nzb",
            ),
            altmount_client=FailingAltMount(),  # type: ignore[arg-type]
            request_store=store,
            settings=Settings(ALLOW_DIRECT_DOWNLOAD_URLS=True),
        )

    assert exc_info.value.status_code == 409
    assert "Below requested minimum resolution" in str(exc_info.value.detail)


def test_direct_download_urls_are_disabled_by_default(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))

    with pytest.raises(HTTPException) as exc_info:
        grab_cached_result(
            GrabRequest(
                title="Manual",
                media_type="movie",
                download_url="http://example.invalid/manual.nzb",
            ),
            altmount_client=FailingAltMount(),  # type: ignore[arg-type]
            request_store=store,
            settings=Settings(),
        )

    assert exc_info.value.status_code == 403
    assert "Direct download URLs are disabled" in str(exc_info.value.detail)


def test_direct_download_urls_can_be_explicitly_enabled(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    altmount = RecordingAltMount()

    response = grab_cached_result(
        GrabRequest(
            title="Manual",
            media_type="movie",
            download_url="http://example.invalid/manual.nzb",
        ),
        altmount_client=altmount,  # type: ignore[arg-type]
        request_store=store,
        settings=Settings(ALLOW_DIRECT_DOWNLOAD_URLS=True),
    )

    assert response.ok is True
    assert len(altmount.requests) == 1
    assert altmount.requests[0].download_url == "http://example.invalid/manual.nzb"


def _release(title: str, min_resolution: str = "any") -> Release:
    quality = parse_quality(title)
    score = score_release(title, 20_000_000_000)
    return Release(
        result_id=title,
        title=title,
        download_url="http://example.invalid/file.nzb",
        quality=quality,
        score=score,
        decision=decide_release(
            score=score,
            quality=quality,
            title_match=match_title("The Batman 2022", title),
            size=20_000_000_000,
            download_url="http://example.invalid/file.nzb",
            min_resolution=min_resolution,
        ),
    )
