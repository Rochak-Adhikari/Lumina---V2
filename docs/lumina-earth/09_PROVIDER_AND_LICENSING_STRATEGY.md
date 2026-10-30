# Lumina Earth — Provider and Licensing Strategy

**Version:** 0.1.0 | **Status:** Decision framework; not a provider approval

## 1. Principle

Do not choose providers based on a demo alone. Select each provider against the exact feature, target regions, technical integration, display rules, attribution, data retention, quotas and cost.

## 2. Capability matrix to complete in P0

| Capability | Candidate approach | Must validate |
|---|---|---|
| 3D globe renderer | CesiumJS or equivalent | Electron compatibility, packaging, GPU use, lifecycle |
| Base imagery | Provider supported by selected globe; potentially Google Photorealistic 3D Tiles where eligible | Coverage, attribution, display restrictions, API terms and costs |
| Terrain | Globe-compatible terrain provider | Coverage, resolution, offline/cache rules |
| Geocoding/places | Google Maps Platform or alternative | Country coverage, ambiguity, quotas, storage restrictions |
| Street panorama | Google Street View APIs or other licensed panorama provider | Coverage, adjacent links, embedding requirements, attribution, terms |
| Current weather/forecast | Weather API with target-region coverage | Forecast horizon, units, update interval, commercial terms |
| Radar/cloud/wind layers | Provider with suitable tiles or time-indexed data | Timestamp semantics, licensing, latency, animation and tile cost |
| Routing | Routing provider | Modes, traffic/ETA, country coverage, restrictions |
| Aircraft | Appropriate aviation data provider | License, completeness, latency, redistribution |
| Satellites | Public/appropriate orbital elements and propagation library | Epoch, accuracy, update cadence, attribution |
| Earthquakes/hazards | Official or reputable public feeds | Update latency, schema, license and attribution |
| Space weather/aurora | Appropriate scientific feed | Geographic resolution, forecast semantics and disclaimers |
| Historical imagery | Provider/dataset with historical access | Time depth, coverage, redistribution/caching rules |
| Astronomy | Validated local astronomy library and/or data source | Accuracy, time zones, coordinate reference and license |

## 3. Selection criteria

Score each candidate from 1–5:
- Required-region coverage.
- Fit for exact interaction model.
- Data freshness and provenance.
- Terms/caching/attribution clarity.
- Expected usage cost at low, typical and high usage.
- Credential restrictions and security.
- SDK/API stability and documentation.
- Testability and mock support.
- Provider lock-in and export limitations.
- Graceful fallback options.

A provider is not approved until terms and estimated cost are recorded.

## 4. Required P0 outputs

- Provider comparison matrix with source links and review date.
- API/key inventory and restrictions.
- Expected cost scenarios based on anticipated requests/sessions.
- Attribution/display checklist.
- Cache and retention policy.
- Target-region coverage test results, including Nepal and representative international locations.
- Minimal technical spike in the actual Electron app.
- Decision log entry for each selected provider.

## 5. Key management

- Keep secret credentials on the trusted backend where feasible.
- If a provider requires a browser-visible key, use provider-supported restrictions (allowed origins, API allowlists, quota limits) and document that it is a restricted public key, not a secret.
- Never commit keys to source control or put secrets in logs.
- Rotate exposed keys and set budget/quota alerts where available.

## 6. Provider-independent domain layer

Internal data types and domain behavior must not depend on raw provider response objects. Adapters normalize provider data and preserve source, time, attribution and limitations. Provider fallback must not silently change licensing semantics or data meaning.
