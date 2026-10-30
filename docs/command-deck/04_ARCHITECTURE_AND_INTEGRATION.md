# Lumina Command Deck: Architecture & Integration Specification

**Document ID:** `CD-ARCH-001`  
**Feature:** Lumina Command Deck (`CD`)  
**Status:** Architecture Specification / Pre-Implementation  
**Target System:** Lumina AI Companion Dashboard (`Lumina---V2`)  
**Author:** AI Systems Engineering Architecture Team  

---

## 1. Executive Summary & Repository Findings

This specification establishes the software architecture and integration contract for the **Lumina Command Deck** (`CD`), a first-class operational command and observability panel inside the existing Lumina web dashboard.

### 1.1 Verified Repository Facts

Inspection of the actual Lumina codebase (`d:\R O C H A K\LUNA 3`) confirms the following architectural realities:

1. **Frontend Architecture:**
   - **Zero-build ES Modules:** No Webpack, Vite, Next.js, Babel, or bundling step. Scripts are loaded natively via `<script type="module" src="/assets/app.js">` in `web/index.html`.
   - **Framework:** Vanilla JavaScript (ES2022+) manipulating native DOM elements. No React, Vue, or Angular.
   - **Styling:** Vanilla CSS split across modular files (`style.css`, `crimson.css`, `hud.css`, `telemetry.css`, `reference.css`, `upload-workspace.css`). Design variables are declared in `:root` in `web/crimson.css`.
   - **Panel UI Primitives:** Existing overlays (Memory/Continuity, Settings, Local Controls, Upload Workspace) use the native HTML `<dialog>` element with standard header, body, and action controls.
   - **Event Bus:** Cross-module communication uses the browser's native `window.dispatchEvent` and `window.addEventListener('lumina-event', ...)` pattern.

2. **Backend Architecture:**
   - **Language & Runtime:** Python 3.12+ asynchronous engine running on `aiohttp.web`. Entry point is `lumina/__main__.py` calling `serve(config)` in `lumina/server.py`.
   - **State Machine:** Governed by `Runtime` in `lumina/runtime.py` maintaining eight discrete states: `IDLE`, `LISTENING`, `THINKING`, `EXECUTING`, `SPEAKING`, `INTERRUPTED`, `WAITING_FOR_USER`, and `ERROR`.
   - **Task Coordination:** `TaskManager` in `lumina/tasks.py` coordinates worker tasks (`claude-code`, custom workers) with session objects, lifecycle states (`RUNNING`, `WAITING_FOR_USER`, `COMPLETED`, `ERROR`, `CANCELLED`, `CANCELLING`, `CANCEL_FAILED`, `REMOVING`, `REMOVED`), and two-step confirmation for destructive mutations (`request_cancel`, `cancel`, `request_remove`, `remove`).
   - **Safety Enforcement:** `ControlAuthority` in `lumina/control_authority.py` implements L0–L4 tool permissions, blocked effects (`@blocked_effect`), emergency stop latching (`request_stop()`), and explicit human approval fences (`confirm` endpoint).
   - **Logging & Redaction:** `SessionLog` in `lumina/session_log.py` implements bounded, local JSON-lines session records (max 3 files, 1MB cap per session) with automated regex redaction for API keys, tokens, and credentials.
   - **Event Transport:** Real-time push over WebSocket at `/ws?token=<session_token>` with automated 20s heartbeat and JSON message envelope. Full state snapshots are delivered on connection via `rt.snapshot()`.
   - **Authentication:** Local session token generated at startup, supplied via `X-Lumina-Token` HTTP header for REST and `?token=` query parameter for WebSockets. Local loopback binding only (`127.0.0.1`).

3. **Desktop Shell:**
   - C# .NET 9 WinForms wrapper (`desktop/Program.cs`) hosting Microsoft WebView2, managing the Python backend process lifecycle, and enforcing loopback communication.

---

## 2. Architectural Blueprint & Component Topology

The Command Deck is architected as a lightweight, modular client-side controller and rendering suite (`web/command-deck.js` and `web/command-deck.css`) backed by Lumina's existing REST and WebSocket APIs. 

No new backend microservices, independent databases, or heavyweight client frameworks are introduced.

### 2.1 Component Diagram

