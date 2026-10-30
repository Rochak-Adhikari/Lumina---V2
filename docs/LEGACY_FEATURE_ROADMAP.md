# LUMINA legacy feature integration roadmap

This roadmap divides the fifteen audited capabilities into three phases of five. The order is based on user value, dependency risk, and how safely each feature can be integrated into the current runtime. Checked items have implementation and recorded test evidence. Unchecked items are deliberately not claimed complete; see the qualification immediately below each one.

The current LUMINA runtime remains authoritative for tools, permissions, confirmations, paths, tasks, provider access, and UI state throughout all three phases.

## Current status — 10 October 2026

The remaining Phase 3 services and native Windows input are implemented in the existing runtime. See ROADMAP_UPGRADE.md for exact behavior, tests, configuration, and limitations. These legacy roadmap phases are separate from the Cloud Core phases. No cloud deployment was performed. Earlier live evidence remains identified as earlier evidence; it is not a fresh hardware/provider test.

## Priority order

| Priority | Capability | Phase | Reason |
|---:|---|---:|---|
| 1 | File processor | 1 | Largest practical capability gain; establishes reusable artifact and background-job patterns |
| 2 | Web search | 1 | Adds missing general search and evidence provenance; also supports monitors and YouTube discovery |
| 3 | Reminder | 1 | Provides durable user-requested scheduling and supplies infrastructure later monitoring can reuse |
| 4 | Browser control | 1 | High-value interaction capability, isolated behind supervised sessions and current policy |
| 5 | Screen processor | 1 | Adds explicit visual context while preserving the superior current camera helper |
| 6 | Background monitor | 2 | Depends on durable scheduling, structured search results, and deduplication |
| 7 | Computer settings | 2 | Useful typed Windows controls with read-back and consequence-aware confirmation |
| 8 | Computer control | 2 | Broad and risk-sensitive; should build on Windows UI Automation before visual coordinates |
| 9 | YouTube video | 2 | Composes search, browser opening, transcript handling, file artifacts, and reasoning |
| 10 | Proactive | 2 | Should consume real task/reminder/monitor events after those event sources are reliable |
| 11 | Plugins | 3 | Extension interfaces should stabilize before third-party code is allowed to depend on them |
| 12 | File controller | 3 | Current implementation is stronger; add transactional editing and durable undo only |
| 13 | Desktop.py | 3 | Port only explicit wallpaper/organization conveniences; reject generated Python execution |
| 14 | Open app | 3 | Current discovery already wins; remaining work is refinement and launch verification |
| 15 | Send message | 3 | Current official adapters already win; remaining work is recipient resolution and delivery evidence |

## Phase 1 — Core useful capabilities

Goal: add the highest-value missing capabilities while establishing safe patterns for artifacts, durable work, provider evidence, and cancellation.

### 1. File processor

- [x] Define provider-neutral processor interfaces for inspection, extraction, transformation, and optional online analysis.
- [x] Integrate every input and output with the current path resolver and secret-file exclusions.
- [x] Implement bounded local extraction for text, PDF, DOCX, PPTX, CSV, Excel, JSON, and image metadata.
- [x] Separate read-only processing from conversions, writes, uploads, and code execution.
- [x] Write generated files atomically and refuse silent overwrite.
- [x] Add cancellation, size limits, timeouts, page/sheet/slide limits, and structured truncation metadata.
- [x] Validate archive members, links, total expanded size, file count, and destination paths before extraction.
- [x] Keep code execution in the existing supervised coding or shell system rather than the file processor.
- [x] Add unit tests for malformed, oversized, encrypted, hostile, and cancelled inputs.
- [x] Run live acceptance with one real file of each initially supported format.

Acceptance gate: a file is never read, changed, extracted, uploaded, or overwritten outside the current path and permission policy; reported output files exist and pass format validation.

### 2. Web search

