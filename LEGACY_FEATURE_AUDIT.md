# LUMINA legacy feature audit and upgrade recommendations

Prepared 7 October 2026. Scope: the fifteen requested capabilities in `sources/actions`, their supporting legacy services, and their equivalents in the current `lumina` runtime.

## Decision

Keep the current runtime as the integration and permission authority. The legacy source contains valuable additional capabilities, but none of these fifteen modules is a safe wholesale replacement for the current foundation. Its strongest reusable ideas are the browser session abstraction, file-type processing dispatch, persistent reminder store, plugin metadata/settings, and user-configured topic monitoring. Its weakest mechanisms are generated Python execution, focus-dependent message sending, first-match UI interaction, and incomplete verification of successful actions.

This is an analysis deliverable, not a claim that the recommended integrations are installed. No production runtime, UI, provider configuration, dependencies, or portable application files were changed for this audit. Keeping existing behavior is deliberate: a feature being larger does not establish that its implementation is better. The proposed best versions below require integration and acceptance testing before promotion.

## Evidence and verification

I inspected the actual legacy actions, action/plugin dispatch, background-loop call sites, confirmation implementation, scheduler persistence/execution, and the current tool registry, desktop services, file operations, camera protocol, communication manager, and relevant tests. The existing graph contains personal notes rather than a useful code dependency index, so it was not used as evidence of code behavior or overwritten.

The targeted current regression command was:

` .\.venv\Scripts\python.exe -m pytest tests/test_desktop.py tests/test_local_operations.py tests/test_communication.py tests/test_gmail_readonly.py tests/test_camera.py tests/test_shell_action.py -q `

Result: **31 passed in 2.74 seconds**. This supports preserving those tested contracts. It is not evidence that physical camera hardware, real messaging accounts, all installed applications, browser automation, or legacy scheduling have passed live acceptance. I did not execute legacy actions that could change settings, upload files, send messages, or register scheduled tasks. “Missing” below means no corresponding callable capability found in the inspected current registry/runtime, not that a dependency could never be installed elsewhere.

## Comparison at a glance

| Feature | Current position | Legacy advantage | Recommended decision |
|---|---|---|---|
| Plugins | Explicit built-in tool registry; no equivalent user plugin loader found | Discovery, metadata, settings, enable/disable | Add constrained extension support; do not copy in-process import execution |
| Background Monitor | Real machine/worker monitoring, not topic-news monitoring | User topic watches and headline deduplication | Keep telemetry; add opt-in topic watches separately |
| Browser control | Open browser/URL and retrieve page text | Stateful Playwright interaction and tabs | Add a supervised browser adapter |
| Computer Control | Structured local actions, not general UI automation | Mouse, keyboard, clipboard, visual targeting | Add Windows UI Automation first; bounded visual fallback |
| Computer settings | Audio-device selection and runtime settings, limited OS controls | Volume, brightness, windows, power controls | Add typed OS settings operations; preserve existing audio controls |
| Desktop.py | Validated filesystem/app/Explorer services | Wallpaper and organization conveniences | Keep current services; reject generated-code execution |
| Screen processor | External Windows camera helper | On-demand screen capture/compression | Keep camera; add separate consent-aware screen capture |
| Web search | Fetch a known public page, not general search | Search/news/research modes | Add structured search; harden existing redirect handling |
| YouTube | Open/fetch generic URLs | Search/play, metadata, transcripts, summaries | Add optional video adapter with honest transcript limits |
| Open app | Indexed Windows application discovery | More aliases and GUI-search fallback | Current wins; improve discovery/verification incrementally |
| Proactive | Existing task/worker result reporting | Idle conversational check-ins | Keep event-driven reporting; make check-ins opt-in |
| Send message | Official isolated service adapters and confirmation | More personal-app UI targets | Current wins; reject blind UI sending |
| File processor | Bounded text reading/search/metadata | Rich document and media processing | Highest-value addition, split into safe adapters |
| Reminder | No equivalent persistent reminder tool found | OS reminders plus separate scheduler subsystem | Adapt persistent jobs; repair execution semantics first |
| File controller | Validated multi-root operations and confirmation | Creation/editing, organization, undo | Current wins; add transactional editing and operation journal |

