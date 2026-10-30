# Lumina Command Deck: Features & Behaviors Specification

**Document ID:** `CD-SPEC-001`  
**Feature:** Lumina Command Deck (`CD`)  
**Status:** Functional Specification / Pre-Implementation  
**Target System:** Lumina AI Companion Dashboard (`Lumina---V2`)  
**Author:** AI Systems Engineering Architecture Team  

---

## 1. Feature Index & Architecture Mapping

| Feature ID | Feature Title | Section / Group | Target Release Priority | Feasibility Rating | Authoritative Source |
|---|---|---|---|---|---|
| **CD-F001** | Live Status Engine | Feature Group A | **P0 (Must-Have)** | **READY** | `Runtime.state`, `GET /api/state`, `/ws` |
| **CD-F002** | Mission Control (Tasks) | Feature Group B | **P0 (Must-Have)** | **READY** | `TaskManager.list_tasks()`, `/api/tasks` |
| **CD-F003** | Operational Activity Feed | Feature Group C | **P0 (Must-Have)** | **READY WITH ADAPTER** | `Runtime.audit`, WebSocket event stream |
| **CD-F004** | Workspace Context Monitor | Feature Group D | **P1 (Should-Have)**| **READY** | `Config.root`, `uploaded_files`, continuity |
| **CD-F005** | System Watch & Alert Center | Feature Group E | **P0 (Must-Have)** | **READY WITH ADAPTER** | `Runtime.state.errors`, `pending`, safety |
| **CD-F006** | Task Diagnostics Drawer | Feature Group F | **P1 (Should-Have)**| **READY** | `TaskManager.read_agent_session()` |
| **CD-F007** | Activity Category Filters | Feature Group G | **P1 (Should-Have)**| **READY** | In-memory client ring buffer filter |
| **CD-F008** | Connection Recovery & Sync | Feature Group H | **P0 (Must-Have)** | **READY WITH ADAPTER** | WebSocket lifecycle & snapshot reconcile |

---

## 2. Feature Group A: Live Status Engine (`CD-F001`)

### 2.1 Purpose & User Value
Provides an instant, high-level operational pulse of the Lumina companion. Enables the user to confirm at a single glance whether Lumina is connected, what cognitive state it occupies, whether a tool is actively executing, and if human approvals are pending.

### 2.2 Inputs & Authoritative Data
- **Transport State:** `ws.readyState` from `web/app.js`.
- **Cognitive State:** `Runtime.state['state']` from `/api/state` or push event `type: 'state'`.
- **Active Tool:** `Runtime.state['current_tool']`.
- **Reasoning Provider Status:** `Runtime.state['provider_status']` (`connected`, `local`, `failed`, `unavailable`).
- **Pending Approvals Count:** Length of `rt.tools.pending` or pending confirmations in state.
- **Heartbeat & Revision:** `Runtime.state['revision']` and client-recorded epoch timestamp of last received packet.

### 2.3 UI Presentation & Visual States
Rendered at the top of the Command Deck as a grid of compact, glowing telemetry telemetry readouts:
1. **Core Status Badge:**
   - `IDLE` -> Mint pill badge: `● READY`
   - `LISTENING` -> Cyan pill badge: `● LISTENING`
   - `THINKING` -> Pulsing amber badge: `▲ PROCESSING`
   - `EXECUTING` -> Crimson glowing badge: `◆ RUNNING: <tool_name>`
   - `WAITING_FOR_USER` -> Flashing amber badge: `⚠ ACTION REQUIRED`
   - `ERROR` -> Solid crimson badge: `✖ SYSTEM ATTENTION`
2. **Provider Indicator:** Displays "Online: Gemini Live" or "Local Mode (Offline-Safe)".
3. **Approvals Readout:** If count > 0, renders a glowing amber button: `[1 PENDING APPROVAL]`.
4. **Data Freshness Tag:** Shows relative age: `Updated 2s ago`. If age > 25s, displays red `[STALE]`.

### 2.4 User Interactions
- Clicking the `[PENDING APPROVAL]` button dispatches `lumina-event: {type: 'confirmation_open'}` which opens Lumina's existing authoritative approval modal.
- Hovering over the cognitive badge displays the underlying numeric revision counter and state transition timestamp.

### 2.5 Edge Cases & Failure Handling
- **WebSocket Disconnection:** Core status immediately switches to `DISCONNECTED (RECONNECTING...)` in muted grey/red; tool status displays `Unavailable`.
- **State Transition Race:** High-frequency state oscillations are debounced by 50ms before triggering DOM updates.

