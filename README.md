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
- Keep missing/failed wanted requests on a bounded background retry loop.
- Retry all wanted requests manually from the Requests panel.
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

The background Seerr sync is enabled by default when `SEERR_API_KEY` is set. It runs every `SEERR_SYNC_INTERVAL_SECONDS` seconds, defaults to `60`, and auto-grabs when `SEERR_AUTO_GRAB=true`. After each sync, DMM can also retry stored wanted rows with status `no_results`, `search_failed`, or `grab_failed`. That retry loop is enabled with `WANTED_SEARCH_ENABLED=true` and bounded by `WANTED_SEARCH_MAX_PER_CYCLE`, default `10`, so it does not fan out into unlimited indexer calls. The sync endpoint can still be called manually with `POST /api/seerr/sync`, and wanted retries can be called manually with `POST /api/wanted/retry`.

## Request Workflow

Manual DMM requests store the search and best candidate until a user clicks grab. Seerr-imported requests can auto-grab through the background sync.

Useful endpoints:

```text
POST /api/requests
GET  /api/requests
POST /api/requests/{id}/search
POST /api/requests/{id}/grab-best
POST /api/seerr/sync
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
