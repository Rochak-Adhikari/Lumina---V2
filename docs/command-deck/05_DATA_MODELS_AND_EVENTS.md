# Lumina Command Deck: Data Models & Event Contracts

**Document ID:** `CD-DATA-001`  
**Feature:** Lumina Command Deck (`CD`)  
**Status:** Data Specification / Pre-Implementation  
**Target System:** Lumina AI Companion Dashboard (`Lumina---V2`)  
**Author:** AI Systems Engineering Architecture Team  

---

## 1. Overview & Data Philosophy

The Lumina Command Deck functions as an operational lens over the real-time runtime state of Lumina. It does not introduce a secondary database, duplicate state cache, or proprietary event store.

All presentation models are **projections** derived from authoritative backend state machines (`Runtime`, `TaskManager`, `ControlAuthority`, `SessionLog`).

### Core Data Principles:
1. **Source Fidelity:** Data models mirror actual server payloads. Missing or unverified fields are treated as `null`/`undefined`, never synthesized.
2. **Immutable Projections:** Client-side event aggregation treats backend messages as append-only records.
3. **Bounded Memory Footprint:** In-memory ring buffers enforce strict capacity ceilings (maximum 150 live events) to prevent memory leaks in long-running sessions.
4. **Strict Sanitization:** Dynamic text fields are strictly sanitized prior to DOM rendering.

---

## 2. Presentation Data Models

### 2.1 Connection Status Model (`CDConnectionModel`)

Represents the physical transport health between the browser client and the local Python runtime.

```typescript
interface CDConnectionModel {
  transport: 'websocket' | 'disconnected' | 'reconnecting'; // Required
  readyState: number;                                       // Required: 0=CONNECTING, 1=OPEN, 2=CLOSING, 3=CLOSED
  lastHeartbeat: number;                                    // Required: Epoch milliseconds of last ping/pong/message
  latencyMs: number | null;                                 // Optional: Measured RTT in milliseconds
  reconnectAttempts: number;                                // Required: Counter for consecutive reconnection tries
  sessionId: string | null;                                 // Optional: Current client session identifier
}
```

- **Source of Truth:** `ws.readyState` and connection timers in `web/app.js`.
- **Validation Rules:** `readyState` must be an integer between 0 and 3. `lastHeartbeat` must be positive.
- **Missing Field Behavior:** If `sessionId` is unavailable, display generic "Local Client".
- **Privacy Considerations:** Contains no user-identifiable data or tokens.

### 2.2 Runtime Status Model (`CDRuntimeModel`)

Captures the operational state machine of the Lumina cognitive engine.

```typescript
interface CDRuntimeModel {
  state: 'IDLE' | 'LISTENING' | 'THINKING' | 'EXECUTING' | 'SPEAKING' | 'INTERRUPTED' | 'WAITING_FOR_USER' | 'ERROR'; // Required
  revision: number;                                         // Required: Monotonically increasing revision counter
  currentTool: string | null;                               // Optional: Name of tool currently being executed
  providerStatus: 'not_connected' | 'connected' | 'connecting' | 'unavailable' | 'failed' | 'local'; // Required
  pendingApprovalsCount: number;                            // Required: Number of actions awaiting human authorization
  speechActive: boolean;                                    // Required: Whether Lumina is currently synthesizing voice
  lastToolResult: {
    ok: boolean;
    name?: string;
    timestamp?: number;
    summary?: string;
  } | null;                                                 // Optional: Summary of the most recent tool execution
}
```

- **Source of Truth:** `Runtime.state` returned by `GET /api/state` and push events `type: 'state'`.
- **Validation Rules:** `state` must match one of the eight defined enum values. If unknown, treat as `'ERROR'`.
- **Missing Field Behavior:** If `currentTool` is null, UI displays "System Idle".
- **Privacy Considerations:** `lastToolResult` summaries must not expose unredacted file contents or shell parameters.

### 2.3 Task Summary Model (`CDTaskModel`)

Represents an autonomous or coordinated agent task running through `TaskManager`.

