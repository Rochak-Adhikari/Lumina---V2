"""Phase 3 bounded text transactions and exact, recoverable organization plans.

FileController(resolver, state_dir=None); status() is synchronous, execute(action,
**args) and execute_confirmed(confirmation, request) are asynchronous. See
ACTION_SCHEMAS. expected_hash is the SHA-256 returned by inspect. Text is UTF-8;
edit_text replaces the complete text, append_text appends literally (no newline).

Only the trusted runtime may call execute_confirmed, after enforcing current
permissions and showing the ENTIRE request. Tokens are not permission grants.
All mutations (including undo/restore) prepare first. Tokens are one-use, expire
after 60 seconds, and do not survive restart. Client dictionaries are never used
as mutation authority. State must be shared by all instances for this workspace.

SQLite FULL transactions retain private pre-edit bytes before publication. The
journal fails closed at its capacity, rather than silently discarding undo. Undo
of create restores absence, retaining the removed bytes in the undo revision.
Undo of edit/append restores bytes, not timestamps or OS file identity. Edits
use an atomic replace after an immediate full content/identity comparison;
like ordinary filesystem compare-before-write this is not a kernel CAS against
uncooperative external writers. No await occurs between that check and replace.

Organization is shallow, deterministic, same-volume, file-only, never deletion.
Move validation uses FilesystemManager on Windows. POSIX uses renameat2's
NOREPLACE because the existing Path.rename implementation overwrites on POSIX.
Interrupted entries are reconciled conservatively; ambiguous outcomes are never
retried automatically. Empty category directories are intentionally retained.
"""
from __future__ import annotations
from .control_authority import blocked_effect

import asyncio
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import tempfile
import time
import uuid
import zipfile

from .desktop import DesktopError, FileSearchService, FilesystemManager


MAX_TEXT_BYTES = 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_OPERATIONS = 128
MAX_PLANS = 64
MAX_PLAN_ITEMS = 256
MAX_SCAN_ENTRIES = 10000
SCAN_SECONDS = 5.0
CONFIRM_SECONDS = 60.0
SECRET_DIRS = {'secrets', 'credentials', 'credential', 'private_keys'}


def _schema(required=(), **properties):
    return dict(type='object', properties=properties, required=list(required), additionalProperties=False)


_PATH = dict(type='string', minLength=1, maxLength=2048)
_ID = dict(type='string', format='uuid')
_TEXT = dict(type='string', maxLength=MAX_TEXT_BYTES)
_HASH = dict(type='string', pattern='^[0-9a-f]{64}$')
ACTION_SCHEMAS = {
    'status': _schema(), 'inspect': _schema(('path',), path=_PATH),
    'create_text': _schema(('path', 'text'), path=_PATH, text=_TEXT),
    'edit_text': _schema(('path', 'text', 'expected_hash'), path=_PATH, text=_TEXT, expected_hash=_HASH),
    'append_text': _schema(('path', 'text', 'expected_hash'), path=_PATH, text=_TEXT, expected_hash=_HASH),
    'history': _schema(operation_id=_ID, limit=dict(type='integer', minimum=1, maximum=128)),
    'undo': _schema(('operation_id',), operation_id=_ID),
    'largest': _schema(('path',), path=_PATH, limit=dict(type='integer', minimum=1, maximum=100)),
    'usage': _schema(('path',), path=_PATH),
    'plan_organization': _schema(('path',), path=_PATH, destination=_PATH),
    'apply_plan': _schema(('plan_id',), plan_id=_ID),
    'restore_plan': _schema(('operation_id',), operation_id=_ID),
    'plan_archive': _schema(('path','destination'),path=_PATH,destination=_PATH),
    'create_archive': _schema(('plan_id',),plan_id=_ID),
}


