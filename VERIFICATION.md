# Phase Two update

The current suite passes 38 tests, including browser checks. See PHASE2.md for current capabilities and limits. The record below describes the original prototype; its billing guard has since been removed at the user’s request. No real cloud inference or physical voice verification was performed in Phase Two.

# LUMINA verification

Run on **October 5, 2026**, on the available Windows host, using Python 3.13.12 and headless Chromium 153. The application was actually launched on `http://127.0.0.1:8764`; browser screenshots were inspected.

**Status:** local functionality and synthetic integration are verified. The full real-Gemini/physical-voice definition of done is **not yet satisfied**. No Gemini API key was available; no cloud inference request was made. No quota or billing change was attempted.

## Results

| Requirement | Evidence | Status |
|---|---|---|
| Server starts and serves the page | Actual `python -m lumina`; HTTP 200; browser loaded UI | Passed |
| Orb renders and stays framed | Inspected desktop, 390px-wide, and short-window screenshots; geometric framing assertions | Passed |
| Bounded, time-based animation | Shader clamps displacement to 16%; pure math checks at 120/60/30/1 FPS; all eight profiles exist | Passed (shader bound also inspected in source) |
| Authoritative runtime state | HTTP/WebSocket integration plus UI state checks | Passed |
| Typed request reaches real Gemini | Credentials absent | Not verified |
| Real Gemini responds | Credentials absent | Not verified |
| Gemini SDK structured tool loop | Real SDK objects with simulated transport; call arguments, function response and thought signature checked | Passed simulation; real service unverified |
| Live microphone PCM pipeline | Chromium fake microphone → real AudioWorklet → WebSocket → simulated provider; PCM chunks asserted | Passed synthetic test; physical microphone unverified |
| Native audio playback | Simulated 24 kHz PCM → actual browser AudioContext scheduling → runtime SPEAKING acknowledgment | Passed synthetic test; real Gemini audio/physical audibility unverified |
| Interruption | Synthetic speaking → Speak → LISTENING; playback state clears, PCM reaches provider; Stop closes session | Passed synthetic test; real Gemini cancellation unverified |
| Real filesystem results | Temporary real files/folders and the actual repository's `config.py` | Passed |
| Honest result counts | Matching folder does not count its unrelated child; context nodes excluded; partials labeled | Passed |
| Search-only graph | Exact/partial tool hits plus required parents; unrelated children absent | Passed |
| Parent connectivity | Every non-root node has an existing parent; links form a connected tree | Passed |
| Fit after simulation settles | Engine-stop callback gates fit; browser waits for settled graph before screenshot | Passed |
| Refresh cannot overwrite search | Deterministically delayed refresh finishes after search; revision/view remain unchanged; real UI refresh also tested | Passed |
| Offline degradation | Browser typed/voice notices; provider-unavailable test followed by successful local search | Passed |
| No hidden frontend CDN/service | Browser recorded no external requests; libraries served from local vendor directory | Passed |
| Filesystem security | Escaping symlink/junction excluded; names/schemas rejected; hidden files excluded | Passed |
| Local service boundary | Host/Origin rejection, mutation token, static-route traversal rejection | Passed |
| Billing guard | Paid, linked-account, missing, malformed proof and missing-key rejection tests | Passed with test data; live Google billing lookup unverified |
| Port conflict handling | Second process against occupied port printed port 8764, another-instance explanation and LUMINA_PORT guidance, without a traceback | Passed |

## Commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# 18 passed (includes synthetic browser voice integration)

node tests/motion.test.mjs
# Camera bounds, eight states, and 120/60/30/1 FPS decay passed

.\.venv\Scripts\python.exe scripts/browser_check.py
# Page, local search, correct direct count, search-preserving refresh,
# Settings, unavailable-provider notices, responsive widths passed.
# No page errors or external requests.
```

Screenshots and machine-readable browser results are under `artifacts/`:

- `lumina-desktop.png`
- `lumina-search.png`
- `lumina-narrow.png`
- `lumina-short.png`
- `browser-report.json`

These are verification artifacts, not fabricated data or a substitute for testing the real provider.

## Remaining real-world acceptance check

1. Configure your actual notes root and review the Gemini project's quota and billing settings.
2. Put a valid Gemini API key in `.gemini-key` or `GEMINI_API_KEY`; no Google Cloud CLI or ADC is needed.
3. Launch LUMINA. With Spoken replies enabled, type “Find my respiratory notes.” Confirm Gemini selects `find_files`, actual hits appear, and the spoken count agrees with the direct count.
4. Repeat with Speak, the physical microphone, and the configured output device. Confirm the transcript and sound are correct.
5. While LUMINA speaks, click Speak and say a new request; confirm queued audio stops and the new turn is processed. Also test Stop.
6. Disable network access or use an unavailable model. Confirm a clear provider failure, no fallback, and a successful Local search afterward.

The repository does not bundle personal respiratory notes. Tests create clearly isolated temporary fixtures; the visible app searches only the root you configure.
