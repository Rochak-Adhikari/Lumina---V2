# LUMINA

A Windows-first personal assistant: a crimson Three.js orb, a real filesystem graph, typed input, and an explicit microphone turn with Gemini Live audio. **The AI thinks. LUMINA acts.**

This is a small, runnable prototype. Local search and the interface work without an account or internet connection after installation. The Gemini integration is implemented, but real Gemini access and physical microphone/speaker operation have **not** been verified in this workspace with a real provider session. See [VERIFICATION.md](VERIFICATION.md) for the exact evidence and remaining acceptance checks.

See [PHASE2.md](PHASE2.md) for the new speaking policy, local controls, worker integration, and explicit limitations. Claude Code is the configured worker in this local configuration; it must already be installed and authenticated.

## Start on Windows

Requires Python **3.12 or newer**, Windows 11, and a modern browser with WebGL and AudioWorklet support (Edge or Chrome). There is no npm install, frontend build, or paid dependency.

Open PowerShell in this folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m lumina
```

Open **http://127.0.0.1:8764**. Stop the server with Ctrl+C. Subsequent launches only need the last command. `start.ps1` also creates the environment on first use and launches the app.

For a local-only installation, `pip install aiohttp==3.14.3` is sufficient. Install `requirements.txt` before selecting Gemini. Installation requires internet access; normal local operation does not. The JavaScript libraries and their licenses are already in `web/vendor/`.

## Choose the filesystem root

By default, LUMINA explores this project folder, not your entire computer. To point it at your own notes:

```powershell
Copy-Item lumina.example.toml lumina.toml
```

Edit `root` in `lumina.toml` using forward slashes, for example:

```toml
root = "C:/Users/YourName/Documents/Notes"
provider = "local"
```

Restart the server. Or override it for the current PowerShell session:

```powershell
$env:LUMINA_ROOT = 'C:\Users\YourName\Documents\Notes'
.\.venv\Scripts\python.exe -m lumina
```

Searches read **names and directory structure only**, never document contents. Hidden dotfiles, common dependency folders, symlinks, Windows junctions, and anything resolving outside the root are excluded. Unreadable directories, time limits, and entry limits are disclosed as incomplete scans.

## Use it

- **Find in your files** is a deterministic local search. It works offline without an AI provider. It never pretends Gemini interpreted your request.
- The message composer sends requests to the selected reasoning provider. In local mode, it explains that online reasoning is not configured.
- With Gemini configured, **Spoken replies** sends typed turns through Gemini Live so replies use native audio. Turn it off for the separate text model.
- **Speak** explicitly starts one microphone turn. Wait for “I’m listening,” then talk; click **Finish speaking** to submit the turn. Audio is streamed as mono, 16-bit PCM at 16 kHz through Python to the configured provider. No browser SpeechRecognition service is used.
- Clicking **Speak** during playback stops buffered speech and starts a new listening turn. **Stop** cancels current work and closes the voice session. There is no passive microphone capture, wake word, or always-listening mode. Merely speaking while the microphone is off cannot trigger interruption.
- Settings can enumerate microphone/speaker devices after browser permission. Device choices are saved only in this browser. Browsers without `AudioContext.setSinkId` use the Windows default output device.
- Drag the graph to orbit; scroll to zoom; select a node or result row to inspect/copy its path. Files are not opened or modified.
- Refresh preserves the active search. **Overview** explicitly returns to the root graph.

## Claude Code worker

The local configuration uses Claude Code for explicitly delegated substantial tasks. Open Local controls, choose the Claude Code worker, and start a task yourself. LUMINA invokes it inside the configured filesystem root with bounded output and a task timeout. It receives no Gemini API key, and it is never started by Gemini tool output. Cancel or close the task from Local controls if needed.

Voice settings include an explicit hands-free mode with local amplitude detection and a short audio pre-roll. A local browser voice can also be selected for runtime notifications, but only after you enable it; there is no hidden speech-recognition or paid speech fallback.

## Gemini and the zero-budget boundary

**The default is local mode. There is no paid fallback, alternate key, Vertex AI route, or grounding service.**

LUMINA uses the API key directly:

1. Read the configured Gemini API key.
2. Send requests directly to the Gemini Developer API.
3. Let Gemini return authentication, quota, model, or billing errors.

The key is read before text generation and Live connection. Quota exhaustion or unavailable models produce an explicit error; the provider is never switched automatically.

To enable online mode:

1. Use a Google AI Studio / Google Cloud project and review its quota and billing settings.
2. Create a Gemini Developer API key belonging to that project. Check model availability and free-tier access for your account and region.
3. Set the provider and API key for the current PowerShell session. The secure prompt avoids putting the key in command history:

```powershell
$env:LUMINA_PROVIDER = 'gemini'
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'Gemini API key' -AsSecureString)).Password
.\.venv\Scripts\python.exe -m lumina
```

The personal and portable voice model is `gemini-3.1-flash-live-preview`. Typed reasoning uses `gemini-3.1-flash-live-preview` because the 3.1 Live Preview endpoint rejects the non-Live `generateContent` API.

**Billing limitation:** LUMINA now connects directly with the API key. It does not inspect or control billing. Keep the key's project on the free tier or set usage limits in Google AI Studio or Google Cloud if you want to avoid charges. Local mode makes no inference calls and has no cloud usage charges.

**Cloud data:** when you choose Gemini, your prompts, enabled microphone audio, and requested tool results (matching filenames and paths) go to Google. File contents do not. Google may use free-tier data to improve its products; review the provider's current terms before sending sensitive material. There is no analytics or background cloud connection at startup.

Primary references used for the adapter and policy:

- [Gemini pricing and free-tier availability](https://ai.google.dev/gemini-api/docs/pricing)
- [Live audio, transcription and activity controls](https://ai.google.dev/gemini-api/docs/live-api/capabilities)
- [Structured Live tool calls](https://ai.google.dev/gemini-api/docs/live-api/tools)

## Configuration

`lumina.toml` is optional, loaded from the working directory, and ignored by Git. Every setting below has an environment override named `LUMINA_` plus the uppercase setting name. Environment variables win. `.env` files are deliberately **not** loaded.

| Setting | Default | Purpose |
|---|---|---|
| `provider` | `local` | Explicit selection: `local` or `gemini` |
| `root` | Current directory | Authorized filesystem boundary |
| `host` | `127.0.0.1` | Loopback only (`localhost`, `::1` also accepted) |
| `port` | `8764` | HTTP/WebSocket server port |
| `model` | `gemini-3.1-flash-live-preview` | Text reasoning model |
| `live_model` | `gemini-3.1-flash-live-preview` | Native audio model |
| `voice` | `Kore` | Provider-native voice |
| `assistant_name` | `LUMINA` | Runtime personality/display name |
| `user_name` | Empty | Optional form of address |
| `microphone_device` | `default` | Browser audio input device ID |
| `speaker_device` | `default` | Browser audio output device ID |
| `graph_limit` | `600` | Maximum graph nodes, allowed range 50–700 |
| `scan_limit` | `20000` | Maximum entries per bounded scan |
| `scan_seconds` | `5` | Scan deadline, allowed range 1–15 seconds |

`GEMINI_API_KEY` is the only online credential. The Windows desktop app reads it from `%LOCALAPPDATA%\LUMINA\.gemini-key`; development mode also accepts `.gemini-key` in the working directory. These local files are excluded from filesystem searches and never packaged. An explicit `GEMINI_API_KEY` environment value takes precedence, including an empty value. Keys are never exposed in `/api/config`, placed in frontend code, or printed by the application. Do not commit credentials or enable third-party HTTP debug logging with real credentials.

## Architecture

```text
Browser: Three.js orb + 3d-force-graph + microphone AudioWorklet + PCM playback
                         │ same-origin HTTP/WebSocket
