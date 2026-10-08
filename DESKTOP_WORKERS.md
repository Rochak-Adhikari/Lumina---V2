# Desktop control and visible workers

## Delivery status

The desktop services and supervised worker panel are implemented. This is **not a claim that every master-prompt acceptance condition is complete**. A real Claude process started in ConPTY and its output reached the browser, but Claude returned “Not logged in”. A successful authenticated Claude coding turn remains unverified. The worker deliberately has scoped file capabilities rather than unrestricted shell execution.

## Architecture audit and changes

The existing application is Python aiohttp with a native WebSocket and vanilla JavaScript. It has no Socket.IO, DI container, or SkillManager. The implementation reuses `Runtime`, `ToolRegistry`, `TaskManager`, the existing confirmation boundary, and the existing WebSocket broadcast queues. The lean-build skill guided this reuse rather than introducing a second server or task system.

`DesktopServices` owns `WorkspaceManager`, `PathResolver`, `FileSearchService`, `FilesystemManager`, `ApplicationManager`, `ProcessManager`, `ExplorerManager`, and `TerminalManager`. Directory search shares the file-search implementation and cache. Desktop scope and worker workspace scope are separate.

Application discovery reads PATH executables, Windows App Paths registry entries, and Start Menu shortcuts. The cache lasts five minutes and can be refreshed. It does not crawl drive roots. Names, aliases, application IDs, launch targets, discovery sources and timestamps are available; unavailable publisher/install-date/icon fields are explicitly null. Ambiguous matches are returned for selection. Browser selection does not silently prefer a vendor.

Search is scoped to one validated directory, bounded to five seconds and 20,000 entries, cached for fifteen seconds, and invalidated after filesystem changes. Counts cover the scanned scope, with explicit incomplete/truncated flags. Search supports exact, partial, fuzzy, extension and path matches. Directory results are genuine matches, not graph parent nodes.

## Files created

- `lumina/desktop.py`: desktop services, scoped paths, search, discovery, structured filesystem operations.
- `lumina/worker_terminal.py`: owned Windows ConPTY transport and cleanup.
- `lumina/worker_bridge.py`: private stdio MCP workspace tools.
- `web/workers.js`: live worker panel and cancellation controls.
- `tests/test_desktop.py`: discovery, paths, filesystem changes, confirmations, bridge boundaries and environment tests.
- `tests/test_visible_workers.py`: streams, independent workers, completion/failure/cancellation, real ConPTY and browser tests.
- `scripts/verify_visible_worker.py`: explicit real Claude authentication/terminal probe.
- `scripts/verify_desktop_acceptance.py`: explicit live server acceptance probe; opens VS Code and creates `test123`.
- `DESKTOP_WORKERS.md`: this delivery and limitations record.

## Files modified

- `lumina/config.py`, `lumina.example.toml`: additional desktop roots.
- `lumina/tools.py`: structured desktop tools, validation and exact confirmations.
- `lumina/runtime.py`: worker events, status, deterministic desktop/delegation commands.
- `lumina/tasks.py`: task/workspace metadata, worker IDs and cancellation cleanup.
- `lumina/workers.py`: supervised lifecycle, stream parsing, controlled environment and scoped bridge.
- `lumina/server.py`: worker snapshots and validated task workspace selection.
- `web/index.html`, `web/controls.js`: worker panel, selected workspace and confirmations.
- `requirements.txt`: Windows-only pywinpty dependency.
- `tests/test_workers.py`, `tests/test_local_operations.py`: updated expectations for structured streaming and discovery.

## New tools and capabilities

Read-only: `desktop_locations`, `resolve_path`, `inspect_path`, `list_directory`, `search_files`, `search_directories`, `discover_applications`, `find_application`, `list_processes`, `worker_status`.

Local actions: `create_directory`, `copy_path`, `open_folder`, `reveal_in_explorer`, `open_terminal`, `open_with`, `launch_application`, `refresh_application_index`. Existing `open_app` now discovers applications instead of using the old short allowlist.

Confirmed actions: `move_path`, `rename_path`, `delete_path`, `terminate_process`. Folder deletion explicitly includes contents and uses the Recycle Bin. Approval expires after sixty seconds, is single-use, binds exact normalized paths, and rejects a changed target tree. Existing destination paths are not overwritten. Only recorded LUMINA-owned processes can be terminated by this tool.

No external Codex skill was installed. These are LUMINA runtime tools.

The previous conservative `open_file` document restrictions remain; use `open_with` for source files such as Python, to avoid accidentally executing them through a default association. Content reads/search in the original tools remain scoped to the original project root.

## Events and UI

No Socket.IO events were added because the project does not use Socket.IO. The existing `/ws` transports `worker_event` envelopes and `worker_panel_open`. `/api/workers` provides reconnectable snapshots.

Worker event types currently emitted: `worker.created`, `worker.starting`, `worker.started`, `worker.output`, `worker.tool_call`, `worker.file_changed`, `worker.completed`, `worker.failed`, `worker.cancelled`, `worker.exited`, `worker.terminal_closed`.

The panel displays independent sessions, task text, workspace, status, elapsed time, actual bounded/redacted terminal records, confirmed changed files, errors, and lifecycle events. Raw output uses text rendering, not HTML, and is not sent to the speech queue. Existing agent result announcements remain concise.

## Worker lifecycle

`WorkerManager` is authoritative for execution state. Each task ID, worker ID and process ID is distinct. A resumed task starts a new worker turn, retaining bounded prior task context; it is not a resumed interactive CLI terminal.