## 1. Plugins

### What legacy actually does

`sources/core/plugin_loader.py` scans Python files, imports each module, reads its `PLUGIN` declaration, and registers its callable `run`. The declaration supports a name, description, parameter schema, settings, blocking/non-blocking behavior, and result scheduling hints. Invalid plugins can appear in the UI with an error rather than preventing all other plugins from loading. Name collisions with core tools are rejected. Enabled state is consulted when advertising/running tools, and settings namespaces are gathered for the settings interface.

`sources/main.py:628` performs discovery, and `sources/main.py:1256` runs plugin calls in an executor. This is a genuine extension framework, not merely a folder of unused files. However, the inspected plugin directory contains a template and initialization file, not a substantial installed plugin collection. Framework support and installed capabilities must be distinguished.

### What is good and what is unsafe

Reusable ideas: per-plugin identity, discoverable settings, collision handling, independent error reporting, and explicit capability descriptions. These are better than scattering optional features through the main runtime.

The loader executes module code before validating its metadata. A disabled or invalid plugin can therefore execute import-time code. Running a call on an executor thread keeps the event loop responsive but does not isolate credentials, filesystem access, process creation, memory consumption, or imports. Metadata validation is shallow; it is not a complete schema/security policy. Returning `result or 'Done.'` also turns empty results into apparent success. No reliable per-plugin process cancellation boundary was found.

The current `lumina/tools.py:95` has the better authority model: known tools, declared arguments, central dispatch, and explicit confirmations. It is less extensible, but should remain the entry point.

### Best version

Add a manifest-first plugin catalog to the current registry. Read inert metadata before loading code. Give each plugin a stable ID, version, supported runtime/API version, dependencies, capabilities, configuration schema, and health status. Only enabled, explicitly installed plugins should become callable. Validate full inputs and outputs, return structured success/failure, and keep plugin-origin errors out of raw conversation output.

For ordinary trusted local plugins, process separation improves crash recovery and timeouts. It is **not by itself a security sandbox**: real restriction needs a brokered capability interface and OS-level limits where required. Never advertise arbitrary third-party Python as safely sandboxed merely because it runs in another process. Credentials should be resolved by the runtime for approved provider operations, not handed wholesale to plugins.

Acceptance: disabled plugins do not execute; invalid metadata/collisions are reported independently; a crashing or hanging plugin cannot freeze speech; uninstall/disable removes tool availability; side-effect requests still require the current runtime's approval policy.

## 2. Background Monitor

### What legacy actually does

`sources/actions/background_monitor.py` stores watched topics in memory and supports adding, removing, and listing them. Its checker retrieves news results, evaluates the first headline, remembers a short hash, and returns an alert when it changes. `sources/main.py:1922` waits five minutes after startup, checks roughly every thirty minutes, and avoids a check when the user spoke in the previous thirty seconds or speech output is active. Each topic is effectively checked once per local calendar day. Alerts are handed to the live conversation for a brief spoken summary.

This is **topic/news monitoring**, not CPU, memory, process, or agent monitoring. Current `lumina/telemetry.py` and worker events solve a different problem and must remain intact.

### Limitations

Only the top headline is compared; lower-ranked important stories are missed, while harmless result reordering can produce alerts. Initial setup has no quiet baseline. A no-results response can mark the topic checked for the day. IDs derived from truncated slugs can collide. Removal can fall back to a first substring match. Memory read/modify/write is not a transaction over the entire operation. The topic exclusion list uses substrings such as “token,” which can reject unrelated technical topics.

Monitoring is tied to an awake live session, so it is not an independent always-operational service. Alert text contains a source label but lacks the complete structured source evidence needed for a reliable UI history.

### Best version

Keep machine telemetry unchanged. Add explicit user-created watches with durable UUIDs, query, source/provider, interval, last successful check, next check, and notification preference. Store canonical URLs/content fingerprints for multiple results. Distinguish “nothing changed,” “no results,” and “provider failed.” Retry transient failures with bounded backoff rather than suppressing the entire day.