class FileControllerError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _fail(code, **extra):
    return dict(ok=False, status=code, code=code, error=code, **extra)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _id(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise FileControllerError('invalid_id')
    return value


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise FileControllerError('invalid_limit')
    return value


def _identity(st):
    return dict(device=st.st_dev, inode=st.st_ino, size=st.st_size, mtime_ns=st.st_mtime_ns)


def _no_links(path):
    for item in (path, *path.parents):
        try:
            st = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & 0x400:
            raise FileControllerError('links_not_allowed')


def _private_directory(path):
    """Protect revision storage, including inherited ACLs on Windows."""
    path = Path(os.path.abspath(path))
    _no_links(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    _no_links(path)
    if os.name != 'nt':
        if path.stat().st_uid != os.getuid():
            raise FileControllerError('state_not_owned')
        path.chmod(0o700)
        return path
    from ctypes import wintypes as w
    adv = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.argtypes, kernel.GetCurrentProcess.restype = [], w.HANDLE
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [ctypes.c_void_p], ctypes.c_void_p
    adv.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    adv.OpenProcessToken.restype = w.BOOL
    adv.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    adv.GetTokenInformation.restype = w.BOOL
    adv.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    adv.ConvertSidToStringSidW.restype = w.BOOL
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = w.BOOL
    adv.SetFileSecurityW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.c_void_p]
    adv.SetFileSecurityW.restype = w.BOOL
    token, sid_text, descriptor = w.HANDLE(), ctypes.c_void_p(), ctypes.c_void_p()
    try:
        if not adv.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
            raise OSError('private_state_unavailable')
        size = w.DWORD()
        adv.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not adv.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            raise OSError('private_state_unavailable')
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        if not adv.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)):
            raise OSError('private_state_unavailable')
        sddl = 'D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;' + ctypes.wstring_at(sid_text) + ')'
        if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
            raise OSError('private_state_unavailable')
        if not adv.SetFileSecurityW(str(path), 0x80000004, descriptor):
            raise OSError('private_state_unavailable')
    finally:
        if descriptor.value:
            kernel.LocalFree(descriptor)
        if sid_text.value:
            kernel.LocalFree(sid_text)
        if token.value:
            kernel.CloseHandle(token)
    return path


class _Journal:
    """Internal shared primitive; never serves revision bytes to history callers."""
    def __init__(self, directory):
        self.directory = _private_directory(directory)
        self.path = self.directory / 'journal.sqlite3'
        self.lock_path = self.directory / 'journal.lock'
        for p in (self.path, self.lock_path):
            _no_links(p)
            if p.exists() and p.stat().st_nlink != 1:
                raise FileControllerError('state_link_not_allowed')
        with self.guard(), self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL, revision BLOB)')

    @contextmanager
    def connection(self):
        _no_links(self.path)
        db = sqlite3.connect(self.path, timeout=0)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA journal_mode=DELETE')
            yield db
            db.commit()
        finally:
            db.close()
        if os.name != 'nt':
            self.path.chmod(0o600)

    @contextmanager
    def guard(self):
        _no_links(self.lock_path)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        locked = False
        try:
            if os.name == 'nt':
                import msvcrt
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                except OSError:
                    raise FileControllerError('busy') from None
            else:
                import fcntl
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise FileControllerError('busy') from None
            locked = True
            yield
        finally:
            if locked:
                if os.name == 'nt':
                    import msvcrt
                    os.lseek(fd, 0, 0)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def add(self, kind, record, revision=None):
        with self.connection() as db:
            cap = MAX_PLANS if kind == 'plan' else MAX_OPERATIONS
            if db.execute('SELECT count(*) FROM records WHERE kind=?', (kind,)).fetchone()[0] >= cap:
                raise FileControllerError('journal_full')
            db.execute('INSERT INTO records VALUES(?,?,?,?)', (record['operation_id'], kind, _json(record), revision))

    def save(self, record):
        with self.connection() as db:
            if db.execute('UPDATE records SET data=? WHERE id=?', (_json(record), record['operation_id'])).rowcount != 1:
                raise FileControllerError('unknown_operation')

    def get(self, identity, kind='operation'):
        _id(identity)
        with self.connection() as db:
            row = db.execute('SELECT data,revision FROM records WHERE id=? AND kind=?', (identity, kind)).fetchone()
        if row is None:
            raise FileControllerError('unknown_operation')
        return json.loads(row[0]), row[1]

    def records(self, kind='operation'):
        with self.connection() as db:
            rows = db.execute('SELECT data FROM records WHERE kind=? ORDER BY rowid DESC', (kind,)).fetchall()
        return [json.loads(row[0]) for row in rows]


class _Confirmations:
    def __init__(self):
        self._pending = {}
        self._clock = time.monotonic

    def _prepare(self, request):
        now = self._clock()
        self._pending = {k: v for k, v in self._pending.items() if v[0] > now}
        if len(self._pending) >= 64:
            raise FileControllerError('too_many_pending_requests')
        token = secrets.token_urlsafe(32)
        frozen = _json(request)
        self._pending[token] = (now + CONFIRM_SECONDS, frozen)
        return dict(ok=False, status='confirmation_required', confirmation_required=True,
                    requires_confirmation=True, confirmation=token,
                    expires_in=CONFIRM_SECONDS, request=json.loads(frozen))

    def _consume(self, token, request):
        stored = self._pending.pop(token, None) if isinstance(token, str) else None
        if stored is None or stored[0] <= self._clock() or stored[1] != _json(request):
            raise FileControllerError('confirmation_mismatch_or_expired')
        return json.loads(stored[1])


