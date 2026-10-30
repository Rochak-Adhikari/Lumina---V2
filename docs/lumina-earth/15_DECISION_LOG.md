# Lumina Earth — Decision Log

**Version:** 0.1.0 | **Status:** Proposed decisions; owner approval required

Use `PROPOSED`, `ACCEPTED`, `REJECTED`, `SUPERSEDED` with date, owner and evidence.

| ID | Decision | Proposed default | Status |
|---|---|---|---|
| D-001 | Earth workspace location | Dedicated workspace inside Electron, not an external browser tab | PROPOSED |
| D-002 | Globe renderer | Evaluate CesiumJS first; validate packaging/performance before adoption | PROPOSED |
| D-003 | Imagery provider | Select only after target-region, licensing, attribution and cost tests | PROPOSED |
| D-004 | Street panorama provider | Evaluate supported Street View API integration and alternatives; no scraping | PROPOSED |
| D-005 | Weather provider | Provider adapter with normalized schema; choose after coverage/cost review | PROPOSED |
| D-006 | Current location | Opt-in only; manual search always available | PROPOSED |
| D-007 | Proactive weather briefings | Off by default; explicit enable and quiet-hour controls | PROPOSED |
| D-008 | Persistent state | Reuse existing Lumina storage and task/memory architecture after inspection | PROPOSED |
| D-009 | Street movement semantics | Traverse provider-linked panoramas; no claim of continuous real-world movement | PROPOSED |
| D-010 | Advanced layers | Feature-flag and lazy-load; each requires source/freshness/attribution | PROPOSED |
| D-011 | Offline globe | Out of MVP; reconsider only with license/storage design | PROPOSED |
| D-012 | Implementation agent | Gemini 3.8 Flash High can implement assigned milestones with evidence-based verification | PROPOSED |
| D-013 | Release policy | Milestone-specific acceptance gate required; no all-at-once implementation | PROPOSED |
| D-014 | Workspace Integration | In-place integration in single-page shell; pause-on-hide WebGL lifecycle | ACCEPTED |
| D-015 | Waypoint Storage | Persistent SQLite table with authenticated REST CRUD API | ACCEPTED |
| D-016 | Atlas UI & Multi-Waypoint Visualization | Slide-out Atlas panel; amber/gold 3D markers with stable ID reconciliation; raycast marker clicks; inline delete confirmation | ACCEPTED |
| D-017 | Local Time & Search History | Native `Intl.DateTimeFormat` local time with managed single timer; SQLite search history in `earth.sqlite3` with 120s duplicate suppression, 100-item cap, and Atlas tab integration | ACCEPTED |

## Decision records

### D-017 — Local Time Intelligence and Persistent Search History Architecture
- **Status:** ACCEPTED
- **Date:** 2026-10-30
- **Owner:** Opus 5.5
- **Context:** P1.6 required accurate local wall-clock time and calendar date display for explored places (supporting IANA timezones, fractional hour offsets, and DST) and durable search history allowing instant location revisits without repeating searches.
- **Options considered:**
  1. Third-party timezone conversion API (e.g. WorldTimeAPI, TimezoneDB). (Rejected: violates $0.00 zero-budget rule, introduces network latency and external points of failure).
  2. Local calculation using native browser `Intl.DateTimeFormat` with IANA timezone strings already authoritative from Open-Meteo geocoding and weather responses. (Accepted: zero network overhead, zero paid APIs, native support for DST and fractional offsets).
  3. Client-side `localStorage` for search history. (Rejected: loses cross-device/server continuity, vulnerable to clearing).
  4. Server-side SQLite persistence in existing `earth.sqlite3` with 120s deduplication and 100-record cap. (Accepted: reliable ACID persistence, shared connection configuration, authenticated endpoints).
- **Decision:** Implemented `createLocalTimeController` in `web/earth/time.js` and `SearchHistoryStore` in `lumina/earth/history.py`. Integrated "Recent Searches" as a tab directly inside the Atlas panel (`web/earth/atlas.js`), with individual item deletion, clear-history confirmation banner, and instant revisit navigation.
- **Consequences/trade-offs:** Zero budget spent ($0.00); native performance; timer automatically pauses on hide/dialog/unmount; seamless history revisit fly-to.
- **Evidence/official sources:** 11/11 Python history store tests, 4/4 history server tests, 9/9 Node.js time tests, 3/3 Node.js history UI tests, 82/82 full Python Earth test suite tests, and 18/18 headless browser CDP tests passing.
- **Review trigger:** Introduction of offline globe or custom layer waypoints in Phase 2.

### D-016 — Atlas UI and Multi-Waypoint Visualization Architecture
- **Status:** ACCEPTED
- **Date:** 2026-10-29
- **Owner:** Opus 5.5
- **Context:** P1.5 required a complete user-facing saved-places experience connected to P1.4 persistent waypoint storage, multi-waypoint 3D globe visualization, selection, editing, and deletion.
- **Options considered:**
  1. Full-screen modal overlay for Atlas. (Rejected: blocks globe exploration).
  2. Integrated slide-out panel inside Earth workspace on right side with dark cinematic styling. (Accepted).
  3. Recreating all 3D markers on every list change. (Rejected: induces WebGL memory leaks and visual flicker).
  4. ID-keyed Map reconciliation (`Map<id, MarkerObj>`) with disposal of removed meshes. (Accepted).
- **Decision:** Built vanilla JS `createAtlasController` and `createAtlasApiClient` with amber/gold Three.js pins for saved places, cyan glow for selection, raycast click detection distinguishing drag from click, and inline delete confirmation.
- **Consequences/trade-offs:** Zero external UI libraries required; 100% zero-budget; strict CSP compliance; completely integrated into Lumina SPA.
- **Evidence/official sources:** All 6 unit tests (`tests/earth_atlas.test.mjs`) and 22/22 browser integration verification tests (`scripts/verify_earth_atlas.mjs`) passing.
- **Review trigger:** Introduction of search history or multi-category filters in P1.6+.

## Decision record template

### D-XXX — Title
- **Status:**
- **Date:**
- **Owner:**
- **Context:**
- **Options considered:**
- **Decision:**
- **Consequences/trade-offs:**
- **Evidence/official sources:**
- **Review trigger:**
