"""Owned, bounded subprocess execution for Windows development commands."""
import asyncio
import os
import secrets
import time
from pathlib import Path
from .shell_policy import inspect

MAX_OUTPUT = 64 * 1024


def mask(text):
    import re
    text = re.sub(r'(?i)(api[_-]?key|access[_-]?token|password|secret|authorization)\s*[:=]\s*[^\s,;]+', r'\1=[REDACTED]', text)
    text = re.sub(r'AIza[0-9A-Za-z_-]{20,}', '[REDACTED_KEY]', text)
    return text


class ShellExecutionService:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.processes = {}
        self.history = []

    def _cwd(self, value):
        path = (self.root / value).resolve() if value else self.root
        if not path.is_dir() or not path.is_relative_to(self.root):
            raise ValueError('The working directory must be an existing folder inside the configured root.')
        return path

    async def execute(self, command, arguments=None, cwd=None, timeout=15, session_id=None):
        arguments = arguments or []
        if not isinstance(arguments, list) or any(not isinstance(item, str) or len(item) > 2048 for item in arguments):
            return {'status': 'denied', 'denied': True, 'reason': 'arguments_invalid'}
        allowed, reason = inspect(command, arguments)
        execution_id = secrets.token_urlsafe(12)
        started = time.monotonic()
        if not allowed:
            result = {'execution_id': execution_id, 'status': 'denied', 'denied': True, 'reason': reason, 'exit_code': None, 'stdout': '', 'stderr': ''}
            self._record(command, cwd, result, started)
            return result
        try:
            workdir = self._cwd(cwd)
            timeout = max(1, min(int(timeout), 120))
        except (TypeError, ValueError) as exc:
            result = {'execution_id': execution_id, 'status': 'denied', 'denied': True, 'reason': str(exc), 'exit_code': None, 'stdout': '', 'stderr': ''}
            self._record(command, cwd, result, started)
            return result
        env = {key: value for key, value in os.environ.items()
               if key.upper() not in {'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'ANTHROPIC_API_KEY'}
               and not key.upper().startswith(('TELEGRAM_', 'DISCORD_', 'WHATSAPP_', 'GMAIL_'))}
        try:
            process = await asyncio.create_subprocess_exec(command, *arguments, cwd=str(workdir), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, creationflags=getattr(subprocess_flags(), 'new_group', 0))
        except OSError:
            result = {'execution_id': execution_id, 'status': 'failed', 'denied': False, 'reason': 'executable_unavailable', 'exit_code': None, 'stdout': '', 'stderr': ''}
            self._record(command, workdir, result, started)
            return result
        self.processes[execution_id] = process
        if session_id: self.processes.setdefault(str(session_id), process)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            status = 'success' if process.returncode == 0 else 'failed'
            result = {'execution_id': execution_id, 'status': status, 'denied': False, 'exit_code': process.returncode,
                      'stdout': mask(stdout[:MAX_OUTPUT].decode(errors='replace')), 'stderr': mask(stderr[:MAX_OUTPUT].decode(errors='replace')),
                      'truncated': len(stdout) > MAX_OUTPUT or len(stderr) > MAX_OUTPUT}
        except asyncio.TimeoutError:
            await self.cancel(execution_id)
            result = {'execution_id': execution_id, 'status': 'timeout', 'denied': False, 'exit_code': None, 'stdout': '', 'stderr': '', 'timed_out': True}
        finally:
            self.processes.pop(execution_id, None); self.processes.pop(str(session_id), None)
        self._record(command, workdir, result, started)
        return result

    async def cancel(self, execution_id):
        process = self.processes.get(str(execution_id))
        if not process or process.returncode is not None: return False
        process.terminate()
        try: await asyncio.wait_for(process.wait(), timeout=3)
        except asyncio.TimeoutError: process.kill(); await process.wait()
        return True

    def _record(self, command, cwd, result, started):
        self.history.append({'execution_id': result['execution_id'], 'tool': 'run_command', 'command': Path(command).name,
                             'cwd': str(cwd or self.root), 'status': result['status'], 'exit_code': result.get('exit_code'),
                             'duration_ms': round((time.monotonic()-started)*1000), 'reason': result.get('reason')})
        self.history = self.history[-100:]


def subprocess_flags():
    class Flags: new_group = 0
    if os.name == 'nt':
        Flags.new_group = getattr(__import__('subprocess'), 'CREATE_NEW_PROCESS_GROUP', 0)
    return Flags
