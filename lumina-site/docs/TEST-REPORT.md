# Test report

Machine: Windows 11 Pro, Intel UHD Graphics 620 (integrated), Node 24.12. Browser: Playwright's cached Chromium 156 (headless, hardware GPU via ANGLE/D3D11 — the renderer string in every run reports `Intel(R) UHD Graphics 620`). Tests ran on 22–23 October 2026.

Levels of evidence are kept separate below: **unit tests**, **end-to-end checks in a real browser**, **measurements**, and **visual review of screenshots**. Nothing here was tested on a physical phone or on a GPU other than the UHD 620.

## 1. Build and static checks

| Check | Command | Result |
|---|---|---|
| TypeScript (strict, no unused) | `npm run typecheck` | Pass, 0 errors |
| Production build | `npm run build` | Pass. Initial JS 57 KB (19.4 KB gz), CSS 40 KB (8.8 KB gz), 3D chunk 565 KB (144.5 KB gz, lazy), audio 5 KB (2 KB gz, lazy) |

## 2. Unit tests — demo engine and shared sequence math

`npm test` (Vitest) → **14 / 14 pass** (`src/demo/engine.test.ts`), independent of the DOM and of WebGL:

- empty / over-long / unrecognised requests rejected with honest messages
- every example request maps to its scenario; parameters extracted deterministically (e.g. "Tuesday at 3pm" → Tuesday 15:00)
- read-only scenario completes with no approval; changing parameters changes the answer
- approval gate: nothing after it runs while waiting; ticking time does nothing
- declining skips every remaining step
- preview-only / unsaved / low-risk runs need no approval; low-risk can be configured to ask
- simulated problem stops the run, is **not** retried automatically, and recovers only on explicit retry
- cancel mid-run
- identical inputs → byte-identical runs; previous states never mutated
- the action-loop progress function is monotonic, pauses at Approve, and matches the step views

## 3. End-to-end checks (real browser, production build)

`node scripts/e2e.mjs --url http://localhost:4183/` → **23 / 23 pass** (log: `test-artifacts/e2e-preview.log`).

| Area | What was exercised |
|---|---|
| Load | h1 present, 3D world reached `ready`, zero console errors for the whole session |
| Audio gating | No `AudioContext` exists before a click; Sound creates one (`running`), toggling off suspends it |
| Navigation | Every primary nav link lands its section at the top of the viewport |
| Reversibility | Store timeline, active chapter and action-step classes are identical at 8 positions going down and coming back up |
| Action loop | Badge reads "Waiting for you" at the approval pause, "Approved by you" after it |
| Memory | Inspect reveals details; Forget / Undo / Restore update both the list and shared state |
| Capabilities | Select / deselect; 9 working, 3 in development, 3 roadmap |
| Demo | Brief → approve → saved result with 7 evidence lines; compare quotes with and without shipping gives different, correct answers; decline changes nothing; simulated problem holds until Retry; free-text reminder; Stop mid-run |
| Explore | Destination buttons focus regions and fill the card; drag orbits without selecting; clicking the cloth selects a region; Reset clears |
| Keyboard | Skip link moves focus to `<main>`; capability cards and demo chips operate with Enter |
| Settings | Lite mode disposes WebGL and hides the canvas; Cinematic rebuilds it on a fresh canvas; Escape closes the panel |
| Reduced motion | `prefers-reduced-motion` honoured; 0 frames rendered while idle, renders on scroll |
| No WebGL | `getContext('webgl*')` forced to fail → fallback art, explanatory status, demo still completes, no errors |
| Mobile (390×844, touch) | Menu opens, navigates, closes; demo runs to the approval step; no horizontal overflow |

Also verified separately: the slow-device notice (forced via the dev hook) appears once, switches to Lite, persists the choice and disposes the renderer.

Audio was verified numerically, not by ear: plucked strings decay cleanly (peaks 0.64–0.82, no clipping, no non-finite samples), and live output is non-silent at the expected gain after enabling. **Nobody has listened to the mix yet.**