- [x] Define structured search results with title, URL, snippet, provider, retrieval time, and publication time when known.
- [x] Add a configured search provider without making it a hard dependency.
- [x] Preserve source provenance when providers fail or fall back.
- [x] Keep retrieval and answer synthesis separate.
- [x] Revalidate every redirect in the existing page reader against local/private destination rules.
- [x] Bound result count, response size, retries, concurrency, and overall deadline.
- [x] Treat all search/page content as untrusted evidence.
- [x] Add tests for empty results, malformed responses, rate limits, cancellation, and provider failure.
- [x] Add redirect tests covering loopback, private IPs, link-local addresses, and excessive redirects.
- [x] Verify live search results include usable source links without exposing provider credentials.

Acceptance gate: search returns structured, attributable evidence; a provider failure leaves LUMINA operational; redirect handling cannot silently reach a prohibited local destination.

### 3. Reminder

- [x] Choose one scheduler authority and adapt the legacy persistent job model into the current runtime.
- [x] Use UUIDs rather than timestamp-derived task names.
- [x] Store timezone-aware due times and the user's configured timezone.
- [x] Add create, list, inspect, snooze, update, and cancel operations.
- [x] Support one-time reminders first; add recurrence only after one-time recovery is proven.
- [x] Persist jobs atomically and quarantine corrupt state.
- [x] Re-evaluate the current permission policy when a scheduled action becomes due.
- [x] Interpret structured tool failures as failures rather than successful function returns.
- [x] Define missed-run, restart-recovery, retry, and duplicate-delivery behavior.
- [x] Test restart recovery, simultaneous reminders, timezone behavior, revoked permission, and notification failure.

Acceptance gate: a reminder survives a LUMINA restart, fires once at the expected local time, can be cancelled, and does not turn stored confirmation state into permanent authority.

### 4. Browser control

- [x] Introduce a browser provider behind the current tool registry.
- [x] Use an explicitly identified automation profile or supported attached session.
- [x] Expose stable browser session and tab IDs.
- [x] Implement navigation, inspect page, click, type, tabs, and screenshots as typed operations.
- [x] Prefer accessible role/name/label locators and return candidates for ambiguous matches.
- [x] Associate mutations with a recent page snapshot and recheck URL/page identity before acting.
- [x] Cancel or invalidate timed-out operations so they cannot execute late.
- [ ] Route submissions, purchases, messages, uploads, and other external commits through current policy.
      The supervised browser still blocks external commits; official messaging tools use exact confirmation. Enabling general browser commits needs a separate reviewed transaction design, not removal of its network guard.
- [ ] Restrict downloads/uploads to validated filesystem locations.
      Browser uploads/downloads remain disabled, rather than being claimed implemented with validated destinations.
- [x] Test profile contention, ambiguous controls, delayed startup, cancellation, and unexpected navigation.

Acceptance gate: one real supervised browser process can be opened, observed, controlled, cancelled, and closed without silent profile switching or unconfirmed external submission.

### 5. Screen processor

- [x] Preserve the current external Windows camera helper unchanged unless a proven defect requires a focused fix.
- [x] Add a separate provider-neutral screen capture interface.
- [x] Support explicit monitor, window, and region capture.
- [x] Return capture dimensions, source identity, and timestamp.
- [x] Release capture resources immediately after each request.
- [x] Keep local capture separate from sending an image to an online vision provider.
- [x] Show a clear capture state in the UI and never enable continuous hidden capture.
- [x] Add DPI-aware multi-monitor coordinate handling.
- [x] Handle black/protected frames, stale windows, timeout, and cancellation without blocking LUMINA.
- [x] Test capture cleanup and verify temporary images are not retained unintentionally.

Acceptance gate: LUMINA can capture one requested screen image and clean up immediately; no capture is uploaded merely because it exists locally.

### Phase 1 completion checklist

- [x] All five capabilities are registered through the existing tool registry.
- [x] No legacy in-process generated Python execution is imported.
- [x] Existing filesystem, messaging, camera, worker, and voice tests still pass.
- [x] New capability tests pass independently and as one integrated suite.
- [x] Capability status accurately distinguishes configured, unavailable, failed, and ready.
- [x] Portable build contains required local dependencies or reports their absence clearly.
- [x] Live acceptance evidence is recorded without credentials or private content.