### 2.6 Acceptance Criteria
- [ ] Core status reflects the exact runtime state (`IDLE`, `EXECUTING`, etc.) within 100ms of a state change.
- [ ] Active tool name is correctly displayed during execution and cleared when execution finishes.
- [ ] Disconnecting the backend immediately updates the UI to "Disconnected" without crashing.

---

## 3. Feature Group B: Mission Control / Task Manager (`CD-F002`)

### 3.1 Purpose & User Value
Exposes all background worker sessions and autonomous coding tasks managed by `TaskManager`. Users can monitor task duration, review output summaries, and detect failed agent runs without opening a CLI.

### 3.2 Inputs & Authoritative Data
- Data fetched from `GET /api/tasks` returning `{'workers': [...], 'tasks': [...]}`.
- Live updates received via WebSocket push events: `type: 'agent_result'`.
- Session attributes consumed: `task_id`, `worker`, `status`, `summary`, `instruction`, `created_at`, `completed_at`, `error`.

### 3.3 UI Presentation & Table/Card Layout
Displayed in the main left-hand column of the Command Deck as a scrollable card stack:
- **Card Header:** Worker avatar/tag (`[Claude Code]`, `[Tmux]`), task ID snippet (`#9f8b2c`), and status badge.
- **Card Body:** User's original prompt/instruction (truncated to 2 lines with ellipsis).
- **Progress / Outcome:** Latest summary reported by the adapter.
- **Timestamps:** Start time, duration (`2m 14s`), or completion timestamp.
- **Actions:** 
  - `[Inspect]` -> Opens Task Diagnostics Drawer (`CD-F006`).
  - `[Cancel]` -> Only visible if status is `RUNNING`; invokes existing 2-step cancellation flow.

### 3.4 State Transitions & Workflow
```
[Task Spawned] ---> RUNNING ---> (Completes) ---> COMPLETED
                       |
                       +-------> (Needs Input) -> WAITING_FOR_USER
                       |
                       +-------> (Fails) -------> ERROR
                       |
                       +-------> (User Cancel) -> CANCELLING ---> CANCELLED
```

### 3.5 Edge Cases & Safety Boundary
- **Never Synthesize Success:** Successful completion is rendered ONLY if the backend explicitly reports `status: 'COMPLETED'`.
- **Destructive Action Safety:** Clicking `Cancel` does NOT send a direct termination signal. It invokes `POST /api/tasks` with `action: 'request_cancel'`, receives a temporary `confirmation_id`, prompts the user for explicit confirmation, and only then executes `action: 'cancel'`.

### 3.6 Acceptance Criteria
- [ ] Lists all tasks returned by `/api/tasks` on panel opening.
- [ ] Real-time updates update task status without requiring a manual refresh.
- [ ] Cancel button is disabled when task is already in `COMPLETED`, `CANCELLED`, or `ERROR` state.

---

## 4. Feature Group C: Operational Activity Feed (`CD-F003`)

### 4.1 Purpose & User Value
Provides an interactive, unified timeline of operational events across tools, tasks, system transitions, and safety fences, giving the user full visibility into Lumina's recent actions.

### 4.2 Inputs & Event Ingestion
- **Bootstrap Source:** `GET /api/audit` on panel open (fetches the last 100 audit events).
- **Live Stream:** WebSocket events:
  - `state` -> State change events.
  - `agent_result` -> Task progress events.
  - `confirmation` / `confirmation_resolved` -> Security events.
  - `capability_result` / `phase2_result` -> Tool execution events.
  - `notice` -> System alerts.

### 4.3 Deduplication & Ring Buffer Limits
- The client maintains an in-memory FIFO buffer capped at **150 events**.
- Older events are evicted automatically as new ones arrive.
- Deduplication prevents repeating identical events delivered via both REST bootstrap and live WebSocket push.

### 4.4 UI Presentation
- Chronological timeline rendered with distinct icon markers:
  - `◈` (Cyan): Task event
  - `⚙` (Muted): Tool execution
  - `⚠` (Amber): Security approval or warning
  - `✖` (Crimson): Failure or error
  - `✓` (Mint): Success or completion
- Each item includes: timestamp (`12:44:05`), category badge, concise summary, and an expandable chevron (`▶`) for details.