## 4. Performance measurements

`node scripts/perf.mjs` on the production preview, cache disabled, localhost (no network latency). Scroll test: a continuous scripted scroll through the entire page and back, three passes (~840 frames each).

| Profile | FCP | LCP | 3D ready | Transfer | Scroll frame time p50 / p95 / p99 | Frames > 33 ms (3 passes) | Heap before → after 3 passes |
|---|---|---|---|---|---|---|---|
| Desktop 1440×900 | 852 ms | 1004 ms | 1490 ms | 270 KB, 9 requests, 0 failed | 16.7 / 16.9 / 16.9 ms | 5 / 0 / 0 | 5.7 → 5.7 MB |
| Desktop, 4× CPU throttle (run 1) | 1356 ms | 1356 ms | 8.8 s | same | 16.8–33.3 / 83–100 / 117–150 ms | 272 / 218 / 262 | 5.4 → 5.7 MB |
| Desktop, 4× CPU throttle (run 2) | 1144 ms | 1144 ms | 9.6 s | same | 16.9–17.0 / 67–83 / 100–117 ms | 265 / 259 / 244 | 5.6 → 5.7 MB |
| Phone emulation 390×844 DPR 2, 4× CPU | 3348 ms | 3348 ms | 5.7 s | same | 17.5 / 35–52 / 53–71 ms | 208 / 193 / 180 | 5.3 → 5.4 MB |

Notes:

- The unthrottled desktop numbers were taken while another process was loading the machine; an earlier quiet run measured FCP 440 ms / LCP 524 ms with identical frame times.
- Idle cost: ~22 rendered frames/s with motion on (ambient shimmer cap), 0 with reduced motion.
- 8 draw calls, ~12.6k triangles; no adaptive downgrade was needed on the UHD 620.
- CPU throttling emulates a slow CPU only; the GPU is still the UHD 620. A CDP trace of a throttled scroll attributes the main-thread time roughly to JS + WebGL submission (11–15 ms per throttled frame across two traces), paint (≈5 ms), style (≈5 ms) and layout (≈1 ms after a fix that removed redundant DOM writes; ≈3 ms before).
- The phone-emulation row predates that DOM-write fix.

**Interpretation:** smooth (60 fps, no long frames after warm-up) on this integrated-GPU laptop. On CPUs roughly four times slower, the median frame stays at the refresh rate but p95 rises to 50–100 ms — visible stutter while scrolling. Mitigations shipped: automatic resolution reduction, a one-time offer to switch to Lite mode when the device stays slow, the Lite toggle in Settings, and reduced-motion mode.

## 5. Visual review

Screenshots from the production build are in `test-artifacts/shots/` with contact sheets `journey-desktop.jpg` and `journey-mobile.jpg`: every chapter at 1440×900, five chapters at 390×844, reduced-motion hero and Lite hero. Defects found during review and fixed: back-face-culled ribbons (nothing rendered), thread crossing the headline, memory knots hidden behind the inspector, memory details forced visible by CSS, pinned sections overflowing on 900 px screens, heddles seen edge-on, fabric reading as strikethrough behind the status note, Lite-mode strings invisible (gradient units), and 3D failing to restart after Lite mode.

## 6. Isolation

The project lives in `D:\R O C H A K\LUNA 3\lumina-site`. Outside it, this work added only `D:\R O C H A K\LUNA 3\.claude\launch.json` (preview server definitions). The Lumina application, `LUMINA-Recovered`, docs, data and credentials were only read.

During a pause in this session (23 Oct 08:02–08:14), another process wrote `.recovery/milestone5f/*` and new objects under the root `.git/objects`. Those were not written by this work.

## 7. Not tested

- Real phones and tablets (only emulation), Safari/WebKit and Firefox (cached builds exist but were not run), Windows High Contrast / forced colours, screen readers (semantics and labels were checked in code, not with NVDA/JAWS/VoiceOver), and other GPUs.
- Deployment, a real domain, CDN caching and HTTPS.
