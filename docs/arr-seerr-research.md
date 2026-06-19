# Arr and Seerr Research Notes

This file records the source-level behavior DMM should copy or deliberately avoid.
Sources reviewed locally:

- Radarr: `Radarr/Radarr`, shallow clone at `/tmp/radarr-src`
- Sonarr: `Sonarr/Sonarr`, shallow clone at `/tmp/sonarr-src`
- Prowlarr: `Prowlarr/Prowlarr`, shallow clone at `/tmp/prowlarr-src`
- Jellyseerr: `Fallenbagel/jellyseerr`, shallow clone at `/tmp/jellyseerr-src`
- Overseerr: `sct/overseerr`, shallow clone at `/tmp/overseerr-src`

## Radarr/Sonarr automatic grabs

Radarr and Sonarr do not continuously run a full search for every wanted item. Their automatic grab path is feed-driven:

1. `RssSyncService` runs a scheduled `RssSyncCommand`.
2. `FetchAndParseRssService` gets only RSS-enabled indexers and calls `FetchRecent()` for each one.
3. Pending delayed releases are merged with the new RSS reports.
4. `DownloadDecisionMaker.GetRssDecision(...)` parses every release title and maps it to a known monitored movie/series/episode.
5. `ProcessDownloadDecisions.ProcessDecisions(...)` prioritizes accepted decisions and sends the best ones to the download client.

Key files:

- Sonarr: `/tmp/sonarr-src/src/NzbDrone.Core/Indexers/RssSyncService.cs`
- Sonarr: `/tmp/sonarr-src/src/NzbDrone.Core/Indexers/FetchAndParseRssService.cs`
- Sonarr: `/tmp/sonarr-src/src/NzbDrone.Core/DecisionEngine/DownloadDecisionMaker.cs`
- Sonarr: `/tmp/sonarr-src/src/NzbDrone.Core/Download/ProcessDownloadDecisions.cs`
- Radarr: `/tmp/radarr-src/src/NzbDrone.Core/Indexers/RssSyncService.cs`
- Radarr: `/tmp/radarr-src/src/NzbDrone.Core/Indexers/FetchAndParseRssService.cs`
- Radarr: `/tmp/radarr-src/src/NzbDrone.Core/DecisionEngine/DownloadDecisionMaker.cs`
- Radarr: `/tmp/radarr-src/src/NzbDrone.Core/Download/ProcessDownloadDecisions.cs`

Design lesson for DMM:

- Use a recent-feed/RSS lane for newly uploaded releases.
- Match each incoming release against DMM's monitored requests locally.
- Do not query every wanted item every minute as the primary mechanism.
- Keep a slower backfill lane for missed items, manual searches, and cutoff-unmet upgrades.

## Radarr/Sonarr backfill search

Manual and missing-item searches are separate from RSS sync.

Sonarr:

- `EpisodeSearchCommand` searches explicit episode IDs.
- `MissingEpisodeSearchCommand` finds monitored episodes without files and already aired, skips queued episodes, groups them by series/season, then searches.
- `CutoffUnmetEpisodeSearchCommand` finds monitored episodes below cutoff, skips queued episodes, then searches.
- New/future episodes become eligible only after metadata refresh knows about them and their air date has passed.

Key file:

- `/tmp/sonarr-src/src/NzbDrone.Core/IndexerSearch/EpisodeSearchService.cs`

Radarr:

- `MoviesSearchCommand` searches explicit movie IDs.
- `MissingMoviesSearchCommand` finds monitored movies without files and skips queued movies.
- `CutoffUnmetMoviesSearchCommand` finds monitored movies below cutoff and skips queued movies.

Key file:

- `/tmp/radarr-src/src/NzbDrone.Core/IndexerSearch/MoviesSearchService.cs`

Design lesson for DMM:

- Store monitored requests separately from release cache.
- Track enough state to know what is wanted, queued/grabbed, complete, failed, and still monitored.
- For TV, track requested seasons or episodes instead of only one show-level row.
- Slow backfill should be limited and ordered by oldest `last_search_at`, not just every request every cycle.

## Prowlarr as an indexer source

Prowlarr exposes two useful layers:

- `/api/v1/search`: manual-style aggregated search. `SearchController` converts the request into `NewznabRequest` and calls `IReleaseSearchService.Search(...)`.
- `/api/v1/indexer/{id}/newznab` and `{id}/api`: Newznab/Torznab-compatible per-indexer proxy. `NewznabController` handles `caps`, `search`, `tvsearch`, `movie`, etc., enforces disabled/query-limit states, and converts download links to Prowlarr proxy links.

