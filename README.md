# Danish Media Manager

Separate test app for Danish media search, release scoring, and AltMount download handoff.

This repo is intentionally separate from `danish-intelligence`. It does not modify Radarr,
Sonarr, Prowlarr, AltMount, or the existing all-in-one stack.

## Current MVP

- Search Prowlarr for movies or TV.
- Score releases with visible Danish-audio/subtitle reasoning.
- Treat plain `NORDiC` releases as likely Danish subtitles.
- Parse quality fields separately from scoring: resolution, source, codec, audio.
- Parse HDR details including DV and HDR10+.
- Parse title/year matching and reject wrong-year releases.
- Show why one release ranks above another.
- Show accepted/rejected counts and decision warnings.
- Show quality diagnostics for each search: resolutions, sources, accepted resolutions, and best score.
- Enforce optional minimum quality per search/request: any, 720p+, 1080p+, or 2160p only.
- Summarize rejection and warning reasons for each search.
- Block rejected cached releases from being sent to AltMount, even through direct API calls.
- Block raw direct download URLs by default; normal grabs must come from cached search results.
- Filter the result list to accepted releases only.
- Create persistent requests and store the current best release.
- Rerun a request search without losing the request history.
- Grab the stored best result manually when ready.
- Send a selected release URL to AltMount through the SAB-compatible API.
- Show normalized AltMount download status, active queue, and recent history.
- Show per-search Prowlarr indexer result counts and best scores.
- Check whether AltMount import paths are visible and using symlinks instead of regular files.
- Show active Prowlarr indexer failures and health warnings.
- Show safe Prowlarr indexer diagnostics.
- Store recent grabs in SQLite.
- Cache search results server-side so browser responses do not expose Prowlarr download URLs.

## Request Workflow

The app does not auto-download in the background. A request stores the search and the best
candidate, but a user action is still required to grab it.

Useful endpoints:

```text
POST /api/requests
GET  /api/requests
POST /api/requests/{id}/search
POST /api/requests/{id}/grab-best
GET  /api/downloads
GET  /api/import-health
GET  /api/prowlarr-diagnostics
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
| `ALTMOUNT_URL` | `http://danish-intelligence:9699/altmount` | SAB-compatible AltMount proxy URL |
| `ALTMOUNT_API_KEY` | empty | AltMount/SAB API key |
| `ALTMOUNT_IMPORT_DIR` | `/mnt/altmount-import` | Read-only path inspected for symlink imports |
| `ALTMOUNT_MOUNT_PATH` | `/mnt/altmount` | Read-only AltMount FUSE path expected as symlink target |
| `MEDIA_ROOT` | `/media` | Read-only media root visibility check |
| `DATABASE_PATH` | `/data/danish-media-manager.db` | SQLite history DB |
| `ALLOW_DIRECT_DOWNLOAD_URLS` | `false` | Set to `true` only for manual debugging of raw NZB URLs |

## Roadmap

- Add metadata lookup for movie/TV posters and exact year matching.
- Add per-folder request targets.
- Add user accounts only if this becomes exposed outside the LAN.