Python runtime: authoritative state + cancellation + transcript + graph revisions
                         │                       │
Provider interfaces      │                  Tool registry / L0 permission
  intelligence           │                       │
  Live / speech input/output                find_files → bounded filesystem scan
         │                                       │
Gemini adapter ← structured tool results
```

- `lumina/config.py`: environment/TOML configuration and loopback validation.
- `lumina/filesystem.py`: Unicode-normalized name matching, ranking, direct counts, connected graph construction. All meaningful words are preferred; partial matches are explicitly marked. Folder descendants are not counted as hits unless they independently match.
- `lumina/tools.py`: tool declarations, permission/schema enforcement, cooperative cancellation, result size and timeout bounds. Includes bounded file reading, system information, allowlisted local opening, and exact external-address confirmation.
- `lumina/runtime.py`: the eight authoritative states, conversation, tool results, and graph ownership/revisions. Search commits invalidate in-flight refreshes.
- `lumina/providers/base.py`: replaceable intelligence, Live session, speech-input and speech-output protocols.
- `lumina/providers/gemini.py`: SDK calls, real function declarations/responses, preserved thought signatures, transcripts, PCM events, error mapping. `stream()` currently yields a complete buffered text turn; Live streams actual audio.
- `lumina/providers/budget.py`: direct API-key presence gate.
- `lumina/server.py`: HTTP/WebSocket transport and one active voice owner, independent Live receive/tool/input tasks, playback acknowledgments and interruption.
- `web/`: HTML/CSS/ES modules. Orb displacement is clamped to 16% of radius; framing uses vertical/horizontal field of view and a bounding sphere. Decay uses elapsed seconds. A ResizeObserver reframes each canvas. Speech pulses trigger on state edges, not repeated updates. The graph fits after simulation stops; stale revisions are ignored.

Core endpoints: `GET /api/state`, `GET /api/config`, `GET /api/graph`, `POST /api/refresh`, `POST /api/reset`, and `/ws`. Mutations require a per-process session token. Host and Origin checks reject DNS-rebinding/cross-origin browser access. No arbitrary shell, file-read, file-write, network-fetch, or destructive tool is available to the model. The service is for one trusted desktop user; it is not a hardened multi-user or remotely accessible server.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest -q
node tests/motion.test.mjs
# With the local-mode app running on port 8764:
.\.venv\Scripts\python.exe scripts/browser_check.py
```

