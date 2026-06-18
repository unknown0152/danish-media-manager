from app.scoring import score_release
from app.models import Release
from app.quality import parse_quality


def test_danish_audio_beats_plain_2160p() -> None:
    danish = score_release("The.Movie.2026.1080p.WEB-DL.DKaudio-NORDIC")
    plain = score_release("The.Movie.2026.2160p.UHD.BluRay.REMUX")

    assert danish.score > plain.score
    assert "Danish audio" in danish.reasons


def test_tiny_dksubs_minirip_does_not_beat_full_quality_multisubs() -> None:
    tiny = score_release(
        "[MiniRip] The.Batman.2022.MiniRip.1080p.BDRIP.DD5.1.DKSUBS.x264-a6POiNT6",
        size=1_879_048_192,
    )
    full = score_release(
        "The.Batman.2022.MultiSubs.UHD.Bluray.2160p.TrueHD.Atmos.7.1.DV.HDR10Plus.x265.MainFrame",
        size=26_843_545_600,
    )

    assert full.score > tiny.score
    assert "Low value encode" in tiny.reasons


def test_plain_nordic_counts_as_likely_danish_subtitles() -> None:
    scored = score_release("The.Batman.2022.NORDiC.2160p.HMAX.WEB-DL.DDP5.1.Atmos.x265")

    assert scored.score >= 8000
    assert "Likely Danish subtitles" in scored.reasons


def test_bad_cam_is_penalized() -> None:
    scored = score_release("The.Movie.2026.CAM.1080p.DKSUBS")

    assert scored.score < 0
    assert "Bad source quality" in scored.reasons


def test_danish_subtitle_reason() -> None:
    scored = score_release("The.Movie.2026.NORDiC.1080p.WEB-DL.DKSUBS")

    assert scored.verdict in {"good", "excellent"}
    assert "Danish subtitles" in scored.reasons


def test_release_serialization_hides_sensitive_url_and_raw() -> None:
    release = Release(
        result_id="abc",
        title="Example",
        download_url="http://prowlarr/download?apikey=secret",
        raw={"downloadUrl": "http://prowlarr/download?apikey=secret"},
        quality=parse_quality("Example.DKSUBS"),
        score=score_release("Example.DKSUBS"),
    )

    dumped = release.model_dump()

    assert "download_url" not in dumped
    assert "raw" not in dumped
    assert dumped["result_id"] == "abc"
