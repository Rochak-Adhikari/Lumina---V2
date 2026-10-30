# Lumina Command Deck: UX & Interface Specification

**Document ID:** `CD-UX-001`  
**Feature:** Lumina Command Deck (`CD`)  
**Status:** User Experience & Visual Specification / Pre-Implementation  
**Target System:** Lumina AI Companion Dashboard (`Lumina---V2`)  
**Author:** AI Systems Engineering Architecture & Design Team  

---

## 1. Visual Theme Authority & Design Token Integration

The Command Deck is not a standalone app or an external website. It lives directly inside Lumina's existing single-page web environment.

The design authority is strictly governed by **`web/crimson.css`** and **`web/style.css`**. No foreign CSS frameworks, ad-hoc hex palettes, or competing component abstractions are allowed.

### 1.1 Verified Design Tokens (from `web/crimson.css`)

All Command Deck UI elements MUST consume these exact CSS Custom Properties:

```css
/* Backgrounds & Surfaces */
--lumina-bg: #030303;                  /* Primary canvas background */
--lumina-bg-secondary: #070708;        /* Nav rail and secondary panels */
--lumina-panel: #0b0c0e;               /* Dialog cards and container base */
--lumina-panel-elevated: #111216;      /* Hover states, drawer surfaces, raised cards */

/* Accent & Crimson Glow */
--lumina-red: #e5092f;                 /* Brand primary crimson */
--lumina-red-bright: #ff173d;          /* Active glow, highlights, borders */
--lumina-red-dark: #8b0018;            /* Button active, background fills */
--lumina-border: #ffffff14;            /* Subtle card dividers (1px solid rgba(255,255,255,0.08)) */
--lumina-border-red: #ff173d47;        /* Glowing panel borders (rgba(255, 23, 61, 0.28)) */
--lumina-glow: 0 0 20px #ff173d29;      /* Ambient crimson glow */
--lumina-glow-active: 0 0 30px #ff173d4d; /* High-intensity alert glow */

/* Semantic Status Accents */
--lumina-success: #20e6a5;             /* Mint: Ready, Completed, Connected */
--lumina-warning: #ffb83e;             /* Amber: Waiting for User, Thinking, Pending Approval */
--lumina-info: #39d9ff;                /* Cyan: Listening, Worker Task Active */

/* Typography & Contrast */
--lumina-text: #f4f6f8;                /* Primary headings and active labels */
--lumina-text-secondary: #a5acb8;      /* Supporting text, timestamps, subtitles */
--lumina-text-muted: #89919d;          /* Minor captions, borders, quiet buttons */
--soft: #ff859a;                       /* Subtle pink accent for focus rings & wordmarks */

/* Typography Families */
font-family: 'Segoe UI Variable', 'Segoe UI', -apple-system, sans-serif;
monospace-font: Consolas, 'SF Mono', 'Courier New', monospace;
```

---

## 2. Navigation & Layout Integration

### 2.1 Nav Rail Placement (`web/index.html`)
The Command Deck button is inserted into the existing vertical rail (`<nav class="nav-rail" id="workspace-navigation">`) as a top-tier item alongside Memory, Workers, and Controls:

```html
<button id="command-deck-open" type="button" aria-label="Command Deck" title="Command Deck">
  <span aria-hidden="true">⌘</span>
  <span>Command Deck</span>
</button>
```

In `web/shell.js`, dynamic SVG injection renders the native radar/deck icon:
```javascript
paths['command-deck-open'] = 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5';
```

When opened, the nav rail highlights the button with the standard active styling:
```css
button[aria-current] {
  color: var(--text);
  background: linear-gradient(90deg, #ff173d25, #ff173d05);
  border-color: var(--lumina-border-red);
  box-shadow: inset 2px 0 var(--lumina-red-bright);
}
```

### 2.2 Modal Structure & Geometry
The Command Deck uses the native `<dialog>` element styled according to Lumina's dialog standards:
- **Class:** `command-deck-modal`
- **Max Width:** `1200px` (or `94vw` on smaller viewports).
- **Max Height:** `88vh`.
- **Backdrop:** `background: #000000a6; backdrop-filter: blur(4px);`
- **Border:** `1px solid var(--lumina-border-red); border-radius: 12px;`

---

## 3. Information Hierarchy & Grid Layout

The layout uses a multi-tier dashboard layout optimized for high density and immediate visual hierarchy:

```
+---------------------------------------------------------------------------------------+
|  COMMAND DECK   /   OPERATIONAL COMMAND CENTER                             [X Close]   |
+---------------------------------------------------------------------------------------+
|  1. LIVE STATUS HEADER (Compact glowing horizontal telemetry strip)                   |
|  [● READY]  [Online: Gemini Live]  [Filesystem: Root Bound]  [0 Pending]  [12:44:05]  |
+-----------------------------------------------------------+---------------------------+
|  LEFT COLUMN: 60%                                         |  RIGHT COLUMN: 40%        |
|                                                           |                           |
|  2. MISSION CONTROL (Task Manager)                        |  4. SYSTEM WATCH          |
|  +-----------------------------------------------------+  |  +---------------------+  |
|  | Active Tasks (1 Running)             [Refresh]     |  |  | Warnings & Health   |  |
|  | +-------------------------------------------------+ |  |  | ● Runtime Normal    |  |
|  | | ◈ Claude Code: Refactor audio worklet          | |  |  | ● Safety Latch OK   |  |
|  | | Status: RUNNING (42s elapsed)       [Inspect]   | |  |  +---------------------+  |
|  | +-------------------------------------------------+ |  |                           |
|  +-----------------------------------------------------+  |  5. WORKSPACE MONITOR     |
|                                                           |  +---------------------+  |
|  3. ACTIVITY FEED (Timeline)                              |  | Active Workspace    |  |
|  [All (48)] [Tasks] [Tools] [Approvals] [System]          |  | d:/R O C H A K/LUNA3|  |
|  +-----------------------------------------------------+  |  | Uploads: 4 Files    |  |
|  | 12:44:01 ◈ Task claude-code startedTurn             |  |  | [Copy Path]         |  |
|  | 12:43:55 ⚙ Tool find_files executed (ok)            |  |  +---------------------+  |
|  | 12:43:10 ⚠ Approval granted: read_file              |  |                           |
|  +-----------------------------------------------------+  |                           |
+-----------------------------------------------------------+---------------------------+
```

---

## 4. UI States Specification

The interface handles all operational states transparently, communicating uncertainty honestly:

### 4.1 Loading State
- Rendered when the dialog opens before initial REST fetches complete.
- Content containers display a subtle pulsing skeleton with animated gradient (`#111216` to `#181920`).
- Text readout displays: `"Synchronizing operational state..."` in `--lumina-text-muted`.

### 4.2 Empty State
- **Tasks Empty:** `"No active or recent agent tasks. When background tasks run, their progress will appear here."`
- **Activity Empty:** `"No operational events recorded in this session."`
- **System Watch Empty:** Mint badge: `"All subsystems healthy. No active warnings or faults."`

### 4.3 Stale / Disconnected State
- If the WebSocket connection drops, the Live Status bar gains a warning border: `border: 1px solid var(--lumina-warning)`.
- Timestamp reads: `[STALE - RECONNECTING...]` in pulsing amber.
- Interactive action buttons (e.g., Cancel Task) are automatically disabled with tooltip: `"Disabled: Runtime disconnected"`.

### 4.4 Error State
- If an individual section fails to load (e.g., `/api/tasks` returns 500), that specific section renders an isolated error card with a retry button:
  `[!] Task service unavailable. [Retry]`
- The rest of the Command Deck continues functioning normally.

---

## 5. Interaction Matrix

Every interactive element defines explicit triggers, visual feedback, and failure handling:

| Control / Target | Trigger | Visual Feedback | Result / Action | Failure State | Read-Only? |
|---|---|---|---|---|---|
| **Close Button (`×`)** | Click or `Esc` key | Border fades; modal closes | `dialog.close()` | None (Native) | Yes |
| **Task Card `[Inspect]`** | Click on task row | Row highlights; drawer slides in | Opens Task Diagnostics Drawer (`CD-F006`) | Shows "Task unavailable" | Yes |
| **Task Card `[Cancel]`** | Click button | Button turns amber: "Confirm?" | Invokes 2-step `POST /api/tasks` (`request_cancel`) | Reverts to "Cancel Failed" | No (Safe) |
| **Activity Filter Pill** | Click category pill | Pill gains border and crimson fill | Filters in-memory feed instantly (<5ms) | Empty list if 0 matches | Yes |
| **Copy Path Button** | Click button | Text flashes: `"Copied!"` (1.5s) | Writes path to `navigator.clipboard` | Notice: "Clipboard unavailable" | Yes |
| **Pending Approval Badge**| Click badge | Dialog closes; main modal opens | Dispatches `lumina-event: {type: 'confirmation_open'}` | Shows notice error | Yes (Navigational)|

---

## 6. Accessibility & Motion Standards

1. **Semantic HTML:**
   All cards use `<article>`, section headers use `<header>` and `<h3>`, and interactive actions use native `<button>`.
2. **Keyboard Navigation:**
   - Opening the dialog traps focus inside using standard modal dialog behavior.
   - Pressing `Escape` closes the panel and returns focus to the nav rail button.
   - All interactive items provide visible focus rings:
     `outline: 2px solid var(--soft); outline-offset: 3px;`
3. **Contrast Compliance:**
   All text combinations exceed WCAG 2.1 AA contrast requirements (minimum 4.5:1 for body text against dark backgrounds).
4. **Reduced Motion (`prefers-reduced-motion`):**
   Adheres to the global rule declared in `web/crimson.css`:
   ```css
   @media (prefers-reduced-motion: reduce) {
     *, *:before, *:after {
       animation: none !important;
       transition: none !important;
       scroll-behavior: auto !important;
     }
   }
   ```
   No pulsing animations or glowing transitions execute when reduced motion is preferred.
