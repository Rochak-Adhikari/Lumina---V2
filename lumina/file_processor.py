"""Local file processing; provider use and confirmations belong to the runtime.

Parser processes receive bounded byte snapshots, not filesystem authority. Cancellation
propagates CancelledError after killing/reaping the parser. No conversion or online
provider is selected implicitly. ZIP extraction requires a new destination directory.
"""
import asyncio
import base64
import importlib.util
import json
import os
from pathlib import Path
import shutil
import secrets
import subprocess
import sys
import tempfile
from typing import Protocol


class TransformationProvider(Protocol):
    async def transform(self, extracted: dict, operation: str) -> dict: ...


class OnlineAnalysisProvider(Protocol):
    """Caller must authorize disclosure before invoking an implementation."""
    async def analyze(self, extracted: dict, instruction: str) -> dict: ...


class InspectionProvider(Protocol):
    async def process(self, path: str, action: str = 'inspect', destination=None, options=None) -> dict: ...


class FileProcessor:
    LIMITS = dict(input_bytes=16 * 1024 * 1024, expanded=32 * 1024 * 1024,
                  members=1000, characters=200000, pages=100, slides=100,
                  sheets=20, rows=2000, columns=100, pixels=40000000)
    TIMEOUT = 20.0
    ACTIONS = ('inspect', 'extract', 'export_text', 'extract_archive',
               'stats', 'filter', 'sort', 'format', 'validate', 'resize', 'convert')
    TRANSFORMS = ('filter', 'sort', 'format', 'resize', 'convert')
    LOCAL_OPERATIONS = (*TRANSFORMS, 'stats', 'validate')
    ALIASES = {'info': 'inspect', 'extract_text': 'extract', 'list': 'inspect',
               'word_count': 'inspect'}

    def __init__(self, resolver):
        self.resolver = resolver
        self._closed = False
        self._tasks = set()
        self._processes = set()
        self._lock = asyncio.Lock()

    def status(self):
        return {'ok': not self._closed, 'status': 'closed' if self._closed else 'ready',
                'error': None, 'actions': list(self.ACTIONS), 'active': len(self._processes),
                'action_aliases': dict(self.ALIASES),
                'limits': dict(self.LIMITS), 'timeout_seconds': self.TIMEOUT,
                'dependencies': {m: 'ready' if importlib.util.find_spec(m) else 'unavailable'
                                 for m in ('pypdf', 'docx', 'pptx', 'openpyxl', 'PIL')},
                'online_analysis': 'unconfigured', 'transformations': 'local'}

    async def save_upload(self, directory, filename, data):
        """Store one user-selected file atomically inside the active path policy."""
        if self._closed:
            return {'ok': False, 'status': 'closed', 'error': 'Processor is closed'}
        if not isinstance(filename, str) or not filename or Path(filename).name != filename or '/' in filename or '\\' in filename:
            return {'ok': False, 'status': 'invalid', 'error': 'The selected filename is invalid.'}
        if not isinstance(data, (bytes, bytearray)) or len(data) > self.LIMITS['input_bytes']:
            return {'ok': False, 'status': 'rejected', 'error': 'Input size limit exceeded.'}
        try:
            target = self._path(Path(directory) / filename, False)
            self._path(target.parent)
            if target.exists():
                return {'ok': False, 'status': 'rejected', 'error': 'A file with that name already exists.'}
            temporary = target.with_name(f'.{target.name}.{secrets.token_hex(8)}.upload')
            created = False
            try:
                with temporary.open('xb') as stream:
                    created = True
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                self._path(target, False)
                os.link(temporary, target)
            except FileExistsError:
                return {'ok': False, 'status': 'rejected', 'error': 'A file with that name already exists.'}
            finally:
                if created:
                    temporary.unlink(missing_ok=True)
            inspected = await self.process(str(target), action='inspect')
            return {'ok': True, 'status': 'uploaded', 'error': None,
                    'path': str(target), 'bytes': len(data), 'inspection': inspected,
                    'warnings': [] if inspected['ok'] else ['Stored locally, but inspection did not succeed.']}
        except (OSError, ValueError):
            return {'ok': False, 'status': 'rejected', 'error': 'The file could not be stored inside the active workspace.'}

    async def close(self):
        self._closed = True
        tasks = list(self._tasks - {asyncio.current_task()})
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        return {'ok': True, 'status': 'closed', 'error': None}

    async def _parse(self, data, suffix, action, options=None, output_suffix=None):
        command = [sys.executable, '-I', str(Path(__file__).with_name('file_processing_worker.py'))]
        # Shield creation so cancellation cannot orphan a process during startup.
        starting = asyncio.create_task(asyncio.create_subprocess_exec(
            *command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)))
        process = None
        try:
            process = await asyncio.shield(starting)
            self._processes.add(process)
            request = json.dumps(dict(data=base64.b64encode(data).decode(), suffix=suffix,
                                      action=action, limits=self.LIMITS,
                                      options=options, output_suffix=output_suffix)).encode()
            output, _ = await process.communicate(request)
            if process.returncode:
                return {'ok': False, 'status': 'failed', 'error': 'Parser process failed'}
            return json.loads(output)
        finally:
            if process is None:
                process = await starting
            if process.returncode is None:
                process.kill()
            await process.wait()
            self._processes.discard(process)

    def _path(self, path, exists=True):
        return self.resolver.path(str(path), must_exist=exists)

    async def process(self, path, action='extract', destination=None, options=None):
        """Process a local file; writes require a new explicit destination.

        Local API (options is a JSON object; unknown options are rejected):
          stats: CSV/TSV, {} -> statistics per column (read-only).
          filter: CSV/TSV, {column: header, condition: equals|contains|gt|lt,
                           value: string or finite number}; default equals.
          sort: CSV/TSV, {column: header, numeric: bool=False,
                         ascending: bool=True}; stable, case-sensitive text order.
          format: JSON, {indent: integer 0..8=2, sort_keys: bool=False}.
          validate: JSON, {} -> metadata.valid (read-only).
          resize: static raster, {width?: positive int, height?: positive int,
                                  quality?: int 1..100=90}.
                  One dimension preserves aspect ratio; two set exact dimensions.
          convert: static raster, {quality?: int 1..100=90}.
        Image output is selected by destination suffix: PNG/JPEG/WEBP.
        Filter/sort output must match input .csv/.tsv; format requires .json.
        Tables require unique nonempty headers and rectangular rows. Numeric
        operations reject nonnumeric/nonfinite cells; stats reports them separately.
        Transformations reject oversized data rather than write partial results.
        Responses contain metadata and, for writes, output_path/output_bytes;
        binary worker payloads are never exposed to callers. No online calls.
        """
        if self._closed:
            return {'ok': False, 'status': 'closed', 'error': 'Processor is closed'}
        if not isinstance(action, str):
            return {'ok': False, 'status': 'unsupported', 'error': 'Action must be a string'}
        action = self.ALIASES.get(action.strip().lower(), action.strip().lower())
        if action not in (*self.ACTIONS, '_analysis_image'):
            return {'ok': False, 'status': 'unsupported', 'error': 'Unsupported local action',
                    'actions': list(self.ACTIONS)}
        if options is not None and not isinstance(options, dict):
            return {'ok': False, 'status': 'rejected', 'error': 'Options must be an object'}
        if options and action not in self.LOCAL_OPERATIONS:
            return {'ok': False, 'status': 'rejected', 'error': 'This action does not accept options'}
        if destination is not None and action in ('stats', 'validate'):
            return {'ok': False, 'status': 'rejected', 'error': 'Read-only action does not accept a destination'}
        task = asyncio.current_task()
        self._tasks.add(task)
        try:
            async with asyncio.timeout(self.TIMEOUT):
                async with self._lock:
                    return await self._process(path, action, destination, options)
        except TimeoutError:
            return {'ok': False, 'status': 'timeout', 'error': 'Processing deadline exceeded'}
        except Exception as exc:
            return {'ok': False, 'status': 'rejected' if isinstance(exc, (ValueError, PermissionError, FileExistsError)) else 'failed',
                    'error': 'File operation refused or failed', 'code': getattr(exc, 'code', type(exc).__name__)}
        finally:
            self._tasks.discard(task)

    async def _process(self, path, action, destination, options=None):
        src = self._path(path)
        if not src.is_file():
            raise ValueError('Expected regular file')
        if src.stat().st_size > self.LIMITS['input_bytes']:
            return {'ok': False, 'status': 'rejected', 'error': 'Input size limit exceeded'}
        dst = None
        if action in ('export_text', 'extract_archive', *self.TRANSFORMS):
            if not destination:
                raise ValueError('Destination required')
            dst = self._path(destination, False)
            if dst.exists():
                raise FileExistsError()
            self._path(dst.parent)
        suffix = src.suffix.lower()
        if action == 'extract_archive' and suffix != '.zip':
            raise ValueError('ZIP required')
        if suffix == '.zip' and action not in ('inspect', 'extract_archive'):
            raise ValueError('Use extract_archive for ZIP')
        # Revalidate immediately before reading; yield between bounded chunks.
        data = bytearray()
        with self._path(src).open('rb') as stream:
            while True:
                chunk = stream.read(min(65536, self.LIMITS['input_bytes'] + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > self.LIMITS['input_bytes']:
                    raise ValueError('Input grew beyond limit')
                await asyncio.sleep(0)
        if action in self.LOCAL_OPERATIONS:
            result = await self._parse(bytes(data), suffix, action, options, dst.suffix.lower() if dst else None)
        else:
            result = await self._parse(bytes(data), suffix, action)
        if not result['ok']:
            result['path'] = str(src)
            return result
        result['path'] = str(src)
        result['action'] = action
        result['metadata']['name'] = src.name
        if action in self.TRANSFORMS:
            payload = base64.b64decode(result.pop('output_data'), validate=True)
            if len(payload) > self.LIMITS['expanded']:
                raise ValueError('Output size limit exceeded')
            await self._export(dst, payload)
            result.update(output_path=str(dst), output_bytes=len(payload))
        elif suffix == '.zip':
            # Validate ALL member paths through the live policy before any writes.
            base = dst if dst is not None else src.parent / (src.stem + '-extracted')
            self._path(base, False)
            for member in result['members']:
                self._path(base / member['name'], False)
            if action == 'extract_archive':
                await self._extract(dst, result['members'])
                result['output_path'] = str(dst)
            result['members'] = [{'name': m['name'], 'directory': m['directory']} for m in result['members']]
        elif action == 'export_text':
            await self._export(dst, result.pop('text', ''))
            result['output_path'] = str(dst)
        return result

    async def _export(self, dst, text):
        self._path(dst, False)
        fd, temporary = tempfile.mkstemp(prefix='lumina-export-', dir=self._path(dst.parent))
        temp = Path(temporary)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(text.encode('utf-8') if isinstance(text, str) else text)
                out.flush()
                os.fsync(out.fileno())
            await asyncio.sleep(0)
            self._path(temp)
            self._path(dst, False)
            # Hard-link publication is atomic and fails if destination exists.
            os.link(temp, dst)
        finally:
            temp.unlink(missing_ok=True)

    async def _extract(self, dst, members):
        self._path(dst, False).mkdir()
        try:
            for member in members:
                target = self._path(dst / member['name'], False)
                for parent in reversed(target.parents):
                    if parent == dst or parent.is_relative_to(dst):
                        self._path(parent, False).mkdir(exist_ok=True)
                if member['directory']:
                    self._path(target, False).mkdir(exist_ok=True)
                else:
                    payload = base64.b64decode(member['data'])
                    with self._path(target, False).open('xb') as out:
                        for offset in range(0, len(payload), 65536):
                            out.write(payload[offset:offset + 65536])
                            await asyncio.sleep(0)
                await asyncio.sleep(0)
        except BaseException:
            # Only the newly-created operation-owned destination is removed.
            self._path(dst)
            shutil.rmtree(dst)
            raise