Run checks independently of voice connectivity; queue notifications until an appropriate idle period. Default to a quiet baseline, deduplicate across restarts, and retain enough source evidence to answer “why did you notify me?” Do not create topics just because the model considers them useful. Test duplicate headlines, reordered results, offline recovery, restart persistence, and quiet-time behavior.

## 3. Browser control

### What legacy actually does

`sources/actions/browser_control.py:450` owns Playwright sessions on a dedicated event loop/thread. It supports navigation, search, clicking, typing, scrolling, keys, page text, URL inspection, forms, tabs, screenshots, back/forward/reload, and named browser sessions. There are browser discovery helpers and a path for opening a normal browser before switching to automation.

This is materially richer than current opening/fetching. A downloaded HTML page cannot click an authenticated app's buttons, interact with client-side state, or manage tabs.

### Limitations

The launch path at line 516 attempts real browser profile directories, then falls back to a separate LUMINA profile when a launch fails. That can silently change the user's expected signed-in session. Current Playwright documentation explicitly says automating the default Chrome profile is unsupported; a separate automation profile is the supported direction. See [Playwright BrowserType](https://playwright.dev/python/docs/api/class-browsertype).

`run` at line 483 times out waiting for a future without cancelling the underlying coroutine, allowing a supposedly failed action to occur later. Smart click/type helpers use first matches and heuristics rather than proving uniqueness. A matched button can submit a form or purchase something: “click” is not inherently a low-risk action. Navigation, downloads, credential entry, and external submissions need different rules. Browser profile state is sensitive and must not be copied/exported casually.

### Best version

Adapt the session abstraction behind a current-runtime browser provider. Use a clearly identified dedicated persistent profile or an explicitly supported connection to a user-selected session. Return tabs with stable IDs and the actual URL/title. Target unique role/name/label locators; ambiguous matches should return candidates. Tie actions to a recent page snapshot and verify the resulting URL or UI state. Timeouts must cancel or invalidate pending work so late mutations cannot occur silently.

Separate reading/navigation from external commits. The runtime should prepare and confirm the exact submission where required. Keep page content untrusted. Use the existing controlled file paths for downloads/uploads. Tests should cover two tabs, ambiguous buttons, delayed startup, cancellation, profile contention, unexpected navigation, and refusal to silently submit a message.

## 4. Computer Control

### What legacy actually does

`sources/actions/computer_control.py` provides PyAutoGUI keyboard/mouse interaction, drag/scroll, clipboard, screenshots, window focus, field clearing, waits, and generated test data. Its `screen_find` path at line 313 uploads a screenshot to Gemini, parses returned coordinates, and `screen_click` uses them.

The current application has structured desktop and shell capabilities, but I found no equivalent general-purpose screen-interaction tool in its registry. Browser tests using Playwright are not a user-facing computer-control feature.

### Limitations

Coordinates alone do not identify the correct application, display, DPI transform, or current target. The screen can change between inference and click. The visual response does not establish a unique or safe target. Fixed sleeps and the foreground clipboard can race with user activity. Parameters are printed, potentially exposing private text. The `user_data` branch can substitute random generated values for missing personal information; that is unacceptable for real forms.

### Best version

Add a Windows helper that first reads UI Automation elements and invokes supported control patterns. Microsoft describes UI Automation as a cross-framework accessibility interface exposing properties and control patterns; it is a stronger target identity mechanism than raw coordinates, although not every app exposes useful elements. See [Microsoft UI Automation](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-uiautomationoverview).

Use visual targeting only where semantic controls are unavailable, with an explicit screen/window capture, timestamp, monitor coordinates, DPI conversion, and bounds validation. Check foreground/window identity again before acting. Serialize input actions, stop on user takeover, and never invent missing personal information. Return observed effects, not merely “clicked.” Submitting data, deleting content, or changing security settings retains its existing consequence-based policy regardless of whether it is done through an API or mouse.

Acceptance must include scaled/multiple monitors, changed focus, missing controls, ambiguous labels, user interruption, and a modal dialog appearing between observation and action.

## 5. Computer settings

### What legacy actually does

