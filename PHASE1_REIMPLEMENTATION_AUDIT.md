# Phase One reimplementation audit — 8 October 2026

## Status

The reported document, screen-analysis and confirmation integration faults have been repaired and exercised. This is **not full legacy feature parity**. Search remains blocked by the configured external provider; legacy media conversion and unrestricted browser automation have not been imported. No claim is made that every legacy feature is available.

## Evidence and root causes

- Current session logs showed document extraction succeeding, followed by an invalid request and unsuccessful agent delegation. Document extraction alone was being treated as analysis.
- Screen capture returned metadata and kept a JPEG locally, but never supplied the image to reasoning. A successful capture could therefore only produce a generic acknowledgement.
- Browser preparation returned `requires_confirmation`; the registry checked `confirmation_required`. Approval could not reach the prepared browser operation.
- The confirmation HTTP route reported every approved result as `open_url`, losing capability-specific output.
- Headed browser startup closed its final page before creating the replacement. Chromium could exit during that gap. Startup now keeps one owned blank page open.
- Live-model text requests used the non-Live generation path. They now use the configured Live adapter. Realtime text replaces unsupported turn submission for the configured 3.1 Live model.
- Isolated vision requests initially raced the asynchronously ingested frame and inherited inappropriate tool instructions. Dedicated evidence instructions, all-input coverage, and a bounded cancellable 1.2-second frame-ingestion interval fixed the tested image requests. This is provider pacing, not camera exposure stabilization; the camera helper was not changed.

## Implemented

### File processing

Direct local extraction remains inside the bounded subprocess parser and path resolver. Text/code, UTF-16 text, XML and TSV complement PDF, DOCX, PPTX, CSV, XLSX, JSON, image metadata and ZIP support. Results include document boundaries and truncation metadata. Upload publication and cleanup were tightened.

The registry now exposes local CSV/TSV statistics, filtering and sorting, JSON validation/formatting, and raster image resize/conversion. Writes require an explicit new destination and confirmation; existing destinations are not overwritten.

`process_file` with `action: analyze` prepares an explicit disclosure confirmation, then sends extracted evidence to the configured provider. Images are decoded in the parser subprocess, resized and re-encoded as JPEG pixels without EXIF. Encoded image payloads are removed before tool results or UI events are emitted. Empty extracted text fails rather than inviting a fabricated summary. Document reading no longer calls coding agents.

### Screen processing

`capture` remains local. `analyze` requests permission for both one capture and disclosure to the configured provider, then returns an actual answer. The latest local JPEG is available through a token-protected, no-store preview endpoint. Capture remains one-shot and is not stored on disk. Existing Windows capture/helper boundaries remain.

### Browser

The existing supervised Playwright provider is retained. Confirmation fields are bridged correctly, repeated start returns a usable tab, and startup preserves an owned window. Approved public navigation can retrieve bounded read assets; destination validation applies to redirects and connections. Profile identity, stale snapshots, cancellation and exact-request checks remain.

### Search

HTTP 403 is reported as provider refusal, not falsely as missing authentication. An explicitly configured SearXNG JSON endpoint is supported alongside existing providers. Provenance is retained and no paid fallback is selected. Example configuration was added to `.env.example`.

### Reminders

Durable UUID jobs remain the scheduler authority. Delivery failures, callback timeouts and uncertain receipts are distinguished. Uncertain deliveries are not automatically retried. The interface accepts a message and delay rather than silently fixing every reminder at one minute. A real UI test verifies the due reminder appears in the conversation.

### Runtime, approvals, UI and logs

Approval now executes the original capability, reports its actual result, resolves the dialog and emits the result to the UI. Typed confirmation accepts only one unexpired pending action. Spoken confirmation is restricted to an exact affirmative and a single action already pending when that speech turn started.

Local Controls includes an uploaded-file path, local reading, document analysis, an analysis question, separate screen analysis, image preview, configurable reminder delay and reminder listing. Uploads populate the document control. Web search results are no longer misrendered as filesystem results.

Session audit remains under `logs/sessions`, retaining the three newest sessions. Tool start/result records now have correlation IDs, elapsed time, action and status; cancellation is explicit and waiting for confirmation is not logged as success. Tool arguments, image bytes and extracted document contents are not added to these diagnostic records. Existing conversation logging remains in place.

## Verification

- Full regression run: 283 tests passed. After the final truncation-reporting refinement, all 11 focused provider/integration tests passed again.
- Additional focused integration suite: seven tests passed, including real generated CSV sorting, JPEG resizing, image disclosure, approval replay rejection, browser confirmation bridging, protected screen preview, browser UI upload/approval and visible reminder delivery.
- JavaScript syntax checks passed for the edited application and controls scripts.
- Real Windows screen capture succeeded and released resources; its image was not sent externally during that hardware check.
- Real headed supervised browser startup, approved public navigation and accessible page inspection succeeded; owned browser was closed afterward.
- Configured Gemini Live successfully read synthetic image text `LUMINA 83924` and identified a red square. A separate test read `CHECK 62917` and identified a green circle.
- Configured Gemini Live extracted the launch date from a synthetic document correctly.
- Earlier failed/wrong vision outputs were not treated as acceptance. No personal screen content or real document contents were used in the live provider checks.

## Remaining limitations and acceptance gaps

- Live web search remains unverified because the current DuckDuckGo endpoint refuses requests. Configure a working explicitly selected provider; no credential was invented or changed.
- Legacy audio/video processing, PDF-to-Word/PPTX-to-PDF conversion, page extraction, older binary Office formats and non-ZIP archives are not implemented here. Scanned PDF OCR is still unavailable. Uploaded raster images can be analyzed with explicit provider disclosure, which is different from local OCR.
- Spreadsheet transformations currently target CSV/TSV. XLSX extraction is supported, but equivalent XLSX filtering/writing is not claimed.
- Browser forms, fetch/XHR, uploads, downloads, authenticated-session cookie forwarding and arbitrary external submissions remain restricted. This is supervised public browsing, not full legacy computer automation.
- Reminder service delivery means accepted into the runtime conversation/announcement queue. The UI notification path was tested, but there is no durable per-client acknowledgement protocol or OS background service when LUMINA is closed.
- Spoken approval routing has code-level restrictions; an actual human microphone approval session has not been witnessed in this audit.
- Provider frame pacing is validated against the configured Live model, not a universal guarantee for other providers. Do not remove it without repeated image-evidence tests.
- Portable packaging was not rebuilt or independently validated in this pass. Restart the runtime to load the code changes.

No generated legacy Python execution, automatic private uploads, new paid fallback, camera rewrite or coding-agent redesign was introduced.