Normal progression is CREATED → STARTING → RUNNING → COMPLETED or FAILED. Cancellation cleans up the owned process tree and terminal before task cancellation is reported. The registry supports WAITING/TERMINATED transitions, but does not manufacture input requests from idle time. No fake PAUSED state or pause button is exposed.

Claude runs its documented structured print stream inside ConPTY on Windows. This is an owned terminal process with live output, not an unattended terminal window. Interactive prompt/input injection is intentionally unavailable; silence is not treated as proof of a prompt. Non-Windows test execution can use pipes.

## Security and environment

A working directory is **not** an operating-system sandbox. The old worker's claimed workspace isolation was not enforced by its `cwd` argument.

The replacement disables Claude's built-in tools, arbitrary shell tools, hooks, project/user setting sources, Chrome integration, slash commands and inherited MCP servers. A private MCP server exposes only bounded workspace search/read/create/exact-edit operations. Its path validator rejects escaping paths, hidden credential files, alternate streams, symlinks and junctions. Enforcement source is pinned before worker edits and copied into a hidden temporary bundle, preventing a task from changing the running bridge by editing LUMINA's source files.

The worker environment starts from an OS-variable allowlist. Gemini, Google, Anthropic API keys, unrelated tokens, NODE_OPTIONS, PYTHONPATH and custom environment secrets are not inherited. The trusted Claude executable may use its own configured account authentication. This is a constrained tool boundary, **not** an OS sandbox for an untrusted Claude binary or an administrator modifying files concurrently.

No paid fallback or extra credential provider was introduced. Raw output stays in bounded memory, with common key/token patterns redacted; it is not written to persistent application audit logs. Audit logs record lifecycle metadata.

## Configuration and running

From the project folder in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start.ps1
```

Open `http://127.0.0.1:8764/`, refresh the page, and use Workers for live output or Local controls to start a task. The task form accepts an optional workspace inside configured desktop roots.

To allow additional desktop locations, add existing bounded directories to `lumina.toml`, for example:

```toml
desktop_roots = ["D:/AI", "D:/Projects"]
```

The current root is always included. Entire drive roots are rejected. These extra roots do not extend an individual worker's workspace.

Claude authentication is required separately. Run the installed `claude` CLI yourself and sign in, then retry the task. LUMINA does not sign in on your behalf or supply another provider's API key.

## Verification

Automated tests cover installed-application discovery from a temporary PATH, exact/alias/ambiguous resolution, absolute/relative/environment paths, metadata, nested creation, search, copy/move/rename, no-overwrite behavior, confirmation expiry/use/changed targets, permission failures, secret/traversal/link rejection, environment sanitization, explicit lifecycle transitions, separate workers, cancellation, completion/failure streams, real Windows ConPTY output/exit/cleanup, and browser status/output/error/multiple-worker rendering.

The live Windows acceptance probe resolved this actual LUMINA project, launched the discovered VS Code executable with the project, created `test123`, and found forty Python files in the bounded project scan at that time. The second run correctly refused to recreate the existing directory. The test folder is retained.

LUMINA was actually restarted on port 8764. A real Claude task appeared in the panel and streamed an authentication failure, which the UI displayed. Screenshot: `artifacts/desktop-live-acceptance.png`. The failure path is verified; authenticated inspection/edit/test completion is not.

Final regression: `.\.venv\Scripts\python.exe -m pytest -q` — **59 passed in 18.99 seconds**. Python compilation check: `.\.venv\Scripts\python.exe -m compileall -q lumina` — passed. There is no configured standalone lint/type-check gate in this repository.

## Remaining limitations and decisions

- Claude must be signed in before successful live task acceptance can be completed. No login or account change was performed.
- Worker shell/test execution is disabled. Running arbitrary project code with a hard workspace boundary needs a genuine OS sandbox/container; giving it an unrestricted shell would violate this prompt's isolation requirement. Test fields report no tests rather than inventing them.
- Interactive input, real pause/resume of a process, and permission-prompt mediation are unavailable. A follow-up task turn is supported after completion.
- Discovery does not yet populate install dates/publishers/icons consistently or enumerate every packaged Windows app. “Installed yesterday” cannot be resolved truthfully from current metadata. Shortcut-only applications can launch, but opening a path with one requires a discoverable executable.
- Search does not build a persistent computer-wide index or background crawler. Recent/context aliases are limited to runtime state; an ambiguous search asks for a specific path.
- Desktop tools remain within configured roots; access to unrelated folders is not silently granted. Listing drives does not authorize traversing them.
- Process inspection covers LUMINA-owned launched applications/terminals; workers have their own authoritative session records. It is not a system-wide process administration service.
- Natural-language local parsing covers the explicit acceptance commands and selected compound requests. General phrasing depends on the configured reasoning provider; a request to start Claude without a task still needs an instruction.
- Copying/moving between actual physical drives, real Recycle Bin deletion and a successful authenticated two-Claude-task run were not exercised in live acceptance. Safe destructive paths and independent cancellation were tested with controlled fixtures.
- Worker/task history is in memory and resets on server restart. There is no claim of durable terminal resumption.

No additional approval is needed for the delivered local implementation. Authentication is the immediate external prerequisite. Any future expansion to unrestricted worker shell execution must first establish an actual isolation mechanism.

## Reference

The Windows terminal adapter follows the [pywinpty API](https://github.com/andfoy/pywinpty). Claude's available flags were inspected from the installed CLI's `--help`, rather than assumed from a different version.
