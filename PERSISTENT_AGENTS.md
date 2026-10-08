# Persistent agent implementation status

Latest policy change: the user explicitly authorized the configured Claude account and
requested removal of LUMINA's metered-billing gate. The CLI billing label no longer
blocks task submission. The old allow_metered_agents setting is accepted for config
compatibility but has no effect. Claude's own permissions and the runtime's other action
boundaries remain unchanged. Source and portable copies are updated; 22 focused tests pass.
Earlier billing-block notes below describe historical verification, not current policy.

The optional tmux worker reuses TaskManager, WorkerManager, task IDs, worker events,
the worker panel and announcements. Configure worker_backend="tmux", worker="claude",
worker_executable, msys_root and agent_limit (default four) in lumina.toml.
MSYS2 and Windows Terminal remain external installation prerequisites.

Detached sessions are created before Windows Terminal attachment. A missing Terminal
leaves the session intact but does not submit work invisibly. The configured executable
is resolved to the existing native Claude binary where its installed shim permits.
Readiness requires the composer, Claude identity and exact tmux pane working directory;
update/login/trust dialogs fail closed. Briefs over 220 characters are UTF-8 files in
the user's local LUMINA agents directory. They contain private user instructions and
are retained for the agent to read across restarts. Paste uses tmux paste-buffer -p,
followed 800 ms later by a separate Enter. Only an unchanged populated composer permits
one Enter retry. Uncertain submission returns an error and preserves the session.

Pane reading returns at most sixty lines and 8000 characters. Session metadata persists
in user-local agents/sessions.json and monitors reattach on application startup. Closing
LUMINA cancels Python monitoring only. Cancel is rejected and disabled for persistent
agents. Completion detection uses Claude TUI heuristics, not a vendor completion event;
CLI UI changes can cause readiness or completion to remain unverified.

Socket discovery scans every tmux-* directory under MSYS2 tmp, configured TMUX_TMPDIR,
and registered sockets. Discovered foreign sessions are not adopted or messaged. The
current cap is enforced for lumina-prefixed live panes. Multiple simultaneous LUMINA
processes are not coordinated by a cross-process spawn lock beyond the desktop mutex.

New desktop task requests create new sessions. Explicit follow-ups support
"message agent <task-id-prefix>: <message>" or "message agent: <message>" when exactly
one session is active. The read_agent_tail tool provides bounded context for one-sentence
provider summaries. Automatic result announcements now summarize the bounded tail through
the configured, budget-guarded Gemini Live provider in a tool-disabled session. A provider
failure reports that the result is available without inventing a summary. Shutdown cancels
pending summary sessions. This path has mocked coverage; live voice delivery remains unverified.

Generic shell and discovered-app launch routes reject agent/terminal bypasses. This is
not a general sandbox against arbitrary Python code; the existing shell allowlist still
permits Python. Comprehensive indirect-process prevention remains an unresolved security
limitation and must be addressed before calling the spawn path exclusive under hostile input.

Live evidence: MSYS2 tmux 3.7c detached a test session and captured its pane. The installed
Claude Code 2.1.212 rendered its real composer in the requested project directory.
It reported API Usage Billing, so no paid test brief was submitted. Windows Terminal
is installed and the Python adapter verified a new attached tmux client against the same
Claude process. An MSYS2 script PTY bridge selects Bash explicitly. Packaged Terminal is
resolved through Get-AppxPackage when the wt alias is unavailable and activated through
ShellExecute. Existing clients cannot falsely satisfy the new-client attachment check.
The inspection session lumina-cli-probe on
C:/msys64/tmp/lumina-cli-probe.sock is preserved, with no task sent. No sessions were killed.

Acceptance remains incomplete: real task submission, completion/voice semantic summaries
and end-to-end restart behavior need live validation. No paid inference was authorized.
The portable application includes these changes and selects the tmux worker backend.
The full regression run initially found two failures caused by a missing re import in
application discovery; that defect was corrected and the affected 30-test group passed.
The new worker tests cover bounded tails, long-brief control-character rejection,
paste/Enter ordering, false idle-completion prevention and tool-disabled Live summaries.

Final full regression: 116 tests passed. A subsequent billing guard rejects submission
when the CLI explicitly reports API Usage Billing unless allow_metered_agents=true
is deliberately configured (or LUMINA_ALLOW_METERED_AGENTS=true). Default is false.
This screen-based guard is not a provider billing/account audit; it cannot establish
that every other CLI/account configuration is free.

Second independent session: lumina-38e7fde84f61 was opened without submitting a brief.
Its separate Claude process, attached Windows Terminal client and ready composer were
verified live. The original inspection session was preserved. The launch-only path does
not invoke inference. PowerShell command discovery now resolves configured .ps1 launchers
when shutil.which cannot. Readiness queries only the target pane; socket enumeration uses
bounded concurrency and tolerates unavailable sockets. Attachment scripts and new socket
paths use MSYS2 tmp to avoid package-private LocalAppData paths inaccessible to Terminal.
The existing second session's socket has a hard-link alias there; no agent was restarted.
Sixteen focused worker/task tests passed after these changes; the portable adapter is synced.
