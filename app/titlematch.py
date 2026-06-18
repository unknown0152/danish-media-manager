import re

from pydantic import BaseModel


YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
NOISE = {
    "a",
    "an",
    "and",
    "bluray",
    "danish",
    "dansk",
    "dk",
    "dksubs",
    "multisubs",
    "nordic",
    "nordisk",
    "of",
    "remux",
    "the",
    "uhd",
    "web",
    "webdl",
}


class TitleMatch(BaseModel):
    query_title: str
    query_year: int | None = None
    release_year: int | None = None
    token_overlap: float = 0.0
    year_matches: bool | None = None


def parse_year(text: str) -> int | None:
    match = YEAR_RE.search(text)
    return int(match.group(1)) if match else None


def clean_title(text: str) -> str:
    without_year = YEAR_RE.sub(" ", text)
    normalized = re.sub(r"[^a-zA-Z0-9]+", " ", without_year).strip().lower()
    return re.sub(r"\s+", " ", normalized)


def title_tokens(text: str) -> set[str]:
    return {token for token in clean_title(text).split() if token and token not in NOISE}


def match_title(query: str, release_title: str, expected_year: int | None = None) -> TitleMatch:
    query_tokens = title_tokens(query)
    release_tokens = title_tokens(release_title)
    overlap = 0.0
    if query_tokens:
        overlap = len(query_tokens & release_tokens) / len(query_tokens)

    query_year = expected_year or parse_year(query)
    release_year = parse_year(release_title)
    year_matches = None
    if query_year and release_year:
        year_matches = query_year == release_year

    return TitleMatch(
        query_title=clean_title(query),
        query_year=query_year,
        release_year=release_year,
        token_overlap=overlap,
        year_matches=year_matches,
    )
