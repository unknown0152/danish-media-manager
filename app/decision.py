from app.models import Decision, ScoreBreakdown
from app.quality import QualityInfo
from app.titlematch import TitleMatch


def decide_release(
    *,
    score: ScoreBreakdown,
    quality: QualityInfo,
    title_match: TitleMatch | None = None,
    size: int | None,
    download_url: str | None,
    min_resolution: str = "any",
) -> Decision:
    rejections: list[str] = []
    warnings: list[str] = []

    if not download_url:
        rejections.append("No download URL from indexer")

    if quality.is_bad_source:
        rejections.append("Rejected bad source quality")

    if not _meets_min_resolution(quality.resolution, min_resolution):
        rejections.append(
            f"Below requested minimum resolution: {quality.resolution or 'unknown'} < {min_resolution}"
        )

    if title_match:
        if title_match.year_matches is False:
            rejections.append(
                f"Wrong year: wanted {title_match.query_year}, release is {title_match.release_year}"
            )
        if title_match.token_overlap < 0.6:
            warnings.append("Weak title match")

    if quality.is_low_value_encode:
        warnings.append("Low value encode")

    if not (
        quality.has_danish_audio
        or quality.has_danish_subtitles
        or quality.has_multi_subtitles
        or quality.has_nordic_signal
    ):
        warnings.append("No Danish/Nordic signal")

    if size:
        gib = size / 1024 / 1024 / 1024
        if gib < 1:
            rejections.append("File is too small for a movie/season release")
        elif gib < 2.5:
            warnings.append("Small encode")

    if score.score < 1000:
        rejections.append("Score below minimum")

    grab_allowed = not rejections
    return Decision(
        accepted=grab_allowed,
        grab_allowed=grab_allowed,
        rejections=rejections,
        warnings=warnings,
    )


def _meets_min_resolution(resolution: str | None, minimum: str) -> bool:
    if minimum == "any":
        return True
    order = {"720p": 720, "1080p": 1080, "2160p": 2160}
    wanted = order.get(minimum)
    found = order.get(resolution or "")
    if wanted is None:
        return True
    if found is None:
        return False
    return found >= wanted
