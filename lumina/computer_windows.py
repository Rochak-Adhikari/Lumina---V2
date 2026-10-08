"""Private, bounded Windows transport and shared confirmation bookkeeping.

Only fixed helper code executes. Requests travel on stdin, never a command line.
No shell, keyboard injection, clipboard, logging, or permission grants exist here.
"""
from __future__ import annotations

import asyncio
import copy
import json
import math
import os
from pathlib import Path
import secrets
import time
import threading


_MUTATION_LOCK = threading.Lock()


class ComputerError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def failure(code, **extra):
    return dict(ok=False, status=code, error=code, **extra)


class WindowsProvider:
    """One owned PowerShell process per operation, killed/reaped on cancellation.

    Timeout after mutation means unknown outcome; callers must inspect, not retry.
    PowerShell/.NET UIA ship with Windows. Unsupported hardware fails explicitly.
    """
    def __init__(self, timeout=12):
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError('timeout must be between 0 and 60 seconds')
        self.timeout = timeout
        self.secret = secrets.token_hex(32)

    def status(self):
        return dict(ok=os.name == 'nt', status='configured' if os.name == 'nt' else 'unavailable',
                    provider='windows-native-uia', visual_fallback=False)

    async def request(self, operation, **arguments):
        if os.name != 'nt':
            return failure('unavailable')
        executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        payload = json.dumps(dict(operation=operation, secret=self.secret, **arguments)).encode('utf-8')
        if len(payload) > 256 * 1024:
            return failure('request_too_large')
        process = None
        spawn = asyncio.create_task(asyncio.create_subprocess_exec(
            str(executable), '-NoLogo', '-NoProfile', '-NonInteractive', '-File',
            str(Path(__file__).with_name('computer_windows_helper.ps1')),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, creationflags=0x08000000))
        try:
            async with asyncio.timeout(self.timeout):
                process = await asyncio.shield(spawn)
                process.stdin.write(payload)
                await process.stdin.drain()
                process.stdin.close()
                # Bound memory even if a provider malfunctions.
                chunks, size = [], 0
                while chunk := await process.stdout.read(8192):
                    size += len(chunk)
                    if size > 1024 * 1024:
                        raise ComputerError('response_too_large')
                    chunks.append(chunk)
                if await process.wait() != 0:
                    raise ComputerError('provider_failed')
                result = json.loads(b''.join(chunks).decode('utf-8-sig'))
                if not isinstance(result, dict) or type(result.get('ok')) is not bool:
                    raise ComputerError('invalid_response')
                return result
        except TimeoutError:
            return failure('timeout', outcome='unknown' if operation.endswith('_apply') else 'not_started')
        except (OSError, ValueError):
            return failure('provider_failed', outcome='unknown' if operation.endswith('_apply') else 'not_started')
        finally:
            if process is None:
                try:
                    process = await asyncio.shield(spawn)
                except (OSError, asyncio.CancelledError):
                    pass
            if process is not None and process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await asyncio.shield(process.wait())


class ConfirmedService:
    """Tokens bind requests, NOT consent. execute_confirmed is trusted-only.

    Integrator MUST gate reads under current privacy policy and mutations under
    current permission/consequence policy. Never register execute_confirmed as a
    model-callable tool. All mutations request approval, including undo.
    """
    def __init__(self, provider=None, *, clock=time.monotonic):
        self.provider = provider or WindowsProvider()
        self.clock = clock
        self.pending = {}
        self.lock = asyncio.Lock()

    def _prune(self):
        now = self.clock()
        self.pending = {k: v for k, v in self.pending.items() if now - v[0] < 60}

    def _prepare(self, public, private):
        self._prune()
        if len(self.pending) >= 128:
            raise ComputerError('too_many_pending_requests')
        token = secrets.token_urlsafe(24)
        self.pending[token] = (self.clock(), copy.deepcopy(public), copy.deepcopy(private))
        return dict(ok=False, status='confirmation_required', requires_confirmation=True,
                    confirmation=token, request=copy.deepcopy(public))

    def _consume(self, token, request):
        self._prune()
        item = self.pending.pop(token, None) if isinstance(token, str) else None
        if item is None or item[1] != request:
            raise ComputerError('confirmation_mismatch_or_expired')
        return item[2]

    async def execute(self, action, **args):
        async with self.lock:
            acquired = False
            try:
                if action == 'execute_confirmed':
                    acquired = _MUTATION_LOCK.acquire(blocking=False)
                    if not acquired:
                        return failure('busy')
                if action == 'status':
                    self._keys(args, set())
                    return self.provider.status()
                if action == 'cancel':
                    self._keys(args, {'confirmation'})
                    self.pending.pop(args['confirmation'], None)
                    return dict(ok=True, status='cancelled')
                return await self._dispatch(action, args)
            except ComputerError as exc:
                return failure(exc.code)
            except (TypeError, KeyError, ValueError):
                # Never include provider exception text or request repr (private text).
                return failure('invalid_request')
            finally:
                if acquired:
                    _MUTATION_LOCK.release()

    @staticmethod
    def _keys(args, required, optional=frozenset()):
        if set(args) - required - optional or required - set(args):
            raise ComputerError('invalid_arguments')

    async def _call(self, operation, **args):
        result = await self.provider.request(operation, **args)
        if not result.get('ok'):
            # Provider owns only fixed error codes, no arbitrary exception messages.
            return result
        return copy.deepcopy(result)