class FileController(_Confirmations):
    def __init__(self, resolver, state_dir=None):
        super().__init__()
        self.resolver = resolver
        self.files = FilesystemManager(resolver, FileSearchService(resolver))
        self.state_dir = Path(state_dir) if state_dir is not None else resolver.workspace.active_workspace / '.lumina-file-controller'
        self.journal = _Journal(self.state_dir)
        self.state_dir = self.journal.directory
        self._lock = asyncio.Lock()
        with self.journal.guard():
            self._recover()

    def status(self):
        return dict(ok=True, status='ready', actions=list(ACTION_SCHEMAS),
                    limits=dict(text_bytes=MAX_TEXT_BYTES, file_bytes=MAX_FILE_BYTES,
                                operations=MAX_OPERATIONS, plans=MAX_PLANS, plan_items=MAX_PLAN_ITEMS,
                                scan_entries=MAX_SCAN_ENTRIES, scan_seconds=SCAN_SECONDS),
                    confirmation_seconds=CONFIRM_SECONDS, journal=str(self.journal.path))

    def _path(self, value, exists=True):
        raw=Path(str(value))
        if any(p.endswith((' ', '.')) and p not in ('.','..') for p in raw.parts):
            raise FileControllerError('invalid_path')
        path = self.resolver.path(str(value), must_exist=exists)
        _no_links(path)
        if path.is_relative_to(self.state_dir) or any(p.casefold() in SECRET_DIRS for p in path.parts):
            raise FileControllerError('protected_path')
        # Reject Windows aliases (trailing dots/spaces and device basenames), even
        # when tests run on POSIX. The normal resolver remains the root authority.
        reserved = {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))}
        if any(p.endswith((' ', '.')) or p.split('.')[0].casefold() in reserved for p in path.parts[1:]):
            raise FileControllerError('invalid_path')
        return path

    def _parent(self, path):
        parent = self._path(path.parent)
        if not parent.is_dir():
            raise FileControllerError('parent_not_directory')
        st = parent.stat()
        return dict(path=str(parent), device=st.st_dev, inode=st.st_ino)

    def _check_parent(self, expected):
        if self._parent(Path(expected['path']) / 'unused') != expected:
            raise FileControllerError('stale_parent')

    def _snapshot_sync(self, path, limit=MAX_TEXT_BYTES):
        path = self._path(path)
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            raise FileControllerError('regular_file_required')
        if before.st_size > limit:
            raise FileControllerError('file_too_large')
        with path.open('rb') as stream:
            opened = os.fstat(stream.fileno())
            if _identity(opened) != _identity(before):
                raise FileControllerError('stale_file')
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        if len(data) > limit:
            raise FileControllerError('file_too_large')
        self._path(path)
        if _identity(before) != _identity(after) or _identity(after) != _identity(path.stat()):
            raise FileControllerError('stale_file')
        fingerprint = self.files.fingerprint(str(path))
        return dict(**_identity(after), sha256=_sha(data), fingerprint=fingerprint), data

    async def _snapshot(self, path, limit=MAX_TEXT_BYTES):
        # Bound synchronous work to at most one bounded file; cancellation is
        # checked before it, never delegated to a thread that can mutate late.
        await asyncio.sleep(0)
        return self._snapshot_sync(path, limit)

    @staticmethod
    def _same_content_identity(actual, expected):
        return all(actual.get(k) == expected.get(k) for k in ('device', 'inode', 'size', 'mtime_ns', 'sha256'))

    def _check(self, path, before, limit=MAX_TEXT_BYTES):
        if before is None:
            if self._path(path, False).exists():
                raise FileControllerError('destination_exists')
        elif self._snapshot_sync(path, limit)[0] != before:
            raise FileControllerError('stale_file')

    @staticmethod
    def _text(value):
        if not isinstance(value, str) or len(value) > MAX_TEXT_BYTES or '\x00' in value:
            raise FileControllerError('invalid_text')
        data = value.encode('utf-8')
        if len(data) > MAX_TEXT_BYTES:
            raise FileControllerError('text_too_large')
        return data

    async def execute_confirmed(self, confirmation, request):
        return await self.execute('execute_confirmed', confirmation=confirmation, request=request)

    async def execute(self, action, **args):
        if action == 'execute_confirmed':
            from .control_authority import denied
            return denied()
        async with self._lock:
            try:
                if action == 'execute_confirmed':
                    if set(args) != {'confirmation', 'request'}:
                        raise FileControllerError('invalid_arguments')
                    with self.journal.guard():
                        request = self._consume(args['confirmation'], args['request'])
                        return await self._apply(request)
                if action not in ACTION_SCHEMAS:
                    raise FileControllerError('unsupported_action')
                schema = ACTION_SCHEMAS[action]
                if set(args) - set(schema['properties']) or set(schema['required']) - set(args):
                    raise FileControllerError('invalid_arguments')
                # PathResolver accepts only strings. Do not coerce model values.
                for key in ('path', 'destination'):
                    if key in args and args[key] is not None and not isinstance(args[key], str):
                        raise FileControllerError('invalid_path')
                with self.journal.guard():
                    return await self._dispatch(action, args)
            except asyncio.CancelledError:
                raise
            except (FileControllerError, DesktopError) as exc:
                return _fail(exc.code)
            except FileExistsError:
                return _fail('destination_exists')
            except (OSError, sqlite3.Error):
                return _fail('io_error')
            except (ValueError, TypeError, KeyError, UnicodeError):
                return _fail('invalid_request')

    async def _dispatch(self, action, args):
        if action == 'status':
            return self.status()
        if action == 'inspect':
            path = self._path(args['path'])
            fp, data = await self._snapshot(path)
            text = data.decode('utf-8')
            if '\x00' in text:
                raise FileControllerError('invalid_text')
            return dict(ok=True, status='inspected', path=str(path), text=text,
                        sha256=fp['sha256'], fingerprint=fp, bytes=len(data))
        if action == 'history':
            limit = _integer(args.get('limit', 50), 1, MAX_OPERATIONS)
            self._recover()
            records = ([self.journal.get(args['operation_id'])[0]] if args.get('operation_id')
                       else self.journal.records())
            return dict(ok=True, status='history', operations=records[:limit], truncated=len(records) > limit)
        if action in ('largest', 'usage'):
            return await self._scan(action, args)
        if action == 'plan_organization':
            return await self._plan(args)
        if action == 'plan_archive':
            return await self._archive_plan(args)
        if action == 'create_archive':
            plan,_=self.journal.get(args['plan_id'],'plan')
            if plan['action']!='plan_archive' or plan.get('applied_operation_id') or plan['collisions']:
                raise FileControllerError('invalid_or_used_archive_plan')
            return self._prepare(dict(service='files',action=action,plan=plan))
        if action == 'apply_plan':
            plan, _ = self.journal.get(args['plan_id'], 'plan')
            if plan['collisions'] or plan.get('applied_operation_id'):
                raise FileControllerError('plan_has_collisions_or_already_applied')
            return self._prepare(dict(service='files', action=action, plan=plan))
        if action == 'restore_plan':
            return await self._prepare_restore(args['operation_id'])
        if action == 'undo':
            record, revision = self.journal.get(args['operation_id'])
            if record['action'] not in ('create_text', 'edit_text', 'append_text') or record['status'] != 'completed':
                raise FileControllerError('undo_unavailable')
            path = self._path(record['path'])
            before, _ = await self._snapshot(path)
            if before != record['after']:
                raise FileControllerError('stale_undo')
            return self._prepare(dict(service='files', action='undo', operation_id=record['operation_id'],
                                      path=str(path), before=before, parent=self._parent(path),
                                      restore_hash=_sha(revision) if revision is not None else None,
                                      restore_absence=record['action'] == 'create_text'))
        path = self._path(args['path'], action != 'create_text')
        parent = self._parent(path)
        text = self._text(args['text'])
        before = None
        if action == 'create_text':
            self._check(path, None)
        else:
            before, old = await self._snapshot(path)
            old.decode('utf-8')
            if '\x00' in old.decode('utf-8'):
                raise FileControllerError('invalid_text')
            if args['expected_hash'] != before['sha256']:
                raise FileControllerError('stale_hash')
            if action == 'append_text' and len(old) + len(text) > MAX_TEXT_BYTES:
                raise FileControllerError('text_too_large')
        return self._prepare(dict(service='files', action=action, path=str(path), text=args['text'],
                                  expected_hash=before['sha256'] if before else None, before=before, parent=parent))

    def _new_record(self, action, **fields):
        return dict(operation_id=str(uuid.uuid4()), action=action, status='running',
                    created_at=time.time(), **fields)

    @blocked_effect
    async def _apply(self, request):
        if request['action']=='create_archive':return await self._archive(request['plan'])
        if request['action'] == 'apply_plan':
            plan = request['plan']
            latest, _ = self.journal.get(plan['operation_id'], 'plan')
            if latest != plan:
                raise FileControllerError('stale_plan')
            return await self._run_moves(plan['items'], 'apply_plan', plan=plan)
        if request['action'] == 'restore_plan':
            return await self._run_moves(request['items'], 'restore_plan',
                                         restores=request['operation_id'], issues=request['issues'])
        return await self._write(request)

    async def _archive_plan(self,args):
        root=self._path(args['path']);destination=self._path(args['destination'],False)
        if not root.is_dir() or destination.suffix.lower()!='.zip':raise FileControllerError('archive_path_required')
        parent=self._parent(destination)
        entries=[];skipped=0;incomplete=False;size=0;deadline=time.monotonic()+SCAN_SECONDS
        with os.scandir(root) as children:
            for index,entry in enumerate(children):
                if index>=MAX_SCAN_ENTRIES or time.monotonic()>deadline or len(entries)>=MAX_PLAN_ITEMS:
                    incomplete=True;break
                try:
                    source=self._path(entry.path)
                    if not source.is_file() or source==destination:
                        skipped+=1;continue
                    if size+source.stat().st_size>MAX_FILE_BYTES//2:
                        skipped+=1;incomplete=True;continue
                    before,_=await self._snapshot(source,MAX_FILE_BYTES//2)
                    entries.append({'source':str(source),'member':source.name,'before':before,'parent':self._parent(source)})
                    size+=before['size']
                except (ValueError,OSError):skipped+=1
        entries.sort(key=lambda item:item['member'].casefold())
        collisions=[{'destination':str(destination),'reason':'destination_exists'}] if destination.exists() else []
        if len({e['member'].casefold() for e in entries})!=len(entries):collisions.append({'reason':'duplicate_archive_member'})
        plan=self._new_record('plan_archive',path=str(root),destination=str(destination),parent=parent,
            items=entries,count=len(entries),bytes=size,collisions=collisions,skipped=skipped,
            scan_incomplete=incomplete or bool(skipped),recursive=False)
        plan['status']='planned';self.journal.add('plan',plan)
        return dict(ok=True,status='planned',plan_id=plan['operation_id'],plan=plan)

    @blocked_effect
    async def _archive(self,plan):
        latest,_=self.journal.get(plan['operation_id'],'plan')
        if latest!=plan:raise FileControllerError('stale_plan')
        path=self._path(plan['destination'],False)
        self._check_parent(plan['parent']);self._check(path,None)
        record=self._new_record('create_archive',path=str(path),before=None,after=None,
            parent=plan['parent'],plan_id=plan['operation_id'],expected_output_hash=None)
        self.journal.add('operation',record)
        plan['applied_operation_id']=record['operation_id'];self.journal.save(plan)
        stage=None
        try:
            stage=self._stage(path,b'')
            deadline=time.monotonic()+20
            with zipfile.ZipFile(stage,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=False) as archive:
                for item in plan['items']:
                    await asyncio.sleep(0)
                    if time.monotonic()>deadline:raise FileControllerError('archive_deadline')
                    source=self._path(item['source']);self._check_parent(item['parent'])
                    self._check(source,item['before'],MAX_FILE_BYTES//2)
                    if Path(item['member']).name!=item['member'] or ':' in item['member']:raise FileControllerError('invalid_archive_member')
                    digest=hashlib.sha256();count=0
                    with source.open('rb') as src,archive.open(item['member'],'w') as dst:
                        while chunk:=src.read(65536):
                            count+=len(chunk)
                            if count>item['before']['size'] or time.monotonic()>deadline:raise FileControllerError('archive_source_changed')
                            digest.update(chunk);dst.write(chunk);await asyncio.sleep(0)
                    if count!=item['before']['size'] or digest.hexdigest()!=item['before']['sha256']:raise FileControllerError('archive_source_changed')
                    self._check(source,item['before'],MAX_FILE_BYTES//2)
            # Validate generated members and CRCs before publishing any output.
            with zipfile.ZipFile(stage) as archive:
                if archive.namelist()!=[item['member'] for item in plan['items']]:raise FileControllerError('archive_validation_failed')
                for item in archive.infolist():
                    with archive.open(item) as member:
                        while member.read(65536):await asyncio.sleep(0)
            with stage.open('rb') as stream:
                data=stream.read(MAX_FILE_BYTES+1)
            if len(data)>MAX_FILE_BYTES:raise FileControllerError('archive_size_limit')
            record['expected_output_hash']=_sha(data);record['staged_identity']=_identity(stage.stat())
            self.journal.save(record)
            # Windows FlushFileBuffers requires a handle opened for writing.
            with stage.open('r+b') as stream:os.fsync(stream.fileno())
            self._check_parent(plan['parent']);self._check(path,None)
            os.link(stage,path);self._sync_directory(path.parent)
            record['after']=self._snapshot_sync(path,MAX_FILE_BYTES)[0]
            if record['after']['sha256']!=record['expected_output_hash']:raise FileControllerError('archive_validation_failed')
            record['status']='completed';self.journal.save(record)
            return dict(ok=True,status='completed',operation_id=record['operation_id'],path=str(path),
                sha256=record['after']['sha256'],verified=True,count=len(plan['items']),scan_incomplete=plan['scan_incomplete'])
        except asyncio.CancelledError:
            record['status']='cancelled';self.journal.save(record);raise
        except (OSError,ValueError,sqlite3.Error,zipfile.BadZipFile) as exc:
            record['status']='interrupted';self.journal.save(record)
            return _fail(getattr(exc,'code','archive_failed'),operation_id=record['operation_id'],
                system_error=getattr(exc,'errno',None),outcome='unknown' if path.exists() else 'not_published')
        finally:
            if stage is not None:stage.unlink(missing_ok=True)

    def _stage(self, path, data):
        self._parent(path)
        fd, name = tempfile.mkstemp(prefix='.lumina-', suffix='.tmp', dir=path.parent)
        stage = Path(name)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
            return stage
        except BaseException:
            stage.unlink(missing_ok=True)
            raise

    @staticmethod
    def _sync_directory(path):
        if os.name != 'nt':
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    @blocked_effect
    async def _write(self, request):
        action, path = request['action'], Path(request['path'])
        self._check_parent(request['parent'])
        self._check(path, request['before'])
        old = self._snapshot_sync(path)[1] if request['before'] else None
        if action == 'undo':
            original, data = self.journal.get(request['operation_id'])
            if original['status'] != 'completed' or original['after'] != request['before']:
                raise FileControllerError('stale_undo')
            remove = request['restore_absence']
            if not remove and (data is None or _sha(data) != request['restore_hash']):
                raise FileControllerError('revision_invalid')
        else:
            data = self._text(request['text'])
            if action == 'append_text':
                data = old + data
            remove = False
        if data is not None and len(data) > MAX_TEXT_BYTES:
            raise FileControllerError('text_too_large')
        record = self._new_record(action, path=str(path), before=request['before'], after=None,
                                  expected_output_hash=None if remove else _sha(data),
                                  restores=request.get('operation_id'), parent=request['parent'])
        self.journal.add('operation', record, old)  # durable BEFORE touching the target
        stage = None
        try:
            if not remove:
                stage = self._stage(path, data)
                record['staged_identity'] = _identity(stage.stat())
                self.journal.save(record)
            await asyncio.sleep(0)
            self._check_parent(request['parent'])
            self._check(path, request['before'])
            if remove:
                path.unlink()
            elif request['before'] is None:
                os.link(stage, path)  # atomic exclusive publication, never overwrites
            else:
                os.replace(stage, path)
            self._sync_directory(path.parent)
            # No await between publication, read-back and durable outcome.
            record['after'] = None if remove else self._snapshot_sync(path)[0]
            if not remove and record['after']['sha256'] != record['expected_output_hash']:
                raise FileControllerError('write_unverified')
            record['status'] = 'completed'
            self.journal.save(record)
            return dict(ok=True, status='completed', operation_id=record['operation_id'],
                        path=str(path), sha256=None if remove else record['after']['sha256'],
                        fingerprint=record['after'], verified=True)
        except asyncio.CancelledError:
            record['status'] = 'cancelled'
            self.journal.save(record)
            raise
        except (OSError, ValueError, sqlite3.Error) as exc:
            record['status'] = 'interrupted'
            record['error'] = getattr(exc, 'code', 'io_error')
            self.journal.save(record)
            self._recover_record(record)
            return _fail(record['error'], operation_id=record['operation_id'], outcome=record['status'])
        finally:
            if stage is not None:
                # Remove only this owned temporary file. Never remove user files
                # or category folders as a cleanup operation.
                stage.unlink(missing_ok=True)

    async def _scan(self, action, args):
        root = self._path(args['path'])
        if not root.is_dir():
            raise FileControllerError('directory_required')
        limit = _integer(args.get('limit', 20), 1, 100)
        pending, found = [root], []
        seen = total = skipped = 0
        deadline = time.monotonic() + SCAN_SECONDS
        incomplete = False
        while pending and not incomplete:
            await asyncio.sleep(0)
            directory = pending.pop()
            try:
                with os.scandir(self._path(directory)) as entries:
                    for entry in entries:
                        if seen >= MAX_SCAN_ENTRIES or time.monotonic() > deadline:
                            incomplete = True
                            break
                        seen += 1
                        try:
                            path = self._path(entry.path)
                            info = path.stat()
                            if stat.S_ISDIR(info.st_mode):
                                pending.append(path)
                            elif stat.S_ISREG(info.st_mode):
                                total += info.st_size
                                found.append(dict(path=str(path), bytes=info.st_size))
                        except (ValueError, OSError):
                            skipped += 1
                        if seen % 64 == 0:
                            await asyncio.sleep(0)
            except (ValueError, OSError):
                skipped += 1
        found.sort(key=lambda row: (-row['bytes'], row['path'].casefold(), row['path']))
        result = dict(ok=True, status='inspected', path=str(root), files=len(found), bytes=total,
                      scanned=seen, skipped=skipped, scan_incomplete=incomplete or bool(skipped))
        if action == 'largest':
            result.update(results=found[:limit], truncated=len(found) > limit)
        return result

    @staticmethod
    def _category(path):
        suffix = path.suffix.casefold()
        for name, extensions in (
            ('Documents', {'.txt', '.md', '.pdf', '.doc', '.docx', '.odt', '.rtf'}),
            ('Spreadsheets', {'.csv', '.tsv', '.xls', '.xlsx', '.ods'}),
            ('Presentations', {'.ppt', '.pptx', '.odp'}),
            ('Images', {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg', '.tif', '.tiff'}),
            ('Audio', {'.mp3', '.wav', '.flac', '.m4a', '.ogg'}),
            ('Videos', {'.mp4', '.mkv', '.mov', '.avi', '.webm'}),
            ('Archives', {'.zip', '.7z', '.rar', '.tar', '.gz'}),
        ):
            if suffix in extensions:
                return name
        return 'Other'

    async def _plan(self, args):
        root = self._path(args['path'])
        destination = self._path(args.get('destination') or str(root))
        if not root.is_dir() or not destination.is_dir():
            raise FileControllerError('directory_required')
        if root.stat().st_dev != destination.stat().st_dev:
            raise FileControllerError('cross_volume_plan_unsupported')
        candidates, skipped = [], 0
        incomplete = False
        with os.scandir(root) as entries:
            for i, entry in enumerate(entries):
                if i >= MAX_SCAN_ENTRIES:
                    incomplete = True
                    break
                try:
                    path = self._path(entry.path)
                    if path.is_file():
                        candidates.append(path)
                except (ValueError, OSError):
                    skipped += 1
        candidates.sort(key=lambda p: (p.name.casefold(), p.name))
        if len(candidates) > MAX_PLAN_ITEMS:
            candidates = candidates[:MAX_PLAN_ITEMS]
            incomplete = True
        items, collisions, total_bytes = [], [], 0
        deadline = time.monotonic() + SCAN_SECONDS
        for src in candidates:
            if time.monotonic() > deadline:
                incomplete = True
                break
            try:
                if total_bytes + src.stat().st_size > MAX_FILE_BYTES:
                    skipped += 1
                    incomplete = True
                    continue
                before, _ = await self._snapshot(src, MAX_FILE_BYTES)
                total_bytes += before['size']
                dst = self._path(destination / self._category(src) / src.name, False)
                item = dict(source=str(src), destination=str(dst), before=before,
                            source_parent=self._parent(src), destination_root=self._parent(destination / 'unused'),
                            destination_parent=self._parent(dst) if dst.parent.exists() else None)
                # Case-folded checks also catch collisions on case-sensitive test hosts.
                conflict = dst.exists() or (dst.parent.is_dir() and any(p.name.casefold() == dst.name.casefold() for p in dst.parent.iterdir()))
                if dst.parent.exists() and not dst.parent.is_dir():
                    conflict = True
                if conflict:
                    collisions.append(dict(source=str(src), destination=str(dst), reason='destination_exists'))
                items.append(item)
            except (ValueError, OSError):
                skipped += 1
        plan = self._new_record('plan_organization', path=str(root), destination=str(destination),
                                items=items, collisions=collisions, scan_incomplete=incomplete or bool(skipped),
                                skipped=skipped, count=len(items), bytes=total_bytes)
        plan['status'] = 'planned'
        self.journal.add('plan', plan)
        return dict(ok=True, status='planned', plan_id=plan['operation_id'], plan=plan)

    async def _prepare_restore(self, operation_id):
        self._recover()
        original, _ = self.journal.get(operation_id)
        if original['action'] != 'apply_plan':
            raise FileControllerError('not_organization_operation')
        items, issues = [], []
        for item in original['items']:
            if item['status'] != 'moved':
                if item['status'] in ('conflict', 'moving'):
                    issues.append(dict(source=item['source'], reason=item['status']))
                continue
            src, dst = Path(item['destination']), Path(item['source'])
            try:
                current, _ = await self._snapshot(src, MAX_FILE_BYTES)
                if not self._same_content_identity(current, item['before']):
                    raise FileControllerError('stale_undo')
                self._check(dst, None)
                items.append(dict(source=str(src), destination=str(dst), before=current,
                                  source_parent=self._parent(src), destination_parent=self._parent(dst),
                                  destination_root=self._parent(dst)))
            except (ValueError, OSError):
                # A previous partial restore is recognized by identity, not name.
                try:
                    current, _ = self._snapshot_sync(dst, MAX_FILE_BYTES)
                    restored = not src.exists() and self._same_content_identity(current, item['before'])
                except (ValueError, OSError):
                    restored = False
                if not restored:
                    issues.append(dict(source=str(src), destination=str(dst), reason='stale_or_occupied'))
        if not items:
            return _fail('nothing_restorable', issues=issues)
        return self._prepare(dict(service='files', action='restore_plan', operation_id=operation_id,
                                  items=items, issues=issues))

    def _move(self, source, destination):
        """No cross-volume fallback, copying, merging, or silent overwrite."""
        src, dst = self._path(source), self._path(destination, False)
        if src in self.resolver.workspace.roots or not src.is_file() or dst.is_relative_to(src):
            raise FileControllerError('invalid_move')
        if src.stat().st_dev != dst.parent.stat().st_dev:
            raise FileControllerError('cross_volume_plan_unsupported')
        if dst.exists():
            raise FileControllerError('destination_exists')
        if os.name == 'nt':
            self.files.move_path(str(src), str(dst))
        else:
            libc = ctypes.CDLL(None, use_errno=True)
            rename = getattr(libc, 'renameat2', None)
            if rename is None:
                raise FileControllerError('exclusive_move_unavailable')
            rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            rename.restype = ctypes.c_int
            if rename(-100, os.fsencode(src), -100, os.fsencode(dst), 1):
                raise OSError(ctypes.get_errno(), 'exclusive_move_failed')
        self._sync_directory(src.parent)
        self._sync_directory(dst.parent)

    @blocked_effect
    async def _run_moves(self, items, action, *, plan=None, restores=None, issues=None):
        record = self._new_record(action, items=[dict(i, status='pending') for i in items],
                                  plan_id=plan['operation_id'] if plan else None,
                                  restores=restores, issues=issues or [])
        self.journal.add('operation', record)
        if plan:
            plan['applied_operation_id'] = record['operation_id']
            self.journal.save(plan)
        try:
            for item in record['items']:
                await asyncio.sleep(0)
                src, dst = Path(item['source']), Path(item['destination'])
                try:
                    self._check_parent(item['source_parent'])
                    self._check_parent(item['destination_root'])
                    self._check(src, item['before'], MAX_FILE_BYTES)
                    self._check(dst, None)
                    if item['destination_parent']:
                        self._check_parent(item['destination_parent'])
                    elif not dst.parent.exists():
                        self._path(dst.parent, False).mkdir()
                    # Record intent BEFORE the move. Recovery checks both paths.
                    item['status'] = 'moving'
                    self.journal.save(record)
                    self._check(src, item['before'], MAX_FILE_BYTES)
                    self._check(dst, None)
                    self._move(src, dst)
                    current, _ = self._snapshot_sync(dst, MAX_FILE_BYTES)
                    if not self._same_content_identity(current, item['before']):
                        raise FileControllerError('move_unverified')
                    item['status'], item['after'] = 'moved', current
                except (OSError, ValueError) as exc:
                    item['error'] = getattr(exc, 'code', 'io_error')
                    self._reconcile_item(item)
                self.journal.save(record)
            record['status'] = 'completed' if all(i['status'] == 'moved' for i in record['items']) and not record['issues'] else 'partial'
            self.journal.save(record)
        except asyncio.CancelledError:
            record['status'] = 'cancelled'
            self.journal.save(record)
            raise
        except (OSError, ValueError, sqlite3.Error):
            record['status'] = 'interrupted'
            self.journal.save(record)
        moved = sum(i['status'] == 'moved' for i in record['items'])
        return dict(ok=record['status'] == 'completed', status=record['status'],
                    operation_id=record['operation_id'], moved=moved, total=len(items),
                    items=record['items'], issues=record['issues'])

    def _reconcile_item(self, item):
        src, dst = Path(item['source']), Path(item['destination'])
        try:
            if not self._path(src, False).exists():
                fp, _ = self._snapshot_sync(dst, MAX_FILE_BYTES)
                if self._same_content_identity(fp, item['before']):
                    item.update(status='moved', after=fp)
                    return
            elif not self._path(dst, False).exists():
                fp, _ = self._snapshot_sync(src, MAX_FILE_BYTES)
                if self._same_content_identity(fp, item['before']):
                    item['status'] = 'failed'
                    return
        except (ValueError, OSError):
            pass
        item['status'] = 'conflict'

    def _recover_record(self, record):
        if 'items' in record:
            for item in record['items']:
                if item['status'] == 'moving':
                    self._reconcile_item(item)
            if record['status'] == 'running':
                record['status'] = 'interrupted'
        elif record['status'] in ('running', 'interrupted'):
            try:
                path = self._path(record['path'], False)
                fp, _ = self._snapshot_sync(path, MAX_FILE_BYTES if record['action'] == 'create_archive' else MAX_TEXT_BYTES)
                staged = record.get('staged_identity')
                if staged and all(fp[k] == v for k, v in staged.items()) and fp['sha256'] == record['expected_output_hash']:
                    record.update(status='completed', after=fp)
                elif fp == record['before']:
                    record['status'] = 'not_applied'
                else:
                    record['status'] = 'conflict'
            except (ValueError, OSError):
                record['status'] = 'interrupted'
        self.journal.save(record)

    def _recover(self):
        for record in self.journal.records():
            if record['status'] in ('running', 'interrupted') or any(i['status'] == 'moving' for i in record.get('items', [])):
                self._recover_record(record)
