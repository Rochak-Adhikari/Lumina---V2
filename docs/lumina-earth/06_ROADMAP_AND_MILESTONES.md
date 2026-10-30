# Lumina Earth — Roadmap and Milestones

**Version:** 0.1.0 | **Status:** Proposed sequencing

The complete 27-feature vision is retained. Milestones control implementation order and acceptance gates; they are not scope deletion.

## P0 — Reconnaissance and provider validation

**Goal:** Resolve repository, provider, licensing, cost and performance unknowns before committing to implementation.

Work:
- Inspect actual repository architecture and identify integration points.
- Validate renderer/library compatibility and packaging.
- Compare globe/imagery options, weather sources, geocoding, Street View, routing and optional tracking feeds.
- Record licensing, attribution, caching, quotas, key restrictions and cost.
- Build a minimal integration spike in an isolated branch or disposable worktree.
- Measure baseline performance alongside Lumina voice operation.

Exit gate:
- Repository integration report reviewed.
- Provider matrix completed for MVP capabilities.
- No unresolved licensing or credential blocker for selected MVP providers.
- ADRs updated and owner approval recorded.

## P1 — Earth foundation

Features: F01–F04, basic portions of F02/F03.

Work:
- Earth workspace lifecycle and globe rendering.
- Camera controls and fly-to.
- Location search and selection.
- Coordinate/local-time panel.
- Waypoint create/list/select/rename/delete and persistence.
- Error states and test seams.

Exit gate:
- Globe usable in packaged Electron app.
- Waypoints survive restart.
- Search ambiguity handled.
- Unit/integration tests pass.
- Voice runtime remains responsive.

## P2 — Weather intelligence

Features: F05, F08, basic F06; weather compare as appropriate.

Work:
- Weather adapter and normalized schemas.
- Current conditions and forecasts.
- Weather UI panel and location binding.
- Voice tool integration and spoken responses.
- Timestamp/freshness, units, stale/error behavior.
- Optional overlay spike.

Exit gate:
- Test fixtures cover success, stale data, timeout, quota and no coverage.
- Spoken answer is generated only from returned data.
- Provider attribution and billing controls reviewed.

## P3 — Street Mode

Features: F10–F13.

Work:
- Panorama adapter and capability checks.
- Globe-to-panorama transition.
- Look/orientation controls.
- Linked-panorama graph movement.
- Voice command sequencing and cancellation.
- Coverage/dead-end handling.

Exit gate:
- Verified movement through a chain of available panoramas.
- “Look” and “move” semantics are distinct.
- No false success on missing links.
- Attribution and provider restrictions pass review.

## P4 — Personal Earth and briefings

Features: F03 enhancements, F09, F18, F24, F27.

Work:
- Collections, notes, visited/planned state.
- Guided tour format and replay.
- Optional weather briefing scheduler.
- Quiet hours, deduplication and disable controls.
- Integration with existing Lumina tasks/memory, without duplicating systems.

Exit gate:
- Preferences persist and can be inspected/deleted.
- Briefings disabled by default.
- Restart and scheduling tests pass.
- No duplicate notifications under retry/restart.

## P5 — Terrain and route planning

Features: F14, F15, F25.

Work:
- Terrain/elevation layer.
- Routing adapter and route visualization.
- Route distance/time with provider attribution.
- Optional forecast sampling along route.
- Street panorama availability at route stops.

Exit gate:
- Route failure and partial coverage states are explicit.
- Estimates are not described as guarantees.
- Route/provider terms reviewed.

## P6 — Scientific and live layers

Features: F16, F17, F19, F20, F22, F26.

Work:
- Select one data feed at a time.
- Normalize timestamps, epochs, units and attribution.
- Add layer registry and legends.
- Test stale feed, missing data and provider quota.
- Separate observed data from propagated/modelled positions.

Exit gate:
- Each layer has source, timestamp semantics, limits and fallback behavior.
- No unsupported “real-time” claims.
- Provider costs and quotas monitored.

## P7 — Advanced exploration

Features: F21, F23 and expansions to F06/F22/F24.

Work:
- Historical imagery comparisons where licensed.
- Location Q&A with grounded sources.
- More data layers, tour narration and advanced visualizations.
- Optional performance/caching improvements.

Exit gate:
- Source provenance and date context visible.
- No feature depends on undocumented provider behavior.
- End-to-end acceptance suite passes.

## Cross-milestone rule

A milestone is not `VERIFIED` until its acceptance criteria have evidence in the implementation report. A coding agent must stop at the assigned milestone and must not start the next milestone automatically.
