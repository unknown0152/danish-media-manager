# Danish Media Manager

Separate test app for Danish media search, release scoring, and AltMount download handoff.

This repo is intentionally separate from `danish-intelligence`. It does not modify Radarr,
Sonarr, Prowlarr, AltMount, or the existing all-in-one stack.

## Current MVP

- Search Prowlarr for movies or TV.
- Look up lightweight metadata for exact year matching; use Seerr, Radarr, Sonarr, or TMDB for posters/overview when configured.
- Use Radarr/Sonarr metadata IDs to improve matching, while keeping Danish Intelligence/Prowlarr as the primary release-search path.
- Score releases with visible Danish-audio/subtitle reasoning.
- Treat plain `NORDiC` releases as likely Danish subtitles.
- Parse quality fields separately from scoring: resolution, source, codec, audio.
- Parse HDR details including DV and HDR10+.
- Prefer 2160p HDR/Dolby Vision over 2160p SDR when Danish/NORDiC signals are close.
- Parse title/year matching and reject wrong-year releases.
- Use metadata year for exact release-year rejection even when the typed query has no year.
- Show why one release ranks above another.
- Use a denser dashboard layout with service cards, result controls, and operational panels.
- Sort results best-first by accepted state, score, resolution, source, size, and age.
- Show accepted/rejected counts and decision warnings.
- Show quality diagnostics for each search: resolutions, sources, accepted resolutions, and best score.
- Enforce optional minimum quality per search/request: any, 720p+, 1080p+, or 2160p only.
- Summarize rejection and warning reasons for each search.
- Block rejected cached releases from being sent to AltMount, even through direct API calls.
- Block raw direct download URLs by default; normal grabs must come from cached search results.
- Filter the result list to accepted releases only.
- Create persistent requests and store the current best release.
- Import Seerr requests into DMM so Seerr can stay the request frontend while DMM handles rich search/scoring.
- Store a target media folder on each request.
- Rerun a request search without losing the request history.
- Watch the recent Prowlarr movie/TV feed like Arr RSS sync, match new releases locally against monitored requests, and update/grab only when a real candidate appears.
- Preserve TV season/episode scope on manual requests and Seerr imports so feed matches can avoid grabbing the wrong season when Seerr asked for a specific one.
- Store feed sync run history and per-request last feed check/match fields for debugging missed releases.
- Maintain first-class monitored items for movies, TV series, TV seasons, and TV episodes, exposed through `/api/monitored-items` and `/api/requests/{id}/items`.
- Expand scoped TV season requests into episode monitored items when Sonarr, TMDB, or Seerr metadata includes episode counts.
- Keep missing/failed wanted requests on a bounded background retry loop.
- Retry all wanted requests manually from the Requests panel.
- Sync the recent feed manually with `POST /api/feed/sync`.
- Grab the stored best result manually when ready.
- Send a selected release URL to AltMount through the SAB-compatible API.
- Show normalized AltMount download status, active queue, and recent history.
- Track AltMount grab IDs through queue/history completion and update monitored item state.
- Trigger Radarr/Sonarr rescans when AltMount reports a grabbed item as completed.
- Show per-search Prowlarr indexer result counts and best scores.
- Track Prowlarr API call counts by workflow context for live API-use debugging.
- Check whether AltMount import paths are visible and using symlinks instead of regular files.
- Show active Prowlarr indexer failures and health warnings.
- Show safe Prowlarr indexer diagnostics, including OldBoys-specific hints when Prowlarr marks every indexer failed.
- Store recent grabs in SQLite.
- Cache search results server-side so browser responses do not expose Prowlarr download URLs.


## Seerr Workflow

Seerr can remain the family/user request UI. DMM imports recent Seerr requests, resolves metadata from Seerr, runs Danish Intelligence rich search, scores releases, repairs the matching Radarr/Sonarr target path/profile, and can send the best accepted candidate to AltMount. This avoids making Seerr/Radarr/Sonarr the release decision brain.

