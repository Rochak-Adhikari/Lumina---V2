# Lumina Earth — Security, Privacy and Safety

**Version:** 0.1.0 | **Status:** Proposed

## 1. Location privacy

- Device/current location is opt-in and must have a visible control/state.
- Manual search and saved waypoint exploration must work without location permission.
- Do not implement continuous background GPS tracking in this project by default.
- Do not store a location trail from routine camera movements.
- User can inspect, edit and delete saved waypoints and briefing rules.
- Explain whether a provider receives coordinates for geocoding/weather/imagery requests.

## 2. Voice and action boundaries

- Voice commands are intent requests, not authorization to bypass provider terms or application permissions.
- Use typed allowlisted commands.
- Validate all coordinates, IDs, counts, durations and layer IDs.
- Ask for clarification if the selected location is ambiguous.
- Require explicit confirmation for destructive bulk operations or external actions that have meaningful consequences.
- Do not claim success until the command result confirms success.
- Provide cancellation and Stop controls for long-running tours/animations/operations.

## 3. Dynamic information

- Weather forecasts are not guarantees.
- Alerts should identify source and issue/valid times.
- Aircraft/satellite positions must show data timestamps and limitations.
- Routing estimates must not be represented as guaranteed arrival times.
- Natural hazard data should preserve source and event time.
- Missing or stale data must be visible and must not be replaced by model guesses.

## 4. API and renderer security

- Keep secrets out of renderer code and source control.
- Restrict provider keys and quotas.
- Validate backend inputs even when the renderer validates them.
- Treat provider output, geocoding results, names and external descriptions as untrusted data.
- Escape content rendered in the UI.
- Do not allow provider responses to trigger arbitrary commands or code.
- Restrict outbound requests to known adapters where the existing architecture supports this.
- Do not let an LLM generate arbitrary network requests, file paths or SQL.

## 5. Proactive notifications

- Disabled by default.
- Require the user to choose a location and briefing type.
- Include schedule/threshold, quiet hours, enable/disable and delete controls.
- Suppress duplicate notifications across retries and restarts.
- Respect local time zones and daylight-saving changes.
- Do not imply that a warning was delivered unless the delivery subsystem confirms it.

## 6. Licensing and attribution

- Do not scrape or bypass access controls.
- Respect provider attribution, caching, storage and display requirements.
- Do not persist provider data beyond permitted terms.
- Do not assume that data being publicly viewable means it can be freely redistributed.
- A provider substitution requires renewed legal/terms review.

## 7. Logging

Log command type, correlation ID, duration, outcome and sanitized error category. Avoid logging credentials, full raw transcripts, or precise location unless required for debugging and explicitly approved. Provide a debug mode with a documented retention policy.
