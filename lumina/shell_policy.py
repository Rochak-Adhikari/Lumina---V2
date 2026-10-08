"""Conservative Windows-first policy for the bounded command capability."""
import re
from pathlib import PureWindowsPath

SAFE_COMMANDS = {'git', 'python', 'python3', 'py', 'powershell', 'pwsh', 'where', 'whoami', 'hostname', 'ipconfig', 'ver', 'set', 'echo'}
DENIALS = (
    ('untracked_agent_terminal', re.compile(r'(?i)(?:\bwt(?:\.exe)?\b|windowsterminal|\bmsys2?\b|\bmintty\b)')),
    ('persistent_process', re.compile(r'(?i)(?:start-process|start-job|start-threadjob|\bstart\s+\/|\bnohup\b|\btmux\b|\bscreen\b|\blaunchctl\b|\bosascript\b)')),
    ('service_persistence', re.compile(r'(?i)(?:\bsc(?:\.exe)?\s+(?:create|config|start)|new-service|installutil|\bservice\b.*(?:create|install|autostart))')),
    ('scheduled_persistence', re.compile(r'(?i)(?:schtasks|new-scheduledtask|register-scheduledtask|at\.exe)')),
    ('startup_persistence', re.compile(r'(?i)(?:startup\\|start menu\\programs\\startup|currentversion\\run|runonce|\bautorun\b)')),
    ('registry_persistence', re.compile(r'(?i)(?:reg(?:\.exe)?\s+(?:add|import|delete)|set-itemproperty[^\n]*(?:run|startup))')),
    ('recursive_ai_launch', re.compile(r'(?i)(?:\b(?:claude|codex|gemini)\b|python\s+-m\s+lumina|lumina\.exe|recursive)')),
    ('wrapper_bypass', re.compile(r'(?i)(?:-encodedcommand|-enc\b|cmd(?:\.exe)?\s+\/c[^\n]*(?:powershell|pwsh)|powershell[^\n]*-windowstyle\s+hidden|invoke-expression|iex\s)')),
    ('privilege_escalation', re.compile(r'(?i)(?:-verb\s+runas|\brunas(?:\.exe)?\b|\bsudo\b|\belevat(?:e|ion)\b)')),
    ('unbounded_process', re.compile(r'(?i)(?:\b(?:watch|server|repl|shell|powershell|cmd)\b[^\n]*(?:--watch|--reload|http\.server|tail\s+-f)|npm\s+run\s+(?:dev|start)|python\s+-m\s+http\.server)')),
)


def inspect(command, arguments):
    if not isinstance(command, str) or not command.strip():
        return False, 'missing_command'
    executable = PureWindowsPath(command).name.casefold()
    if executable.endswith(('.exe', '.cmd', '.bat')):
        executable = executable.rsplit('.', 1)[0]
    if executable not in SAFE_COMMANDS:
        return False, 'command_not_allowlisted'
    text = ' '.join([command, *(str(arg) for arg in (arguments or []))])
    code_argument = executable in {'python', 'python3', 'py'} and '-c' in (arguments or [])
    if not code_argument and any(operator in text for operator in ('&&', '||', ';', '|', '>', '<')):
        return False, 'shell_chaining_or_redirection'
    for reason, pattern in DENIALS:
        if pattern.search(text):
            return False, reason
    return True, None


# Human-readable boundary, surfaced through /api/capabilities so restrictions are
# inspectable rather than discovered on failure.
DENIAL_REPORT = [
    {'reason':'untracked_agent_terminal','capability':'wt.exe, WindowsTerminal, mintty, MSYS launchers',
     'why':'Would start an untracked agent through a second launch path.','always_denied':True,
     'alternative':'Use the supervised spawn/task tool.'},
    {'reason': 'persistent_process', 'capability': 'tmux, screen, nohup, launchctl, osascript, Start-Process, Start-Job',
     'why': 'Would leave a process running after the task ends.', 'always_denied': True,
     'alternative': 'Run a bounded command that terminates on its own.'},
    {'reason': 'service_persistence', 'capability': 'sc create/config, New-Service, installutil',
     'why': 'Creates a Windows service that survives the session.', 'always_denied': True,
     'alternative': 'None through the generic shell; use a dedicated approved workflow.'},
    {'reason': 'scheduled_persistence', 'capability': 'schtasks, Register-ScheduledTask, at.exe',
     'why': 'Schedules future execution outside the current task.', 'always_denied': True, 'alternative': None},
    {'reason': 'startup_persistence', 'capability': 'Startup folder, CurrentVersion\\Run, RunOnce, autorun',
     'why': 'Makes a program auto-launch on logon or reboot.', 'always_denied': True, 'alternative': None},
    {'reason': 'registry_persistence', 'capability': 'reg add/import/delete, Set-ItemProperty on Run keys',
     'why': 'Registry-based autorun persistence.', 'always_denied': True, 'alternative': 'Read-only inspection only.'},
    {'reason': 'recursive_ai_launch', 'capability': 'claude, codex, gemini, python -m lumina (incl. indirect via osascript -> Terminal -> claude)',
     'why': 'Prevents uncontrolled recursive agent process trees.', 'always_denied': True,
     'alternative': 'Use the formal worker/task subsystem.'},
    {'reason': 'wrapper_bypass', 'capability': '-EncodedCommand, cmd /c powershell, Invoke-Expression, hidden window',
     'why': 'Obscures the effective operation to bypass policy.', 'always_denied': True, 'alternative': None},
    {'reason': 'privilege_escalation', 'capability': '-Verb RunAs, runas, sudo, elevation',
     'why': 'A routine action must not silently gain Administrator rights.', 'always_denied': True, 'alternative': None},
    {'reason': 'unbounded_process', 'capability': 'dev servers, watchers, REPLs, http.server, tail -f, npm run dev/start',
     'why': 'Interactive/long-running processes exceed the task-bounded shell.', 'always_denied': True,
     'alternative': 'Use a lifecycle-aware tool for long-running processes.'},
    {'reason': 'command_not_allowlisted', 'capability': 'Any executable outside the safe allowlist',
     'why': 'Only reviewed, bounded commands are permitted.', 'always_denied': False,
     'alternative': 'Request the command be added to SAFE_COMMANDS if it is safe and bounded.'},
    {'reason': 'shell_chaining_or_redirection', 'capability': '&&, ||, ;, |, >, < operators',
     'why': 'Chaining/redirection can hide a denied effective operation.', 'always_denied': False,
     'alternative': 'Run one command per request.'},
]