## Phase 2 — Automation and situational intelligence

Goal: use Phase 1's scheduler, evidence, browser, and capture foundations to add controlled automation and useful event-driven intelligence.

### 6. Background monitor

- [x] Store user-created watches with UUID, query, provider, interval, status, and notification preference.
- [x] Use Phase 1 structured search rather than parsing formatted prose.
- [x] Establish a quiet baseline when a watch is created.
- [x] Fingerprint multiple canonical results rather than only the first headline.
- [x] Distinguish no change, no results, provider failure, and material change.
- [x] Add bounded retry/backoff and restart-safe deduplication.
- [x] Queue alerts when voice is busy and aggregate related changes.
- [x] Include source evidence in alert history.
- [x] Add list, inspect, pause, resume, and remove operations.
- [x] Test result reordering, offline recovery, duplicate stories, and quiet-time behavior.

Acceptance gate: only explicitly requested watches run; the same event is not repeatedly announced after restart; source evidence explains every alert.

### 7. Computer settings

- [x] Define typed Windows providers for audio endpoints, brightness, windows, and selected system settings.
- [x] Preserve the current microphone and speaker selection implementation.
- [x] Implement get-before-set and read-back verification where Windows supports it.
- [x] Address a specific device, monitor, or window rather than an implicit global target where possible.
- [x] Separate native settings operations from keyboard shortcuts.
- [x] Record target identity and exact previous values for undo.
- [x] Reject stale undo if the state changed independently.
- [x] Keep restart, shutdown, connectivity loss, and other consequential actions behind current confirmation.
- [x] Report unsupported monitor/device operations honestly.
- [ ] Test missing devices, disconnected endpoints, unsupported brightness, and cancelled power actions.
      Device/brightness cases pass. Power actions are not implemented, so cancellation of power actions is not claimed.

Acceptance gate: every reported setting change is either verified or explicitly marked unverified; existing web audio settings continue working.

### 8. Computer control

- [x] Build a Windows UI Automation helper/provider as the primary interaction path.
- [x] Enumerate semantic controls, properties, windows, and supported control patterns.
- [x] Use visual targeting only as a bounded fallback.
- [x] Include monitor, window, DPI, capture time, and bounds in visual target results.
- [x] Recheck foreground window and target state immediately before mutation.
- [x] Serialize input operations and stop promptly on user takeover.
- [x] Prevent logging of typed private content and clipboard data.
- [x] Never generate fake personal data when requested information is unavailable.
- [x] Return observed state changes instead of treating a click as success.
- [ ] Test multiple monitors, focus changes, modal dialogs, ambiguity, DPI scaling, and interruption.
      Contract tests cover identity, coordinates, focus and interruption; a disposable native fixture passes. Physical multiple-monitor/DPI and every modal application combination still need hands-on acceptance.

Acceptance gate: LUMINA can inspect and invoke a named control in a real Windows app while refusing ambiguous or stale targets.

### 9. YouTube video

- [x] Expose search, metadata, open, transcript, and summarize as separate operations.
- [x] Use Phase 1 search/browser providers instead of fragile direct HTML regex where possible.
- [x] Validate exact YouTube hosts and video IDs.
- [x] Return transcript language, generation source, and timestamps when available.
- [x] Report unavailable captions and access limitations accurately.
- [x] Summarize long transcripts in bounded sections rather than truncating only the end.
- [x] Preserve links to relevant timestamps in summaries.
- [x] Make saving/opening a summary explicit.
- [x] Use atomic no-overwrite artifact handling from the file processor.
- [x] Test spoofed domains, Shorts, private videos, disabled captions, long videos, and non-English transcripts.

Acceptance gate: YouTube operations fail honestly when captions are unavailable and never describe scraped or inferred metadata as authoritative API data.

### 10. Proactive

