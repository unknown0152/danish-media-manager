from app.scoring import score_release
from app.decision import decide_release
from app.main import indexer_summaries, quality_summary, reason_summary
from app.models import Release
from app.quality import parse_quality
from app.titlematch import match_title


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


def test_no_danish_signal_is_not_grabbable_even_when_quality_is_good() -> None:
    title = "Chicago.Med.2015.S10E11.GERMAN.5.1.DL.DTS.1080p.Bluray.Remux.h264"
    quality = parse_quality(title)
    score = score_release(title, 10_000_000_000)
    decision = decide_release(
        score=score,
        quality=quality,
        title_match=match_title("Chicago Med 2015", title),
        size=10_000_000_000,
        download_url="http://example.invalid/file.nzb",
        min_resolution="1080p",
    )

    assert not decision.grab_allowed
    assert "No Danish/Nordic signal" in decision.rejections


def test_hdr_details_are_parsed() -> None:
    quality = parse_quality(
        "Movie.2026.NORDiC.2160p.UHD.BluRay.DV.HDR10Plus.TrueHD.Atmos.x265"
    )

    assert quality.resolution == "2160p"
    assert quality.source == "bluray"
    assert "DV" in quality.hdr
    assert "HDR10+" in quality.hdr


def test_h265_and_ddp_atmos_are_parsed_without_truehd() -> None:
    quality = parse_quality("Movie.2026.NORDiC.2160p.WEB-DL.DV.H.265.DDP5.1.Atmos")

    assert quality.codec == "HEVC/x265"
    assert quality.audio == "DDP/EAC3 Atmos"
    assert "DV" in quality.hdr


def test_2160p_dolby_vision_beats_2160p_sdr_when_other_signals_are_close() -> None:
    sdr = score_release(
        "The.Batman.2022.NORDiC.2160p.SDR.BluRay.DTS-HD.MA.TrueHD.7.1.Atmos.x265-NorTekst",
        size=40_000_000_000,
    )
    dv = score_release(
        "The.Batman.2022.NORDiC.2160p.DV.HMAX.WEB-DL.DDP5.1.Atmos.x265",
        size=40_000_000_000,
    )

    assert dv.score > sdr.score
    assert "Dolby Vision" in dv.reasons
    assert "2160p SDR" in sdr.reasons


def test_bad_cam_is_penalized() -> None:
    scored = score_release("The.Movie.2026.CAM.1080p.DKSUBS")

    assert scored.score < 0
    assert "Bad source quality" in scored.reasons


def test_danish_subtitle_reason() -> None:
    scored = score_release("The.Movie.2026.NORDiC.1080p.WEB-DL.DKSUBS")

    assert scored.verdict in {"good", "excellent"}
    assert "Danish subtitles" in scored.reasons


def test_release_serialization_hides_sensitive_url_and_raw() -> None:
    quality = parse_quality("Example.DKSUBS")
    score = score_release("Example.DKSUBS")
    release = Release(
        result_id="abc",
        title="Example",
        download_url="http://prowlarr/download?apikey=secret",
        raw={"downloadUrl": "http://prowlarr/download?apikey=secret"},
        quality=quality,
        score=score,
        decision=decide_release(
            score=score,
            quality=quality,
            title_match=match_title("Example", "Example.DKSUBS"),
            size=5_000_000_000,
            download_url="http://prowlarr/download?apikey=secret",
        ),
    )

    dumped = release.model_dump()

    assert "download_url" not in dumped
    assert "raw" not in dumped
    assert dumped["result_id"] == "abc"


def test_bad_source_is_not_grabbable() -> None:
    quality = parse_quality("Movie.2026.CAM.1080p.DKSUBS")
    score = score_release("Movie.2026.CAM.1080p.DKSUBS")
    decision = decide_release(
        score=score,
        quality=quality,
        title_match=match_title("Movie 2026", "Movie.2026.CAM.1080p.DKSUBS"),
        size=5_000_000_000,
        download_url="http://example.invalid/file.nzb",
    )

    assert not decision.grab_allowed
    assert "Rejected bad source quality" in decision.rejections


