# Lumina Earth — System Architecture

**Version:** 0.1.0 | **Status:** Proposed; validate against repository before coding

## 1. Architectural intent

Build a modular geographic subsystem that reuses Lumina's existing Electron frontend, backend, dependency injection, event system, skill/tool execution, voice/TTS and persistence conventions where appropriate. The names below are logical responsibilities, not a mandate to duplicate existing modules.

## 2. Logical components

### Earth Workspace (renderer)
Responsibilities:
- Render globe, camera controls, layers, waypoint markers, panels and Street Mode.
- Present loading, stale, unavailable and error states.
- Emit user intent through a narrow command interface.
- Never own secret provider credentials.

### EarthController
Responsibilities:
- Validate and execute typed Earth actions.
- Maintain a coherent active geographic context.
- Apply cancellation and request supersession.
- Return structured outcomes.
- Never report success before the underlying operation confirms it.

### Globe Engine Adapter
Responsibilities:
- Wrap CesiumJS or the approved renderer.
- Provide camera, layer, entity and terrain operations.
- Isolate renderer-specific APIs from application/domain logic.

### Location Service
Responsibilities:
- Geocode and search places.
- Normalize coordinates and place identifiers.
- Resolve time-zone/location metadata when supported.

### Weather Service
Responsibilities:
- Fetch current conditions, forecasts, alerts and supported overlay metadata.
- Normalize provider responses into internal schemas.
- Preserve timestamps, units, source and stale/error semantics.

### Street View Adapter
Responsibilities:
- Resolve panoramas, orientation and supported adjacent links.
- Expose provider-neutral movement operations.
- Enforce provider restrictions and attribution.

### Routing and Data-Layer Adapters
Responsibilities:
- Route calculations, terrain data, tracking feeds and scientific overlays.
- Each integration has a capability declaration and explicit provider limits.

### Earth State Repository
Responsibilities:
- Persist waypoints, preferences, saved tours and optional briefing rules.
- Reuse existing Lumina storage where possible.
- Avoid duplicating the memory engine for structured Earth data.

### Voice/Skill Integration
Responsibilities:
- Map utterances to Earth command intents.
- Require clarification for ambiguous targets.
- Pass validated arguments to EarthController.
- Speak results returned by the controller and services.

## 3. Data flow

1. User speaks or interacts with Earth Workspace.
2. Existing Lumina conversation/tool layer resolves a command and arguments.
3. EarthController validates the request and current context.
4. Relevant service/provider adapter performs the operation.
5. Controller receives a typed result, updates shared state and emits an event if needed.
6. UI renders the result; voice layer speaks only confirmed outcomes.
7. Persistent changes go through the approved state repository.

## 4. Proposed boundaries

- UI state is not the source of truth for saved waypoints.
- Provider response schemas do not leak directly into UI components.
- The model does not construct arbitrary URLs, raw SQL or unvalidated provider requests.
- Each provider adapter can be replaced without rewriting domain logic.
- Weather and tracking data are time-bound; cache policy is provider-specific.
- Long-running operations support cancellation where practical.
- One active context should identify selected coordinates/place, current view mode, active layer and optional panorama ID.

## 5. Suggested domain types

- `GeoPoint`: latitude, longitude, optional altitude.
- `PlaceReference`: stable internal ID, display name, coordinate and provider reference.
- `EarthContext`: selected place/coordinate, view mode, camera state, active layer, optional panorama state.
- `EarthCommand`: discriminated command union with validated arguments.
- `EarthResult`: success/failure/cancelled/unavailable result with typed data and diagnostics.
- `DataProvenance`: provider/source, retrieval time, observation/forecast time, expiry/freshness status.
- `LayerDescriptor`: ID, category, units, source, attribution, supported time range and capabilities.

## 6. Events

Proposed semantic events (map to existing bus conventions after inspection):
- `earth.context.changed`
- `earth.command.started`
- `earth.command.completed`
- `earth.command.failed`
- `earth.layer.changed`
- `earth.waypoint.created|updated|deleted`
- `earth.weather.updated`
- `earth.street.panorama.changed`
- `earth.briefing.due`

Events must carry stable IDs and typed payloads. Do not broadcast secrets or unnecessary precise location data.

## 7. Error and concurrency model

- Assign each request a correlation ID.
- New search/camera requests may supersede older requests of the same category.
- Cancel or ignore late results when they no longer match the active context.
- Distinguish `invalid_argument`, `not_found`, `coverage_unavailable`, `provider_error`, `rate_limited`, `stale_data`, `cancelled` and `internal_error`.
- Never silently substitute a different location or provider result.
- Keep provider retries bounded and respect retry-after/quota signals.

## 8. Repository integration gate

Before implementation, document:
- Actual renderer framework and route/view conventions.
- Existing backend API patterns and auth boundaries.
- DI registration and lifecycle conventions.
- Event bus semantics and naming.
- Existing tool/skill schema and result conventions.
- Existing persistence and migrations.
- Existing logging/telemetry/test commands.
- Conflicts or duplication with current modules.

No broad refactor is authorized by this specification alone.
