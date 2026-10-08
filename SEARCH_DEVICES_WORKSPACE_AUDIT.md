# Search, device discovery and Workspace repair

2026-10-08

## Verified changes

Workspace has a dedicated sidebar entry which opens the existing persistent upload panel, using the same dialog/control architecture as Workers and Settings. The existing upload, selection and analysis logic is retained. A 1366×768 browser check confirmed that the panel is visible; the analysis input was expanded to the panel width.

Audio settings now request browser device access when names are hidden. The brief discovery stream is released in a finally block; it is not sent to Gemini. Discovery prefers a selected or identifiable built-in microphone, using the Windows default only when the browser hides identities. Closing settings invalidates a late discovery result. Authorized output selections are retained even if enumeration omits them. Device counts and browser output limitations are shown explicitly. Unsupported capture is distinguished from permission failure.

A full Chromium browser on this Windows machine discovered two real microphone endpoints and four real output endpoints after permission. Windows audio services were running. The lighter headless test browser could expose only default placeholders and rejected capture as unsupported; it is not evidence of a Windows hardware failure. Physical speaker audibility remains a user check.

Natural commands including “Search the web for…”, “Search online for…” and “…on the web” now route directly to the search tool without relying on a model to select it.

## Search provider change and blocker

The default is now gemini_grounded, using the existing Gemini Live model/account and Google's supported Google Search tool. The core search layer binds through a provider interface; Gemini-specific calls remain in its adapter. Only provider-supplied grounding source metadata becomes a search result. Generated URLs or a model's unsourced answer are not converted into evidence. Existing explicit Bing, Brave, DuckDuckGo or SearXNG settings remain authoritative. No account, key, paid fallback or alternate model was added.

Live probes confirmed that the old Bing feed returned empty results for both WebView2 documentation and Ryzen pricing queries. DuckDuckGo rejected the request; other public pages returned challenges or errors. No challenge bypass was attempted.

The real Gemini grounding request was refused with quota exhaustion during session setup. Therefore the replacement is implemented and covered by offline integration tests, but a successful live grounded search is NOT verified. It requires restored provider quota and grounding metadata from the configured model. If metadata is absent, the tool explicitly fails rather than inventing source links. This supersedes the previous audit's Bing-default description.

Official integration reference: https://ai.google.dev/gemini-api/docs/live-api/tools

## Test evidence

Full suite: 321 passed in 113.11 seconds. Focused tests cover sidebar navigation, automatic device discovery and probe cleanup, natural search routing, explicit provider preservation, quota reporting and rejection of generated links without grounding metadata. Existing speech, upload, reminders, workers and security regressions passed.

Subsequent changes were limited to the workspace input style and an explicit unsupported-browser error message; device and navigation checks were rerun afterward.

## User checks

Restart the Python runtime and reload the browser. The portable executable/distribution was not rebuilt.

Open Workspace from the sidebar, upload a harmless text file containing “The launch code is ORBIT 42”, and select it. Say “Show my uploaded files”, then “Read the selected uploaded file”. Its actual contents should appear. Refresh and confirm that the file remains listed.

Open microphone settings and allow the browser prompt if shown. Choose a real microphone, press Test microphone, speak, then stop the test. Choose a speaker and press Play test sound. Closing settings must release the probe/test microphone.

Say “Search the web for official Windows WebView2 documentation”. After quota is restored this must return attributable source links, or a specific provider failure. A quota error is currently expected and is not a passed search acceptance test.

Then say “Search online for Ryzen 7 5700X price in Australia”. Confirm that returned sources actually concern that processor and country. Do not accept invented prices or a generic manufacturer homepage as evidence. Search returns evidence; it does not independently verify stock or current checkout prices.

Say “Create a reminder in 30 seconds to check my audio settings” to check that the existing reminder path still works.