`sources/actions/computer_settings.py` combines volume/mute, brightness, display sleep, window sizing/snapping, browser keyboard shortcuts, clipboard/edit shortcuts, theme changes, opening settings, lock, Wi-Fi, restart, and shutdown. Its local intent resolver avoids an additional model call for common aliases and numeric values. Some operations push undo callbacks.

It contains a real human UI confirmation mechanism for restart, shutdown, and Wi-Fi. `sources/core/confirm.py:89` stores the action and requires the UI to resolve it, with a ninety-second expiry; this is better than letting a model send `confirmed=true`.

### Comparison and limitations

Current microphone/speaker device selection concerns the app's audio pipeline, not general system volume/brightness. Keep that working path. Legacy adds breadth, but mixes native operations with focus-dependent keyboard shortcuts. Its top-level PyAutoGUI availability gate can disable operations that do not inherently require PyAutoGUI. Undo implemented as toggling may restore the wrong state if the user changed it meanwhile. Window close and Enter can have consequential effects even when not listed among the three gated actions.

### Best version

Use typed operations such as get/set volume on a selected endpoint, get/set brightness on a supported monitor, list/focus/minimize a specific window, and open a known settings page. Read back changes where the OS supports it. Report unsupported external-monitor brightness instead of pretending success. Keep settings, keyboard interaction, and power actions in separate providers sharing one policy gate.

Undo should record the previous value, target identity, and post-change value, then refuse stale reversal rather than undoing a later manual change. Do not conflate speaker volume with microphone selection. Test absent devices, disconnected endpoints, unsupported brightness, stale undo, and power-action cancellation without actually restarting the machine.

## 6. Desktop.py

### What legacy actually does

`sources/actions/desktop.py` supports wallpaper operations, desktop contents/statistics, organizing files by type, and archiving desktop files into a dated folder. It also asks Gemini to generate Python for generic desktop tasks and executes it in a custom globals dictionary.

### Why the current version wins

The legacy `_build_sandbox` at line 38 exposes powerful objects including `Path`, `ctypes`, and filesystem/mouse helpers. `_execute_generated_code` at line 83 executes generated code in process. Removing a few builtins does not make these objects safe: paths can mutate files and native APIs can bypass intended limits. Unknown actions can fall through to this generated-code route. Organization/cleanup can move files immediately without an exact reviewed change plan.

Current `lumina/desktop.py` is a different architecture: separate path, search, filesystem, application, Explorer, terminal, and owned-process services. Preserve it. Neither filename implies the same implementation or the native desktop application's launcher.

### Best version

Add only the useful conveniences as explicit operations. Wallpaper accepts a validated local image and records the previous setting. Organization first returns a plan of exact source/destination pairs, collisions, and exclusions. Apply the approved plan through existing move validation with stale-target detection. Keep a recoverable operation journal. “Clean desktop” must mean a previewed organization/archive operation, never generated code or silent deletion.

Test redirected/OneDrive Desktop paths, collisions, files opened by another app, changes after preview, and partial failures. Do not import the legacy execution sandbox.

## 7. Screen processor

### What legacy actually does

`sources/actions/screen_processor.py:88` captures the first physical display using MSS and compresses images to at most 1280×720 JPEG at quality 82. The camera branch probes numeric OpenCV indices, checks mean brightness, remembers an index, reads a fixed number of warm-up frames, and returns an image. The legacy main session sends captured images to Gemini.

### Comparison

Screen capture is useful functionality missing from the current tool registry. Camera capture is already better separated in current `lumina/camera.py:12`: a dedicated Windows helper, request/response files, request identity, time bounds, bounded JPEG validation, cleanup, and local capture separated from upload. Preserve that path.

The legacy camera does not identify built-in versus virtual devices by reliable metadata. Falling back to index zero after detection failure can select an unintended camera. Fixed warm-up frames are not exposure-state polling. Device indices can change. A failure path does not consistently guarantee release using `finally`.

### Best version

Add a screen provider separate from the camera provider. Allow explicit monitor/window/region selection, return dimensions and capture time, close capture resources immediately, and avoid storing images unless requested. Keep full-resolution or crop options for reading text instead of always reducing a large display to 720p. Treat local capture and sending to Gemini as separate capabilities with appropriate authorization. Show a capture indicator and never start continuous screen collection as a hidden side effect.

