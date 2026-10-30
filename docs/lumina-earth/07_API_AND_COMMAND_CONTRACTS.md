# Lumina Earth — API and Command Contracts

**Version:** 0.1.0 | **Status:** Proposed pseudocontracts; adapt to existing project conventions

These are logical contracts, not final language-specific code. Inspect existing schemas, error conventions and tool dispatch before implementing.

## 1. Common result envelope

```json
{
  "ok": true,
  "status": "success",
  "request_id": "opaque-correlation-id",
  "data": {},
  "provenance": {
    "provider": "provider-id",
    "retrieved_at": "ISO-8601 timestamp",
    "observed_at": null,
    "forecast_for": null,
    "stale": false
  },
  "error": null
}
```

Allowed status values should include at least:
- `success`
- `invalid_argument`
- `not_found`
- `coverage_unavailable`
- `provider_error`
- `rate_limited`
- `stale_data`
- `cancelled`
- `internal_error`

Never include secrets in `error`, `data` or logs.

## 2. Proposed command union

- `earth.open`
- `earth.close`
- `earth.fly_to`
- `earth.search_places`
- `earth.select_place`
- `earth.set_layer`
- `earth.reset_view`
- `earth.waypoint.create`
- `earth.waypoint.list`
- `earth.waypoint.update`
- `earth.waypoint.delete`
- `earth.weather.current`
- `earth.weather.forecast`
- `earth.weather.compare`
- `earth.weather.alerts`
- `earth.street.enter`
- `earth.street.look`
- `earth.street.move_linked`
- `earth.street.exit`
- `earth.time.local`
- `earth.sun.times`
- `earth.tour.create`
- `earth.tour.play`
- `earth.route.plan`
- `earth.layer.query`

Only expose commands when their implementation and provider capability exist. Unsupported commands return a structured `not_supported`/`coverage_unavailable` result; they must not be simulated.

## 3. Example input schemas

### Fly to a coordinate

```json
{
  "command": "earth.fly_to",
  "latitude": 27.7172,
  "longitude": 85.324,
  "altitude_m": null,
  "duration_ms": 1200
}
```

Validation:
- Latitude in [-90, 90].
- Longitude in [-180, 180].
- Duration is clamped to a configured safe range.
- Do not accept arbitrary script, URL or provider query parameters.

### Weather query

```json
{
  "command": "earth.weather.current",
  "location": {
    "latitude": 27.7172,
    "longitude": 85.324
  },
  "units": "metric"
}
```

The normalized result must identify the provider, retrieval time, observation time if supplied, units and stale status.

### Street movement

```json
{
  "command": "earth.street.move_linked",
  "direction": "forward",
  "steps": 2,
  "stop_on_failure": true
}
```

Rules:
- Validate `steps` against a small configured maximum.
- Resolve each next panorama from provider-returned links.
- Stop on the first failed step by default.
- Return completed step count and final panorama ID.
- Never claim a requested number of moves completed unless confirmed.

## 4. Provider adapter interfaces

Logical methods:
- `GeocodingProvider.search(query, bias?)`
- `WeatherProvider.get_current(point, units)`
- `WeatherProvider.get_forecast(point, horizon, units)`
- `WeatherProvider.get_alerts(point)`
- `ImageryProvider.get_capabilities(point)`
- `StreetProvider.find_panorama(point)`
- `StreetProvider.get_panorama(id)`
- `StreetProvider.get_links(id)`
- `RoutingProvider.route(origin, destination, options)`
- `TrackingProvider.query(bounds, time_range)`
- `EarthLayerProvider.get_descriptor(layer_id)`
- `EarthLayerProvider.query(layer_id, bounds, time)`

Provider-specific schemas are normalized inside adapters, not in UI components.

## 5. Voice-to-command rules

- Resolve user intent and entities, then call a typed command.
- For “there,” use the active Earth context only when it is unambiguous and recent.
- For “my location,” require location permission and a valid location source; otherwise ask the user to choose a place.
- Ask clarification for ambiguous place names or unclear movement target.
- Keep voice interpretation separate from execution.
- Speak the result returned by execution, not the model's pre-execution expectation.
- Cancellation must propagate through the orchestration path where possible.

## 6. Idempotency and concurrency

- Save/update/delete operations should use stable IDs and predictable retry behavior.
- Assign a correlation ID to each command.
- Superseded searches and camera requests should not update state late.
- Do not retry non-idempotent operations blindly.
- Rate-limit repeated provider requests and respect provider retry guidance.