- [x] Limit initial proactivity to real task, reminder, monitor, worker, and provider events.
- [x] Require explicit opt-in and expose a master disable control.
- [x] Add quiet hours, cooldown, snooze, and active-conversation suppression.
- [x] Persist event delivery IDs to avoid repeat announcements after restart.
- [x] Aggregate multiple low-priority events into one concise notification.
- [x] Use minimal event context rather than broad personal memory.
- [x] Disable action tools during notification phrasing.
- [x] Never start agents, investigations, monitors, or reminders proactively.
- [x] Allow read/dismiss inspection from the UI.
- [x] Test provider failure, restart duplication, active speech, quiet hours, and unauthorized-action attempts.

Acceptance gate: proactive output is attributable to a real configured event, concise, non-duplicated, and incapable of initiating unrelated work.

### Phase 2 completion checklist

- [x] Every automation is observable and stoppable.
- [x] UI Automation is primary; raw coordinate actions are the exception.
- [x] No fake data or decorative values are reported as system state.
- [x] Scheduled/background operations survive restart without duplicate notifications.
- [x] Confirmation behavior is based on consequence, not which adapter performed the action.
- [x] Phase 1 regression and Phase 2 integration suites pass.
- [x] Live tests cover at least one real monitor, settings change with restoration, UI control, YouTube transcript, and event notification.

## Phase 3 — Extensibility and refinement

Goal: stabilize extensions and close smaller capability gaps without replacing current implementations that are already superior.

### 11. Plugins

- [x] Define an inert manifest containing ID, version, compatibility, capabilities, configuration, permissions, and entry point.
- [x] Discover metadata without importing or executing plugin code.
- [x] Require explicit install and enable states.
- [x] Reject core tool collisions and incompatible runtime versions.
- [x] Validate complete input and output schemas.
- [x] Run enabled plugin work through a supervised process boundary with timeout and cancellation.
- [x] Broker only declared capabilities; do not hand plugins unrestricted credentials or runtime objects.
      Returned proposals are constrained and inert. Explicitly trusted Python is not sandboxed and retains the account’s OS permissions; this is disclosed before approval.
- [x] Expose plugin health, errors, version, and disable/uninstall operations.
- [x] Make clear that process separation is crash isolation, not a complete security sandbox.
- [x] Test disabled import behavior, crashes, hangs, malformed output, collision, upgrade, and uninstall.

Acceptance gate: a disabled or invalid plugin cannot execute; a crashing plugin cannot bring down LUMINA; plugin side effects still obey current policy.

### 12. File controller

- [x] Keep current multi-root validation, no-overwrite behavior, fingerprint confirmations, and Recycle Bin deletion.
- [x] Add bounded create-text-file support.
- [x] Add edit/append with expected original hash/version.
- [x] Write edits atomically and preserve a recoverable revision.
- [x] Add durable operation IDs and a bounded operation journal.
- [x] Implement undo only when the current target still matches the recorded operation output.
- [x] Add bounded largest-files and disk-usage inspection with incomplete-scan reporting.
- [x] Add organization preview and apply it through existing move validation.
- [x] Resolve redirected Windows Known Folders.
- [x] Test multiple drives, ADS, junctions, stale approval, destination races, partial copies, and stale undo.

Acceptance gate: current filesystem guarantees remain intact, and new editing/undo functions never silently overwrite a changed target.

### 13. Desktop.py conveniences

- [x] Reject the legacy generated-Python execution path permanently.
- [x] Add validated wallpaper inspection/set/restore as explicit operations if desired.
- [x] Resolve the real Windows Desktop Known Folder, including redirection.
- [x] Produce exact organization/archive previews with collision reporting.
- [x] Apply approved plans through current file operations.
- [x] Journal each moved item for recoverability.
- [x] Refuse deletion under the label “cleanup.”
- [x] Handle locked files and partial failures without claiming full completion.
- [x] Expose real counts and paths in the UI.
- [x] Test OneDrive Desktop, naming collisions, changed files, cancellation, and partial restore.
      Redirected OneDrive folders use a test provider; actual Windows Known Folder metadata is also queried. This does not claim a live OneDrive account migration.

