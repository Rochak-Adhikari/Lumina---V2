# Lumina Command Deck: Comprehensive Specification Pack

**Official Feature Name:** Lumina Command Deck  
**Short Name:** `CD`  
**Panel Heading:** `COMMAND DECK`  
**Subline:** `OPERATIONAL COMMAND CENTER`  
**Document Pack Version:** 1.0.0 (Pre-Implementation Architectural Specification)  
**Target Repository:** Lumina AI Companion (`Lumina---V2`)  
**Specification Directory:** `docs/command-deck/`  

---

> [!IMPORTANT]
> **DOCUMENTATION & SPECIFICATION ONLY — NOT AUTHORIZATION TO IMPLEMENT.**  
> This specification pack defines the complete product vision, technical architecture, UX design, safety requirements, and implementation plan for the Lumina Command Deck. It serves as the authoritative blueprint for future implementation. The creation of these documents does **NOT** authorize immediate code implementation or modifications to Lumina application source files.

---

## 1. Feature Summary & Product Vision

The **Lumina Command Deck** (`CD`) is an operational command and observability center integrated natively into Lumina's existing web dashboard.

While existing Lumina panels serve distinct cognitive purposes:
- **Chat & Presence:** Conversational interaction and voice streaming.
- **Knowledge:** Semantic 3D concept visualization and file discovery.
- **Memory & Continuity:** Canonical facts, decisions, and belief history.
- **Settings:** Audio device routing and model configuration.

The Command Deck answers a vital operational question:
> **"What is Lumina doing right now, what is happening in my workspace, what has occurred recently, and what requires my immediate attention?"**

The Command Deck combines the aesthetic appeal of a futuristic AI command deck with the rigorous clarity, precision, and telemetry of a high-performance developer console.

---

## 2. Current Repository Context

The specifications in this pack were produced following deep, evidence-based inspection of the real Lumina companion codebase (`d:\R O C H A K\LUNA 3`):

1. **Frontend Architecture:** Pure Vanilla JavaScript (ES2022+) using native ES modules (`<script type="module">`). Zero build step (no Webpack, Vite, or Next.js). Single-page application loaded via `web/index.html`.
2. **Design System:** Dark cyberpunk aesthetic governed by `web/crimson.css` and `web/style.css` using native CSS Custom Properties (`--lumina-bg: #030303`, `--lumina-panel: #0b0c0e`, `--lumina-red: #e5092f`, `--lumina-border-red: #ff173d47`, etc.).
3. **Backend Engine:** Asynchronous Python 3.12+ service running on `aiohttp.web` (`lumina/server.py`, `lumina/runtime.py`). Local loopback binding only (`127.0.0.1`).
4. **State Machine:** Authoritative 8-state cognitive engine (`IDLE`, `LISTENING`, `THINKING`, `EXECUTING`, `SPEAKING`, `INTERRUPTED`, `WAITING_FOR_USER`, `ERROR`) in `lumina/runtime.py`.
5. **Task Manager:** Native task session coordinator (`lumina/tasks.py`) supporting autonomous worker adapters (`claude-code`, tmux, custom) with 2-step confirmation for destructive mutations.
6. **Safety & Permission Fences:** Tiered L0–L4 tool permissions with fail-closed emergency revocation latches (`lumina/control_authority.py`).
7. **Session Logging:** Local bounded JSON-lines log rotation (max 3 files, 1MB cap) with automated regex redaction of keys and tokens (`lumina/session_log.py`).
8. **Real-time Transport:** WebSocket at `/ws?token=<session_token>` providing bidirectional event streaming, 20s heartbeats, and initial state snapshots (`rt.snapshot()`).

---

## 3. Specification Pack Document Index

This specification pack contains 10 numbered technical documents designed to be read in sequence or consulted as standalone references:

| File | Document Title | Purpose & Core Content |
|---|---|---|
| [01_PRODUCT_REQUIREMENTS.md](file:///d:/R%20O%20C%20H%20A%20K/LUNA%203/docs/command-deck/01_PRODUCT_REQUIREMENTS.md) | **Product Requirements Document (PRD)** | Problem definition, target scenarios, user stories (US-001–US-007), scope boundaries, and MoSCoW feature prioritization. |
| [02_UX_AND_INTERFACE.md](file:///d:/R%20O%20C%20H%20A%20K/LUNA%203/docs/command-deck/02_UX_AND_INTERFACE.md) | **UX & Interface Specification** | Visual tokens from `crimson.css`, nav rail integration, modal geometry, 2-column grid layout, UI states, and accessibility standards. |
| [03_FEATURES_AND_BEHAVIORS.md](file:///d:/R%20O%20C%20H%20A%20K/LUNA%203/docs/command-deck/03_FEATURES_AND_BEHAVIORS.md) | **Features & Behaviors Specification** | Detailed behavioral specifications for all feature groups: Live Status (`CD-F001`), Mission Control (`CD-F002`), Activity Feed (`CD-F003`), Workspace Monitor (`CD-F004`), System Watch (`CD-F005`), Task Details (`CD-F006`), Filters (`CD-F007`), and Recovery (`CD-F008`). |
| [04_ARCHITECTURE_AND_INTEGRATION.md](file:///d:/R%20O%20C%20H%20A%20K/LUNA%203/docs/command-deck/04_ARCHITECTURE_AND_INTEGRATION.md) | **Architecture & Integration Specification** | Repository facts, component topology, navigation registration in `shell.js`, lifecycle cleanup, and comprehensive Source-of-Truth matrix. |
| [05_DATA_MODELS_AND_EVENTS.md](file:///d:/R%20O%20C%20H%20A%20K/LUNA%203/docs/command-deck/05_DATA_MODELS_AND_EVENTS.md) | **Data Models & Event Contracts** | TypeScript presentation schemas, verified WebSocket event contracts (`state`, `agent_result`, `confirmation`), state mapping tables, and deduplication logic. |
| [06_SAFETY_PRIVACY_AND_PERMISSIONS.md](file:///d:/R%20O%20C%20H%20A%20K/LUNA%203/docs/command-deck/06_SAFETY_PRIVACY_AND_PERMISSIONS.md) | **Safety, Privacy & Permissions** | Read-only default policies, preservation of L2–L4 human approval boundaries, computer control fences, regex secret redaction, and action risk classification. |
| [07_RELIABILITY_PERFORMANCE_AND_FAILURES.md](file:///d:/R%20O%20C%20H%20A%20K/LUNA%203/docs/command-deck/07_RELIABILITY_PERFORMANCE_AND_FAILURES.md) | **Reliability, Performance & Fault Tolerance** | Bounded in-memory event buffers (max 150 items), section-level error boundaries, zero-cost closed polling discipline, and self-healing reconnection flows. |
| [08_TESTING_AND_ACCEPTANCE.md](file:///d:/R%20O%20C%20H%20A%20K/LUNA%203/docs/command-deck/08_TESTING_AND_ACCEPTANCE.md) | **Testing Strategy & Acceptance Criteria** | Node.js unit tests (`node:assert/strict`), component integration checks, backend pytest suites, regression checklists, and P0 acceptance conditions. |
| [09_IMPLEMENTATION_ROADMAP.md](file:///d:/R%20O%20C%20H%20A%20K/LUNA%203/docs/command-deck/09_IMPLEMENTATION_ROADMAP.md) | **Phased Implementation Roadmap** | Phased engineering plan (Phases 0 through 6), prerequisites, risks, definitions of done, and stop conditions. |
| [10_GEMINI_IMPLEMENTATION_PROMPT.md](file:///d:/R%20O%20C%20H%20A%20K/LUNA%203/docs/command-deck/10_GEMINI_IMPLEMENTATION_PROMPT.md) | **Standalone Coding Implementation Prompt** | Complete copy-paste instruction set for a future coding agent to implement the feature autonomously without hallucinating or refactoring unrelated systems. |

---

## 4. Recommended Reading Order

For engineers, architects, or autonomous agents engaging with this specification:

```
1. README.md (You are here: Executive Overview & Feasibility)
       │
       ▼
2. 01_PRODUCT_REQUIREMENTS.md (Understand user value, goals & non-goals)
       │
       ▼
3. 04_ARCHITECTURE_AND_INTEGRATION.md (Grasp codebase hooks & Source-of-Truth)
       │
       ▼
4. 05_DATA_MODELS_AND_EVENTS.md (Understand event payloads & state mapping)
       │
       ▼
5. 06_SAFETY_PRIVACY_AND_PERMISSIONS.md (Learn non-negotiable security boundaries)
       │
       ▼
6. 03_FEATURES_AND_BEHAVIORS.md & 02_UX_AND_INTERFACE.md (Deep dive into UI & interactions)
       │
       ▼
7. 07_RELIABILITY_PERFORMANCE_AND_FAILURES.md & 08_TESTING_AND_ACCEPTANCE.md (Verify resilience & QA)
       │
       ▼
8. 09_IMPLEMENTATION_ROADMAP.md & 10_GEMINI_IMPLEMENTATION_PROMPT.md (Execution phase preparation)
```

---

## 5. Feasibility Analysis & Release Verdict

A critical finding of this repository audit is that **every single P0 capability required for the Command Deck already possesses an authoritative data source in the Lumina backend**. No new backend microservices or database migrations are required.

### 5.1 Mandatory Feasibility Matrix

| Feature ID & Title | Authoritative Source Exists? | Integration Effort | Implementation Complexity | Safety Risk Level | Target Priority | Final Recommendation |
|---|---|---|---|---|---|---|
| **CD-F001: Live Status** | **YES** (`Runtime.state`, `/ws`) | Low | Low | Low (Read-only) | **P0** | **READY** — Deliver in first vertical slice. |
| **CD-F002: Mission Control** | **YES** (`TaskManager`, `/api/tasks`) | Low | Low-Medium | Low (Read-only view) | **P0** | **READY** — Direct projection of task sessions. |
| **CD-F003: Activity Feed** | **YES** (`Runtime.audit`, `/ws` push) | Medium | Medium | Low | **P0** | **READY WITH ADAPTER** — Client ring buffer. |
| **CD-F004: Workspace Monitor**| **YES** (`Config.root`, uploads) | Low | Low | Low (Passive path) | **P1** | **READY** — Read-only path presentation. |
| **CD-F005: System Watch** | **YES** (`state.errors`, `pending`) | Low-Medium | Medium | Low (Alert desk) | **P0** | **READY WITH ADAPTER** — Unified alert desk. |
| **CD-F006: Task Detail Drawer**| **YES** (`TaskManager.read_session`) | Low | Low | Low (Safe details) | **P1** | **READY** — Slide-over diagnostic card. |
| **CD-F007: Activity Filters** | **YES** (Client memory buffer) | Low | Low | None (Client only) | **P1** | **READY** — Client-side filter bar. |
| **CD-F008: Connection Recovery**| **YES** (`ws.onclose`, snapshot) | Medium | Medium | Low | **P0** | **READY WITH ADAPTER** — Reconcile on reconnect. |
| **CD-F009: Machine Telemetry** | **YES** (`lumina/telemetry.py`) | Low | Low | None (Kernel sample) | **P2** | **READY** — Instantaneous CPU gauge. |
| **CD-F010: Task Cancellation** | **YES** (`POST /api/tasks` 2-step) | Medium | Medium | Medium (State change) | **P2** | **REQUIRES SMALL EXTENSION** — 2-step modal. |
| **CD-F011: Historical Logs** | **PARTIAL** (`SessionLog.listing`) | High | High | Low (Disk reads) | **Deferred** | **DEFER** — Out of scope for v1. |
| **CD-F012: Drag-and-Drop Grid**| **NO** (Not supported in theme) | High | High | None | **Deferred** | **REJECT** — Unnecessary complexity. |

### 5.2 Smallest Viable Release Recommendation (P0 Scope)
The smallest complete, genuinely useful first release of the Command Deck comprises:
1. Navigation registration in `web/index.html` and `web/shell.js`.
2. Core `<dialog id="command-deck-panel">` shell styled with `web/crimson.css` design tokens.
3. **CD-F001 (Live Status):** Real-time cognitive state pill, active tool name, provider health, and pending approval badge.
4. **CD-F002 (Mission Control):** Active and recent agent tasks from `TaskManager` with duration timers and status pills.
5. **CD-F003 (Activity Feed):** Real-time operational timeline with bounded 150-event FIFO buffer and category icons.
6. **CD-F005 (System Watch):** Real-time alert desk showing runtime faults and connection status.
7. **CD-F008 (Connection Recovery):** Clean handling of connection drops, stale-state labeling, and snapshot reconciliation.

---

## 6. Key Technical and Safety Principles

1. **Native Integration:** Reuses Lumina's existing HTML/CSS/JS architecture without external bundlers, package installations, or new databases.
2. **Design Authority:** `web/crimson.css` is the sole visual authority. No conflicting color palettes.
3. **Truth in Telemetry:** All visual readouts reflect source-confirmed backend data. Zero synthetic or imagined metrics.
4. **Read-Only Default:** Opening the panel triggers zero process spawning, zero file modifications, and zero camera/screen captures.
5. **Human Approval Invariance:** The Command Deck preserves all L2–L4 human confirmation fences and emergency stop latches.

---

## 7. Status & Next Steps

- **Specification Status:** Complete, cross-referenced, and fully verified against the Lumina repository.
- **Source Code Status:** **0 application source files modified during this task.**
- **Next Step:** When authorized by the user, provide [10_GEMINI_IMPLEMENTATION_PROMPT.md](file:///d:/R%20O%20C%20H%20A%20K/LUNA%203/docs/command-deck/10_GEMINI_IMPLEMENTATION_PROMPT.md) to a coding agent to execute Phase 0 and Phase 1 of the implementation roadmap.