def test_wrong_year_is_rejected() -> None:
    quality = parse_quality("The.Batman.2021.NORDiC.2160p.BluRay.x265")
    score = score_release("The.Batman.2021.NORDiC.2160p.BluRay.x265", 20_000_000_000)
    decision = decide_release(
        score=score,
        quality=quality,
        title_match=match_title("The Batman 2022", "The.Batman.2021.NORDiC.2160p.BluRay.x265"),
        size=20_000_000_000,
        download_url="http://example.invalid/file.nzb",
    )

    assert not decision.grab_allowed
    assert any(reason.startswith("Wrong year") for reason in decision.rejections)


def test_metadata_expected_year_rejects_wrong_release_year_when_query_has_no_year() -> None:
    quality = parse_quality("The.Batman.2021.NORDiC.2160p.BluRay.x265")
    score = score_release("The.Batman.2021.NORDiC.2160p.BluRay.x265", 20_000_000_000)
    decision = decide_release(
        score=score,
        quality=quality,
        title_match=match_title(
            "The Batman",
            "The.Batman.2021.NORDiC.2160p.BluRay.x265",
            expected_year=2022,
        ),
        size=20_000_000_000,
        download_url="http://example.invalid/file.nzb",
    )

    assert not decision.grab_allowed
    assert any(reason.startswith("Wrong year") for reason in decision.rejections)


def test_minimum_resolution_rejects_lower_quality() -> None:
    quality = parse_quality("The.Batman.2022.NORDiC.1080p.BluRay.x265")
    score = score_release("The.Batman.2022.NORDiC.1080p.BluRay.x265", 20_000_000_000)
    decision = decide_release(
        score=score,
        quality=quality,
        title_match=match_title("The Batman 2022", "The.Batman.2022.NORDiC.1080p.BluRay.x265"),
        size=20_000_000_000,
        download_url="http://example.invalid/file.nzb",
        min_resolution="2160p",
    )

    assert not decision.grab_allowed
    assert "Below requested minimum resolution: 1080p < 2160p" in decision.rejections


def test_indexer_summaries_count_results_by_source() -> None:
    releases = []
    for title, indexer, indexer_id in [
        ("The.Batman.2022.NORDiC.2160p.BluRay.x265", "NZBgeek", 1),
        ("The.Batman.2022.CAM.1080p.DKSUBS", "NZBgeek", 1),
        ("The.Batman.2022.NORDiC.1080p.WEB-DL.x265", "altHUB", 2),
    ]:
        quality = parse_quality(title)
        score = score_release(title, 20_000_000_000)
        releases.append(
            Release(
                result_id=title,
                title=title,
                indexer=indexer,
                indexer_id=indexer_id,
                quality=quality,
                score=score,
                decision=decide_release(
                    score=score,
                    quality=quality,
                    title_match=match_title("The Batman 2022", title),
                    size=20_000_000_000,
                    download_url="http://example.invalid/file.nzb",
                ),
            )
        )

    summaries = indexer_summaries(releases)

    assert [(summary.name, summary.total, summary.accepted) for summary in summaries] == [
        ("NZBgeek", 2, 1),
        ("altHUB", 1, 1),
    ]


def test_quality_summary_counts_best_resolution_and_sources() -> None:
    releases = []
    for title in [
        "The.Batman.2022.NORDiC.2160p.BluRay.x265",
        "The.Batman.2022.NORDiC.1080p.WEB-DL.x265",
        "The.Batman.2022.CAM.1080p.DKSUBS",
    ]:
        quality = parse_quality(title)
        score = score_release(title, 20_000_000_000)
        releases.append(
            Release(
                result_id=title,
                title=title,
                quality=quality,
                score=score,
                decision=decide_release(
                    score=score,
                    quality=quality,
                    title_match=match_title("The Batman 2022", title),
                    size=20_000_000_000,
                    download_url="http://example.invalid/file.nzb",
                ),
            )
        )

    summary = quality_summary(releases)

    assert summary.resolutions["1080p"] == 2
    assert summary.resolutions["2160p"] == 1
    assert summary.sources["bluray"] == 1
    assert summary.sources["web-dl"] == 1
    assert summary.best_resolution == "2160p"
    assert summary.accepted_by_resolution == {"2160p": 1, "1080p": 1}


def test_reason_summary_counts_repeated_rejections() -> None:
    summary = reason_summary(
        [
            "Below requested minimum resolution: 1080p < 2160p",
            "Below requested minimum resolution: 1080p < 2160p",
            "Rejected bad source quality",
        ]
    )

    assert summary == {
        "Below requested minimum resolution: 1080p < 2160p": 2,
        "Rejected bad source quality": 1,
    }