```typescript
interface CDTaskModel {
  taskId: string;                                           // Required: Unique 32-char hex task identifier
  worker: string;                                           // Required: Worker adapter name (e.g., 'claude-code', 'tmux')
  status: 'RUNNING' | 'WAITING_FOR_USER' | 'COMPLETED' | 'ERROR' | 'CANCELLED' | 'CANCELLING' | 'CANCEL_FAILED' | 'REMOVING'; // Required
  instruction: string;                                      // Required: Initial user prompt or objective (truncated to 400 chars)
  summary: string;                                          // Optional: Latest progress summary or final outcome
  createdAt: number;                                        // Required: Unix timestamp in seconds
  completedAt: number | null;                               // Optional: Unix timestamp in seconds
  workspace: string | null;                                 // Optional: Working directory bound to the task
  exitCode: number | null;                                  // Optional: Process exit code if available
  changedFiles: string[];                                   // Required: List of modified file paths (can be empty)
  hasError: boolean;                                        // Required: Derived boolean flag
  errorMessage: string | null;                              // Optional: Safe error description
}
```

- **Source of Truth:** `TaskManager._sessions` returned by `GET /api/tasks` and push events `type: 'agent_result'`.
- **Validation Rules:** `taskId` must be a valid hex string. `createdAt` must be a valid unix timestamp.
- **Missing Field Behavior:** Missing `summary` falls back to "Task in progress..." for running tasks, or "No summary reported".
- **Privacy Considerations:** Task instructions may contain file names; paths must be displayed using relative workspace references where possible.

### 2.4 Activity Event Model (`CDActivityEvent`)

Represents a single unified operational timeline item in the Activity Feed.

```typescript
interface CDActivityEvent {
  id: string;                                               // Required: Unique deterministic event ID
  timestamp: number;                                        // Required: Epoch milliseconds
  category: 'runtime' | 'task' | 'tool' | 'approval' | 'connection' | 'safety'; // Required
  severity: 'info' | 'warning' | 'error' | 'success';       // Required
  title: string;                                            // Required: Concise, scannable headline (<80 chars)
  detail: string | null;                                    // Optional: Secondary diagnostic context (<400 chars)
  sourceSubsystem: string;                                  // Required: Subsystem name (e.g., 'TaskManager', 'Runtime', 'ControlAuthority')
  correlationId?: string;                                   // Optional: Associated taskId or confirmationId
  rawPayload?: Record<string, unknown>;                     // Optional: Retained for expanded drawer inspection
}
```

- **Source of Truth:** Aggregated from `GET /api/audit`, `GET /api/tasks`, and live WebSocket messages.
- **Deduplication Key:** Combination of `${category}:${sourceSubsystem}:${timestamp}:${title}`.

---

## 3. Verified Backend Event Contracts

The Command Deck consumes existing WebSocket events emitted by `Runtime.broadcast()` in `lumina/runtime.py`.

### 3.1 Event: `state`
Broadcast whenever the runtime state, current tool, or cognitive state changes.

```json
{
  "type": "state",
  "data": {
    "state": "EXECUTING",
    "revision": 42,
    "task": "Searching documentation",
    "current_tool": "find_files",
    "last_tool_result": {
      "ok": true,
      "results": [{"filename": "app.js", "path": "web/app.js", "match_type": "name"}]
    },
    "provider_status": "connected",
    "errors": [],
    "live_connected": true,
    "speech_id": 14,
    "control_safety": {
      "mode": "disarmed",
      "quarantined": false,
      "unresolved": false
    }
  }
}
```

### 3.2 Event: `agent_result`
Broadcast when a background worker task makes progress, completes, or requires human input.

```json
{
  "type": "agent_result",
  "data": {
    "task_id": "9f8b2c14e0a74d28913c5f284e9d6b10",
    "worker": "claude-code",
    "status": "WAITING_FOR_USER",
    "summary": "Completed architecture review. Awaiting review of changes."
  }
}
```

### 3.3 Event: `confirmation`
Broadcast when a tool execution encounters an L2–L4 permission fence requiring human authorization.

```json
{
  "type": "confirmation",
  "data": {
    "confirmation_id": "conf_8a9f3b2e7c1d4a0b",
    "tool": "delete_file",
    "arguments": {"path": "temp/cache.json"},
    "expires": 1729810500.0,
    "message": "Allow deletion of temp/cache.json?"
  }
}
```

### 3.4 Event: `confirmation_resolved`
Broadcast when a pending approval has been approved, denied, or expired.

```json
{
  "type": "confirmation_resolved",
  "confirmation_id": "conf_8a9f3b2e7c1d4a0b"
}
```

### 3.5 Event: `notice`
Broadcast for system-level notices, warnings, and error alerts.

```json
{
  "type": "notice",
  "text": "Audio transport disconnected. Local capabilities remain operational."
}
```

---

## 4. State Mapping Logic

