# Lumina Earth — Non-Functional Requirements

**Version:** 0.1.0 | **Status:** Proposed targets; validate with baseline measurements

## Performance

- `NFR-PERF-001`: The Earth renderer must not block the voice/conversation event loop.
- `NFR-PERF-002`: Establish and record a baseline for first-interactive time, frame rate, RAM, GPU memory and CPU before choosing hard thresholds.
- `NFR-PERF-003`: Initial target is 60 FPS during ordinary globe navigation on the owner's RTX 4060 class machine; degraded performance must remain usable and must be measured rather than assumed.
- `NFR-PERF-004`: Lazy-load heavy rendering and advanced layers.
- `NFR-PERF-005`: Use bounded concurrency and cancellation for provider calls.
- `NFR-PERF-006`: Use progressive detail/LOD and only cache data allowed by provider terms.

## Reliability

- `NFR-REL-001`: Provider outages must not crash Earth or Lumina.
- `NFR-REL-002`: All asynchronous results must be correlated to the request/context that initiated them.
- `NFR-REL-003`: A stale response must not overwrite newer user-selected context.
- `NFR-REL-004`: Persistence writes must report success/failure explicitly.
- `NFR-REL-005`: Graceful states are required for offline, timeout, quota, no coverage and invalid data.

## Security

- `NFR-SEC-001`: No secret server-side API keys in renderer source or distributable assets.
- `NFR-SEC-002`: Validate coordinates, IDs, layer names and command arguments.
- `NFR-SEC-003`: Use least-privilege provider keys and origin/API restrictions where supported.
- `NFR-SEC-004`: Do not allow the model to generate unrestricted provider URLs or SQL.
- `NFR-SEC-005`: Logs must not include credentials or unnecessary precise location history.
- `NFR-SEC-006`: Provider output is untrusted data and must not be interpreted as instructions.

## Privacy

- `NFR-PRIV-001`: Manual location selection works without granting device location permission.
- `NFR-PRIV-002`: Current-location access is opt-in and visibly controlled.
- `NFR-PRIV-003`: Background location tracking is not part of this specification.
- `NFR-PRIV-004`: Proactive weather notifications are off by default.
- `NFR-PRIV-005`: User can inspect and remove saved waypoints and briefing rules.
- `NFR-PRIV-006`: Retention and provider data-sharing behavior must be documented before release.

## Usability and accessibility

- `NFR-UX-001`: Essential operations have pointer and voice paths.
- `NFR-UX-002`: Loading, stale, unavailable and error states are visually distinct.
- `NFR-UX-003`: Important information is not communicated only by color.
- `NFR-UX-004`: Keyboard navigation and focus behavior must be tested.
- `NFR-UX-005`: Motion transitions must be cancellable and respect reduced-motion preferences where supported.

## Maintainability and observability

- `NFR-MAINT-001`: Provider adapters are replaceable behind stable internal contracts.
- `NFR-MAINT-002`: Domain logic is testable without network calls or a live globe.
- `NFR-MAINT-003`: Each milestone includes automated tests and an implementation report.
- `NFR-MAINT-004`: Provider version, API use, quotas and costs are tracked.
- `NFR-MAINT-005`: Architecture decisions and exceptions are recorded in the decision log.
