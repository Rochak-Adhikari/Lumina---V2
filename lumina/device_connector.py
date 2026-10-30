"""Opt-in outbound device link; local approval is never inferred from model output."""
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

from .device_protocol import TOOLS, TERMINAL, arguments, digest, origin, signature_message


class ConnectorError(ValueError):
    pass


class DeviceVault:
    """Atomic current-user DPAPI state, including the execution receipt journal."""
    def __init__(self, path, protect=None):
        self.path = Path(path).absolute()
        self.protect = protect
        self.lock = None

    def _crypt(self, data, decrypt=False):
        if self.protect:
            return self.protect(data, decrypt)
        from .communication.gmail_credentials import _protect
        return _protect(data, decrypt)

    def _check(self):
        if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
               for p in (self.path, *self.path.parents)):
            raise ConnectorError('Connector storage cannot contain filesystem links.')

    def acquire(self):
        if self.lock:
            return
        self._check()
        from .cloud.operations import service_lock
        self.lock = service_lock(self.path.parent)
        try:
            self.lock.__enter__()
        except Exception:
            self.lock = None
            raise ConnectorError('Another LUMINA process owns this device connection.') from None

    def close(self):
        if self.lock:
            self.lock.__exit__(None, None, None)
            self.lock = None

    def load(self):
        self._check()
        if not self.path.exists():
            return {}
        self.acquire()
        if self.path.stat().st_size > 4*1024*1024:
            raise ConnectorError('Connector storage exceeds its limit.')
        try:
            value = json.loads(self._crypt(self.path.read_bytes(), True))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except Exception:
            raise ConnectorError('Connector storage could not be unlocked by this Windows user.') from None

    def save(self, state):
        self._check()
        self.acquire()
        data = json.dumps(state, ensure_ascii=False).encode()
        if len(data) > 3*1024*1024:
            raise ConnectorError('Connector journal is full; resolve pending requests first.')
        encrypted = self._crypt(data)
        fd, name = tempfile.mkstemp(prefix='.device-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(encrypted); stream.flush(); os.fsync(stream.fileno())
            self._check()
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)


class LocalDeviceExecutor:
    def __init__(self, registry):
        self.registry = registry
        self.root = registry.index.root

    def path(self, value, exists=True):
        candidate = Path(value)
        if '..' in candidate.parts or any(p.startswith('.') or ':' in p
                                          for p in candidate.parts if p != candidate.anchor):
            raise ConnectorError('Hidden paths, traversal and alternate streams are not shared.')
        candidate = candidate if candidate.is_absolute() else self.root/candidate
        target = self.registry.processor.resolver.path(str(candidate), must_exist=exists)
        if not target.is_relative_to(self.root):
            raise ConnectorError('Remote access is restricted to this workspace.')
        parts = target.relative_to(self.root).parts
        if target.suffix.lower() in {'.pem', '.key', '.pfx', '.p12', '.sqlite3', '.db'} or any(
                word in part.casefold() for part in parts
                for word in ('credential', 'secret', 'token', 'api_key', 'backup-key')):
            raise ConnectorError('Credential and database files are not shared.')
        return target

    def validate(self, tool, args):
        args = arguments(tool, args)
        if 'path' in args:
            args['path'] = str(self.path(args['path'], tool != 'create_directory'))
        if tool == 'open_app':
            # No terminal/interpreter/agent escape through application discovery.
            if args['name'].casefold() not in {'notepad', 'calculator', 'chrome', 'edge'}:
                raise ConnectorError('Only Notepad, Calculator, Chrome and Edge may be opened remotely.')
            args = {'app': args['name'].casefold()}
        return args

    async def execute(self, tool, args):
        return await self.registry.execute(tool, self.validate(tool, args))

    def shareable(self, tool, result):
        if not isinstance(result, dict) or not result.get('ok') or result.get('confirmation_required'):
            return {'ok': False, 'error': 'The device operation was refused or failed. Inspect its local UI.'}
        allowed = {'ok', 'content', 'truncated', 'scan_incomplete', 'system', 'release',
                   'architecture', 'cpu_count', 'disk_free', 'disk_total', 'size', 'encoding'}
        value = {k: v for k, v in result.items() if k in allowed and isinstance(v, (str, int, float, bool, type(None)))}
        entries = result.get('results', result.get('entries'))
        if isinstance(entries, list):
            value['results'] = []
            for row in entries[:50]:
                try:
                    target = self.path(row['path'])
                    value['results'].append({'path': str(target.relative_to(self.root)), 'type': row.get('type', 'unknown')})
                except (ValueError, OSError, KeyError, TypeError):
                    continue
            value['returned_count'] = len(value['results'])
            value['truncated'] = bool(value.get('truncated') or len(entries) > 50)
        if 'content' in value:
            value['truncated'] = bool(value.get('truncated') or len(value['content']) > 8000)
            value['content'] = value['content'][:8000]
        from .workers import redact
        def clean(v):
            if isinstance(v, str): return redact(v)
            if isinstance(v, list): return [clean(x) for x in v]
            if isinstance(v, dict): return {k: clean(x) for k, x in v.items()}
            return v
        value = clean(value)
        if len(json.dumps(value, ensure_ascii=False).encode('utf-8')) > 15000:
            return {'ok': True, 'truncated': True, 'message': 'Result exceeds the sharing limit; narrow the request.'}
        return value


