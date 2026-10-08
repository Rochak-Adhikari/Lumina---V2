# LUMINA Phase One implementation audit

Phase One is implemented in the existing runtime. The work is limited to the five capabilities in the Phase One checklist: file processing, web search, reminders, browser control, and screen processing.

## What was added

The existing tool registry now exposes `process_file`, `web_search`, `reminder`, `browser_control`, and `screen_capture`. Each capability has an independent status report and is started and closed with the LUMINA runtime. A failure in one provider does not prevent the remaining tools or text runtime from starting.

File processing uses provider-neutral inspection, extraction, transformation, and optional online-analysis interfaces. Local extraction is bounded for text, PDF, DOCX, PPTX, CSV, Excel, JSON, images, and ZIP archives. Inputs are resolved through the existing path policy, secret files remain excluded, archive members are validated before extraction, exports are atomic and no-overwrite, and cancellation and size limits are enforced.

Web search returns attributable structured evidence with title, URL, snippet, provider, retrieval time, publication time when available, and an explicit untrusted flag. DuckDuckGo is the zero-cost default; Brave is opt-in through configuration and there is no automatic paid fallback. Public page retrieval and every redirect validate both the URL and the resolved connection addresses, with bounded response size, redirect count, concurrency, and deadlines.

Reminders use one durable local scheduler with UUIDs, timezone-aware due times, atomic persistence, corrupt-state quarantine, restart recovery, one-time delivery, cancellation, inspection, update, snooze, and execution-time policy evaluation. Delivery state is persisted before notification so a restart cannot duplicate a delivered reminder.

Browser control uses a dedicated marked Playwright profile, stable session and tab identifiers, typed operations, DOM snapshots, accessible locator matching, stale-snapshot checks, cancellation cleanup, and confirmation for navigation or page mutations. Downloads, arbitrary subresources, sockets, and silent profile switching are blocked by the provider boundary.

Screen processing is isolated behind a one-shot Windows helper. It supports monitor, window, and region capture, DPI-aware coordinates, source identity, dimensions, timestamps, black-frame detection, stale-window checks, timeouts, cancellation, and immediate resource release. A local capture is never uploaded automatically.

## Configuration and packaging

`requirements-phase1.txt` records the optional local dependencies. The portable build installs those dependencies and attempts to bundle Playwright Chromium into the portable output. Search settings are read with the same environment-over-`.env` precedence as the existing communication providers. The example configuration documents the zero-cost DuckDuckGo default and the explicitly configured Brave option.

## Verification

The Phase One tests pass independently: 74 tests. The complete existing test suite passes: 207 tests. Python compilation passes. A real Playwright Chromium session started, exposed status and tab operations, and closed cleanly.

The file, reminder, registry, cancellation, archive, redirect, policy, and provider-failure checks are covered by local tests using real format parsers and bounded fixtures. No secret values or private file contents are included in test output.

Two live checks remain environment-dependent. The configured DuckDuckGo endpoint returned an authorization or anti-automation response on this machine, so no live source links are claimed; the provider failure was returned as structured status and did not affect LUMINA. A physical screen capture was not bypassed around the existing confirmation boundary; screen capability discovery and the helper's capture, timeout, stale-window, and cleanup paths are covered by tests.

No Phase Two or Phase Three capability was started. Existing filesystem, messaging, camera, worker, voice, server, and security boundaries remain in place.
