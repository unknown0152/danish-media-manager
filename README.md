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
- Keep missing/failed wanted requests on a bounded background retry loop.
- Retry all wanted requests manually from the Requests panel.
- Sync the recent feed manually with `POST /api/feed/sync`.
- Grab the stored best result manually when ready.
- Send a selected release URL to AltMount through the SAB-compatible API.
- Show normalized AltMount download status, active queue, and recent history.
- Show per-search Prowlarr indexer result counts and best scores.
- Check whether AltMount import paths are visible and using symlinks instead of regular files.
- Show active Prowlarr indexer failures and health warnings.
- Show safe Prowlarr indexer diagnostics, including OldBoys-specific hints when Prowlarr marks every indexer failed.
- Store recent grabs in SQLite.
- Cache search results server-side so browser responses do not expose Prowlarr download URLs.


## Seerr Workflow

Seerr can remain the family/user request UI. DMM imports recent Seerr requests, resolves metadata from Seerr, runs Danish Intelligence rich search, scores releases, repairs the matching Radarr/Sonarr target path/profile, and can send the best accepted candidate to AltMount. This avoids making Seerr/Radarr/Sonarr the release decision brain.

The background Seerr sync is enabled by default when `SEERR_API_KEY` is set. It runs every `SEERR_SYNC_INTERVAL_SECONDS` seconds, defaults to `60`, and auto-grabs when `SEERR_AUTO_GRAB=true`. DMM also has an Arr-style recent-feed monitor enabled with `RECENT_FEED_SYNC_ENABLED=true`: each cycle it asks Prowlarr once for recent movies and once for recent TV, then matches those releases locally against monitored DMM requests. This is the primary path for newly posted releases and avoids one indexer search per wanted item.

After the feed pass, DMM can also retry stored wanted rows with status `no_results`, `search_failed`, or `grab_failed`. That retry loop is enabled with `WANTED_SEARCH_ENABLED=true` and bounded by `WANTED_SEARCH_MAX_PER_CYCLE`, default `10`, so it remains a slower backfill path. The sync endpoints can still be called manually with `POST /api/seerr/sync`, `POST /api/feed/sync`, and `POST /api/wanted/retry`.

For TV, DMM stores `tv_season` and `tv_episode` when a request is scoped. Seerr multi-season requests preserve the full season list inside `origin_details`; single-season requests also populate `tv_season`. Recent feed matching uses that scope to reject obvious wrong-season releases.

Each request also gets monitored child items. A movie request creates a `movie` item; a TV request creates a `series`, `season`, or `episode` item depending on scope. Seerr multi-season requests add season items for each requested season. These items track their own feed check/match state, which is the foundation for Sonarr-like wanted boards.

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
GET  /api/downloads
GET  /api/import-health
GET  /api/prowlarr-diagnostics
GET  /api/targets
```

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
