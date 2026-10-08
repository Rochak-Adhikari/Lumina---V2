# LUMINA legacy feature integration roadmap

This roadmap divides the fifteen audited capabilities into three phases of five. The order is based on user value, dependency risk, and how safely each feature can be integrated into the current runtime. A checkbox means implementation and verification are still required; it does not imply the legacy module should be copied unchanged.

The current LUMINA runtime remains authoritative for tools, permissions, confirmations, paths, tasks, provider access, and UI state throughout all three phases.

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

- [ ] Define provider-neutral processor interfaces for inspection, extraction, transformation, and optional online analysis.
- [ ] Integrate every input and output with the current path resolver and secret-file exclusions.
- [ ] Implement bounded local extraction for text, PDF, DOCX, PPTX, CSV, Excel, JSON, and image metadata.
- [ ] Separate read-only processing from conversions, writes, uploads, and code execution.
- [ ] Write generated files atomically and refuse silent overwrite.
- [ ] Add cancellation, size limits, timeouts, page/sheet/slide limits, and structured truncation metadata.
- [ ] Validate archive members, links, total expanded size, file count, and destination paths before extraction.
- [ ] Keep code execution in the existing supervised coding or shell system rather than the file processor.
- [ ] Add unit tests for malformed, oversized, encrypted, hostile, and cancelled inputs.
- [ ] Run live acceptance with one real file of each initially supported format.

Acceptance gate: a file is never read, changed, extracted, uploaded, or overwritten outside the current path and permission policy; reported output files exist and pass format validation.

### 2. Web search

- [ ] Define structured search results with title, URL, snippet, provider, retrieval time, and publication time when known.
- [ ] Add a configured search provider without making it a hard dependency.
- [ ] Preserve source provenance when providers fail or fall back.
- [ ] Keep retrieval and answer synthesis separate.
- [ ] Revalidate every redirect in the existing page reader against local/private destination rules.
- [ ] Bound result count, response size, retries, concurrency, and overall deadline.
- [ ] Treat all search/page content as untrusted evidence.
- [ ] Add tests for empty results, malformed responses, rate limits, cancellation, and provider failure.
- [ ] Add redirect tests covering loopback, private IPs, link-local addresses, and excessive redirects.
- [ ] Verify live search results include usable source links without exposing provider credentials.

Acceptance gate: search returns structured, attributable evidence; a provider failure leaves LUMINA operational; redirect handling cannot silently reach a prohibited local destination.

### 3. Reminder

- [ ] Choose one scheduler authority and adapt the legacy persistent job model into the current runtime.
- [ ] Use UUIDs rather than timestamp-derived task names.
- [ ] Store timezone-aware due times and the user's configured timezone.
- [ ] Add create, list, inspect, snooze, update, and cancel operations.
- [ ] Support one-time reminders first; add recurrence only after one-time recovery is proven.
- [ ] Persist jobs atomically and quarantine corrupt state.
- [ ] Re-evaluate the current permission policy when a scheduled action becomes due.
- [ ] Interpret structured tool failures as failures rather than successful function returns.
- [ ] Define missed-run, restart-recovery, retry, and duplicate-delivery behavior.
- [ ] Test restart recovery, simultaneous reminders, timezone behavior, revoked permission, and notification failure.

Acceptance gate: a reminder survives a LUMINA restart, fires once at the expected local time, can be cancelled, and does not turn stored confirmation state into permanent authority.

### 4. Browser control

- [ ] Introduce a browser provider behind the current tool registry.
- [ ] Use an explicitly identified automation profile or supported attached session.
- [ ] Expose stable browser session and tab IDs.
- [ ] Implement navigation, inspect page, click, type, tabs, and screenshots as typed operations.
- [ ] Prefer accessible role/name/label locators and return candidates for ambiguous matches.
- [ ] Associate mutations with a recent page snapshot and recheck URL/page identity before acting.
- [ ] Cancel or invalidate timed-out operations so they cannot execute late.
- [ ] Route submissions, purchases, messages, uploads, and other external commits through current policy.
- [ ] Restrict downloads/uploads to validated filesystem locations.
- [ ] Test profile contention, ambiguous controls, delayed startup, cancellation, and unexpected navigation.

