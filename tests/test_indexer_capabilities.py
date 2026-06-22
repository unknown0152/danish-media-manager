from app.indexer_capabilities import capability_for_indexer
from app.prowlarr import release_from_item


def _release(indexer: str, attrs: dict[str, list[str]]):
    return release_from_item(
        {
            "title": "Inside.Out.2.2024.1080p.WEB-DL.x265-GRP",
            "indexer": indexer,
            "size": 8_000_000_000,
            "downloadUrl": "https://example.invalid/download.nzb",
            "attrs": attrs,
        },
        query="Inside Out 2",
        min_resolution="1080p",
        expected_year=2024,
    )


def test_nzblife_audio_and_sub_attrs_are_trusted() -> None:
    release = _release(
        "Nzb.life {DK}",
        {
            "audio": ["Danish, English"],
            "language": ["en"],
            "subs": ["Danish, English, Finnish, Norwegian, Swedish"],
        },
    )

    assert release.quality.has_danish_audio is True
    assert release.quality.has_danish_subtitles is True
    assert release.decision.grab_allowed is True
    assert "Danish audio" in release.score.reasons
    assert "Danish subtitles" in release.score.reasons


def test_nzbgeek_sub_attrs_are_trusted_without_audio_attr() -> None:
    release = _release(
        "NZBgeek {DK}",
        {
            "subs": ["English, Danish"],
        },
    )

    assert release.quality.has_danish_audio is False
    assert release.quality.has_danish_subtitles is True
    assert release.decision.grab_allowed is True


def test_abnzb_sub_attrs_are_trusted() -> None:
    release = _release(
        "abNZB {DK}",
        {
            "subs": ["da, en, no, sv"],
        },
    )

    assert release.quality.has_danish_subtitles is True
    assert release.decision.grab_allowed is True


def test_drunkenslug_language_attr_is_not_release_language() -> None:
    release = _release(
        "DrunkenSlug {DK}",
        {
            "language": ["en-gb"],
            "subs": ["Danish"],
        },
    )

    assert release.quality.has_danish_audio is False
    assert release.quality.has_danish_subtitles is False
    assert release.decision.grab_allowed is False


def test_althub_structured_language_attrs_are_not_trusted() -> None:
    release = _release(
        "altHUB {DK}",
        {
            "language": ["Danish"],
            "subs": ["Danish"],
        },
    )

    assert release.quality.has_danish_audio is False
    assert release.quality.has_danish_subtitles is False
    assert release.decision.grab_allowed is False


def test_raw_nfo_capabilities_are_recorded_for_future_enrichment() -> None:
    althub = capability_for_indexer("altHUB {DK}")
    msgnews = capability_for_indexer("msgnews {DK}")
    slug = capability_for_indexer("DrunkenSlug {DK}")
    ninja = capability_for_indexer("NinjaCentral {DK}")

    assert althub.nfo_endpoint == "getnfo"
    assert althub.nfo_id_source == "attr_guid"
    assert msgnews.nfo_endpoint == "getnfo"
    assert msgnews.nfo_id_source == "attr_guid"
    assert slug.nfo_endpoint == "info"
    assert slug.nfo_id_source == "hash_guid"
    assert ninja.nfo_endpoint is None
