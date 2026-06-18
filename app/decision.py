from app.models import Decision, ScoreBreakdown
from app.quality import QualityInfo


def decide_release(
    *,
    score: ScoreBreakdown,
    quality: QualityInfo,
    size: int | None,
    download_url: str | None,
) -> Decision:
    rejections: list[str] = []
    warnings: list[str] = []

    if not download_url:
        rejections.append("No download URL from indexer")

    if quality.is_bad_source:
        rejections.append("Rejected bad source quality")

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