Acceptance gate: every desktop mutation is an explicit typed operation with a reviewable target; no model-written code is executed.

### 14. Open app refinements

- [x] Keep current PATH, App Paths, Start Menu, and packaged-app discovery.
- [x] Add curated aliases as matching hints, never silent substitutions.
- [x] Improve product deduplication and publisher/source metadata where available.
- [x] Resolve Windows Known Folders and stable executable identities.
- [x] Add bounded visible-window readiness checks where supported.
- [x] Distinguish launch requested, process started, already running, and visible window observed.
- [x] Support safe script/shim discovery only with preserved argument boundaries.
- [x] Preserve the prohibition against bypassing supervised agent launch.
- [x] Return candidates for ambiguity rather than choosing the first fuzzy match.
- [x] Test packaged apps, shortcuts, PATH shims, duplicate products, and apps without windows.

Acceptance gate: LUMINA never reports “opened” solely because it typed a name and pressed Enter; ambiguous applications require a resolved identity.

### 15. Send message refinements

- [x] Keep official Telegram, Discord, WhatsApp, and read-only Gmail adapters.
- [x] Preserve exact-message confirmation in the runtime layer.
- [x] Add provider-specific human-readable destination resolution where APIs permit it.
- [x] Display exact provider, destination identity, and content before confirmation.
- [x] Store provider receipt/message IDs after verified success.
- [x] Distinguish sent, failed, and unknown outcome.
- [x] Never retry an unknown-outcome send automatically.
- [x] Improve provider status and permission diagnostics without exposing secrets.
- [x] Keep Gmail unable to send while the active requirement remains read-only.
- [x] Test expired credentials, inaccessible destinations, rate limits, duplicate prevention, and redaction.

Acceptance gate: no external message leaves the machine without exact user confirmation, and success is supported by a provider response rather than keyboard timing.

### Phase 3 completion checklist

- [x] Plugin interfaces match the stabilized runtime rather than creating a parallel tool system.
- [x] Existing superior implementations remain authoritative.
- [x] No focus-dependent UI messaging is introduced.
- [x] No generated Python execution is introduced.
- [x] No hard-coded application list replaces discovery.
- [x] Full regression, portable build, restart, and failure-isolation tests pass.
      Final suite: 1,398 passed, two explicitly skipped platform/optional-dependency checks; one additional private-review browser test passed. The final portable passed local capability checks and relocated WebView2 startup/reuse/conflict/shutdown acceptance. See ROADMAP_UPGRADE.md for evidence and the remaining live-service/hardware limits.
- [x] Documentation clearly distinguishes installed capabilities from optional adapters and configuration requirements.

## Starting checklist

Historical starting slice: File Processor, local read-only extraction. This slice has been superseded by the delivered Phase 1–3 work. It establishes the artifact, background execution, cancellation, format-detection, limits, and structured-result conventions needed by later capabilities.

- [x] Record the current full test baseline before editing.
- [x] Inventory available document-processing dependencies in the development and portable runtimes.
- [x] Define the processor interface and structured result schema.
- [x] Implement current-path validation and secret exclusions at the processor boundary.
- [x] Add bounded TXT/Markdown and PDF extraction first.
- [x] Add DOCX and PPTX extraction.
- [x] Add CSV/Excel metadata and statistics without mutation.
- [x] Add JSON validation and image metadata.
- [x] Add cancellation, time, file-size, and output-size budgets.
- [x] Add tests for every supported type and failure category.
- [x] Integrate capability status and the current tool registry.
- [x] Run the focused suite, then the full current suite.
- [x] Perform live acceptance on copies of representative non-sensitive files.
- [ ] Stop the first slice before conversions, archive extraction, online upload, media transcoding, or code execution.
      Historical first-slice stopping point, not a current acceptance gate. Later approved phases added bounded transformation/archive/analysis tools; generated-code execution remains excluded.

Definition of done for the starting slice: LUMINA can inspect and extract useful content from supported local files without modifying them, leaving its configured scope, uploading them, blocking the runtime, or misreporting truncated/failed processing as complete.