```mermaid
graph TD
    subgraph Browser Frontend (ES Modules)
        NavRail[Nav Rail: #workspace-navigation]
        Topbar[Topbar: Status Dot & Header]
        ShellJS[web/shell.js: Navigation Router]
        AppJS[web/app.js: Global Orchestrator & WS Client]
        
        subgraph Command Deck Module (web/command-deck.js)
            CDController[Command Deck Controller]
            CDStore[In-Memory Ring Buffer & State Store]
            
            subgraph Presentation Sections
                SecLive[Live Status Section]
                SecMission[Mission Control Section]
                SecFeed[Activity Feed Section]
                SecWorkspace[Workspace Monitor Section]
                SecWatch[System Watch Section]
                SecDrawer[Task Detail Drawer]
            end
        end
    end

    subgraph Backend Services (aiohttp / Python 3.12)
        Server[lumina/server.py: Route & WS Handlers]
        Runtime[lumina/runtime.py: Runtime Core & Event Dispatcher]
        Tasks[lumina/tasks.py: TaskManager & Session State]
        Safety[lumina/control_authority.py: ControlAuthority]
        Audit[lumina/session_log.py: SessionLog & Audit Ring]
        Telemetry[lumina/telemetry.py: MachineLoad]
    end

    NavRail -->|Click / Keydown| ShellJS
    ShellJS -->|Open Panel| CDController
    AppJS -->|lumina-event / WS message| CDController
    CDController --> CDStore
    CDStore --> SecLive
    CDStore --> SecMission
    CDStore --> SecFeed
    CDStore --> SecWorkspace
    CDStore --> SecWatch
    CDStore --> SecDrawer

    CDController -->|GET /api/tasks| Server
    CDController -->|GET /api/audit| Server
    CDController -->|GET /api/telemetry| Server
    AppJS <-->|WebSocket: /ws| Server
    Server <--> Runtime
    Runtime <--> Tasks
    Runtime <--> Safety
    Runtime <--> Audit
    Runtime <--> Telemetry
```

---

## 3. Integration Points with Existing Lumina Subsystems

### 3.1 Navigation Registration Strategy

Lumina's dashboard uses a vertical navigation rail (`<nav class="nav-rail" id="workspace-navigation">`) defined in `web/index.html` and managed by `web/shell.js`.

To integrate the Command Deck seamlessly alongside Memory, Knowledge, and Settings, the following registration sequence is specified:

1. **HTML Markup (`web/index.html`):**
   - Insert the Command Deck nav button between **Workers** and **Workspace** or directly before **Memory**:
     ```html
     <button id="command-deck-open" type="button" aria-label="Command Deck" title="Command Deck">
       <span aria-hidden="true">⌘</span>
       <span>Command Deck</span>
     </button>
     ```
   - In the topbar header action buttons (`<header class="topbar">`):
     ```html
     <button class="icon-button" id="command-deck-topbar-open" aria-label="Open Command Deck">Deck</button>
     ```
   - Insert the Command Deck container dialog into `web/index.html`:
     ```html
     <dialog id="command-deck-panel" class="command-deck-modal" aria-labelledby="command-deck-title">
       <div class="dialog-head">
         <div class="cd-title-group">
           <h2 id="command-deck-title">COMMAND DECK</h2>
           <span class="cd-subtitle">OPERATIONAL COMMAND CENTER</span>
         </div>
         <button id="command-deck-close" aria-label="Close Command Deck">×</button>
       </div>
       <div id="command-deck-body" class="command-deck-grid">
         <!-- Modular section containers rendered dynamically -->
       </div>
     </dialog>
     ```

2. **SVG Icon Injection (`web/shell.js`):**
   - In `web/shell.js`, map `'command-deck-open'` to a futuristic command radar/deck icon:
     ```javascript
     paths['command-deck-open'] = 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5';
     ```

3. **Orchestrator Setup (`web/app.js`):**
   - Import and initialize the Command Deck module in `web/app.js`:
     ```javascript
     import {setupCommandDeck} from './command-deck.js';
     // ...
     const commandDeck = setupCommandDeck({
       getConfig: () => config,
       notice,
       send
     });
     ```

### 3.2 State Ownership and Lifecycle Cleanup

- **Zero Global Pollution:** The Command Deck encapsulates its internal state inside a closure or class instance in `web/command-deck.js`.
- **Event Listeners:** All subscriptions to `window.addEventListener('lumina-event', ...)` or WebSocket dispatchers register clean unbind hooks. When the dialog closes (`dialog.close()`), background polling (e.g., telemetry sampling) is paused immediately to conserve resources.
- **Polling Discipline:** The Command Deck NEVER polls tasks or audit logs when the panel is closed. When opened, it performs a single fetch and relies exclusively on real-time WebSocket push notifications (`agent_result`, `state`, `confirmation`, `worker_event`) for live updates.

---

## 4. Source-of-Truth Matrix

Every visual indicator and readout in the Command Deck maps to a source-confirmed backend authority. No synthetic or hallucinated metrics are permitted.