Node is only used for the optional pure animation-math test, never to run/build the application. The browser checks save screenshots and a report in `artifacts/`. The synthetic voice test uses a simulated provider and Chromium's fake microphone. It does not consume Gemini quota.

## Operational limits

- LUMINA does not inspect billing. API usage follows the Gemini project attached to the key; check Google AI Studio or Google Cloud for quota and billing controls.
- The real Gemini/audio acceptance flow remains unverified until your credentials and hardware are available. No local STT or TTS engine is bundled, and offline reasoning/voice is not simulated.
- Search is name-only, bounded, and rescans per request. Counts cover the scanned entries. At most 100 ranked hits are returned; the graph is separately capped and may show fewer hits when parent chains consume the limit. Neither context folders nor visual descendants inflate counts.
- Directory entries can change during a scan. Junction/symlink containment protects normal desktop use; this is not a sandbox against a hostile local process racing filesystem metadata.
- Microphone mode is explicit tap-to-talk, not passive voice detection. Interruption uses the Speak/Stop controls. Live conversation context survives turns in the same session; stopping/disconnecting Live clears that provider session. The visible transcript is kept in memory until server restart, with a 40-message limit.
- Browser autoplay, permissions, device routing, provider session duration, and regional free-tier availability can prevent audio. A disconnect does not silently reconnect Gemini or replay a prompt.
- Refresh is root-bound and does not change an active search. Overview is an explicit reset. Other environment entities, content indexing, wake words, memory, autonomous work, and desktop control are deliberately outside this prototype.

If the port is occupied, LUMINA prints the port and asks you to check for another instance or change `LUMINA_PORT`. Authentication/quota/model errors remain visible in the transcript while local search stays available.
