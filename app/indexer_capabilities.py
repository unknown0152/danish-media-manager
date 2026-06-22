import re
from dataclasses import dataclass
from typing import Any

from app.quality import QualityInfo


@dataclass(frozen=True)
class IndexerCapability:
    structured_audio: bool = False
    structured_language: bool = False
    structured_subs: bool = False
    nfo_endpoint: str | None = None
    nfo_id_source: str | None = None
    release_language_is_metadata: bool = False
    notes: str = ""


CAPABILITIES: dict[str, IndexerCapability] = {
    "nzblife": IndexerCapability(
        structured_audio=True,
        structured_language=True,
        structured_subs=True,
        release_language_is_metadata=True,
        notes="Raw API returns useful audio/language/subs attrs.",
    ),
    "nzbgeek": IndexerCapability(
        structured_language=True,
        structured_subs=True,
        release_language_is_metadata=True,
        notes="Raw API returns language/subs attrs; audio attr was absent.",
    ),
    "scenenzbs": IndexerCapability(
        structured_language=True,
        structured_subs=True,
        release_language_is_metadata=True,
        notes="Raw API may return language/subs plus tmdb attrs.",
    ),
    "abnzb": IndexerCapability(
        structured_subs=True,
        notes="Search results can expose subs; details often drops them.",
    ),
    "nzbfinder": IndexerCapability(
        structured_subs=True,
        notes="Search results can expose strong subtitle lists.",
    ),
    "althub": IndexerCapability(
        nfo_endpoint="getnfo",
        nfo_id_source="attr_guid",
        notes="No useful structured attrs; getnfo works with the newznab attr guid.",
    ),
    "msgnews": IndexerCapability(
        nfo_endpoint="getnfo",
        nfo_id_source="attr_guid",
        notes="No useful structured attrs; getnfo works with the newznab attr guid.",
    ),
    "drunkenslug": IndexerCapability(
        nfo_endpoint="info",
        nfo_id_source="hash_guid",
        notes="JSON language is channel/feed language, not release language; info often returns no NFO.",
    ),
    "ninjacentral": IndexerCapability(
        notes="No useful structured language attrs observed; skip language enrichment.",
    ),
}


DANISH_LANGUAGE_TOKENS = {
    "da",
    "dan",
    "danish",
    "dansk",
    "danske",
    "dk",
    "danmark",
}

SUBS_KEYS = ("subs", "subtitles", "subtitle")
AUDIO_KEYS = ("audio", "audiotracks", "audio_tracks")
LANGUAGE_KEYS = ("language", "languages", "lang")


def capability_for_indexer(indexer_name: str) -> IndexerCapability:
    slug = _slug(indexer_name)
    for key, capability in CAPABILITIES.items():
        if key in slug:
            return capability
    return IndexerCapability()


def apply_indexer_attrs_to_quality(
    quality: QualityInfo,
    *,
    indexer_name: str,
    attrs: dict[str, list[Any]],
) -> QualityInfo:
    capability = capability_for_indexer(indexer_name)
    if not attrs:
        return quality

    if capability.structured_audio and _contains_danish(_values_for(attrs, AUDIO_KEYS)):
        quality.has_danish_audio = True

    if capability.structured_language and _contains_danish(_values_for(attrs, LANGUAGE_KEYS)):
        quality.has_danish_audio = True

    if capability.structured_subs and _contains_danish(_values_for(attrs, SUBS_KEYS)):
        quality.has_danish_subtitles = True
        quality.has_likely_danish_subtitles = False

    return quality


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _values_for(attrs: dict[str, list[Any]], keys: tuple[str, ...]) -> list[str]:
    wanted = {key.lower() for key in keys}
    values: list[str] = []
    for key, raw_values in attrs.items():
        if key.lower() not in wanted:
            continue
        for raw_value in raw_values:
            if raw_value is not None:
                values.append(str(raw_value))
    return values


def _contains_danish(values: list[str]) -> bool:
    for value in values:
        for token in _language_tokens(value):
            if token in DANISH_LANGUAGE_TOKENS:
                return True
    return False


def _language_tokens(value: str) -> set[str]:
    normalized = value.lower()
    normalized = normalized.replace("danish (dk)", "danish dk")
    return {
        token
        for token in re.split(r"[^a-z0-9+-]+", normalized)
        if token
    }