The background Seerr sync is enabled by default when `SEERR_API_KEY` is set. It runs every `SEERR_SYNC_INTERVAL_SECONDS` seconds and defaults to `60`. By default, new Seerr imports run one active DMM search and can auto-grab the best accepted release when `SEERR_AUTO_GRAB=true`, so Seerr requests behave like immediate download requests. Set `SEERR_ACTIVE_SEARCH_ON_IMPORT=false` for low API-call operation where DMM only imports the request and waits for recent-feed matching or a manual search. DMM also has an Arr-style recent-feed monitor enabled with `RECENT_FEED_SYNC_ENABLED=true`: each cycle it asks Prowlarr once for recent movies and once for recent TV, then matches those releases locally against monitored requests.

After the feed pass, DMM can also retry stored wanted rows with status `no_results`, `search_failed`, or `grab_failed`. That retry loop is opt-in with `WANTED_SEARCH_ENABLED=true` and bounded by `WANTED_SEARCH_MAX_PER_CYCLE`, default `10`, so it remains a slower backfill path instead of the normal request path. The sync endpoints can still be called manually with `POST /api/seerr/sync`, `POST /api/feed/sync`, and `POST /api/wanted/retry`.

For TV, DMM stores `tv_season` and `tv_episode` when a request is scoped. Seerr multi-season requests preserve the full season list inside `origin_details`; single-season requests also populate `tv_season`. Recent feed matching uses that scope to reject obvious wrong-season releases.

Each request also gets monitored child items. A movie request creates a `movie` item; a TV request creates a `series`, `season`, or `episode` item depending on scope. Seerr multi-season requests add season items for each requested season. These items track their own feed check/match state, which is the foundation for Sonarr-like wanted boards.

When metadata includes season episode counts, DMM expands a scoped season request into episode child items. This is optional and backward-compatible: if no episode-count metadata is available, DMM keeps the season item and can expand later when richer metadata arrives.

After a grab, DMM stores the AltMount download ID when the SAB-compatible API returns one. Each background cycle checks AltMount queue/history, marks linked monitored items as `downloading`, `failed`, or `import_pending`, and asks Radarr/Sonarr to rescan the matching movie or series once AltMount reports completion. The same completion pass can be run manually with `POST /api/completions/sync`.

## Request Workflow

Manual DMM requests store the search and best candidate until a user clicks grab. Seerr-imported requests can auto-grab through the background sync.

Useful endpoints:

```text
POST /api/requests
GET  /api/requests
GET  /api/requests/{id}/items
GET  /api/monitored-items
POST /api/requests/{id}/search
POST /api/requests/{id}/grab-best
POST /api/seerr/sync
POST /api/feed/sync
GET  /api/feed/runs
POST /api/wanted/retry
POST /api/completions/sync
GET  /api/downloads
GET  /api/import-health
GET  /api/prowlarr-diagnostics
GET  /api/debug/prowlarr-calls
POST /api/debug/prowlarr-calls/reset
GET  /api/debug/network
POST /api/debug/network/reset
GET  /api/targets
```

## Network Analyzer

For live indexer API-use tests, reset the network marker before adding requests in Seerr:

```bash
curl -fsS -X POST http://127.0.0.1:8088/api/debug/network/reset
```

After adding films or TV shows, read the analyzer:

```bash
curl -fsS http://127.0.0.1:8088/api/debug/network | python3 -m json.tool
```

The analyzer combines DMM's direct Prowlarr calls with Prowlarr history fanout, so it shows
the real upstream indexer/provider call count. It groups DMM calls by context, such as
`seerr_background`, `recent_feed_sync`, `wanted_retry`, and `manual_search`, and groups
upstream calls by indexer, media type, query type, result count, elapsed time, failures, and
cached calls. It intentionally omits provider URLs and API keys.

For diagnostics, debug responses show search query text by default. Set
`DEBUG_REDACT_QUERIES=true` to replace query fields with `<redacted>`.

