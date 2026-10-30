# Lumina Command Deck: Safety, Privacy & Permission Boundaries

**Document ID:** `CD-SAFE-001`  
**Feature:** Lumina Command Deck (`CD`)  
**Status:** Safety Specification / Pre-Implementation  
**Target System:** Lumina AI Companion Dashboard (`Lumina---V2`)  
**Author:** AI Systems Engineering Architecture Team  

---

## 1. Safety Architecture Philosophy

Lumina's core tenet is that the user retains absolute, unequivocal authority over their physical workstation, local filesystem, and active processes.

The Command Deck is an **observability window**, not an elevated management console or backdoor around established safety boundaries. It must strictly adhere to the security model implemented across `lumina/control_authority.py`, `lumina/tools.py`, and `lumina/server.py`.

```
+-------------------------------------------------------------------------+
|                        LUMINA SAFETY FOUNDATION                         |
+-------------------------------------------------------------------------+
|  1. Local Loopback Only (127.0.0.1)                                     |
|  2. Token Authorization on All Mutations (X-Lumina-Token)               |
|  3. Explicit Human Approval Boundary (L0-L4 Permission Model)          |
|  4. Strict Read-Only Default on Observability Views                     |
|  5. Fail-Closed Emergency Revocation Latch (ControlAuthority)           |
+-------------------------------------------------------------------------+
```

---

## 2. Read-Only Default Policy

### 2.1 Zero-Side-Effect Principle
Simply navigating to, opening, resizing, or refreshing the Command Deck MUST NOT trigger:
- Process spawning or shell command execution.
- File system reads outside the configured root or any file modifications.
- Screen frame capture, OCR extraction, or camera device activation.
- Automated approval of any pending confirmation requests.
- Activation of voice recording or microphone capture.
- Transmission of telemetry or analytics over the internet.

### 2.2 Passive Monitoring Guarantees
- The **Workspace Monitor** displays file counts and paths from existing memory structures (`Config.root`, `uploaded_files`). It does not perform a recursive filesystem crawl on open.
- The **Telemetry Monitor** samples CPU performance using Windows kernel counters (`GetSystemTimes`) via a low-frequency, unprivileged local call without querying external endpoints.

---

## 3. Human Approval & Confirmation Boundaries

### 3.1 Preservation of the Authoritative Approval Flow
In Lumina, all consequential actions (file deletion, arbitrary shell commands, computer input events, sensitive file access) are classified into permission levels:
- **L0:** Read-only safe queries (e.g., `system_info`, `find_files`).
- **L1:** Low-risk workspace actions (e.g., creating files within project sandbox).
- **L2–L4:** Sensitive or destructive operations requiring explicit human consent (e.g., `delete_file`, `run_command`, `computer_control`).

When an L2–L4 operation is proposed, the backend generates a cryptographically random `confirmation_id` with an explicit 60-second expiration window (`time.monotonic() + 60`).

### 3.2 Command Deck Approval Representation
The Command Deck represents pending approvals within **Live Status** and **System Watch**:
1. **Indicator Only:** It displays a prominent amber badge showing the count of pending approvals (e.g., `"1 Pending Approval"`).
2. **Authoritative Redirection:** The Command Deck does NOT implement an inline "One-Click Quick Approve" button that skips the confirmation details. Clicking on an approval notice triggers a navigation event (`lumina-event: {type: 'confirmation_inspect', id: ...}`) which opens Lumina's existing authoritative confirmation modal.
3. **No Automatic Approval:** No automated timer, script, or model output can approve a confirmation through the Command Deck interface.

---

## 4. Computer-Control & Perception Boundaries

### 4.1 Screen Perception and Sharing Boundary
Lumina supports supervised screen capture and window inspection via `lumina/screen_sharing.py` and `lumina/owned_windows.py`.
- **Status Display Only:** Command Deck reflects whether screen observation is currently `ACTIVE` or `DISARMED`.
- **No Implicit Capture:** Opening Command Deck does not start the capture worker, capture a display frame, or wake a sleeping display.
- **Preview Isolation:** If an existing preview frame is referenced, it is loaded from the existing memory buffer (`GET /api/screen-preview`), without initiating a new OS-level screen capture.

### 4.2 Local Computer Control Boundary
Autonomous mouse/keyboard interaction is strictly governed by `ControlAuthority` in `lumina/control_authority.py`:
- All control effects are blocked by default (`@blocked_effect`).
- The Command Deck does not expose any direct mouse/keyboard simulation triggers.
- In the event of an active agent running on the desktop, the Command Deck provides immediate access to the **Emergency Revocation Latch** (`request_stop()`), allowing the user to halt all execution immediately.

---

## 5. Sensitive Data Handling & Automated Redaction

Operational feeds often contain sensitive information such as environment variables, directory structures, and API keys.

### 5.1 Redaction Strategy at Rest and in Transit
1. **Server-Side Redaction (`SessionLog._safe`):**
   The backend applies strict regex redaction before writing to session logs or returning audit trails:
   ```python
   _SECRET_KEY = re.compile(r"token|secret|password|api[_-]?key|authorization|cookie|credential|refresh", re.I)
   _SECRET_VALUE = re.compile(r"(?i)(bearer\s+|api[_-]?key\s*[=:]\s*|token\s*[=:]\s*)[^\s,;]+")
   ```
2. **Client-Side Defense-in-Depth:**
   The Command Deck normalizer scrubs all display strings before rendering:
   - File paths outside the workspace root are replaced with `~/<relative_path>`.
   - Authorization headers and bearer tokens are masked as `Bearer [REDACTED]`.
   - Windows environment variables containing secrets (`%APPDATA%`, `%TEMP%`) are sanitized.

### 5.2 Diagnostic Payload Isolation
Detailed diagnostic payloads and full stack traces are collapsed by default inside `<details>` elements. They are only rendered into the DOM when explicitly expanded by the user, minimizing exposure during screen-shares or pair programming.

---

## 6. Action Classification & Auditability Matrix

Every user interaction in the Command Deck is formally classified by risk tier:

| Interaction | Target Endpoint | Risk Classification | Authorization Required | Audit Event Logged |
|---|---|---|---|---|
| **Open / Close Panel** | Client DOM only | **Read-Only** | None | No |
| **Filter Activity Feed** | In-memory store | **Read-Only** | None | No |
| **Inspect Task Details** | `GET /api/tasks` | **Read-Only** | Session Token | Yes (`audit: task_inspect`) |
| **Copy File Path** | Clipboard API | **Read-Only** | None | No |
| **Request Task Cancel** | `POST /api/tasks` (`request_cancel`) | **Navigational / Safety** | Token + 2-Step Confirmation | Yes (`audit: task_cancel_request`) |
| **Confirm Task Cancel** | `POST /api/tasks` (`cancel`) | **State-Changing** | Valid `confirmation_id` | Yes (`audit: task_cancelled`) |
| **Emergency Halt** | `Runtime.control_authority.stop()` | **Safety Override** | Session Token | Yes (`audit: emergency_stop`) |
| **Clear Local Activity** | In-memory store | **Read-Only** | None | No |

---

## 7. Safety Verification Checklist for Implementers

- [x] Does opening Command Deck execute any child processes? **NO.**
- [x] Can an agent or model bypass approvals using this interface? **NO.**
- [x] Are API keys or bearer tokens visible in diagnostic views? **NO (Redacted).**
- [x] Does the panel send telemetry outside 127.0.0.1? **NO.**
- [x] Are dynamic strings inserted via `innerHTML`? **PROHIBITED (Use `textContent`).**
- [x] Does the emergency stop latch immediately halt pending tasks? **YES.**
