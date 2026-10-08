# Supplied UI integration

The visual source is `E:\test\LUMINA-UI-Replacement.zip`, retained under `sources/ui-replacement`. The application uses its frame, circuit, gauge, brand and sphere artwork, plus its licensed fonts. It does not mount the prototype's sample-data, graph, messaging, SpeechRecognition or speech-synthesis runtime.

`web/reference.js` wraps the existing live controls. `reference-art.js` contains only extracted visual helpers. `reference-orb.js` adapts the supplied canvas renderer to the existing `constructor`/`setState` contract. `reference-source.css` preserves the supplied styling; `reference.css` adapts it to the real responsive layout. Embedded fonts were extracted to local WOFF2 files to preserve the existing content security policy. Backend, API, WebSocket, tool permissions and voice transport were not changed.

The sidebar's expand/collapse button is keyboard accessible, reports `aria-expanded`, and saves the choice in `lumina.sidebarCollapsed`. Collapsed items retain accessible names and tooltips. The Iron Man helmet, sidebar reactor badge and Stark branding are not rendered. Only measured CPU/agent/microphone data is displayed; unsupported sample metrics are omitted.

Source assets and fonts were copied to `dist/LUMINA-Portable/app/web` and verified by hash. Reload the browser or reopen the portable application to load the update.

Validation: `python -m pytest tests -q` passed all 132 application tests. Browser coverage includes expanded/collapsed navigation, persistence across reload, graph search with no camera movement, controls/settings, responsive widths from 390 to 2560, and JavaScript/console errors. Screenshots: `artifacts/crimson-1366.png`, `artifacts/crimson-1920.png`, `artifacts/reference-collapsed.png`.

A root-wide pytest discovery also found unrelated tests under the pre-existing `sources/tests` tree; those have missing fixtures/timezone data and separate branding checks. They were not altered to make this UI task pass. Physical audio, authenticated online providers, actual coding-agent runs and native portable-window rendering were not live-verified; automated tests use simulated providers where appropriate.
