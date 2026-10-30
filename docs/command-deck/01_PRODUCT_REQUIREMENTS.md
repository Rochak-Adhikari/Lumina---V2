# Lumina Command Deck: Product Requirements Document (PRD)

**Document ID:** `CD-PRD-001`  
**Feature:** Lumina Command Deck (`CD`)  
**Status:** Product Requirements / Approved for Pre-Implementation  
**Target System:** Lumina AI Companion Dashboard (`Lumina---V2`)  
**Author:** AI Systems Engineering Product Management Team  

---

## 1. Product Definition & Vision

### 1.1 Problem Statement
In the existing Lumina companion experience, users interact primarily through the conversational presence (the interactive 3D orb, voice pipeline, and chat stream) and the semantic knowledge graph. While these capabilities deliver high conversational engagement and knowledge visualization, they leave an operational gap:

> **When Lumina is executing tasks, delegating to autonomous workers, or experiencing backend failures, the user lacks a clear, single-pane-of-glass operational readout answering:**
> 1. *"What is Lumina executing right now?"*
> 2. *"What background tasks are running, queued, or blocked?"*
> 3. *"What recent tools ran, and did they succeed or fail?"*
> 4. *"Are there pending security approvals or dangerous operations requiring my attention?"*
> 5. *"Is the local runtime healthy and synchronized?"*

Without an operational command center, background worker actions feel opaque, connection drops can be confusing, and task failures require digging into terminal logs.

### 1.2 Target User & Usage Scenarios
- **Primary User:** Software engineers, technical researchers, and power users who employ Lumina as a local AI companion for code analysis, file organization, autonomous task delegation, and knowledge synthesis.
- **Scenario A (Autonomous Task Monitoring):** The user instructs Lumina to delegate a multi-file refactoring job to an agent (`claude-code`). The user opens the Command Deck to track task progress, review modified files, and inspect exit codes without interrupting the main conversation orb.
- **Scenario B (Safety & Approval Review):** An autonomous tool requests deletion of temporary files. The user notices the amber badge in the Command Deck, views the pending action, inspects the target paths, and navigates to the confirmation modal to grant or deny access.
- **Scenario C (Diagnostics & Error Recovery):** A network interruption disconnects the online Gemini provider. The Command Deck prominently displays "Attention Needed", indicates that local tools remain operational, and details the exact provider reconnection status.

### 1.3 Product Goals & Non-Goals

#### Core Goals:
1. **Total Observability:** Provide complete visibility into runtime lifecycle states, active tools, agent tasks, and recent operational events.
2. **First-Class Integration:** Integrate natively into Lumina's existing navigation rail and dialog system using the established dark crimson theme.
3. **Operational Clarity:** Distinguish clearly between healthy, degraded, disconnected, stale, and failed states.
4. **Safety Preservation:** Preserve Lumina's strict human authorization boundaries and emergency stop mechanisms without introducing security shortcuts.
5. **Zero-Lag Performance:** Maintain lightweight client-side rendering with bounded memory and zero unnecessary background polling.

#### Non-Goals:
- **Not a Replacement Dashboard:** It does not replace the main conversational presence, 3D orb, or knowledge graph.
- **Not a Process Manager:** It does not start arbitrary Windows processes, kill OS threads, or manage system services.
- **Not a Full-Fledged IDE:** It does not provide code editors, syntax highlighting engines, or diff editors.
- **Not a Cloud Admin Console:** It does not monitor external fleets, servers, or cloud infrastructure. It observes only the local Lumina workstation instance.

### 1.4 Relationship to Existing Lumina Panels

| Panel | Core Question Answered | Primary Artifacts |
|---|---|---|
| **Chat / Presence** | *"What are we talking about right now?"* | 3D Orb, live transcription, conversational turns. |
| **Knowledge** | *"What concepts and file relationships does Lumina know?"* | 3D WebGL semantic graph, file search results. |
| **Memory & Continuity** | *"What past facts, decisions, and beliefs are preserved?"* | Fact evidence, belief history, contradiction audits. |
| **Workers** | *"What worker processes are configured?"* | Worker adapter listings, terminal logs. |
| **Settings** | *"How is Lumina configured?"* | Audio devices, provider keys, root paths. |
| **COMMAND DECK (New)** | ***"What is Lumina doing right now, what happened recently, and what requires my action?"*** | **Live status, task queue, activity timeline, system watch alerts.** |

---

## 2. Detailed User Stories

