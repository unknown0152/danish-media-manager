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
- Create persistent requests and store the current best release.
- Rerun a request search without losing the request history.
- Grab the stored best result manually when ready.
- Send a selected release URL to AltMount through the SAB-compatible API.
- Show normalized AltMount download status, active queue, and recent history.
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
| `DATABASE_PATH` | `/data/danish-media-manager.db` | SQLite history DB |

## Roadmap

- Add metadata lookup for movie/TV posters and exact year matching.
- Add provider/indexer failure tracking.
- Add per-folder request targets.
- Add import/symlink verification.
- Add user accounts only if this becomes exposed outside the LAN.