Seerr import can stay frequent with `SEERR_SYNC_INTERVAL_SECONDS=60`. The expensive recent
feed fanout is separately throttled by `RECENT_FEED_SYNC_INTERVAL_SECONDS`, default `900`
seconds, so it does not hit every enabled indexer every minute.

## Run Locally

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
PROWLARR_URL=http://prowlarr:9696 \
PROWLARR_API_KEY=... \
ALTMOUNT_URL=http://danish-intelligence:9699/altmount \
ALTMOUNT_API_KEY=... \
DATABASE_PATH=./data/danish-media-manager.db \
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open:

```text
http://localhost:8080
```

## Docker

```bash
cp docker-compose.example.yml docker-compose.yml
PROWLARR_API_KEY=... ALTMOUNT_API_KEY=... docker compose up -d
```

After a tagged release exists, the image will be published as:

```text
ghcr.io/unknown0152/danish-media-manager:<tag>
```

For local development:

```bash
PROWLARR_API_KEY=... ALTMOUNT_API_KEY=... docker compose -f docker-compose.dev.yml up -d --build
```

The container expects to be on the same Docker network as `prowlarr` and
`danish-intelligence` or whichever service exposes the AltMount SAB API.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `PROWLARR_URL` | `http://prowlarr:9696` | Prowlarr API base URL |
| `PROWLARR_API_KEY` | empty | Prowlarr API key |
| `DANISH_INTELLIGENCE_URL` | `http://danish-intelligence:9699` | Native rich search API base URL |
| `RADARR_URL` | `http://radarr:7878` | Optional Radarr API base URL for movie metadata lookup |
| `RADARR_API_KEY` | empty | Optional Radarr API key |
| `SONARR_URL` | `http://sonarr:8989` | Optional Sonarr API base URL for TV metadata lookup |
| `SONARR_API_KEY` | empty | Optional Sonarr API key |
| `SEERR_URL` | `http://seerr:5055` | Optional Seerr/Jellyseerr API base URL for metadata lookup |
| `SEERR_API_KEY` | empty | Optional Seerr/Jellyseerr API key |
| `SEERR_ACTIVE_SEARCH_ON_IMPORT` | `true` | Run full active search immediately when importing a new Seerr request; set false for low API-call operation |
| `RECENT_FEED_SYNC_ENABLED` | `true` | Watch recent Prowlarr movie/TV feeds and match them against monitored requests |
| `RECENT_FEED_LIMIT` | `500` | Max recent Prowlarr releases fetched per media type each cycle |
| `MONITORED_REQUESTS_MAX_PER_CYCLE` | `100` | Max monitored DMM requests checked against the recent feed each cycle |
| `ALTMOUNT_URL` | `http://danish-intelligence:9699/altmount` | SAB-compatible AltMount proxy URL |
| `ALTMOUNT_API_KEY` | empty | AltMount/SAB API key |
| `ALTMOUNT_IMPORT_DIR` | `/mnt/altmount-import` | Read-only path inspected for symlink imports |
| `ALTMOUNT_MOUNT_PATH` | `/mnt/altmount` | Read-only AltMount FUSE path expected as symlink target |
| `MEDIA_ROOT` | `/media` | Read-only media root visibility check |
| `DATABASE_PATH` | `/data/danish-media-manager.db` | SQLite history DB |
| `ALLOW_DIRECT_DOWNLOAD_URLS` | `false` | Set to `true` only for manual debugging of raw NZB URLs |
| `TMDB_API_KEY` | empty | Optional TMDB fallback API key for posters, overview, and external metadata IDs |
| `MOVIE_TARGETS` | built-in movie folders | Comma list like `Movies=/media/movies,Danish=/media/danish-movies` |
| `TV_TARGETS` | built-in TV folders | Comma list like `TV=/media/tv,Danish TV=/media/danish-tv` |

## Roadmap

- Add user accounts only if this becomes exposed outside the LAN.
