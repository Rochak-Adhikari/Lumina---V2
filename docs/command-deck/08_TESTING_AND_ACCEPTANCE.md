# Lumina Command Deck: Testing Strategy & Acceptance Criteria

**Document ID:** `CD-TEST-001`  
**Feature:** Lumina Command Deck (`CD`)  
**Status:** Verification & Testing Specification / Pre-Implementation  
**Target System:** Lumina AI Companion Dashboard (`Lumina---V2`)  
**Author:** AI Systems Engineering Quality Assurance Team  

---

## 1. Testing Philosophy & Verification Framework

Testing the Command Deck requires verifying that:
1. All client-side presentation components render source-verified data accurately without hallucinations.
2. Existing safety and authorization boundaries remain untouched and inviolable.
3. Network interruptions, malformed payloads, and edge cases are handled gracefully.
4. No regressions are introduced to existing conversational, voice, memory, or knowledge systems.

### Existing Test Tooling in Repository:
- **Python Backend:** `pytest` (configured via `pytest.ini`). Test files located in `tests/test_*.py`.
- **Frontend / ES Modules:** Node.js native test runner (`node:assert/strict`). Test files located in `tests/*.test.mjs` (e.g. `tests/motion.test.mjs`).

---

## 2. Unit Testing Specifications

Unit tests must be authored in `tests/command_deck.test.mjs` using native Node.js assertions (`node:assert/strict`) to test pure logic without browser DOM overhead.

### 2.1 State Mapping & Normalization Tests
- **Test UM-01 (Runtime State Enum Mapping):** Verify that all eight runtime states (`IDLE`, `LISTENING`, `THINKING`, `EXECUTING`, `SPEAKING`, `INTERRUPTED`, `WAITING_FOR_USER`, `ERROR`) map to their exact assigned UI labels and badge styles.
- **Test UM-02 (Task State Mapping):** Verify that task statuses (`RUNNING`, `WAITING_FOR_USER`, `COMPLETED`, `ERROR`, `CANCELLED`) produce the expected badge and action permissions.
- **Test UM-03 (Missing Fields Fallback):** Verify that payloads missing optional fields (`summary`, `error`, `latencyMs`) render safe default placeholders rather than throwing `TypeError`.
- **Test UM-04 (Event Deduplication):** Verify that pushing two events with the same `id` into `BoundedEventBuffer` results in only one stored entry.
- **Test UM-05 (Buffer FIFO Eviction):** Verify that pushing 151 events into a buffer with a max size of 150 results in exactly 150 items, with the oldest item evicted.
- **Test UM-06 (Secret Redaction Sanitizer):** Verify that strings containing `Bearer sk-12345` or `key-abcdef1234567890` are masked to `[REDACTED]`.

---

## 3. Component & DOM Integration Tests

Component tests verify DOM interactions inside a headless browser or mock environment (`tests/command_deck_dom.test.mjs`):

- **Test CD-01 (Nav Button Registration):** Verify clicking `#command-deck-open` toggles `dialog.open === true` on `#command-deck-panel`.
- **Test CD-02 (Keyboard Escape Trap):** Verify pressing `Escape` closes the open dialog and restores focus to `#command-deck-open`.
- **Test CD-03 (Filter Bar Selection):** Verify clicking the `[Tasks]` filter pill hides all non-task rows in the activity timeline.
- **Test CD-04 (Path Truncation & Copy):** Verify clicking `[Copy Path]` calls `navigator.clipboard.writeText` with the un-truncated absolute path.
- **Test CD-05 (Section Isolation):** Inject a synthetic parsing exception into `#workspace-monitor`; verify `#mission-control` and `#live-status` remain interactive and rendered.

---

## 4. End-to-End & Integration Tests

Integration tests run against the live Python local server (`tests/test_command_deck_api.py` using `pytest`):

- **Test INT-01 (REST Endpoints Compatibility):**
  - Verify `GET /api/tasks` returns `200 OK` with valid `workers` array and `tasks` array.
  - Verify `GET /api/audit` returns `200 OK` with a list of at most 100 event objects.
  - Verify `GET /api/telemetry` returns `200 OK` with numeric CPU load or `null`.
- **Test INT-02 (WebSocket State Snapshot):**
  - Connect to `/ws?token=<token>`.
  - Verify first message received is `type: 'client_ready'`.
  - Verify second message is `type: 'state'` containing valid snapshot data matching the schema defined in `05_DATA_MODELS_AND_EVENTS.md`.
- **Test INT-03 (Two-Step Task Cancellation):**
  - Start a test worker session.
  - Issue `POST /api/tasks` with `action: 'request_cancel'`.
  - Verify response contains `confirmation_id` with 60-second expiry.
  - Issue `POST /api/tasks` with `action: 'cancel'` and valid confirmation token; verify task enters `CANCELLED` status.

---

## 5. Regression Test Suites to Run

Before approving any implementation diff, the implementer MUST run these existing test suites and verify 100% pass rate:

```powershell
# 1. Existing Server Core & Route Regressions
.venv\Scripts\pytest.exe tests/test_server.py

# 2. Existing Safety & Control Authority Boundaries
.venv\Scripts\pytest.exe tests/test_control_authority.py
.venv\Scripts\pytest.exe tests/test_safety_hardening.py

# 3. Existing Task & Worker Management
.venv\Scripts\pytest.exe tests/test_roadmap_plugins.py

# 4. Existing Continuity & Memory Store
.venv\Scripts\pytest.exe tests/test_continuity_core.py

# 5. Existing Frontend Motion & UI Contracts
node tests/motion.test.mjs
```

---

## 6. Manual QA Verification Checklist across Viewports

| Verification Step | Desktop (1920x1080) | Compact (1200x800) | Mobile / Narrow (640x900) | Pass/Fail Criteria |
|---|---|---|---|---|
| **Nav Button Alignment** | Vertical rail, text visible | Icon-only rail | Top horizontal bar | Clear visibility, no overflow |
| **Dialog Dimensions** | 1200px wide, centered | 94vw wide, centered | Fullscreen modal (100vw/100vh) | No clipping or horizontal scroll |
| **Grid Re-stacking** | 2-column (60% / 40%) | 2-column compact | 1-column stacked | Clean reflow, all sections visible |
| **Scroll Bounds** | Inner card scroll only | Inner card scroll only | Full-dialog vertical scroll | Main body scroll locked |
| **Contrast & Legibility** | Verified AA | Verified AA | Verified AA | Sharp text against dark panels |

---

## 7. Objective Acceptance Criteria for P0 Release

The Command Deck feature is considered **ACCEPTED** only when:

- [ ] **AC-01:** Navigating to Command Deck opens the panel in < 100ms without console errors.
- [ ] **AC-02:** Live Status accurately displays the current runtime state (`IDLE`, `EXECUTING`, etc.) and updates in real time.
- [ ] **AC-03:** Mission Control lists all tasks currently active in `TaskManager`.
- [ ] **AC-04:** Activity Feed streams events as they occur in the runtime with correct icons and timestamps.
- [ ] **AC-05:** System Watch alerts user when backend disconnects and recovers cleanly upon reconnect.
- [ ] **AC-06:** No application code outside the specified integration points was modified.
- [ ] **AC-07:** All existing regression test suites pass with zero failures.
- [ ] **AC-08:** Memory footprint remains under 15MB increase during continuous 1-hour session.