| Display Field / Section | Authoritative Source | Transport Mechanism | Freshness & Latency Rule | Availability Status | Fallback When Unavailable |
|---|---|---|---|---|---|
| **App Connection Status** | `ws.readyState` in `web/app.js` | Direct client socket lifecycle | Instantaneous (<50ms) | **READY** | Display "Runtime Disconnected" + reconnection banner |
| **Runtime Lifecycle State** | `Runtime.state['state']` via `/api/state` | WebSocket `type: 'state'` & initial snapshot | Event-driven (push on change) | **READY** | Retain last known state tagged with "Stale" marker |
| **Current Active Tool** | `Runtime.state['current_tool']` | WebSocket `type: 'state'` | Event-driven | **READY** | Display `None (Idle)` |
| **Pending Approvals Count** | `rt.tools.pending` in `lumina/server.py` | Injected into snapshot / event `type: 'confirmation'` | Event-driven | **READY** | Display `0 Pending` |
| **Active / Recent Tasks** | `TaskManager.list_tasks()` via `GET /api/tasks` | REST on dialog open + push `type: 'agent_result'` | Immediate on open; push thereafter | **READY** | Display "Task manager idle / no active sessions" |
| **Task Status & Progress** | `_Session.status`, `summary`, `error` | REST `/api/tasks` + WS `agent_result` | Real-time push | **READY** | Display "Status unknown" |
| **Audit Activity Feed** | `Runtime.audit` via `GET /api/audit` | REST on open + client aggregator from WS | Bounded (last 100 events) | **READY WITH ADAPTER** | Fallback to session-only client ring buffer |
| **Workspace Root Path** | `Config.root` via `GET /api/config` | REST boot load | Static per process | **READY** | Display "Path not configured" |
| **Active Project Context** | `Runtime._continuity_workspace` | REST `/api/continuity?action=state` | On open | **READY** | Display "Default workspace root" |
| **CPU / Machine Load** | `MachineLoad.sample()` via `GET /api/telemetry` | REST poll (only when dialog open, 3s interval) | Sampled 3s | **READY** | Hide gauge or display "Telemetry unavailable" |
| **Screen Perception State** | `ScreenSharingManager` via `GET /api/screen-share/status` | REST on open + WS `screen_preview` | Event-driven | **READY** | Display "Screen perception inactive" |
| **Safety / Stop Latch** | `ControlAuthority.status()` via `snapshot()` | WebSocket `type: 'state'` (`control_safety`) | Event-driven | **READY** | Display "Safety authority: Normal" |

---

## 5. Security & Isolation Boundaries

To ensure the Command Deck does not introduce security vulnerabilities or become an accidental vector for privilege escalation:

1. **Read-Only Default:**
   Opening, viewing, filtering, or navigating the Command Deck executes zero mutations. No background processes are spawned, no filesystem operations are performed, and no network requests outside loopback are initiated.

2. **Strict Authority Isolation:**
   - The Command Deck does not possess or store OS execution credentials.
   - Any operational action triggered from the Command Deck (such as requesting task cancellation via `POST /api/tasks`) MUST follow Lumina's existing two-step authorization token sequence (`request_cancel` -> receives 60s `confirmation_id` -> user confirms -> `cancel`).

3. **Session Token Enforcement:**
   Every HTTP request generated by `command-deck.js` includes the runtime session token via `headers: {'X-Lumina-Token': config.token}`. Missing or invalid tokens result in `403 Forbidden`.

4. **DOM Injection Protection:**
   All diagnostic outputs, task summaries, error messages, and filenames are rendered strictly using `node.textContent` or pre-escaped text nodes. `innerHTML` is strictly prohibited on dynamic strings to eliminate cross-site scripting (XSS) risks.

5. **Diagnostic Data Redaction:**
   Logs and diagnostic traces displayed in the Command Deck pass through the server-side redaction filters established in `lumina/session_log.py` (`_safe()` function), ensuring API keys, passwords, and authorization headers are never rendered in plain text.

---

## 6. Architecture Compliance Checklist

Before coding begins, the implementer must verify that the planned implementation adheres to:

- [x] No modifications to existing dashboard files except adding nav hook and container dialog.
- [x] Uses vanilla ES module imports without bundlers.
- [x] Uses existing dark crimson CSS variables from `web/crimson.css`.
- [x] Completely decoupled from model prompts or synthetic fallbacks.
- [x] Fully bounds client memory with FIFO ring buffers.
- [x] Implements fail-safe error boundaries preventing panel crashes from impacting main chat/voice orb.