class DeviceConnector:
    def __init__(self, executor, vault=None, transport=None):
        self.executor = executor
        root_id = hashlib.sha256(str(executor.root).casefold().encode()).hexdigest()[:16]
        base = Path(os.environ.get('LOCALAPPDATA', Path.home()))/'LUMINA'/'device-connector'/root_id
        self.vault = vault or DeviceVault(base/'state.dpapi')
        self.transport = transport  # Tests only; production always verifies HTTPS.
        self.state = {}
        self.token = None
        self.token_until = 0
        self.runner = self.active = self.http = None
        self.lock = asyncio.Lock()
        self.error = None
        self.connected_at = 0
        self.storage_failed = False

    def save(self):
        self.vault.save(self.state)

    def status(self):
        return {'enabled': self.state.get('enabled', False), 'origin': self.state.get('origin'),
                'device_id': self.state.get('device_id'), 'fingerprint': self.state.get('fingerprint'),
                'status': 'connected' if time.time()-self.connected_at < 15 else 'offline' if self.state.get('device_id') else 'not_paired',
                'workspace': str(self.executor.root), 'capabilities': list(TOOLS), 'error': self.error,
                'requests': [{k: v for k, v in r.items() if k in ('id', 'tool', 'args_json', 'local_status', 'preview')}
                             for r in self.state.get('journal', {}).values() if r.get('local_status') not in ('delivered', 'closed')]}

    async def start(self):
        try:
            self.state = self.vault.load()
            if self.state and self.state.get('root') != str(self.executor.root):
                raise ConnectorError('Connector workspace changed; configure pairing again.')
            for row in self.state.get('journal', {}).values():
                if row['local_status'] in ('starting', 'running'):
                    row.update(local_status='ready_to_send', outcome='unknown',
                               preview={'ok': False, 'error': 'Device restarted during execution; outcome is unknown.'})
            if self.state: self.save()
        except Exception:
            self.state = {}; self.storage_failed = True
            self.error = 'Connector storage is unavailable. Local LUMINA remains operational.'
        if not self.runner: self.runner = asyncio.create_task(self.run())

    async def request(self, path, body=None, authenticated=True):
        if self.transport:
            return await self.transport(path, body or {}, self.token if authenticated else None)
        import aiohttp
        if not self.http:
            self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12), trust_env=False)
        headers = {'Authorization': 'Bearer '+self.token} if authenticated and self.token else {}
        url = origin(self.state['origin'])+'/device/v1'+path
        async with self.http.post(url, json=body or {}, headers=headers, allow_redirects=False) as response:
            data = bytearray()
            async for chunk in response.content.iter_chunked(8192):
                data.extend(chunk)
                if len(data) > 65536: raise ConnectorError('Cloud response exceeds the device limit.')
            if response.status == 401: self.token = None
            if response.status != 200:
                raise ConnectorError('Cloud connection rejected or unavailable; check pairing and cloud status.')
            return json.loads(data)

    async def pair(self, cloud_origin, code):
        async with self.lock:
            if self.storage_failed: raise ConnectorError('Repair connector storage before pairing; existing receipts are preserved.')
            if self.state.get('enabled') or self.active and not self.active.done():
                raise ConnectorError('Disconnect this device before pairing again.')
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
            cloud_origin = origin(cloud_origin)
            if not isinstance(code, str) or not 20 <= len(code) <= 200:
                raise ConnectorError('Enter the pairing code shown by your Cloud Core.')
            code_hash = hashlib.sha256(code.encode()).hexdigest()
            if self.state.get('pairing_hash') != code_hash or self.state.get('origin') != cloud_origin:
                if self.state.get('device_id'):
                    raise ConnectorError('This installation is already paired. Revoke it in Cloud Core and use a new connector profile to change identity.')
                key = Ed25519PrivateKey.generate()
                self.state = {'root': str(self.executor.root), 'origin': cloud_origin, 'enabled': False,
                              'private_key': base64.b64encode(key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode(),
                              'public_key': base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode(),
                              'pairing_hash': code_hash, 'journal': {}}
                self.save()  # Persist before exchange; a lost response can retry safely.
            reply = await self.request('/enroll', {'code': code, 'public_key': self.state['public_key']}, False)
            self.state.update(device_id=reply['id'], fingerprint=reply['fingerprint'], enabled=True)
            self.save(); self.error = None
            return self.status()

    async def authenticate(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        device = self.state['device_id']
        challenge = await self.request('/challenge', {'device_id': device}, False)
        signature = Ed25519PrivateKey.from_private_bytes(base64.b64decode(self.state['private_key'])).sign(
            signature_message(self.state['origin'], device, challenge['nonce']))
        reply = await self.request('/authenticate', {'device_id': device, 'nonce': challenge['nonce'],
                                   'signature': base64.b64encode(signature).decode()}, False)
        self.token, self.token_until = reply['access_token'], reply['expires_at']

    async def tick(self):
        if not self.state.get('enabled') or not self.state.get('device_id'): return
        if not self.token or self.token_until < time.time()+20: await self.authenticate()
        reply = await self.request('/heartbeat')
        self.connected_at = time.time(); self.error = None
        command = reply.get('command')
        journal = self.state.setdefault('journal', {})
        if command:
            arguments(command['tool'], command['args_json'])
            if command['device_id'] != self.state['device_id'] or command['expires_at'] < time.time():
                raise ConnectorError('Device command identity or expiry is invalid.')
            row = journal.get(command['id'])
            if row and row['digest'] != digest(command): raise ConnectorError('A received device request changed.')
            if not row:
                if len(journal) >= 100:
                    oldest = next((k for k, r in journal.items() if r['local_status'] in ('delivered', 'closed')), None)
                    if oldest is None: raise ConnectorError('Device journal is full.')
                    del journal[oldest]
                journal[command['id']] = {**command, 'digest': digest(command), 'local_status': 'awaiting_local'}
            elif row['local_status'] == 'awaiting_local': row.update(fence=command['fence'])
            self.save()
        for row in tuple(journal.values()):
            if row['local_status'] in ('delivered', 'closed'): continue
            current = await self.request('/command', {'id': row['id']})
            if current['status'] in TERMINAL:
                was_running = row['local_status'] == 'running'
                row['local_status'] = 'closed'; row.pop('preview', None); self.save()
                if was_running and self.active and not self.active.done(): self.active.cancel()
                continue
            if row['local_status'] == 'ready_to_send':
                await self.request('/finish', {'id': row['id'], 'fence': row['fence'],
                                   'status': row['outcome'], 'result': row['preview']})
                row['local_status'] = 'delivered'; row.pop('preview', None); self.save()

    async def run(self):
        delay = 2
        while True:
            try:
                async with self.lock: await self.tick()
                delay = 2
            except asyncio.CancelledError: raise
            except Exception:
                self.error = 'Cloud connection unavailable or pairing needs approval. Local tools still work.'
                delay = min(30, delay*2)
            await asyncio.sleep(delay)

    async def decide(self, identity, action):
        async with self.lock:
            row = self.state.get('journal', {}).get(identity)
            if not row or not self.state.get('enabled'): raise ConnectorError('This device request is no longer available.')
            if action in ('share', 'withhold') and row['local_status'] == 'awaiting_share':
                if action == 'withhold':
                    row['preview'] = {'ok': False, 'error': 'Executed locally; result disclosure was declined.'}
                    row['outcome'] = 'declined'
                row['local_status'] = 'ready_to_send'; self.save(); return self.status()
            if row['local_status'] != 'awaiting_local' or action not in ('approve', 'decline'):
                raise ConnectorError('This decision is stale or invalid.')
            if action == 'decline':
                row.update(local_status='ready_to_send', outcome='declined', preview={'ok': False, 'error': 'Declined on the device.'})
                self.save(); return self.status()
            if self.active and not self.active.done(): raise ConnectorError('A device request is already executing.')
            self.executor.validate(row['tool'], row['args_json'])
            row['local_status'] = 'starting'; self.save()
            try:
                await self.request('/begin', {'id': row['id'], 'fence': row['fence']})
            except Exception:
                row.update(local_status='ready_to_send', outcome='unknown', preview={'ok': False, 'error': 'Execution was not started; authorization receipt was lost.'})
                self.save(); raise
            row['local_status'] = 'running'; self.save()
            self.active = asyncio.create_task(self.execute(row))
            return self.status()

    async def execute(self, row):
        try:
            async with asyncio.timeout(30): result = await self.executor.execute(row['tool'], row['args_json'])
            preview = self.executor.shareable(row['tool'], result)
            outcome = 'succeeded' if preview.get('ok') else 'failed'
        except asyncio.CancelledError:
            if row['local_status'] != 'closed':
                row.update(local_status='ready_to_send', outcome='unknown', preview={'ok': False, 'error': 'Device execution was interrupted; outcome is unknown.'})
                self.save()
            raise
        except Exception:
            preview = {'ok': False, 'error': 'Device operation failed or timed out; inspect locally before retrying.'}
            outcome = 'unknown'
        if row['local_status'] == 'running':
            row.update(local_status='awaiting_share', outcome=outcome, preview=preview); self.save()

    async def set_enabled(self, enabled):
        if not isinstance(enabled, bool): raise ConnectorError('Enabled must be a boolean.')
        async with self.lock:
            if not self.state.get('device_id'): raise ConnectorError('Pair this device first.')
            if self.active and not self.active.done(): raise ConnectorError('Wait for the current local operation to settle.')
            self.state['enabled'] = enabled; self.token = None; self.connected_at = 0; self.save()
        return self.status()

    async def close(self):
        for task in (self.runner, self.active):
            if task: task.cancel()
        await asyncio.gather(*(t for t in (self.runner, self.active) if t), return_exceptions=True)
        if self.http: await self.http.close()
        self.vault.close()
