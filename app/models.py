from typing import Any, Literal

from pydantic import BaseModel, Field

from app.quality import QualityInfo
from app.titlematch import TitleMatch


MediaType = Literal["movie", "tv"]
MinimumResolution = Literal["any", "720p", "1080p", "2160p"]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    media_type: MediaType = "movie"
    limit: int = Field(default=100, ge=1, le=500)
    min_resolution: MinimumResolution = "any"
    expected_year: int | None = None
    tmdb_id: str | None = None
    tvdb_id: str | None = None
    imdb_id: str | None = None


class MediaRequestCreate(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    media_type: MediaType = "movie"
    limit: int = Field(default=100, ge=1, le=500)
    min_resolution: MinimumResolution = "any"
    target_path: str | None = None


class MetadataResult(BaseModel):
    title: str
    year: int | None = None
    overview: str | None = None
    poster_url: str | None = None
    source: str = "local"
    external_id: str | None = None
    tmdb_id: str | None = None
    tvdb_id: str | None = None
    imdb_id: str | None = None


class MediaTarget(BaseModel):
    media_type: MediaType
    label: str
    path: str


class MediaRequest(BaseModel):
    id: int
    created_at: str
    updated_at: str
    query: str
    media_type: MediaType
    min_resolution: MinimumResolution = "any"
    target_path: str | None = None
    target_label: str | None = None
    metadata_title: str | None = None
    metadata_year: int | None = None
    metadata_poster_url: str | None = None
    external_source: str | None = None
    external_id: str | None = None
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
    indexer_attrs: dict[str, list[Any]] = Field(default_factory=dict)
    quality: QualityInfo
    title_match: TitleMatch | None = None
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)
    score: ScoreBreakdown
    decision: Decision


class IndexerSearchSummary(BaseModel):
    id: int | None = None
    name: str
    total: int = 0
    accepted: int = 0
    best_score: int | None = None


class QualitySearchSummary(BaseModel):
    resolutions: dict[str, int] = Field(default_factory=dict)
    sources: dict[str, int] = Field(default_factory=dict)
    verdicts: dict[str, int] = Field(default_factory=dict)
    accepted_by_resolution: dict[str, int] = Field(default_factory=dict)
    best_score: int | None = None
    best_resolution: str | None = None
    best_source: str | None = None


class SearchResponse(BaseModel):
    query: str
    media_type: MediaType
    metadata: MetadataResult | None = None
    total: int
    accepted: int
    rejected: int
    indexers: list[IndexerSearchSummary] = Field(default_factory=list)
    quality: QualitySearchSummary = Field(default_factory=QualitySearchSummary)
    rejection_summary: dict[str, int] = Field(default_factory=dict)
    warning_summary: dict[str, int] = Field(default_factory=dict)
    releases: list[Release]


class MediaRequestResponse(BaseModel):
    request: MediaRequest
    search: SearchResponse


class SeerrSyncResult(BaseModel):
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    requests: list[MediaRequestResponse] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


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


class IndexerFailure(BaseModel):
    id: int | None = None
    name: str
    disabled_till: str | None = None
    initial_failure: str | None = None
    most_recent_failure: str | None = None
    level: str | None = None


class HealthIssue(BaseModel):
    source: str | None = None
    type: str | None = None
    message: str


class DiagnosticHint(BaseModel):
    level: str = "info"
    message: str


class ProwlarrDiagnostics(BaseModel):
    indexer_failures: list[IndexerFailure] = Field(default_factory=list)
    health: list[HealthIssue] = Field(default_factory=list)
    hints: list[DiagnosticHint] = Field(default_factory=list)


class DownloadItem(BaseModel):
    id: str | None = None
    name: str
    status: str
    category: str | None = None
    size_mb: float | None = None
    progress_percent: float | None = None
    time_left: str | None = None


class DownloadStatus(BaseModel):
    status: str
    paused: bool = False
    speed: str | None = None
    size_left_mb: float | None = None
    queue: list[DownloadItem] = Field(default_factory=list)
    history: list[DownloadItem] = Field(default_factory=list)


class PathProbe(BaseModel):
    path: str
    exists: bool
    is_dir: bool = False
    readable: bool = False


class SymlinkProbe(BaseModel):
    path: str
    target: str | None = None
    target_exists: bool = False
    target_under_mount: bool = False


class ImportHealth(BaseModel):
    import_dir: PathProbe
    mount_path: PathProbe
    media_root: PathProbe
    symlink_count: int = 0
    regular_file_count: int = 0
    sample_symlinks: list[SymlinkProbe] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