Test multiple monitors, DPI, protected/black capture, empty region, stale window, cancelled upload, and cleanup. A screenshot's existence does not establish successful visual interpretation.

## 8. Web search

### What legacy actually does

`sources/actions/web_search.py:81` uses Gemini with Google Search grounding. Text search falls back to DDGS; news tries DDGS first, then grounded Gemini. Additional modes build research, price, and comparison prompts. Results are formatted into prose and displayed by the legacy main UI.

Current `lumina/local_operations.py:97` fetches a known page with response size/type limits and text extraction. That is useful, but it is **not a search engine**. A search provider and page reader should coexist.

### Limitations and a current issue found

Legacy grounding returns concatenated model text without a dependable structured citation payload. Research/price/compare are mostly prompt variants, not independent verification workflows. Fallback changes output semantics from synthesized prose to snippets. Thread-based deadlines can stop waiting while the underlying work continues. News quality checks based on string length are not robust success validation. Provider/model fallback configuration must not silently expand spending or data destinations.

The current page reader checks the initial URL for private/local addresses, but its redirect handler does not revalidate each redirected destination. This is an identified hardening gap, not proof of complete SSRF protection. DNS resolution/connect-time consistency also deserves a dedicated review. Do not reuse this reader for autonomous wide search and call it fully protected without addressing those issues.

### Best version

Return structured results containing title, URL, snippet, provider, retrieval time, and publication time only when known. Keep retrieval separate from synthesis so LUMINA can cite evidence and distinguish search snippets from fetched pages. Support a configured grounded provider and an explicitly configured independent search adapter. Bound results, retries, concurrency, and total latency. Preserve provenance across fallbacks.

Harden URL validation for every redirect and resolved connection; block credentials/local services and limit response bodies. Treat retrieved content as evidence, never authority to run tools. Test redirects to loopback/private IPs, rate limiting, malformed results, empty results, citation preservation, and cancellation. No live search provider was configured or enabled by this audit.

## 9. YouTube video

### What legacy actually does

`sources/actions/youtube_video.py` searches YouTube HTML for a first video ID, opens videos, retrieves transcripts through `YouTubeTranscriptApi`, summarizes up to 80,000 characters with Gemini, saves summaries on Desktop, scrapes video metadata, and scrapes regional trending titles. It prefers manually created transcripts, then generated captions, then another available language.

### Limitations

The URL check at line 115 accepts a substring containing the YouTube domain rather than validating the actual hostname. HTML regexes are fragile; independently extracted title/channel arrays can misassociate entries. The transcript call shape depends on the installed library version and needs compatibility testing. Transcript errors are collapsed into “no transcript,” losing the reason. Truncating a long transcript can produce a summary of only the beginning. Saving and opening a summary are extra actions that should be explicit rather than surprising defaults.

Do not promise that an official API solves arbitrary transcript retrieval: Google's caption download endpoint requires permission to edit the video. See [YouTube captions download](https://developers.google.com/youtube/v3/docs/captions/download?authuser=1). Metadata/search and caption access are separate capabilities.

### Best version

Provide search, metadata, open, transcript retrieval, and summarize as explicit operations. Validate exact allowed hosts and video IDs. Prefer supported APIs for metadata where configured; treat other retrieval paths as optional and failure-prone, never a promise of all-video access. User-provided transcripts remain a reliable input route. Return caption language/source and timestamps; summarize long transcripts in bounded sections with links to relevant times. Report incomplete coverage and unavailable captions honestly. Use the current application/provider layer for opening and reasoning.

Tests: spoofed domains, Shorts URLs, disabled captions, inaccessible/private videos, missing library, long transcript coverage, non-English captions, and summary file collisions.

## 10. Open app

### What legacy actually does

`sources/actions/open_app.py` has a large cross-platform alias dictionary. On Windows it attempts PATH launch, URI launch, then typing a name into Start search and pressing Enter. After sleeps, those paths can return “Opened” without observing the resulting application. Partial alias matching can choose the wrong app. Some aliases intentionally substitute a different program, such as Safari becoming Edge on Windows.

