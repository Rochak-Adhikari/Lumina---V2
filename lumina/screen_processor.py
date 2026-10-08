"""One-shot local screen capture. Only ``last_frame`` contains image bytes.

Coordinates are physical virtual-desktop pixels (negative origins are valid).
Window sources are opaque identities returned by sources(); captures show visible
desktop pixels and may include occlusion. No provider or upload is involved.
"""
import asyncio
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import sys


class ScreenProcessor:
    def __init__(self, *, timeout=10.0):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('timeout must be positive and finite')
        self.timeout = timeout
        self._last_frame = None
        self._closed = False
        self._task = None
        self._state = 'ready'

    @property
    def last_frame(self):
        return self._last_frame

    def status(self):
        missing = [name for name in ('mss', 'PIL') if importlib.util.find_spec(name) is None]
        available = sys.platform == 'win32' and not missing and not self._closed
        return {'ok': available, 'available': available,
                'state': 'closed' if self._closed else self._state if available else 'unavailable',
                'missing_dependencies': ['Pillow' if x == 'PIL' else x for x in missing],
                'platform': sys.platform, 'has_frame': self._last_frame is not None,
                'continuous': False}

    async def sources(self):
        return await self._request({'operation': 'sources'})

    async def capture(self, target='monitor', source='1', region=None):
        """Return metadata; region is absolute ``x,y,w,h`` within source bounds.

        Use target='region' with a monitor source, or supply region to crop a
        monitor/window. Monitor indices and window identities come from sources().
        A new attempt clears the previous frame, including failed attempts.
        """
        if self._task is not None:
            return {'ok': False, 'error': 'busy'}
        self._last_frame = None
        try:
            if target not in ('monitor', 'window', 'region'):
                raise ValueError('target must be monitor, window, or region')
            if not isinstance(source, str) or not source:
                raise ValueError('source must be a nonempty string')
            if region is not None:
                if not isinstance(region, str):
                    raise ValueError('region must be x,y,w,h')
                values = tuple(int(x.strip()) for x in region.split(','))
                if len(values) != 4 or values[2] <= 0 or values[3] <= 0:
                    raise ValueError('region must have positive width and height')
            else:
                values = None
            if target == 'region' and values is None:
                raise ValueError('region target requires x,y,w,h')
        except ValueError as exc:
            return {'ok': False, 'error': 'invalid_request', 'message': str(exc)}
        return await self._request({'operation': 'capture', 'target': target,
                                    'source': source, 'region': values})

    async def _request(self, request):
        if self._task is not None:
            return {'ok': False, 'error': 'busy'}
        if not self.status()['available']:
            return {**self.status(), 'ok': False, 'error': 'unavailable'}
        self._state = 'capturing' if request['operation'] == 'capture' else 'enumerating'
        task = asyncio.create_task(self._run(request))
        self._task = task
        try:
            async with asyncio.timeout(self.timeout):
                metadata, jpeg = await task
            if self._closed:
                return {'ok': False, 'error': 'closed'}
            if metadata.get('ok') and request['operation'] == 'capture':
                if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
                    raise ValueError('invalid JPEG response')
                self._last_frame = jpeg
            self._state = 'ready' if metadata.get('ok') else 'failed'
            return metadata
        except TimeoutError:
            self._state = 'failed'
            return {'ok': False, 'error': 'timeout'}
        except asyncio.CancelledError:
            self._last_frame = None
            self._state = 'ready'
            raise
        except (OSError, ValueError, KeyError, TypeError, asyncio.IncompleteReadError):
            self._state = 'failed'
            return {'ok': False, 'error': 'worker_failed'}
        finally:
            self._task = None

    async def _run(self, request):
        # Shield process creation so cancellation cannot orphan a newly spawned child.
        spawn = asyncio.create_task(asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).with_name('screen_capture_worker.py')),
            json.dumps(request), stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            creationflags=0x08000000 if os.name == 'nt' else 0))
        process = None
        try:
            process = await asyncio.shield(spawn)
            size = struct.unpack('!I', await process.stdout.readexactly(4))[0]
            if size > 1024 * 1024:
                raise ValueError('oversized metadata')
            metadata = json.loads(await process.stdout.readexactly(size))
            if not isinstance(metadata, dict):
                raise ValueError('invalid metadata')
            size = metadata.get('byte_count', 0)
            if not isinstance(size, int) or not 0 <= size <= 32 * 1024 * 1024:
                raise ValueError('oversized frame')
            jpeg = await process.stdout.readexactly(size)
            if await process.wait() != 0:
                raise ValueError('worker exited unsuccessfully')
            return metadata, jpeg
        finally:
            if process is None:
                process = await spawn
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.wait()

    async def close(self):
        self._closed = True
        self._last_frame = None
        task = self._task
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
