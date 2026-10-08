# Phase 2 — Automation and situational intelligence

Implemented against sections 6–10 of LEGACY_FEATURE_ROADMAP.md. This is not the older voice prototype also named Phase Two. Existing Phase 1, audio-device selection, camera, graph and worker behavior remain covered by regression tests.

## Delivered
- [x] Durable UUID web watches with explicit creation, quiet baseline, canonical multi-result fingerprints, pause/resume/remove, bounded retry and restart-safe outbox.
- [x] Typed Windows brightness, mouse speed, window state and endpoint volume/mute operations. Exact confirmation, previous values, read-back verification and stale-safe undo. Existing microphone/speaker selection is preserved.
- [x] Windows UI Automation inventory and expiring snapshots. Invoke and text entry use supported patterns, exact control identity, explicit optional foreground activation, geometry/focus checks and user-takeover detection. Mutations are serialized and helper processes are bounded.
- [x] YouTube search, keyless oEmbed metadata, configured Data API support, authorized captions and local SRT/WebVTT transcripts. Bounded summary context covers the transcript in sections with timestamp links and sampling disclosure. Saving requires confirmation and refuses overwrite.
- [x] Proactive master opt-in, quiet hours/timezone, cooldown, snooze, durable delivery IDs, aggregation, inbox dismissal and busy-conversation suppression. Monitor, worker and provider events never initiate actions or agents. Existing explicit reminders retain their established delivery path.
- [x] Five tools integrated into the existing registry and confirmation flow; runtime-owned scheduling and shutdown; Automation panel in the sidebar with selectable Windows targets and controls.
- [x] 464 tests passed with the opt-in disposable native Windows UI fixture enabled; no skipped tests in that full run.
- [x] Separate portable distribution created without overwriting the prior build.
- [x] Relocated portable launch verified: native WebView visible, owned server started and stopped, pre-existing LUMINA reused and preserved, foreign port occupant rejected, graph rendered.

## Live evidence
A temporary, nonpersistent acceptance watch queried Windows WebView2 documentation using tavily_keyless, saved a baseline and produced zero alerts. It was not installed in the user's runtime. Native mouse-speed read-back and same-value verified set/undo passed. Native audio inventory returned 36 endpoints (including inactive/system endpoints; this is not a claim of 36 physical devices). A disposable WPF application accepted a real UIA button invocation and private text entry; results did not expose the typed value. YouTube oEmbed returned Me at the zoo by jawed without credentials. Evidence is stored in artifacts/phase2-live.json. The native tests live in tests/test_phase2_windows.py.

## Honest limits
Packaging evidence is recorded in artifacts/phase2-desktop-package-verification.json. This verifies launcher lifecycle and rendering, not a human microphone/speaker conversation or every physical monitor setting.

- Monitoring runs while LUMINA's backend is running. Closing the owned backend pauses checks; stored watches recover on restart. This is not a Windows service.
- Deduplication and history are bounded. The outbox retains 512 events; unknown delivery is not automatically retried.
- Brightness depends on WMI-capable monitors. Unsupported/disconnected devices fail explicitly. The live setting test wrote the already-current mouse speed, not a different hardware setting.
- UIA supports accessible Invoke and Value controls. There is no raw-coordinate, arbitrary-shell, clipboard or privilege-elevation fallback. Windows can refuse foreground activation; stale controls require a new inspection.
- Official caption download requires OAuth video-edit permission. Arbitrary public-video transcripts are not universally available. Local SRT/WebVTT is supported without OAuth; its video association is user-supplied. Token refresh/setup is explicit, not automatic.
- Summarize returns bounded evidence for LUMINA's current conversational model, not a second model-generated answer. The panel labels this Summary context. Long captions may be sampled, with disclosure.
- Automatic YouTube viewing-time reminders and screen-behavior inference are not implemented. No watch, screen capture or notification opt-in is created by installation.
- Portable executable remains unsigned; existing WebView2 Evergreen is reused. No Windows security settings were changed.

## Try it
Close the old LUMINA application and its old backend before opening dist/LUMINA-Portable-Phase2/LUMINA.exe; otherwise the launcher may reuse that existing older backend. Select Automation in the sidebar. Create a public-topic watch, then enable notifications only if wanted. Inspect or pause the watch; Remove uses the existing confirmation dialog. Configure quiet hours in your timezone.

For settings, choose a setting and Find targets. Select an observed target, read its current value, then request a change. Review confirmation. A verified result supplies an undo record; Undo requires fresh confirmation and rejects independent changes.

For Windows controls, list windows, select the intended app and inspect it. Select a supported control, choose Invoke or Set text, then review the exact confirmation, including foreground activation. If the app changed meanwhile, inspect again.

For YouTube, paste a video URL and request Metadata. For captions without OAuth, supply a local .srt or .vtt path under permitted locations. Summary context returns timestamped excerpts. Missing captions are a limitation, not a successful analysis.

Useful voice prompts: “List my background watches.” “Watch for Windows WebView2 documentation updates every fifteen minutes.” “Pause that watch.” “Disable proactive notifications.” “List audio endpoints.” “Read the volume of that endpoint.” “Get metadata for this YouTube video.” Always use returned identities when several targets exist.