### Why current wins

`lumina/desktop.py:269` discovers actual PATH executables, both registry views of App Paths, Start Menu shortcuts, and Windows Start Apps. It caches discovery, exposes refresh, returns ambiguity, uses resolved IDs, and reserves agent launch for the supervised agent path. This is a better fit for your requirement to discover arbitrary installed apps rather than pretend a name exists.

Current success is still not perfect proof that a visible usable window appeared: packaged/shortcut launches have no owned process handle, and a matching process name does not prove the requested window is foreground. PATH scanning currently covers `.exe`/`.com`, not every script shim. Known user folders are derived from home paths rather than fully resolving redirected Windows Known Folders.

### Best version

Keep current discovery. Add tested aliases as hints, not substitutions; improve product deduplication and record source provenance. Resolve Windows Known Folders. Add optional window activation/launch verification with a bounded wait, distinguishing launch requested, already running, and window observed. Script launch support, if needed, must preserve argument boundaries and existing agent-launch restrictions. Do not restore a blind Start-menu typing fallback that claims success.

## 11. Proactive

### What legacy actually does

`sources/actions/proactive.py` waits roughly fifteen minutes of silence with a twenty-minute cooldown and rotates goal/check-in/fact prompts. It includes memory, watched topics, recent turns, and time of day. `sources/main.py:1955` checks once a minute, avoids interrupting ongoing speech, and injects the prompt into the live Gemini session.

### Assessment

This is an unsolicited conversation generator, not an autonomous task executor. Its prompt says not to use tools, but the active session still has tools; prose is not an enforcement boundary. Passing broad memory adds privacy exposure and context cost. Marking the cooldown before a failed send can suppress a later useful attempt. Cooldown state is process-local. Generic “fun facts” are not necessarily useful to you.

Current task/worker result reporting is more relevant and should remain. I found no equivalent generic idle-conversation engine in the current tool registry.

### Best version

Use an opt-in notification policy over real events: requested task finished, an explicitly configured watch changed, or an existing reminder is due. Add quiet hours, active-call suppression, aggregation, snooze, and clear read/dismiss state. Persist delivery IDs so restarts do not announce the same completion repeatedly. If personal check-ins are wanted, make them separately configurable and use minimal relevant memory.

Never let proactivity create agents, investigations, reminders, or watches without a user request. Disable action tools during purely proactive phrasing, or route the result through a text-only summarization boundary. Test that no event causes unauthorized new work.

## 12. Send message

### What legacy actually does

`sources/actions/send_message.py:137` opens an app, searches a recipient, waits, presses Enter, pastes content, presses Enter again, and returns a success sentence. It supports more consumer app targets, but its generic flow depends on focus, UI layout, search order, and keyboard behavior. Logging includes recipient/text previews.

I found no mandatory confirmation in this dispatcher or the general legacy action dispatch. A persona instruction to confirm does not provide the same guarantee as a runtime gate. It also lacks a reliable provider receipt, exact recipient identity verification, rate-limit semantics, or duplicate-send protection.

### Why current wins

Current `lumina/communication/manager.py:35` isolates Telegram, Discord, WhatsApp, and Gmail. Initialization validates providers independently. `lumina/tools.py:133` and its communication dispatch store exact prepared messages behind expiring confirmation. Official adapters are a stronger base than UI typing.

The active Gmail adapter is deliberately `ReadonlyGmail`, matching your later requirement for inbox judgment with a read-only token. The presence of older Gmail send implementation code does not mean the active runtime can or should send mail. Preserve that restriction. Bot APIs also do not provide unrestricted access to all personal-account conversations; WhatsApp incoming messages require its configured webhook path, and retained inboxes/search scopes are limited.

### Best version

Keep the official adapters and read-only Gmail. Improve human-readable recipient resolution, exact preview, provider receipt IDs, and an outgoing journal distinguishing confirmed success, failure, and unknown outcome. Never automatically retry a send whose outcome is uncertain. Do not add Signal/Instagram UI sending merely because legacy lists them. If a provider cannot access a destination, report the limitation accurately.

