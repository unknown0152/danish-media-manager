from app.quality import parse_quality

from app.models import ScoreBreakdown


def score_release(title: str, size: int | None = None) -> ScoreBreakdown:
    quality = parse_quality(title)

    score = 0
    reasons: list[str] = []

    if quality.has_danish_audio:
        score += 7000
        reasons.append("Danish audio")

    if quality.has_danish_subtitles:
        score += 3600
        reasons.append("Danish subtitles")

    if quality.has_multi_subtitles:
        score += 3000
        reasons.append("Multi subtitles")

    if quality.has_nordic_subtitles:
        score += 2600
        reasons.append("Nordic subtitles")

    if quality.has_likely_danish_subtitles:
        score += 2400
        reasons.append("Likely Danish subtitles")

    if quality.has_nordic_signal:
        score += 2200
        reasons.append("Nordic release")

    if quality.resolution == "2160p":
        score += 2600
        reasons.append("2160p/UHD")
    elif quality.resolution == "1080p":
        score += 1100
        reasons.append("1080p")
    elif quality.resolution == "720p":
        score += 250
        reasons.append("720p")

    if quality.source == "remux":
        score += 1100
        reasons.append("Remux")
    elif quality.source == "bluray":
        score += 850
        reasons.append("BluRay")
    elif quality.source == "web-dl":
        score += 650
        reasons.append("WEB-DL")
    elif quality.source == "webrip":
        score += 250
        reasons.append("WEBRip")

    if quality.codec == "HEVC/x265":
        score += 250
        reasons.append("HEVC/x265")

    if quality.audio in {"TrueHD/Atmos", "DTS-HD"}:
        score += 350
        reasons.append("High quality audio")

    if "DV" in quality.hdr:
        score += 180
        reasons.append("Dolby Vision")
    if "HDR10+" in quality.hdr:
        score += 120
        reasons.append("HDR10+")

    if quality.is_bad_source:
        score -= 7000
        reasons.append("Bad source quality")

    if quality.is_low_value_encode:
        score -= 4500
        reasons.append("Low value encode")

    if size:
        gib = size / 1024 / 1024 / 1024
        if gib < 1:
            score -= 3000
            reasons.append("Small file")
        elif gib < 2.5:
            score -= 1800
            reasons.append("Small movie encode")
        elif gib > 80:
            score -= 150
            reasons.append("Very large file")

    if score >= 9000:
        verdict = "excellent"
    elif score >= 5000:
        verdict = "good"
    elif score >= 1500:
        verdict = "maybe"
    else:
        verdict = "weak"

    return ScoreBreakdown(score=score, verdict=verdict, reasons=reasons or ["No Danish signals"])
