import re
from typing import Literal

from pydantic import BaseModel, Field


Resolution = Literal["2160p", "1080p", "720p", "sd", "unknown"]
Source = Literal["remux", "bluray", "web-dl", "webrip", "hdtv", "dvd", "cam", "unknown"]


class QualityInfo(BaseModel):
    resolution: Resolution = "unknown"
    source: Source = "unknown"
    codec: str | None = None
    audio: str | None = None
    hdr: list[str] = Field(default_factory=list)
    has_danish_audio: bool = False
    has_danish_subtitles: bool = False
    has_multi_subtitles: bool = False
    has_nordic_signal: bool = False
    has_nordic_subtitles: bool = False
    has_likely_danish_subtitles: bool = False
    is_low_value_encode: bool = False
    is_bad_source: bool = False


BAD_SOURCE = re.compile(r"\b(cam|hdcam|ts|telesync|tc|telecine|r5|dvdscr|screener)\b", re.I)
LOW_VALUE_ENCODE = re.compile(r"\b(minirip|micro|yify|yts)\b", re.I)


def parse_quality(title: str) -> QualityInfo:
    normalized = title.replace(".", " ").replace("_", " ")
    compact = re.sub(r"[^a-z0-9]+", "", title.lower())
    text = normalized.lower()

    info = QualityInfo()

    if "2160p" in text or "uhd" in text:
        info.resolution = "2160p"
    elif "1080p" in text:
        info.resolution = "1080p"
    elif "720p" in text:
        info.resolution = "720p"
    elif re.search(r"\b(dvd|dvdrip|bdrip|xvid)\b", text):
        info.resolution = "sd"

    if BAD_SOURCE.search(text):
        info.source = "cam"
        info.is_bad_source = True
    elif "remux" in text:
        info.source = "remux"
    elif "bluray" in compact or "blu ray" in text or "bdrip" in text:
        info.source = "bluray"
    elif "web dl" in text or "web-dl" in text or "webdl" in compact:
        info.source = "web-dl"
    elif "webrip" in compact:
        info.source = "webrip"
    elif "hdtv" in text:
        info.source = "hdtv"
    elif "dvd" in text:
        info.source = "dvd"

    if any(codec in text for codec in ("x265", "hevc")) or "h265" in compact:
        info.codec = "HEVC/x265"
    elif "x264" in text or "h264" in text or "h.264" in text:
        info.codec = "H.264/x264"

    if "truehd" in text:
        info.audio = "TrueHD/Atmos" if "atmos" in text else "TrueHD"
    elif "dts-hd" in text or "dts hd" in text:
        info.audio = "DTS-HD"
    elif "ddp" in text or "eac3" in text:
        info.audio = "DDP/EAC3 Atmos" if "atmos" in text else "DDP/EAC3"
    elif "atmos" in text:
        info.audio = "Atmos"

    hdr: list[str] = []
    if "dv" in text or "dolby vision" in text:
        hdr.append("DV")
    if "hdr10plus" in compact or "hdr10+" in text:
        hdr.append("HDR10+")
    elif "hdr10" in compact:
        hdr.append("HDR10")
    elif re.search(r"\bhdr\b", text):
        hdr.append("HDR")
    if "sdr" in text:
        hdr.append("SDR")
    info.hdr = hdr

    info.has_danish_audio = any(
        token in compact for token in ("dkaudio", "dansklyd", "dktale")
    ) or bool(re.search(r"\b(danish|dansk|dk)\s*(audio|tale|lyd)\b", text))
    info.has_danish_subtitles = any(
        token in compact for token in ("dksubs", "dksub", "danishsubs", "dansksubs")
    ) or bool(
        re.search(
            r"\b(danish|dansk|dk)\s*(sub|subs|subtitle|subtitles|undertekst|undertekster)\b",
            text,
        )
    )
    info.has_multi_subtitles = "multisubs" in compact or "multi subs" in text
    info.has_nordic_subtitles = "nortekst" in compact or "nortext" in compact
    info.has_nordic_signal = bool(re.search(r"\b(nordic|nordi?c|nordisk)\b", text)) or info.has_nordic_subtitles
    info.has_likely_danish_subtitles = info.has_nordic_signal and not (
        info.has_danish_subtitles or info.has_multi_subtitles or info.has_nordic_subtitles
    )
    info.is_low_value_encode = bool(LOW_VALUE_ENCODE.search(text))

    return info