Acceptance uses fake providers first, then a user-authorized exact test recipient/message. No real message was sent in this audit.

## 13. File processor

### What legacy actually does

`sources/actions/file_processor.py:784` dispatches by type. Images support description/OCR and resize/compress/convert. PDFs support extraction, summary, information, and text-to-Word conversion. Documents/text support rewriting and translation-like instructions. CSV/Excel support information, statistics, filtering, sorting, and conversion. JSON supports validation/formatting. Code supports explanation/review/generation and direct Python execution. Audio/video support transcription and FFmpeg/pydub-style conversions. Archives support listing/extraction. Presentations support extracting slide text and summarization.

This is the largest practical capability gap: current bounded text reads do not replace PDF extraction, spreadsheets, or document processing. Reuse the type-dispatch concept, not the whole execution policy.

### Important limitations

The entry point only proves that a path exists and is a file; it does not use current root/credential boundaries. Model-backed operations can upload content without a distinct current-runtime approval step. Several reads load entire files before truncating prompts. Output paths are predictable and writes may replace earlier generated output. FFmpeg return codes are not consistently checked before reporting output. Archive extraction uses `shutil.unpack_archive` without its own explicit member/path/link/expansion limits; safety depends partly on runtime/archive type and is insufficient as a policy boundary.

At line 465, Python code can run through whichever `python` is on PATH, outside the supervised worker policy. Code execution should not be a hidden action of a document reader. XML is routed to the JSON processor despite the advertised XML support. PDF-to-Word extracts text rather than guaranteeing layout preservation. These distinctions matter when describing the feature to you.

### Best version

Split into local readers, local converters, and online analysis. Start with text/PDF/DOCX/PPTX extraction, image information/transforms, CSV/Excel statistics, and JSON validation. Return structured artifacts with source, type, page/sheet/slide location, limits, and truncation. Use common path validation and a bounded task executor. Make upload to the configured reasoning provider explicit; never treat a selected local file as blanket consent to upload unrelated contents.

Create new outputs atomically, avoid overwrites by default, enforce input/output/decompression limits, and verify the generated file before reporting success. Archive extraction needs member validation, link handling, count/size budgets, and transactional staging. Keep code execution in the existing supervised coding/shell path. Add media later with checked exit codes, progress, cancellation, and cleanup.

Acceptance: oversized/malformed PDF, encrypted document, multi-sheet workbook, invalid JSON/XML distinction, malicious archive paths, expansion bomb, converter failure, cancelled job, existing output, and upload refusal. Do not claim full Office fidelity from text extraction.

## 14. Reminder

### Two separate legacy systems

`sources/actions/reminder.py:287` accepts a date/time/message, creates a notification script, and registers an OS task. The Windows implementation at line 146 uses Task Scheduler with an interactive user token and least privilege. This can notify after LUMINA closes, but requires a suitable user session to display the notification.

Separately, `sources/core/scheduler` contains jobs, persistent storage, recurrence/time parsing, execution, and a service enabled by `LUMINA_SCHEDULER=1`. `jobstore.py` uses temporary-file replacement, validation, versions, and idempotency keys. `service.py` drives due jobs and recovers jobs left RUNNING after a crash. This is substantially more useful infrastructure than a single timer, but it is a separate path from the reminder action and must not be confused with one already unified scheduler.

### Defects to resolve before adoption

The simple reminder names tasks from the scheduled timestamp. Two reminders for the same minute can collide; `/F` can replace an existing task. Datetimes are naive local times, and XML paths are interpolated without proper XML escaping. The scheduler registration subprocess lacks a timeout. Generated script/runtime paths also matter when moving a portable install.

The central executor marks success when `run_tool` returns without throwing, even if it returns an error string or structured failure. Its recovery retries RUNNING jobs; that is at-least-once behavior, not guaranteed exactly-once execution. An external effect may have happened before the crash. The permission check uses stored job fields, so its claim of rechecking authoritative current policy is stronger than the implementation shown. Per-instance locks/atomic writes do not establish safe concurrent multi-process ownership.

