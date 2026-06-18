from typing import Any, Literal

from pydantic import BaseModel, Field

from app.quality import QualityInfo


MediaType = Literal["movie", "tv"]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    media_type: MediaType = "movie"
    limit: int = Field(default=100, ge=1, le=500)


class MediaRequestCreate(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    media_type: MediaType = "movie"
    limit: int = Field(default=100, ge=1, le=500)


class MediaRequest(BaseModel):
    id: int
    created_at: str
    updated_at: str
    query: str
    media_type: MediaType
    status: str
    best_result_id: str | None = None
    best_title: str | None = None
    best_score: int | None = None
    total: int = 0
    accepted: int = 0
    rejected: int = 0


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


class Decision(BaseModel):
    accepted: bool
    grab_allowed: bool
    rejections: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


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
    decision: Decision


class SearchResponse(BaseModel):
    query: str
    media_type: MediaType
    total: int
    accepted: int
    rejected: int
    releases: list[Release]


class MediaRequestResponse(BaseModel):
    request: MediaRequest
    search: SearchResponse


class GrabResponse(BaseModel):
    ok: bool
    message: str
    altmount_response: dict[str, Any] | str | None = None


class IndexerStatus(BaseModel):
    id: int | None = None
    name: str
    implementation: str | None = None
    protocol: str | None = None
    enable: bool | None = None
    priority: int | None = None
    tags: list[int] = Field(default_factory=list)
