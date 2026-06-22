# Frontend Contract

This is the current production frontend contract for Danish Media Manager.

The live files are:

- `app/static/index.html`
- `app/static/styles.css`
- `app/static/app.js`

The app is served by FastAPI from `/`.

## Required DOM IDs

The existing JavaScript expects these IDs to exist.

Keep these IDs or update `app/static/app.js` at the same time.

```text
status
sidebarStatus
serviceMetric
serviceMetricCard
requestMetric
requestMetricCard
requestMetricSub
queueMetric
queueMetricCard
queueMetricMini
queueMetricSub
indexerMetric
indexerMetricCard
indexerMetricMini
indexerMetricSub
serviceStrip
metadata
searchSummary
results
downloads
importHealth
grabs
indexers
prowlarrHealth
requests
searchForm
query
minResolution
targetPath
acceptedOnly
refreshQueue
retryWanted
requestBest
```

The current JS also expects:

```text
.segmented button[data-type="movie"]
.segmented button[data-type="tv"]
[data-set-theme="dark"]
[data-set-theme="light"]
```

## Main API Endpoints

All endpoints return JSON unless noted.

### Status

`GET /api/status`

Returns Prowlarr and AltMount readiness.

### Search

`POST /api/search`

Body:

```json
{
  "query": "The Batman 2022",
  "media_type": "movie",
  "limit": 100,
  "min_resolution": "1080p"
}
```

Returns metadata, indexer summaries, quality summary, rejection/warning summary, and release list.

### Create DMM Request

`POST /api/requests`

Body:

```json
{
  "query": "Moana 2 2024",
  "media_type": "movie",
  "limit": 100,
  "min_resolution": "1080p",
  "target_path": "/media/kids-movies"
}
```

Returns the created request plus an immediate search response.

### Requests And Wanted Items

```text
GET  /api/requests
GET  /api/requests/{request_id}
GET  /api/requests/{request_id}/items
GET  /api/monitored-items
POST /api/requests/{request_id}/search
POST /api/requests/{request_id}/grab-best
POST /api/wanted/retry
```

Use these to build a wanted board and request detail view.

### Seerr

`POST /api/seerr/sync`

Imports Seerr requests into DMM and optionally grabs accepted releases.

Useful UI action labels:

- Sync Seerr
- Import requests
- Check requests

### Feed / Upcoming / RSS Style Monitoring

```text
POST /api/feed/sync
GET  /api/feed/runs
```

DMM watches recent indexer feeds so upcoming media can be matched later without manually searching every time.

### AltMount / Downloads

```text
GET  /api/queue
GET  /api/downloads
POST /api/completions/sync
GET  /api/import-health
```

Use this area to show downloads, imports, completed items, failed items, and path health.

### Targets

`GET /api/targets`

Returns per-folder request targets for movies and TV. Example paths:

```text
/media/movies
/media/danish-movies
/media/kids-movies
/media/documentaries
/media/tv
/media/danish-tv
/media/kids-tv
/media/documentary-series
```

### Indexers / Diagnostics

```text
GET /api/indexers
GET /api/prowlarr-diagnostics
GET /api/debug/prowlarr-calls
POST /api/debug/prowlarr-calls/reset
GET /api/debug/network
POST /api/debug/network/reset
```

Use these to show indexer state and API call usage.

## Important Product Concepts

### DMM Search Is Not Radarr/Sonarr Search

DMM should make the decision itself from Prowlarr/indexer data and Danish Intelligence. Radarr/Sonarr should not be presented as the main search source.

### Release Decision Fields

Each release has:

- `score.score`
- `score.verdict`
- `score.reasons`
- `decision.accepted`
- `decision.grab_allowed`
- `decision.rejections`
- `decision.warnings`
- `quality.resolution`
- `quality.source`
- `indexer_attrs`

The UI should expose the reasons clearly, not hide them.

### Target Folder Matters

Users request different media into different libraries:

- Normal movies
- Danish movies
- Kids movies
- Documentaries
- Normal TV
- Danish TV
- Kids TV
- Documentary series

Target path should be visible on requests and editable/selectable during request creation.

### TV Needs Child Items

TV requests may represent:

- whole series
- season
- episode

The UI should have space for season/episode monitored items and status.

