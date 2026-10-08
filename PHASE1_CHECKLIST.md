# Phase 1 checklist — 8 October 2026

Status is evidence-based. Implemented does not mean every original live acceptance
condition or every legacy feature has passed.

## File processor
- [x] Registered in the existing tool registry; provider-neutral processing boundary.
- [x] Bounded local extraction: text, PDF, DOCX, PPTX, CSV, XLSX, JSON and image metadata.
- [x] Existing path policy and secret-file exclusions; parser subprocess and cancellation.
- [x] Read operations separated from analysis disclosure, conversion and writes.
- [x] Atomic new-file output; no silent overwrite; bounded safe ZIP handling.
- [x] Persistent uploads appear in the Workspace panel.
- [x] Documents and images can be sent to the configured analysis provider after confirmation.
- [x] Malformed, oversized, hostile, cancellation and permission regression tests.
- [ ] Scanned-PDF OCR, old binary Office formats and full legacy media conversions are not supported.

## Web search
- [x] Free keyless Tavily search; no Gemini search or automatic paid fallback.
- [x] Title, source URL, snippet, provider and retrieval time; publication time when supplied.
- [x] Retrieval separated from answer synthesis; external content marked untrusted.
- [x] Public destination checks, redirect checks, size/concurrency/deadline bounds.
- [x] Explicit rate-limit, malformed response, cancellation and provider-failure handling.
- [x] Live official-documentation and Australian processor-search checks returned relevant links.
- [ ] Free-service availability and current retailer prices cannot be guaranteed.

## Reminders
- [x] One durable scheduler, UUID jobs and timezone-aware due times.
- [x] Create, list, inspect, snooze, update and cancel one-time reminders.
- [x] Atomic persistence, corrupt-state quarantine and restart recovery.
- [x] Current permission evaluation; structured failures and uncertain delivery distinguished.
- [x] Duplicate-delivery/recovery, timezone and notification-failure regression tests.
- [x] Runtime notification delivery tested; user previously confirmed reminders work.
- [ ] No always-running Windows reminder service when LUMINA is closed; recurrence not claimed.

## Browser control
- [x] Dedicated identified supervised profile; stable session/tab IDs.
- [x] Typed navigation, inspection, click/type preparation, tabs and screenshots.
- [x] Accessible locator ambiguity, stale-page checks and cancellation cleanup.
- [x] Consequential actions remain behind policy; no silent external commits.
- [x] Real bundled Chromium opens and closes in the portable package.
- [ ] Arbitrary submissions, purchases, uploads/downloads and authenticated browsing are restricted.
      The original broader browser acceptance goal is therefore not fully complete.

## Screen processor
- [x] Separate Windows screen provider; existing camera helper preserved.
- [x] Explicit monitor/window/region capture with dimensions, source and time.
- [x] DPI, stale-window, black-frame, timeout, cancellation and cleanup handling.
- [x] Local capture does not upload by itself; online analysis requires disclosure confirmation.
- [x] Real local capture and synthetic-image vision evidence recorded in earlier audits.
- [x] Optional explicit bounded screen sharing is visible and stoppable.
- [ ] Fresh end-to-end physical voice/screen-sharing acceptance remains provider-dependent.

## Integration and this repair
- [x] Existing workers, messaging, filesystem, camera and voice regression coverage retained.
- [x] Exact-task cancellation confirmation and native worker/child termination verified.
- [x] Inactive agent removal preserves workspace files and logs.
- [x] Portable health identity, owned shutdown, pre-existing server reuse and relocation verified.
- [x] Notes and graph included only with explicit personal-knowledge packaging.
- [x] Actual WebView2 renders 10 concepts plus one gold hyperedge hub.
- [x] Talk and Send are matching 39-pixel controls; microphone icon survives call transitions.
- [x] Native microphone prompts use WebView2 deferrals instead of blocking its callback.
- [x] Trusted-local playback permission separated from microphone capture consent.
- [x] User confirmed microphone and speaker devices are listed after native permission approval.
- [ ] Audible playback and an extended physical voice/screen-share session still need human verification.
- [ ] Installed Evergreen WebView2 update remains blocked by execution policy.
- [ ] Trusted production signing unavailable; this portable build is explicitly unsigned.

New personal build: dist/LUMINA-Portable-AudioGraph/LUMINA.exe.
Do not distribute this personal build without removing personal notes/graph data.
Generic builds omit that data unless IncludePersonalKnowledge is explicitly selected.

## Persistent capture update
- [x] Removed microphone silence and three-minute call cutoffs.
- [x] Removed browser/server screen-share duration caps and idle-frame expiry.
- [x] Sharing remains explicit, visibly indicated, rate/size limited, and stopped on Stop, disconnect or app close.
- [x] Enabled Gemini sliding-window context compression for longer audio/video sessions.
- [ ] Physical long-duration microphone/screen-sharing acceptance still requires a working provider and user consent.
- [ ] Provider disconnect resumption and proactive YouTube reminders are not implemented by this patch.
