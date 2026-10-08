# LUMINA action layer

The runtime exposes structured capabilities through `ToolRegistry`. Models can request a
capability, but they cannot create subprocesses or grant themselves permission.

## Available capabilities

Read-only operations include `read_file`, `find_files`, `search_file_contents`,
`file_metadata`, `fetch_web_page`, `search_memory`, and `system_info`. Their output is bounded,
credential paths are restricted, and web content is marked untrusted. `run_command` is a
bounded L1 operation for allowlisted `git`, Python, PowerShell, and small Windows inspection
commands. It captures stdout and stderr, returns exit status and duration, masks obvious
credentials, has a maximum output size, and enforces a timeout.

L1 local actions include `open_app`, `open_file`, and `open_url`. Applications are resolved
from an explicit Windows allowlist. URLs are restricted to HTTP and HTTPS. The current UI asks
for confirmation before opening a URL, which is a deliberately stronger boundary than the
minimum read-only web rule. `delete_file` is an L4 capability: the UI displays the exact file,
requires a short-lived single-use approval, and moves it to the Windows Recycle Bin when the
runtime confirms success.

## Denied by default

The generic command runner denies detached or persistent process creation, hidden process
launches, Windows service creation or modification, Scheduled Task creation or modification,
startup-folder and autorun persistence, registry autorun changes, encoded or wrapper-bypass
commands, privilege elevation, recursive LUMINA or AI launches, indefinite shells, servers,
watchers, and unbounded interactive processes. It also denies commands outside its explicit
allowlist, shell chaining, redirection, and unsupported URI schemes. Those categories could be
implemented later as separate visible, lifecycle-aware capabilities with stronger approvals;
they are not hidden inside `run_command`.

Ordinary user-visible application opening, project file reading, filename search, content search,
`git status`, bounded tests, short Python scripts, ordinary PowerShell inspection, public text
web fetches, and system information remain available. A nonzero exit code is reported as a
failure even when stdout contains plausible text.

## Ownership and observability

Each command receives an execution ID and an owned process handle. Cancellation terminates the
owned process and uses a new process group on Windows. Timeouts return a timeout result and do
not claim success. The runtime keeps the most recent bounded action history with tool, command
name, working directory, status, exit code, duration, and denial reason, while excluding raw
arguments and secrets.

Web responses are limited to readable HTTP or HTTPS content, follow at most three redirects,
reject private and local addresses, do not execute JavaScript, and are returned as untrusted
text. Retrieved page instructions never become local authority.