### Best version

Adapt the durable job model into one current-runtime scheduler. Use UUIDs, timezone-aware instants, stored user timezone, recurrence rules, missed-run policy, and idempotent notification delivery. Expose create/list/update/snooze/cancel and next-run visibility. Include Windows timezone data requirements in packaging and test Asia/Katmandu/Kathmandu handling explicitly rather than assuming timezone support.

For reminders after exit, use one deliberate Windows notification/wake integration with validated relocatable resources, not competing schedulers each claiming authority. Scheduled side effects must call current policy at execution time; a stale stored boolean cannot authorize arbitrary future actions. Unknown-outcome sends must not be retried blindly. Interpret structured tool failure as failure. Test simultaneous reminders, restart recovery, clock changes, DST/timezone cases, revoked permissions, failed notifications, and changed installation path.

## 15. File controller

### What legacy actually does

`sources/actions/file_controller.py:648` dispatches listing, file/folder creation, delete, copy/move/rename, text read/write, find, largest files, disk usage, desktop organization, and metadata. It restricts resolved paths to the user's home directory and contains undo helpers, including attempted Recycle Bin restoration and bounded previous-content snapshots.

### Why current wins

The home-only root is narrower than your multi-drive requirement, yet broad enough to include sensitive user files. Legacy deletion/move/write dispatch does not route through the current confirmation system. Undo is useful but does not replace permission; large/unreadable originals may not be recoverable, and matching a recycled file by name/folder is weaker than identifying an exact operation.

Current `lumina/desktop.py:43` validates paths; filesystem operations reject existing destinations, inspect recursive children, and prevent root mutations. `lumina/tools.py` expires and revalidates destructive-operation confirmations using target fingerprints. These protections and the separation of desktop roots from worker scope should stay.

The current implementation still has improvement areas: Known Folder redirection, long text-search resource budgets, durable operation history, and explicit safe text creation/editing. A no-overwrite check before a directory/move operation is not a universal race-proof transaction; concurrent filesystem changes need careful treatment.

### Best version

Add create-text and edit-text operations with bounded content, expected original version/hash, atomic replacement, explicit overwrite approval, and recoverable revision records. Add largest-files and disk-usage views using bounded scans and honest incomplete results. Organization should produce an exact preview and apply through existing validators. Undo should refer to an operation ID and verify the current file still matches the operation's output.

Tests: another mounted drive, UNC policy, redirected Desktop, ADS/device paths, junctions, credential exclusions, destination races, files changing after approval, partial folder copy, stale undo, and Recycle Bin cancellation. Preserve existing behavior while adding these capabilities incrementally.

## Recommended implementation sequence

First preserve and harden the foundations: current filesystem/application/messaging/camera behavior, redirected Known Folders, structured results, and page-reader redirect validation. Add the read-only document processor and a structured web-search provider next; these deliver substantial usefulness without requiring general mouse control.

Then adapt durable reminders and topic watches into one scheduling/notification authority. Add a controlled browser provider and explicit screen capture. Build Windows UI Automation and system-settings adapters afterward, using the same permission and task machinery. Add YouTube as an optional composition of search, metadata, transcript access, and analysis. Introduce plugin packaging only once these interfaces are stable. Generic proactive conversation is the lowest-priority item; useful event notifications should come first.

For every adopted capability, distinguish unavailable, ready, running, completed, failed, cancelled, and awaiting confirmation where appropriate. A result must reflect evidence: process creation is not app readiness; pressing Enter is not delivery; a created file path is not verified conversion; a scheduler returning normally is not a successful action.

## Final recommendation

The best version is a hybrid: current LUMINA remains the runtime, security boundary, UI, conversation system, and provider host. Carefully port useful legacy capabilities behind its existing registry and task system. Preserve current application discovery, official messaging, camera lifecycle, and filesystem confirmations. Replace neither the working interface nor those foundations merely to gain a longer action list.

The next implementation should be a bounded document-processing slice, alongside the independently scoped page-reader hardening, with tests and a visible capability status. The report's proposed integrations are not yet installed, and no legacy live acceptance is implied by this audit.