Acceptance gate: one real supervised browser process can be opened, observed, controlled, cancelled, and closed without silent profile switching or unconfirmed external submission.

### 5. Screen processor

- [ ] Preserve the current external Windows camera helper unchanged unless a proven defect requires a focused fix.
- [ ] Add a separate provider-neutral screen capture interface.
- [ ] Support explicit monitor, window, and region capture.
- [ ] Return capture dimensions, source identity, and timestamp.
- [ ] Release capture resources immediately after each request.
- [ ] Keep local capture separate from sending an image to an online vision provider.
- [ ] Show a clear capture state in the UI and never enable continuous hidden capture.
- [ ] Add DPI-aware multi-monitor coordinate handling.
- [ ] Handle black/protected frames, stale windows, timeout, and cancellation without blocking LUMINA.
- [ ] Test capture cleanup and verify temporary images are not retained unintentionally.

Acceptance gate: LUMINA can capture one requested screen image and clean up immediately; no capture is uploaded merely because it exists locally.

### Phase 1 completion checklist

- [ ] All five capabilities are registered through the existing tool registry.
- [ ] No legacy in-process generated Python execution is imported.
- [ ] Existing filesystem, messaging, camera, worker, and voice tests still pass.
- [ ] New capability tests pass independently and as one integrated suite.
- [ ] Capability status accurately distinguishes configured, unavailable, failed, and ready.
- [ ] Portable build contains required local dependencies or reports their absence clearly.
- [ ] Live acceptance evidence is recorded without credentials or private content.

## Phase 2 — Automation and situational intelligence

Goal: use Phase 1's scheduler, evidence, browser, and capture foundations to add controlled automation and useful event-driven intelligence.

### 6. Background monitor

- [ ] Store user-created watches with UUID, query, provider, interval, status, and notification preference.
- [ ] Use Phase 1 structured search rather than parsing formatted prose.
- [ ] Establish a quiet baseline when a watch is created.
- [ ] Fingerprint multiple canonical results rather than only the first headline.
- [ ] Distinguish no change, no results, provider failure, and material change.
- [ ] Add bounded retry/backoff and restart-safe deduplication.
- [ ] Queue alerts when voice is busy and aggregate related changes.
- [ ] Include source evidence in alert history.
- [ ] Add list, inspect, pause, resume, and remove operations.
- [ ] Test result reordering, offline recovery, duplicate stories, and quiet-time behavior.

Acceptance gate: only explicitly requested watches run; the same event is not repeatedly announced after restart; source evidence explains every alert.

### 7. Computer settings

- [ ] Define typed Windows providers for audio endpoints, brightness, windows, and selected system settings.
- [ ] Preserve the current microphone and speaker selection implementation.
- [ ] Implement get-before-set and read-back verification where Windows supports it.
- [ ] Address a specific device, monitor, or window rather than an implicit global target where possible.
- [ ] Separate native settings operations from keyboard shortcuts.
- [ ] Record target identity and exact previous values for undo.
- [ ] Reject stale undo if the state changed independently.
- [ ] Keep restart, shutdown, connectivity loss, and other consequential actions behind current confirmation.
- [ ] Report unsupported monitor/device operations honestly.
- [ ] Test missing devices, disconnected endpoints, unsupported brightness, and cancelled power actions.

Acceptance gate: every reported setting change is either verified or explicitly marked unverified; existing web audio settings continue working.

### 8. Computer control

- [ ] Build a Windows UI Automation helper/provider as the primary interaction path.
- [ ] Enumerate semantic controls, properties, windows, and supported control patterns.
- [ ] Use visual targeting only as a bounded fallback.
- [ ] Include monitor, window, DPI, capture time, and bounds in visual target results.
- [ ] Recheck foreground window and target state immediately before mutation.
- [ ] Serialize input operations and stop promptly on user takeover.
- [ ] Prevent logging of typed private content and clipboard data.
- [ ] Never generate fake personal data when requested information is unavailable.
- [ ] Return observed state changes instead of treating a click as success.
- [ ] Test multiple monitors, focus changes, modal dialogs, ambiguity, DPI scaling, and interruption.

Acceptance gate: LUMINA can inspect and invoke a named control in a real Windows app while refusing ambiguous or stale targets.

### 9. YouTube video

