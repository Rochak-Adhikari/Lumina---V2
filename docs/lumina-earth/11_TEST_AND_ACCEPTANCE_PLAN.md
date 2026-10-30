# Lumina Earth — Test and Acceptance Plan

**Version:** 0.1.0 | **Status:** Proposed

## 1. Test layers

### Unit tests
- Coordinate validation and normalization.
- Time-zone and solar calculation wrappers.
- Provider response normalization.
- Freshness and stale-data logic.
- Command schema validation.
- Waypoint CRUD and migration logic.
- Briefing threshold, quiet-hour and deduplication logic.
- Street navigation graph selection and step count handling.

### Contract tests
- Provider adapters map success, partial data, malformed response, timeout, quota and no coverage into documented internal results.
- Every result includes the required provenance fields where applicable.
- Unknown provider fields do not break normalization.
- Mock providers satisfy the same internal contract as live providers.

### Integration tests
- Earth workspace loads and closes in Electron.
- Search → select → fly-to updates active context.
- Waypoint create → restart → retrieve preserves data.
- Weather query → UI card and spoken-response payload use the same normalized result.
- Street panorama → linked move → return to globe preserves context.
- Provider failure leaves the app responsive.
- Voice runtime continues during globe rendering and network delays.

### End-to-end tests
- “Show [place]” selects the expected place after ambiguity is resolved.
- “What's the weather there?” uses the current Earth context.
- “Save this as [name]” persists the current point.
- “Enter Street Mode” handles coverage/no-coverage cases.
- “Move forward twice” reports actual completed moves and stops on first failure by default.
- A proactive briefing fires only when enabled and not during quiet hours.

## 2. Required test fixtures

- Valid and invalid coordinates.
- Ambiguous place search.
- No search results.
- Weather current + forecast success.
- Missing optional weather fields.
- Stale weather response.
- Timeout, quota and provider outage.
- Panorama with two forward links, one link, and no links.
- Panorama provider returns missing target.
- Route with partial panorama coverage.
- Time-zone boundary and daylight-saving test cases.
- Briefing duplicate/restart/quiet-hour cases.
- Late provider response after a newer location is selected.

## 3. Performance test

Record hardware, OS, build, renderer resolution, active layers and provider. Measure:
- First interactive render.
- Average and low-percentile FPS during orbit/zoom/fly-to.
- Renderer RAM and GPU memory.
- CPU use.
- Weather response latency.
- Voice interruption latency while Earth is active.
- Performance with no network and with delayed provider responses.

Do not claim a performance target passes without measurements from the actual packaged app.

## 4. Security/privacy tests

- No secret key appears in packaged renderer bundle or logs.
- Location permission denied path remains functional through manual search.
- Proactive notifications remain disabled by default.
- Waypoint deletion and briefing disable/delete work.
- Provider text cannot inject HTML/script.
- Arbitrary URLs and unrecognized command names are rejected.
- Stale responses cannot overwrite current context.

## 5. Milestone acceptance evidence

Every implementation report must include:
1. Commit/hash or diff summary.
2. Files changed.
3. Exact commands run.
4. Test counts and failures.
5. Manual checks and environment.
6. Provider configuration used (never include secrets).
7. Known gaps and deviations.
8. Screenshots/recordings when UI behavior is material.
9. Explicit statement of each acceptance criterion: pass/fail/blocked/not tested.

A task is `VERIFIED` only when evidence supports the claim. “Looks good” is not an acceptance test.
