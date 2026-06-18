from typing import Any, Literal

from pydantic import BaseModel, Field

from app.quality import QualityInfo


MediaType = Literal["movie", "tv"]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    media_type: MediaType = "movie"
    limit: int = Field(default=100, ge=1, le=500)


class GrabRequest(BaseModel):
    title: str
    media_type: MediaType = "movie"
    result_id: str | None = None
    download_url: str | None = None
    guid: str | None = None
    indexer_id: int | None = None
    category: str | None = None


class ScoreBreakdown(BaseModel):
    score: int
    verdict: str
    reasons: list[str]


class Release(BaseModel):
    result_id: str
    title: str
    indexer: str = "Unknown"
    protocol: str | None = None
    age: int | None = None
    size: int | None = None
    guid: str | None = None
    download_url: str | None = Field(default=None, exclude=True)
    indexer_id: int | None = None
    categories: list[Any] = Field(default_factory=list)
    quality: QualityInfo
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)
    score: ScoreBreakdown


class SearchResponse(BaseModel):
    query: str
    media_type: MediaType
    releases: list[Release]


class GrabResponse(BaseModel):
    ok: bool
    message: str
    altmount_response: dict[str, Any] | str | None = None