- [ ] Expose search, metadata, open, transcript, and summarize as separate operations.
- [ ] Use Phase 1 search/browser providers instead of fragile direct HTML regex where possible.
- [ ] Validate exact YouTube hosts and video IDs.
- [ ] Return transcript language, generation source, and timestamps when available.
- [ ] Report unavailable captions and access limitations accurately.
- [ ] Summarize long transcripts in bounded sections rather than truncating only the end.
- [ ] Preserve links to relevant timestamps in summaries.
- [ ] Make saving/opening a summary explicit.
- [ ] Use atomic no-overwrite artifact handling from the file processor.
- [ ] Test spoofed domains, Shorts, private videos, disabled captions, long videos, and non-English transcripts.

Acceptance gate: YouTube operations fail honestly when captions are unavailable and never describe scraped or inferred metadata as authoritative API data.

### 10. Proactive

- [ ] Limit initial proactivity to real task, reminder, monitor, worker, and provider events.
- [ ] Require explicit opt-in and expose a master disable control.
- [ ] Add quiet hours, cooldown, snooze, and active-conversation suppression.
- [ ] Persist event delivery IDs to avoid repeat announcements after restart.
- [ ] Aggregate multiple low-priority events into one concise notification.
- [ ] Use minimal event context rather than broad personal memory.
- [ ] Disable action tools during notification phrasing.
- [ ] Never start agents, investigations, monitors, or reminders proactively.
- [ ] Allow read/dismiss inspection from the UI.
- [ ] Test provider failure, restart duplication, active speech, quiet hours, and unauthorized-action attempts.

Acceptance gate: proactive output is attributable to a real configured event, concise, non-duplicated, and incapable of initiating unrelated work.

### Phase 2 completion checklist

- [ ] Every automation is observable and stoppable.
- [ ] UI Automation is primary; raw coordinate actions are the exception.
- [ ] No fake data or decorative values are reported as system state.
- [ ] Scheduled/background operations survive restart without duplicate notifications.
- [ ] Confirmation behavior is based on consequence, not which adapter performed the action.
- [ ] Phase 1 regression and Phase 2 integration suites pass.
- [ ] Live tests cover at least one real monitor, settings change with restoration, UI control, YouTube transcript, and event notification.

## Phase 3 — Extensibility and refinement

Goal: stabilize extensions and close smaller capability gaps without replacing current implementations that are already superior.

### 11. Plugins

- [ ] Define an inert manifest containing ID, version, compatibility, capabilities, configuration, permissions, and entry point.
- [ ] Discover metadata without importing or executing plugin code.
- [ ] Require explicit install and enable states.
- [ ] Reject core tool collisions and incompatible runtime versions.
- [ ] Validate complete input and output schemas.
- [ ] Run enabled plugin work through a supervised process boundary with timeout and cancellation.
- [ ] Broker only declared capabilities; do not hand plugins unrestricted credentials or runtime objects.
- [ ] Expose plugin health, errors, version, and disable/uninstall operations.
- [ ] Make clear that process separation is crash isolation, not a complete security sandbox.
- [ ] Test disabled import behavior, crashes, hangs, malformed output, collision, upgrade, and uninstall.

Acceptance gate: a disabled or invalid plugin cannot execute; a crashing plugin cannot bring down LUMINA; plugin side effects still obey current policy.

### 12. File controller

- [ ] Keep current multi-root validation, no-overwrite behavior, fingerprint confirmations, and Recycle Bin deletion.
- [ ] Add bounded create-text-file support.
- [ ] Add edit/append with expected original hash/version.
- [ ] Write edits atomically and preserve a recoverable revision.
- [ ] Add durable operation IDs and a bounded operation journal.
- [ ] Implement undo only when the current target still matches the recorded operation output.
- [ ] Add bounded largest-files and disk-usage inspection with incomplete-scan reporting.
- [ ] Add organization preview and apply it through existing move validation.
- [ ] Resolve redirected Windows Known Folders.
- [ ] Test multiple drives, ADS, junctions, stale approval, destination races, partial copies, and stale undo.

Acceptance gate: current filesystem guarantees remain intact, and new editing/undo functions never silently overwrite a changed target.

### 13. Desktop.py conveniences

