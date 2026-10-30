# Lumina Earth — Feature Catalog

**Version:** 0.1.0 | **Status:** Proposed scope inventory

All features below are retained in the intended product vision. Listing a feature does not imply implementation readiness or guaranteed provider availability.

## A. Globe and geographic context

### F01 — Interactive 3D Earth
Render a navigable globe with camera controls, supported imagery, terrain and smooth fly-to transitions. Imagery/terrain coverage and license are provider-dependent.

### F02 — Location search
Resolve place names, addresses, landmarks and coordinates to geographic results. Handle ambiguous results explicitly.

### F03 — Waypoints and personal atlas
Create, rename, tag, annotate, group, revisit and delete saved locations. Persist through Lumina's approved storage mechanism.

### F04 — Global time and day/night
Display local time, time zone, date, sunrise/sunset and a day/night terminator using geographic and time-zone/solar data.

## B. Weather intelligence

### F05 — Current weather and forecasts
Show current conditions and hourly/daily forecasts from a selected provider, with units, timestamps and location.

### F06 — Animated weather layers
Render supported cloud, precipitation, temperature or wind layers. Each layer must declare units, time semantics, source and freshness.

### F07 — Storm tracking and severe-weather alerts
Show available radar/forecast frames and official alert feeds. Clearly separate observations, forecasts and warnings.

### F08 — Spoken weather assistant
Answer weather questions through Lumina's existing conversation and TTS path. Do not invent data when a provider fails.

### F09 — Proactive weather briefings
Optional scheduled summaries or threshold-triggered notifications. Require opt-in, quiet hours, duplicate suppression and user controls.

## C. Street-level exploration

### F10 — Globe-to-Street transition
Enter a supported street panorama near a selected location and preserve geographic context.

### F11 — Voice-controlled Street navigation
Support look/turn commands and move-to-linked-panorama commands. “Forward” means selecting an available linked panorama, not continuous physical movement.

### F12 — Visual road selection
Let the user choose available panorama links or visible navigation controls. The controller must validate that the destination link exists.

### F13 — Street Mode context awareness
Track current panorama identifier, position, heading, pitch and available links. Explain missing coverage/dead ends and return to the globe without losing context.

## D. Travel and terrain

### F14 — Terrain explorer
Display elevation and terrain; optionally profile a line or route when the data source supports it.

### F15 — Journey planner
Show routes, distances and estimated durations from a routing provider. Street imagery along the route is optional and coverage-dependent.

### F16 — Aircraft tracking
Optional aircraft overlay using a licensed/appropriate aviation data source. Show timestamps, coverage and available fields.

### F17 — Satellite tracking
Show propagated satellite positions/orbits using orbital elements and a documented propagation method. Display data epoch and limitations.

### F18 — Personal travel memory
Connect places to notes, planned visits, tasks and reminders using existing Lumina memory/task systems after code inspection.

## E. Scientific and informational layers

### F19 — Space weather and aurora
Display available geomagnetic data and aurora forecasts from appropriate space-weather sources. Avoid guarantees of visibility.

### F20 — Earthquakes and natural hazards
Show recent earthquakes and supported hazard feeds with event time, source, magnitude/severity and data freshness.

### F21 — Historical Earth
Compare historical imagery or dated datasets where licensing and historical coverage permit.

### F22 — Global data layers
Toggle datasets such as population density, land cover, protected areas or other geographic information, with legends and attribution.

### F23 — Ask Lumina about anywhere
Answer contextual questions about a selected location using appropriate sourced knowledge. Dynamic factual claims should have provenance.

### F24 — Guided world tours
Create and replay tours across waypoints, with camera transitions, narration and optional Street Mode stops.

### F25 — Weather-aware route planning
Overlay available forecast information along a route. This is informational assistance, not a safety guarantee.

### F26 — Astronomy and sky context
Calculate or display solar position, twilight and supported celestial information for a location/time.

### F27 — Location-triggered automations
Optional local application rules tied to selected waypoints or opening a location. Must not silently become background GPS tracking.

## Cross-cutting capabilities

- Voice command routing through a typed Earth command interface.
- UI accessibility and equivalent direct controls.
- Cancellation and stale-result protection.
- Provider status, freshness and attribution.
- Persistent preferences and user-controlled notifications.
- Performance telemetry and testable provider adapters.
- Graceful degradation when data or coverage is missing.