- **US-001 (Checking Active State):** As a user, I want to see Lumina's current operational state (Ready, Listening, Thinking, Executing) at a glance so that I know whether Lumina is actively processing my request.
- **US-002 (Task Progress Tracking):** As a developer, I want to see all active and recently completed worker tasks with their execution times and status so that I can monitor background coding agents without switching to a terminal.
- **US-003 (Error Investigation):** As a user, I want to review recent failures with sanitized error messages so that I can understand why an operation failed without opening Python log files.
- **US-004 (Pending Approval Discovery):** As a security-conscious user, I want to be immediately notified of pending L2–L4 permission requests so that I can approve or reject consequential operations before they time out.
- **US-005 (Workspace Context Verification):** As a user working in multiple directories, I want to verify which directory Lumina is currently bound to so that I don't accidentally run operations in the wrong project.
- **US-006 (Stale Data Recognition):** As a user experiencing network hiccups, I want stale indicators to appear if the runtime disconnects so that I don't act on outdated task information.
- **US-007 (Quick Diagnostics Copy):** As a developer filing an issue, I want to copy a sanitized diagnostic summary of a failed task to my clipboard with a single click.

---

## 3. Feature Priorities & Release Scope

Features are categorized using the MoSCoW method and mapped to stable feature identifiers:

### 3.1 Priority Classifications

| Feature ID | Feature Name | Priority | Justification & Dependencies |
|---|---|---|---|
| **CD-F001** | **Live Status Readout** | **P0** | Essential core requirement. Data readily available from `Runtime.state` and WebSocket snapshots. Zero architectural risk. |
| **CD-F002** | **Mission Control (Task Queue)** | **P0** | Primary operational value. Displays background agent tasks from `TaskManager.list_tasks()`. Directly answers user need. |
| **CD-F003** | **Activity Feed (Timeline)** | **P0** | Real-time stream of runtime, tool, and task events. Backed by `Runtime.audit` and WebSocket broadcasts. |
| **CD-F005** | **System Watch (Alerts & Health)** | **P0** | Surfacing errors, disconnects, and pending approvals is critical for operational reliability and user safety. |
| **CD-F008** | **Connection Recovery & Sync** | **P0** | Essential for robust real-world use. Ensures the UI recovers gracefully when WebSocket reconnects. |
| **CD-F004** | **Workspace Monitor** | **P1** | Useful project context display. Reads `Config.root` and `uploaded_files`. Low effort, high contextual value. |
| **CD-F006** | **Task Detail Drawer** | **P1** | Allows expanding a task to inspect instructions, exit code, and modified files. Read-only modal/drawer. |
| **CD-F007** | **Activity Filters (Category)** | **P1** | Client-side filtering of the event timeline (All, Tasks, Tools, Safety, System). Enhances usability. |
| **CD-F009** | **Instantaneous Machine Telemetry** | **P2** | Displays live CPU utilization sampled from existing `lumina/telemetry.py`. Purely informational. |
| **CD-F010** | **Task Cancellation Request** | **P2** | Triggers existing 2-step task cancellation through `POST /api/tasks`. Requires strict confirmation handling. |
| **CD-F011** | **Historical Log Browser** | **Deferred** | Browsing old sessions from disk is complex and already partially served by `session_log.py`. |
| **CD-F012** | **Custom Widget Layouts** | **Deferred** | Configurable drag-and-drop dashboard adds excessive complexity with negligible operational value. |

---

## 4. Scope Boundaries & Subsystem Responsibilities

```
+-------------------------------------------------------------------------+
|                          LUMINA SUBSYSTEM BOUNDARIES                    |
+-------------------------------------------------------------------------+
|  COMMAND DECK (web/command-deck.js)                                     |
|  - Renders unified operational UI                                       |
|  - Aggregates live events into bounded client buffer (max 150)          |
|  - Formats relative timestamps and status badges                        |
|  - Routes approval clicks to authoritative confirmation dialog          |
+-------------------------------------------------------------------------+
                                    |
                                    v (Read-only queries / 2-step actions)
+-------------------------------------------------------------------------+
|  AUTHORITATIVE BACKEND SERVICES                                         |
|  - lumina/runtime.py: State machine, tool execution, event broadcasting |
|  - lumina/tasks.py: Task session lifecycle, cancellation token logic    |
|  - lumina/control_authority.py: Security boundaries, permission checks  |
|  - lumina/session_log.py: Server-side audit logging & regex redaction   |
+-------------------------------------------------------------------------+
```

---

## 5. Success Criteria & Quality Metrics

1. **Functional Completeness:** All P0 user stories successfully executed in manual QA.
2. **Zero Inventions:** All presented data fields map directly to verified existing backend sources.
3. **Theme Uniformity:** Passes visual inspection matching the `--lumina-*` design tokens from `web/crimson.css`.
4. **Performance Integrity:**
   - Panel open latency < 100ms.
   - Client memory consumption bounded (< 15MB heap addition over 2-hour session).
   - Zero CPU usage when panel is closed.
5. **Safety Preservation:** Zero bypass of existing approval gates. Emergency stop latch tested and functional.
