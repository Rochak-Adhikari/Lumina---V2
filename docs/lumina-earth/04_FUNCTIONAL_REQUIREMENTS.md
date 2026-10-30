# Lumina Earth — Functional Requirements

**Version:** 0.1.0 | **Status:** Proposed

Priority: `MUST` = release-blocking for relevant milestone; `SHOULD` = expected unless justified; `MAY` = optional extension.

## Context and globe

- `FR-001 MUST`: The user can open/close Earth without restarting Lumina.
- `FR-002 MUST`: The globe supports pointer-based rotate, zoom and pan/orbit controls appropriate to the chosen renderer.
- `FR-003 MUST`: A place search returns selectable results with coordinates and labels.
- `FR-004 MUST`: A confirmed selection updates the active Earth context.
- `FR-005 MUST`: Fly-to operations expose completion/failure and can be superseded safely.
- `FR-006 MUST`: The user can return to a default/global view.
- `FR-007 SHOULD`: Current location is available only through an explicit permission path; manual selection remains possible.
- `FR-008 MUST`: Missing imagery or terrain does not crash the workspace.

## Waypoints and persistence

- `FR-009 MUST`: Create a waypoint with a name and valid coordinates.
- `FR-010 MUST`: List, select, rename, update, and delete a waypoint.
- `FR-011 MUST`: Waypoints persist across application restarts.
- `FR-012 SHOULD`: Waypoints support tags, notes and collections.
- `FR-013 MUST`: Destructive deletion follows existing Lumina confirmation conventions where applicable.
- `FR-014 MUST`: Persistence errors are shown and do not produce false success.

## Weather

- `FR-015 MUST`: Retrieve current conditions for a valid coordinate.
- `FR-016 MUST`: Retrieve supported forecast intervals for a valid coordinate.
- `FR-017 MUST`: Normalize units and timestamps.
- `FR-018 MUST`: Show source freshness or stale/unavailable status.
- `FR-019 MUST`: The spoken answer is grounded in a successful weather result.
- `FR-020 MUST`: Provider failure produces an honest failure/partial result, not invented weather.
- `FR-021 SHOULD`: Support weather overlays when the chosen provider offers compatible data.
- `FR-022 SHOULD`: Compare weather for two or more selected/saved locations.
- `FR-023 MUST`: Proactive briefing is disabled by default until explicitly enabled.
- `FR-024 MUST`: Briefing settings include location, schedule/trigger, quiet hours and disable control.
- `FR-025 SHOULD`: Duplicate alert suppression and delivery audit are implemented before proactive alerts ship.

## Street Mode

- `FR-026 MUST`: Enter Street Mode only when a valid panorama is available.
- `FR-027 MUST`: Look commands change orientation without implying geographic movement.
- `FR-028 MUST`: Move-forward/backward commands select a valid linked panorama only.
- `FR-029 MUST`: Unsupported movement returns `coverage_unavailable` or `not_found` with a clear explanation.
- `FR-030 MUST`: UI displays the current panorama/location when available.
- `FR-031 MUST`: Return-to-globe preserves the last useful geographic context.
- `FR-032 SHOULD`: Repeated movement commands execute sequentially and stop on the first failed movement unless the user explicitly requests another policy.
- `FR-033 MUST`: Provider attribution and restrictions are respected.

## Time, tours and routes

- `FR-034 MUST`: Local-time display is based on the selected location's time zone.
- `FR-035 SHOULD`: Show sunrise/sunset and day/night boundary using validated calculations/data.
- `FR-036 SHOULD`: Tours are ordered collections of waypoint/view actions with saved narration metadata.
- `FR-037 SHOULD`: Route estimates clearly identify their provider and are not described as guaranteed.
- `FR-038 SHOULD`: Street Mode along a route is available only where panorama coverage exists.

## Advanced data layers

- `FR-039 MUST`: Every dynamic layer exposes source and time semantics.
- `FR-040 MUST`: Tracking feeds show data epoch/retrieval time and gaps.
- `FR-041 SHOULD`: Earthquake/hazard events include source, event time and severity/magnitude where available.
- `FR-042 SHOULD`: Astronomy/space-weather features state their model/data limitations.
- `FR-043 MUST`: Unsupported provider capability is represented explicitly rather than faked.

## Voice and command execution

- `FR-044 MUST`: Earth commands use typed, validated schemas.
- `FR-045 MUST`: Ambiguous destinations request clarification rather than guessing silently.
- `FR-046 MUST`: Controller results distinguish success, failure, unavailable and cancelled.
- `FR-047 MUST`: Lumina speaks completion only after confirmed success.
- `FR-048 MUST`: Long operations can be cancelled where technically possible.
- `FR-049 SHOULD`: Voice and UI commands produce equivalent results.
