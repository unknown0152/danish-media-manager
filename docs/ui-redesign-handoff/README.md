# DMM UI Redesign Handoff

This folder is a handoff package for asking another AI or designer to make a better Danish Media Manager website without needing access to the live server.

Use these files:

- `PROMPT_FOR_OTHER_AI.md` - paste this into the other AI first.
- `FRONTEND_CONTRACT.md` - technical constraints, API endpoints, required element IDs, and expected workflows.
- `SAMPLE_DATA.md` - realistic sample data shapes for designing populated states, empty states, and failure states.

Goal:

Create a modern, professional web app UI for Danish Media Manager. It should feel closer to Seerr/Radarr/Sonarr quality, but not copy them directly. The app is a local operations dashboard for requests, search, indexer health, AltMount downloads, and Danish/NORDiC release decisions.

Important:

- Do not redesign it as a marketing landing page.
- The first screen must be the usable app.
- Keep it dense, fast, operational, and readable.
- The UI must support movies, TV shows, seasons, episodes, wanted items, upcoming items, failed grabs, indexer diagnostics, and manual search.
- Another AI should return either:
  - a complete replacement `index.html` and `styles.css`, or
  - a standalone HTML/CSS mockup that can be converted into the existing app.