Authoritative backend states are mapped to user-facing UI labels and visual tokens without altering underlying data values:

### 4.1 Runtime State Mapping Matrix

| Backend State (`Runtime.state['state']`) | UI Display Label | Visual Badge Style | Operational Meaning |
|---|---|---|---|
| `IDLE` | **Ready** | Mint Outline (`--lumina-success`) | System is waiting for user interaction. |
| `LISTENING` | **Listening** | Bright Cyan (`--lumina-info`) | Microphone is open; processing audio input. |
| `THINKING` | **Processing** | Soft Amber (`--lumina-warning`) | Reasoning provider or model turn in progress. |
| `EXECUTING` | **Executing** | Crimson Glow (`--lumina-red-bright`) | Running tool or local command. |
| `SPEAKING` | **Speaking** | Soft Rose (`--soft`) | Voice output active. |
| `INTERRUPTED` | **Interrupted** | Soft Amber (`--lumina-warning`) | Current turn cancelled by user speech or stop action. |
| `WAITING_FOR_USER` | **Action Required** | Pulsing Amber (`--lumina-warning`) | Blocked on human confirmation or input. |
| `ERROR` | **Attention Needed** | Solid Crimson (`--lumina-red`) | Fault detected; local capabilities preserved. |

### 4.2 Task State Mapping Matrix

| Backend Task Status (`_Session.status`) | UI Display Label | Badge Color / Icon | Action Allowed |
|---|---|---|---|
| `RUNNING` | **Active** | Cyan Pulse (`◈`) | Cancel Task |
| `WAITING_FOR_USER` | **Awaiting Input** | Amber Alert (`▲`) | Resume / Message |
| `COMPLETED` | **Finished** | Mint Dot (`✓`) | View Details / Clear |
| `ERROR` | **Failed** | Crimson Dot (`✗`) | View Error Details |
| `CANCELLING` | **Stopping...** | Muted Dash (`-`) | Disabled |
| `CANCELLED` | **Cancelled** | Muted Slash (`⊘`) | Remove from List |
| `CANCEL_FAILED` | **Halt Incomplete** | Crimson Warning (`⚠`) | Retry Cancellation |
| `REMOVING` | **Purging...** | Muted (`...`) | Disabled |

---

## 5. Event Ordering, Deduplication, and Freshness

### 5.1 Deterministic Sequence & ID Generation
For events originating from REST polls or audit logs lacking an explicit UUID, the client normalizer synthesizes a deterministic hash ID:
```javascript
function generateEventId(event) {
  return `${event.time || Date.now()}-${event.operation || event.type}-${event.status || ''}`;
}
```

### 5.2 Deduplication Strategy
The Command Deck maintains an in-memory set of known event IDs (`Set<string>`) capped at 500 entries. Incoming events matching an existing ID are silently dropped.

### 5.3 Freshness & Stale Data Policies
- **Event Freshness:** Timestamps within the last 60 seconds are rendered as relative time (`"just now"`, `"24s ago"`). Older timestamps display standard time format (`HH:mm:ss`).
- **Heartbeat Timeout:** If no WebSocket message or ping is received within **25 seconds** (exceeding the server's 20s heartbeat), the Command Deck marks all live monitors with a **`[STALE]`** visual tag.
- **Reconnect Reconciliation:** Upon reconnection, the client issues a `GET /api/tasks` fetch to reconcile any task completions or cancellations that occurred while the connection was broken.

---

## 6. Privacy, Redaction, and Data Safety

1. **Client-Side Secret Masking:**
   Even though the backend's `SessionLog._safe()` redacts sensitive parameters, the frontend Command Deck includes a defensive secondary sanitizer:
   ```javascript
   const SECRET_PATTERN = /(bearer\s+[a-z0-9_\-\.]+)|(key-[a-z0-9]{16,})/gi;
   function sanitizeText(str) {
     return typeof str === 'string' ? str.replace(SECRET_PATTERN, '[REDACTED]') : '';
   }
   ```
2. **Path Shortening:**
   Full absolute paths (e.g. `d:\R O C H A K\LUNA 3\web\app.js`) are trimmed for display to relative paths relative to workspace root (e.g. `web/app.js`), preserving screen real estate and preventing accidental exposure of local directory hierarchies. Full paths remain available on explicit copy action.
3. **No External Transmission:**
   All diagnostic data remains strictly within the local browser context and loopback interface. No telemetry is transmitted to third-party endpoints.