- [ ] Reject the legacy generated-Python execution path permanently.
- [ ] Add validated wallpaper inspection/set/restore as explicit operations if desired.
- [ ] Resolve the real Windows Desktop Known Folder, including redirection.
- [ ] Produce exact organization/archive previews with collision reporting.
- [ ] Apply approved plans through current file operations.
- [ ] Journal each moved item for recoverability.
- [ ] Refuse deletion under the label “cleanup.”
- [ ] Handle locked files and partial failures without claiming full completion.
- [ ] Expose real counts and paths in the UI.
- [ ] Test OneDrive Desktop, naming collisions, changed files, cancellation, and partial restore.

Acceptance gate: every desktop mutation is an explicit typed operation with a reviewable target; no model-written code is executed.

### 14. Open app refinements

- [ ] Keep current PATH, App Paths, Start Menu, and packaged-app discovery.
- [ ] Add curated aliases as matching hints, never silent substitutions.
- [ ] Improve product deduplication and publisher/source metadata where available.
- [ ] Resolve Windows Known Folders and stable executable identities.
- [ ] Add bounded visible-window readiness checks where supported.
- [ ] Distinguish launch requested, process started, already running, and visible window observed.
- [ ] Support safe script/shim discovery only with preserved argument boundaries.
- [ ] Preserve the prohibition against bypassing supervised agent launch.
- [ ] Return candidates for ambiguity rather than choosing the first fuzzy match.
- [ ] Test packaged apps, shortcuts, PATH shims, duplicate products, and apps without windows.

Acceptance gate: LUMINA never reports “opened” solely because it typed a name and pressed Enter; ambiguous applications require a resolved identity.

### 15. Send message refinements

- [ ] Keep official Telegram, Discord, WhatsApp, and read-only Gmail adapters.
- [ ] Preserve exact-message confirmation in the runtime layer.
- [ ] Add provider-specific human-readable destination resolution where APIs permit it.
- [ ] Display exact provider, destination identity, and content before confirmation.
- [ ] Store provider receipt/message IDs after verified success.
- [ ] Distinguish sent, failed, and unknown outcome.
- [ ] Never retry an unknown-outcome send automatically.
- [ ] Improve provider status and permission diagnostics without exposing secrets.
- [ ] Keep Gmail unable to send while the active requirement remains read-only.
- [ ] Test expired credentials, inaccessible destinations, rate limits, duplicate prevention, and redaction.

Acceptance gate: no external message leaves the machine without exact user confirmation, and success is supported by a provider response rather than keyboard timing.

### Phase 3 completion checklist

- [ ] Plugin interfaces match the stabilized runtime rather than creating a parallel tool system.
- [ ] Existing superior implementations remain authoritative.
- [ ] No focus-dependent UI messaging is introduced.
- [ ] No generated Python execution is introduced.
- [ ] No hard-coded application list replaces discovery.
- [ ] Full regression, portable build, restart, and failure-isolation tests pass.
- [ ] Documentation clearly distinguishes installed capabilities from optional adapters and configuration requirements.

## Starting checklist

The first implementation slice should be File Processor: local, read-only extraction only. It establishes the artifact, background execution, cancellation, format-detection, limits, and structured-result conventions needed by later capabilities.

- [ ] Record the current full test baseline before editing.
- [ ] Inventory available document-processing dependencies in the development and portable runtimes.
- [ ] Define the processor interface and structured result schema.
- [ ] Implement current-path validation and secret exclusions at the processor boundary.
- [ ] Add bounded TXT/Markdown and PDF extraction first.
- [ ] Add DOCX and PPTX extraction.
- [ ] Add CSV/Excel metadata and statistics without mutation.
- [ ] Add JSON validation and image metadata.
- [ ] Add cancellation, time, file-size, and output-size budgets.
- [ ] Add tests for every supported type and failure category.
- [ ] Integrate capability status and the current tool registry.
- [ ] Run the focused suite, then the full current suite.
- [ ] Perform live acceptance on copies of representative non-sensitive files.
- [ ] Stop the first slice before conversions, archive extraction, online upload, media transcoding, or code execution.

Definition of done for the starting slice: LUMINA can inspect and extract useful content from supported local files without modifying them, leaving its configured scope, uploading them, blocking the runtime, or misreporting truncated/failed processing as complete.
