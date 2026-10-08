# Crimson Core presentation

The existing ES-module frontend is retained. `web/crimson.css` holds the centralized palette and responsive presentation; `web/shell.js` delegates navigation to existing controls. No backend endpoint, permission policy, provider configuration, worker launch logic or audio capture implementation changed.

The shell adds an accessible navigation rail, environment actions, conversation console, compact measured telemetry, and restrained orbital framing. CPU and agent readouts share the existing telemetry request; unavailable values disappear. The semantic graph preserves community/relation colors, hyperedge hubs, direct-hit filtering, node cap, and main-component framing. Search wording now describes concepts and source files accurately. The grid is decorative, not telemetry.

Updated assets are copied to `dist/LUMINA-Portable/app/web`; reopen the portable app or reload the browser to load them. No executable rebuild is needed for these external web assets.

Validation: browser layout/navigation checks cover 2560×1440, 1920×1080, 1600×900, 1440×900, 1366×768 and 390×844. Screenshots are in `artifacts/crimson-1920.png` and `artifacts/crimson-1366.png`. Browser checks exercise the real local server and existing dialogs; provider/audio integration tests use simulated providers.

The initial full regression run exposed a timing assumption in `test_synthetic_browser_capture_playback_and_barge_in`: the test closed the fake microphone before its first tone passed VAD. The test now waits for actual PCM arrival with a six-second bound, retaining the PCM assertions. The focused audio and layout run passed all three tests; the presentation/settings/knowledge regression run passed eleven tests. No production voice code changed.

Physical microphone/speaker operation, authenticated Gemini, actual coding-agent execution, native portable-window rendering and frame-rate/CPU benchmarks were not live-verified by this redesign. Portable asset hashes match the source assets.

Final full regression: 132 tests passed in 79.51 seconds.
