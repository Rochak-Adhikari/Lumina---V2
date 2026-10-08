# Portable repair audit — 9 October 2026

## Evidence reviewed

Reviewed the two latest sessions in the Phase 2 portable logs and the newer main-runtime session containing the user's test prompts. Portable and main runtimes had separate logs. The portable log recorded two screen-share stops without a failure reason; the older portable session recorded missing Gemini configuration. The main log also recorded PROFILE_BUSY, unsupported_setting, invalid_window, and application search incorrectly receiving a supervised-video request.

The old logs do not prove that Windows denied screen access. No Windows privacy settings were changed.

## Repairs

- Screen sharing now has an explicit Windows monitor/window selector, a local preview, and a separate online-viewing checkbox. The existing bounded Windows capture worker supplies frames. It works without a Gemini session, browser display picker, microphone or audio playback. Only the latest reduced JPEG remains in memory; stopping releases it. Online-provider failure keeps the local preview available and visibly reports the downgrade. No automatic online reconnection or paid fallback was introduced.
- The optional browser picker is invoked directly from the Start click, without a preceding blocking confirmation dialog. Stops, disconnected tabs, stale frames and cancelled starts invalidate the session. Rate limiting delays the next frame instead of treating it as a permanent failure. Sharing has no silence or duration timeout.
- Session logs record capture start, first frame, stop reason, provider failure and safe client failure stage/code. They never store image bytes. Tool results now include their returned error as well as their code. Existing bounded three-session retention remains.
- Browser profiles use an exclusive Windows handle with deletion on close or process exit. A stale empty legacy lock can be recovered, while a live lock holder remains protected. Chromium profile contention is identified separately. There is no silent alternate profile or forced termination of another browser.
- Gemini credentials now follow environment, .env, user-local key and local key precedence. Explicit empty values disable online access. The gate rereads configuration on checks, and unreadable credentials fail without revealing their contents. No credentials were copied into the portable package.
- Settings schemas describe the actual accepted kinds and values. Window and control schemas identify where opaque IDs must come from. Invalid inspections return current candidates instead of fabricating a usable window ID.
- Background watches validate the configured search provider before being saved. Provider mismatches are explained during inspection. Model-invented provider names no longer create doomed watches.
- Common capability checks execute deterministically through local tools. This includes Phase 1/2 status, audio endpoints, mouse speed, window inspection, watches, notification enable/disable, video metadata and opening the previously inspected video. Ambiguous window matches require selection. All mutations retain their existing confirmation boundary.
- Gemini Live text turns retain bounded conversation/tool evidence for follow-ups. This prevents a fresh turn from losing the previously returned identities. No additional reasoning provider was added.

## Verification

The full regression run passed 531 tests with the opt-in disposable Windows control fixture enabled. Eleven focused checks passed after the final capture UI adjustments, including a new Live-context regression. Tests cover local capture without Gemini, provider failure, explicit source selection, cancellation, stale frames, cleanup, UI preview, browser profile ownership, credential precedence and deterministic commands.

The actual portable Python runtime performed a real Windows capture, producing a 1280-by-720 JPEG in memory, then cleared it. It launched, inspected and closed a supervised browser in a temporary profile; enumerated 36 Windows audio endpoints (including inactive/system endpoints); retrieved three usable WebView2 documentation links through tavily_keyless; and retrieved official YouTube oEmbed metadata. No captured private image or credential was saved in the evidence.

The relocated portable application passed the desktop launcher checks: it started its own server, reused an existing valid server, rejected a foreign service on the configured port, and displayed a real WebView2 window with the graph rendered. Ownership and shutdown checks passed. The verification is retained in artifacts/portable-repair-desktop-verification.json. A manual end-to-end online screen conversation has not been claimed as verified.

## Updated build and use

The main code and dist/LUMINA-Portable-Phase2/app were updated. Its model configuration remains gemini-3.1-flash-live-preview. Existing configuration, uploaded files, notes, watches and credentials were preserved. Earlier portable code is backed up under artifacts/portable-repair-backup-20261008-201258. The executable remains unsigned.

Restart the old LUMINA backend and window before opening the Phase 2 executable. Click Share screen, choose the actual monitor or window, and click Start sharing. Leave online viewing unchecked to verify the free local preview. Stop sharing, then start again with Enable online viewing checked to permit frames to reach the configured reasoning provider. A description of arbitrary screen content still requires that provider; local capture does not pretend to understand the image.

Useful regression prompts: “List my audio endpoints.” “Inspect the Notepad window.” “Show me the status of every Phase 2 capability.” “Get metadata for https://www.youtube.com/watch?v=jNQXAC9IVRw.” Then: “Open this video in the supervised browser.”

Web search remains a separate retrieval tool using the configured non-Gemini provider. A free provider can still impose limits or become unavailable; those failures remain explicit.

Reference consulted: [Microsoft's WebView2 screen-capture lifecycle](https://learn.microsoft.com/en-us/dotnet/api/microsoft.web.webview2.core.corewebview2.screencapturestarting). The Windows-source capture path avoids dependence on the embedded browser picker while preserving explicit source selection.
