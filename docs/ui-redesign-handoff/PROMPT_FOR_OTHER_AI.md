# Prompt For Another AI

You are redesigning the frontend for **Danish Media Manager**, a local-first media automation web app.

## What DMM Is

Danish Media Manager is not a normal media website. It is an operational control desk for a private media stack.

It connects to:

- Seerr for user requests.
- Prowlarr and indexers for release search.
- Danish Intelligence for richer Danish/NORDiC release interpretation.
- AltMount for downloads and imports.
- Radarr/Sonarr only as passive library/file metadata managers, not as the main search brain.

DMM decides which releases are actually good based on Danish audio, Danish subtitles, NORDiC naming, indexer metadata, quality, year matching, target folder, and grab safety.

## Design Goal

Make the app look and feel like a polished professional operations product, closer in quality to Seerr/Radarr/Sonarr, but do not copy their layouts directly.

The current UI is too plain. Redesign it completely.

The first viewport must be the real app, not a landing page.

## Product Personality

Use this direction:

- Professional local media operations dashboard.
- Dense but not cluttered.
- Fast to scan.
- Clear priority states.
- Strong visual hierarchy.
- Dark mode first, with light mode support.
- Modern, but not decorative.
- No giant marketing hero.
- No childish graphics.
- No vague gradients as the main design.
- No one-color purple/blue theme.

The user should immediately understand:

- Are services online?
- Are indexers healthy?
- What requests are wanted or failed?
- What did DMM find?
- Which release is best and why?
- Is AltMount importing/downloading?
- What needs manual attention?

## Main Screens To Design

Design this as one responsive single-page app with these work areas.

1. **Command Header**
   - App name.
   - Online/offline service state.
   - Quick actions:
     - Search
     - Sync Seerr
     - Retry wanted
     - Refresh queue
     - Theme toggle

2. **Wanted Board**
   - List movies/TV/seasons/episodes requested from Seerr or DMM.
   - Show status:
     - wanted
     - searching
     - grabbed
     - completed
     - failed
     - upcoming
   - Show poster, title, year, target folder, best score, last checked, and action buttons.
   - Action buttons:
     - Search now
     - Grab best
     - Open details
     - Retry failed

3. **Search / Release Browser**
   - Main search input with media type selector.
   - Filters:
     - Movies / TV
     - minimum quality
     - target folder
     - accepted only
   - Results table/card hybrid:
     - score
     - release title
     - quality
     - source
     - size
     - indexer
     - Danish audio/subtitle signals
     - warnings/rejections
     - grab button
   - Make the best release visually obvious.

4. **Metadata Panel**
   - Poster.
   - Exact title/year.
   - Overview.
   - IDs if available:
     - TMDB
     - TVDB
     - IMDB
   - For TV:
     - seasons
     - episode count
     - requested season/episode scope

5. **Operations / Health**
   - Prowlarr/indexer health.
   - API call/network analyzer summary.
   - AltMount queue/downloads.
   - Import path health.
   - Recent grabs.
   - Recent feed sync runs.

6. **Request Detail Drawer Or Modal**
   - Poster, title, year, request source.
   - Wanted child items for TV seasons/episodes.
   - Best current release and why.
   - Search history.
   - Grab history.
   - Manual actions.

## UX Requirements

- Design all states:
  - loading
  - empty
  - healthy
  - warning
  - failed
  - partial data
  - no poster
  - no indexers available
  - no accepted releases
- On mobile, the app should become a clean stacked workflow:
  - Status
  - Wanted
  - Search
  - Results
  - Health
- On desktop, use a dense multi-column operations layout.
- Buttons should use clear familiar UI patterns.
- Use icons if available, but the implementation may be plain HTML/CSS.
- Cards are allowed for repeated items, not for every section nested inside cards.
- Text must never overflow buttons or panels.

## Technical Constraints

This app currently uses plain static HTML, CSS, and JavaScript. No React/Vue build system is required.

If returning production-ready code, preserve the required IDs listed in `FRONTEND_CONTRACT.md`, because `app/static/app.js` uses those IDs.

If returning a mockup, label the required IDs clearly so the mockup can be wired into the existing JS later.

## Deliverable

Return:

1. A short design explanation.
2. A complete `index.html` body structure.
3. A complete CSS file or CSS sections.
4. Notes about any JavaScript changes needed.
5. Responsive behavior notes.

Do not produce a marketing page. Build the actual DMM application screen.

