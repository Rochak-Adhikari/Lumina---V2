# Lumina Earth — Product Requirements Document

**Version:** 0.1.0 | **Status:** Proposed

## 1. Product vision

Lumina Earth is a persistent, interactive Earth workspace inside Lumina. A user can explore geographic locations, inspect weather, navigate available street-level panoramas, save personal places, ask contextual questions, and operate the experience using natural voice commands.

The product should feel like one coherent capability—not separate map, weather, and Street View applications.

## 2. Problem statement

Today, geographic questions often require the user to switch between map, weather, time, route, and search applications. Lumina Earth aims to keep the location context in one workspace and let Lumina answer or act directly through her existing conversation and speech pipeline.

## 3. Product principles

1. **Voice-first, not voice-only:** every important operation is also inspectable and operable through the UI.
2. **One geographic context:** selected location, coordinates, active layer, panorama and waypoint selection are shared across features.
3. **Evidence-backed answers:** weather, routes, tracking and other dynamic information must include provenance/freshness internally and should expose timestamps where meaningful.
4. **Honest execution:** Lumina must not claim a camera move, panorama move, save, refresh or notification succeeded unless the responsible service confirms it.
5. **Provider isolation:** map, weather, geocoding, routing and tracking providers are adapters, not embedded business logic.
6. **Progressive capability:** the full vision remains on the roadmap; milestones have fixed acceptance gates.
7. **Privacy by default:** location access and proactive reports are explicit opt-ins with visible controls.
8. **Reuse Lumina:** integrate with existing DI, events, tool/skill execution, TTS, state and memory after repository inspection. Do not introduce duplicate frameworks without a documented reason.

## 4. Target users and jobs

Primary user: the Lumina owner using a Windows-first Electron desktop.

Jobs:
- “Show me this place.”
- “What's the weather there?”
- “Compare the local times.”
- “Save this as a waypoint.”
- “Enter Street Mode and move forward.”
- “Take me on a tour of these places.”
- “Show the route and relevant forecast.”
- “Tell me what this selected place is known for.”

## 5. Product outcomes

- A user can find a place and see it on a 3D globe.
- Current weather and forecasts are rendered and spoken from provider results.
- A user can save and reopen named waypoints.
- Street Mode supports orientation changes and movement only along available panorama links.
- Earth commands are deterministic, typed, cancellable where appropriate, and testable without a live provider.
- Dynamic data has clear loading, unavailable, stale and error states.
- Earth does not materially stall Lumina's conversational/voice runtime under the agreed performance budget.

## 6. Scope

### Included in the intended product vision

The 27 features in `02_FEATURE_CATALOG.md`: globe and search; waypoints; time/day-night; weather and forecasts; weather layers and alerts; spoken/proactive briefings; Street Mode; terrain; routes; aircraft/satellite tracking; personal travel memory; space weather; earthquakes/hazards; historical Earth; data layers; contextual place Q&A; guided tours; weather-aware routing; astronomy; location-triggered automations.

### MVP scope

MVP is deliberately narrower:
- 3D globe and basic camera navigation.
- Location search and selection.
- Coordinates, local time and location information.
- Named persistent waypoints.
- Current weather and forecast.
- Voice commands for location, weather and waypoint operations.
- Instrumentation, failure states, test seams and provider abstraction.

### Non-goals for MVP

- Building a proprietary global imagery or weather-data pipeline.
- Guaranteeing universal 3D city coverage or Street View coverage.
- Real-time video of streets or free movement through unobserved space.
- Turn-by-turn navigation as a safety-critical navigation product.
- Autonomous physical-world actions.
- Offline storage of a full detailed Earth.
- Predicting weather independently of authoritative providers.
- Presenting public tracking feeds as complete or perfectly real-time.

## 7. Product constraints

- Provider terms, attribution, caching restrictions, quotas and cost must be validated before implementation.
- Geographic coverage varies by region.
- API credentials must not be embedded in renderer bundles when they are secret credentials.
- The renderer must remain responsive when remote data is slow or unavailable.
- User-facing claims must match the actual semantics of the underlying data.

## 8. Success metrics

Capture a baseline before setting final numeric targets:
- Globe first-interactive time.
- Frame rate during common navigation.
- Renderer and GPU memory.
- Weather response latency and error rate.
- Earth command success/failure classification.
- Waypoint persistence across application restarts.
- Percentage of dynamic answers with valid freshness/provenance metadata.
- Voice interruption/cancellation responsiveness.
- Provider API usage and cost per active session.

## 9. Release criteria

A release cannot be called complete merely because the UI renders. It must pass the milestone-specific acceptance tests, use approved provider configurations, preserve existing Lumina behavior, and document known limitations.
