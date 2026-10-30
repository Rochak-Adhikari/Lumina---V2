# Lumina Earth — Data Model

**Version:** 0.1.0 | **Status:** Proposed logical model

Inspect Lumina's current state and database architecture before choosing actual tables/files. Reuse existing infrastructure when appropriate.

## 1. GeoPoint

- `latitude`: required decimal in [-90, 90]
- `longitude`: required decimal in [-180, 180]
- `altitude_m`: optional
- Coordinates should be normalized consistently and never confused with screen pixels.

## 2. Waypoint

- `id`: stable opaque ID
- `name`: required non-empty display name
- `point`: GeoPoint
- `provider_place_id`: optional provider-specific reference
- `notes`: optional
- `tags`: optional list
- `collection_id`: optional
- `created_at`, `updated_at`: timestamps
- `visited_at`: optional
- `source`: user-created/imported/system-suggested
- `metadata`: allowlisted structured fields only

Avoid storing a complete provider response unless there is a documented need and it complies with provider terms.

## 3. EarthContext (ephemeral unless user saves it)

- `selected_place_id`: optional
- `selected_point`: optional
- `view_mode`: `globe | street`
- `active_layer_ids`: list
- `camera_state`: renderer-neutral snapshot where practical
- `panorama_id`: optional
- `heading_deg`, `pitch_deg`: optional
- `context_updated_at`: timestamp

Persist only a small, useful last-view snapshot if the user experience requires it. Do not turn transient exploration into permanent location history by default.

## 4. DataProvenance

- `provider_id`
- `retrieved_at`
- `observed_at`: optional
- `forecast_for`: optional
- `data_epoch`: optional (e.g., propagated tracking data)
- `expires_at`: optional
- `stale`: boolean
- `attribution_text` or approved attribution reference
- `limitations`: optional list

## 5. WeatherSnapshot (normalized)

- `point`
- `temperature`
- `feels_like`: optional
- `humidity_pct`: optional
- `wind_speed` and `wind_unit`
- `visibility`: optional
- `precipitation`: optional
- `condition_code` and localized description
- `observed_at`
- `provenance`

Use explicit units. Never silently mix Celsius/Fahrenheit or different wind units.

## 6. SavedTour

- `id`, `name`, `created_at`, `updated_at`
- `stops`: ordered list of waypoint references or validated coordinates
- `narration_mode`: off/on/ask
- `created_by`: user
- optional per-stop duration/transition metadata

A tour should remain usable if a panorama becomes unavailable; the UI should skip, replace only with user consent, or stop according to a documented policy.

## 7. BriefingRule

- `id`
- `enabled`: default false
- `location_ref`: waypoint or explicitly configured location
- `kind`: morning_summary / threshold_alert / severe_alert
- `schedule` or threshold configuration
- `quiet_hours`
- `last_evaluated_at`
- `last_sent_event_key`
- `created_at`, `updated_at`

Do not store provider credentials or unnecessary precise live-location history here.

## 8. LayerDescriptor

- `id`, `label`, `category`
- `provider_id`
- `units` and legend definition
- `temporal_mode`: static / current / forecast / historical / propagated
- `available_time_range`
- `attribution`
- `coverage/capability metadata`
- `cache policy`
- `enabled_by_default`: false for expensive/advanced layers

## 9. Retention and migrations

- Persist user-created waypoints and preferences until the user deletes them.
- Dynamic provider data cache TTL must follow provider terms and freshness requirements.
- Keep schema migrations reversible where practical.
- Do not persist raw voice transcripts or location histories solely for Earth unless an explicit product requirement and privacy review approve it.
