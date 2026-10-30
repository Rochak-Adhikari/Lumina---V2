# LUMINA COMMAND DECK — FUNCTIONAL IMPLEMENTATION AND DATA-FLOW REPAIR

## Objective

The Command Deck already exists visually in the current Lumina dashboard. Its files have been created and integrated, but the user reports that the panel is essentially static and the planned functionality has not been implemented.

Your task is to transform the existing Command Deck into a genuinely functional, live operational dashboard connected to Lumina's real runtime, task manager, WebSocket transport, configuration and diagnostic sources.

**Do not rebuild the UI from scratch. Do not create another panel, another application, or duplicate frontend controllers. Preserve the existing design and repair or complete the implementation in place.**

The authoritative repository is the currently active Lumina checkout. Confirm its path before editing; do not assume another checkout is equivalent.

## Phase 1 — Diagnose the actual problem before changing code

Inspect these files in their current state:

- `web/command-deck.js`
- `web/command-deck.css`
- `web/index.html`
- `web/app.js`
- `web/shell.js`
- `lumina/server.py`
- `lumina/runtime.py`
- `lumina/tasks.py`
- `lumina/session_log.py`
- `lumina/control_authority.py`
- `docs/command-deck/`

Run `git status --short` first and preserve all existing user changes.

Trace the entire data path for each feature:

1. Where the backend produces the data.
2. Which route or WebSocket event exposes it.
3. Where the existing application receives it.
4. How `web/app.js` forwards it.
5. How `web/command-deck.js` stores and processes it.
6. How the UI renders it.
7. What happens when the data is missing, malformed or stale.

Identify the precise reasons the current panel is static. Examples to investigate—not assumptions—include event handlers never being registered, controller initialization occurring before dependencies exist, mismatched event names, incorrect payload shapes, missing initial HTTP requests, incorrect state selectors, stale cached data, and render functions never being called.

Inspect the actual browser console and network behavior if a supported local browser or test workflow is available. Otherwise, report that live-browser verification was unavailable; do not pretend it occurred.

Produce a short diagnosis with evidence from the actual source files before proceeding. Do not stop after writing the diagnosis: implement the fixes after the interfaces are verified.

## Phase 2 — Preserve the existing architecture

Use Lumina's existing vanilla JavaScript ES-module frontend, backend routes and WebSocket lifecycle.

Do not add dependencies, introduce a new framework, create a second WebSocket connection unnecessarily, or invent backend contracts.

Verify every route, method, response shape, event name and payload against the current source.

The specification documents are design guidance. Actual source code determines what currently exists.

If a feature requires a missing capability, first determine whether existing state or events can support it. Add only the smallest justified extension, and explain why it is necessary.

Keep the Command Deck read-only by default. Do not bypass approval, task cancellation, computer-control or emergency-stop safeguards.

## Phase 3 — Implement genuinely live features

### A. Live Status

- Populate the panel from actual runtime state.
- Update it when real state events arrive.
- Display the connection state based on the actual transport lifecycle.
- Display the latest successful update time.
- Distinguish live, stale, disconnected and unavailable information.
- Do not use static default values that resemble live state.
- Do not treat a connected WebSocket alone as proof that all data is current.

### B. Mission Control

- Load the initial task list using the verified existing task API or interface.
- Populate the panel with real task records.
- Process genuine task lifecycle events.
- Update the relevant task without duplicating it.
- Use the actual task identifiers, statuses and available fields.
- Refresh the task list after reconnection.
- Make task inspection open details for the selected real task.
- Do not invent tasks or task metadata.

If the task list is empty, display a useful empty state.

### C. Activity Feed

- Populate the feed from verified event sources.
- Include an initial history only if an existing authoritative history interface is available.
- Add new genuine events as they arrive.
- Normalize actual event payloads into a documented presentation format.
- Deduplicate events where possible.
- Keep no more than 150 entries in the in-memory buffer.
- Make category filters change the visible entries immediately.
- Handle malformed events without breaking the feed.
- Clearly indicate that the feed is recent, bounded history and may not represent every event.

Do not fabricate activity merely to make the interface look active.

### D. Workspace Monitor

- Read the workspace root from the actual configuration interface.
- Display the real value.
- Make the copy action work.
- Handle clipboard permission failures gracefully.
- Do not scan unrelated files or expose secrets.

### E. System Watch

- Subscribe to genuine runtime error and connection-failure information.
- Display errors only when the source actually exposes them.
- Distinguish current faults from historical events where supported.
- Avoid repeated duplicate alerts.
- Display an honest unavailable state if an error source cannot be observed.

### F. Task Diagnostics

- Open details for the selected real task.
- Render only fields that exist in the actual task response.
- Support safe truncation and expansion for long text.
- Sanitize credentials and secrets.
- Do not assume that prompts, modified files, exit codes or complete traces exist for every worker.
- Ensure the details view works with keyboard and pointer interaction.

Do not display controls for unavailable actions as if they work.

### G. Connection Recovery

- Integrate with the existing WebSocket lifecycle.
- Mark connection-dependent data stale when the transport disconnects.
- Update the connection indicator immediately.
- On reconnection, refresh the latest runtime snapshot and task list using verified interfaces.
- Reconcile existing records rather than duplicating them.
- Clean up listeners when the controller is disposed or initialized again.
- Do not create a competing reconnect loop.

## Phase 4 — Verify every interactive control

Inspect the complete panel and test each button, filter, detail view and copy action.

Every visible control must either work or be clearly marked unavailable. Remove or disable nonfunctional controls rather than presenting them as implemented.

Check:

- Navigation entry opens the correct dialog.
- Close button and Escape behavior work.
- Focus behavior remains accessible.
- Category filters actually filter the feed.
- Task inspection opens the correct record.
- Workspace copy works or displays an error.
- Connection status reflects real transport events.
- Empty and error states render correctly.
- Repeated opening and closing does not accumulate listeners.
- The interface does not break existing dashboard functionality.

## Phase 5 — Tests and evidence

Extend `tests/command_deck.test.mjs` using the repository's established test conventions.

Test:

1. Initial state population.
2. Realistic runtime payloads.
3. Realistic task payloads.
4. Incoming WebSocket events updating the UI model.
5. Activity filtering and event deduplication.
6. The 150-entry limit.
7. Missing and malformed payloads.
8. Secret sanitization.
9. Disconnect, stale state and reconnection reconciliation.
10. Repeated initialization and listener cleanup.
11. Empty task lists and unavailable optional data.
12. Read-only behavior and preservation of existing safety boundaries.

Use controlled fixtures for deterministic unit tests. Clearly distinguish unit tests from integration tests and manual browser verification.

Run the relevant existing frontend and backend regression suites using commands verified for this repository. Report actual results and do not claim a test passed unless it ran successfully.

## Phase 6 — Final report

Report:

1. The exact root cause of the static behavior, with source locations.
2. Every file created or modified.
3. The actual data source used by each implemented feature.
4. Any features that remain unavailable and why.
5. Actual test commands and outcomes.
6. Whether live-browser behavior was verified.
7. Confirmation that unrelated user changes were preserved.
8. Confirmation that existing authorization, approval and emergency-stop boundaries remain intact.

Do not describe the feature as fully functional unless its real data flow and relevant interactions have been verified.

## Final instruction

Start with repository status and source tracing. Find why the existing implementation is static, fix the actual cause, then complete and verify the data flow feature by feature.

Preserve the current UI. Focus on functionality, not another redesign. Do not stop after generating a plan or report—implement the verified fixes and test them.