### 4.5 Acceptance Criteria
- [ ] Event stream renders newest events at the top or maintains smooth autoscroll.
- [ ] Buffer strictly caps memory at 150 items.
- [ ] Expanding an event reveals the sanitized JSON detail payload.

---

## 5. Feature Group D: Workspace Context Monitor (`CD-F004`)

### 5.1 Purpose & User Value
Eliminates ambiguity regarding which folder, project, or sandbox Lumina is currently operating within.

### 5.2 Behavior & Safe Display
- Displays the absolute path of `Config.root` and active project name.
- Truncates long paths visually (e.g. `d:/R O C H A K/.../LUNA 3`) with a click-to-copy button.
- Displays counts of uploaded files available in the active session.
- **Passive Guarantee:** Does NOT crawl disk directories or inspect file contents on open.

### 5.3 Acceptance Criteria
- [ ] Displays the exact configured root directory matching `GET /api/config`.
- [ ] Click-to-copy copies the true absolute path to clipboard and shows "Path copied." toast.

---

## 6. Feature Group E: System Watch & Alert Center (`CD-F005`)

### 6.1 Purpose & User Value
Surfaces critical faults, degraded dependencies, connection drops, and safety quarantines into a single unified health desk.

### 6.2 Monitored Vectors
1. **Runtime Faults:** `Runtime.state.errors` (contains any fatal exceptions or provider crashes).
2. **Safety Quarantines:** `control_safety.quarantined` or `unresolved` flags from `ControlAuthority`.
3. **Transport Drops:** Disconnected WebSocket or failed reconnect backoffs.
4. **Stale Observation Warnings:** Perception or screen sharing capture timeouts.

### 6.3 Presentation & Alert Severity
- **P0 Critical (Crimson):** "Local Runtime Unreachable" or "Safety Latch Active".
- **P1 Warning (Amber):** "Online Provider Offline - Local Fallback Active" or "Pending Security Fences".
- **P2 Notice (Muted Cyan):** "Screen sharing disarmed".

### 6.4 Acceptance Criteria
- [ ] If `state.errors` is non-empty, a warning box appears in System Watch with the exact sanitized error text.
- [ ] Disconnecting the server immediately triggers a Critical Alert banner in the panel.

---

## 7. Feature Group F: Task Diagnostics Drawer (`CD-F006`)

### 7.1 Purpose & User Value
Provides deep diagnostic inspection for a selected task without cluttering the main task list.

### 7.2 Content Displayed
- Task UUID, Worker type, and Workspace directory.
- Full un-truncated initial user instruction.
- Process exit code and total elapsed execution time.
- List of modified files (`changed_files`), if reported by the worker adapter.
- Full error message or failure stack (redacted of secrets).
- `[Copy Diagnostics]` button formatted as a clean Markdown snippet for bug reporting.

---

## 8. Feature Group G: Activity Category Filters (`CD-F007`)

### 8.1 Behavior
A pill-button filter bar atop the Activity Feed:
- `[All (128)]`
- `[Tasks (14)]`
- `[Tools (85)]`
- `[Approvals (2)]`
- `[System (27)]`
Filtering is executed entirely in client-side memory with zero server requests.

---

## 9. Feature Group H: Connection Recovery & Sync (`CD-F008`)

### 9.1 Recovery Flow
1. **Drop Detected (`ws.onclose`):**
   - Retain current UI state.
   - Apply translucent overlay with glowing tag: `[RECONNECTING...]`.
   - Freeze relative timestamp timers.
2. **Reconnected (`ws.onopen`):**
   - Clear reconnecting overlay.
   - Refetch `GET /api/tasks` and `GET /api/audit` to reconcile events missed during the drop.
   - Dispatch `notice('Connection restored. Operational state synchronized.')`.

---

## 10. Evaluation of Optional Future Enhancements (Post-P0)

| Enhancement | Value Proposition | Engineering Complexity | Recommendation |
|---|---|---|---|
| **Real-time CPU Graph Canvas** | High visual appeal | Medium (requires Canvas 2D/WebGL ticker) | **Defer to P2** |
| **Full Session Log File Browser** | High for deep debugging | Medium (requires paging large log files) | **Defer to P2** |
| **Custom Draggable Panels** | Low operational value | Very High (requires complex layout engine) | **Reject / Out of Scope** |
| **Task Re-run / Forking** | Moderate convenience | High (requires reconstructing prompts safely) | **Defer to Post-V2** |