Key files:

- `/tmp/prowlarr-src/src/Prowlarr.Api.V1/Search/SearchController.cs`
- `/tmp/prowlarr-src/src/Prowlarr.Api.V1/Search/SearchResource.cs`
- `/tmp/prowlarr-src/src/Prowlarr.Api.V1/Indexers/NewznabController.cs`

Design lesson for DMM:

- For search UI/manual backfill, `/api/v1/search` is fine.
- For Arr-style RSS, prefer a recent-feed abstraction that pulls recent reports once per cycle.
- Respect Prowlarr query limits and disabled indexer status.
- Record per-indexer failures and last successful feed sync so DMM can explain missed releases.

## Seerr/Jellyseerr request model

Jellyseerr/Overseerr are request routers, not release decision engines.

They:

- Store `Media` rows keyed by TMDB/media type with status fields: unknown, pending, processing, partially available, available, blocklisted, deleted.
- Store `MediaRequest` rows with request status: pending, approved, declined, failed, completed.
- Resolve the request target: server ID, root folder, profile ID, tags, 4K/non-4K, user, seasons.
- For movies, call Radarr `addMovie(...)` with TMDB ID, root folder, profile, monitored, tags, and optional `searchNow`.
- For TV, call Sonarr `addSeries(...)`, build monitored seasons, set `monitorNewItems`, and optionally run a missing episode search.
- For existing Sonarr series, requested seasons are re-monitored and episode monitor flags are repaired.

Key files:

- `/tmp/jellyseerr-src/server/entity/MediaRequest.ts`
- `/tmp/jellyseerr-src/server/entity/Media.ts`
- `/tmp/jellyseerr-src/server/api/servarr/radarr.ts`
- `/tmp/jellyseerr-src/server/api/servarr/sonarr.ts`
- `/tmp/jellyseerr-src/server/constants/media.ts`

Design lesson for DMM:

- Seerr should remain the request UI/source of user intent.
- DMM should ingest Seerr requests and preserve target/root/profile/season intent.
- DMM should not mark a whole TV show available from a single episode release.
- DMM needs its own monitored state for releases it is responsible for, because Seerr does not score or pick releases.

## DMM target architecture

DMM should become:

1. Request intake:
   - Import from Seerr.
   - Accept direct DMM requests.
   - Preserve media type, metadata IDs, year, folder target, quality target, and TV season/episode scope.

2. Feed-driven monitor:
   - Pull recent releases once per cycle.
   - Parse and score each release with DMM's Danish/NORDiC/indexer metadata logic.
   - Match release against monitored requests by TMDB/TVDB/IMDB when possible, otherwise normalized title/year.
   - Grab only the highest accepted release per movie/episode/season.

3. Backfill:
   - Limited, slower active searches for missing/cutoff-unmet requests.
   - Ordered by oldest search time.
   - Rate-limited to protect indexer API quotas.

4. State:
   - `pending`: imported/requested but not searched yet.
   - `monitoring`: no acceptable release yet; keep watching RSS/recent.
   - `ready`: acceptable release found but auto-grab disabled or grab deferred.
   - `grabbed`: sent to AltMount.
   - `completed`: imported/available.
   - `failed`/`grab_failed`: retryable with backoff.

5. UI:
   - Wanted board should show monitored, next retry/feed check, last feed match, last active search, and why no release was accepted.
   - TV requests need season/episode visibility, not only one show-level card.

## Immediate DMM fixes from this research

- The background worker must not tie wanted monitoring to Seerr availability.
- Seerr sync failure must not block DMM wanted monitoring in the same cycle.
- The current active wanted retry loop is useful as backfill, but it should not be the only automatic mechanism.
- Implemented in v0.32.0: DMM now has a recent-feed sync path using Prowlarr once per movie/TV cycle, then local release-to-request matching before updating or grabbing a monitored request.

## Remaining gaps after v0.32.0

- TV is still show/request level. To fully match Sonarr, DMM needs season/episode rows, air-date eligibility, queued/downloaded state, and cutoff-unmet tracking.
- Recent-feed sync currently uses title/year matching. Stronger TMDB/TVDB/IMDB matching depends on indexers exposing enough attributes or DMM building richer parsing.
- Feed history is not yet persisted per indexer, so DMM can report current failures but not exact "last successful RSS window" coverage like Arrs do.
