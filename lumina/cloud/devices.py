"""Durable device pairing and fenced, owner-approved device commands.

The HTTP layer authorizes owner operations and resolves bearer tokens before
calling device operations. Runtime calls recover() periodically. No local tool
executes here. All timestamps are Unix seconds; command *_json fields are decoded
by Repository, just like the other Cloud Core records.
"""
import base64
import binascii
import hashlib
from pathlib import Path
import re
import secrets
import sqlite3
import time
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..device_protocol import TOOLS, TERMINAL, arguments, origin, signature_message
from .store import CloudError, bounded, canonical


INVITE_TTL = 600
CHALLENGE_TTL = 30
TOKEN_TTL = 600
LEASE_TTL = 30
COMMAND_TTL = 86400
MAX_DEVICES = 16
MAX_UNFINISHED = 50
MAX_CHALLENGES = 4  # Per device, including concurrent handshake attempts.
MAX_TOKENS = 8     # Per device, bounded even when clients repeatedly reconnect.
MAX_RESULT_BYTES = 16000
_OPAQUE = re.compile(r'[A-Za-z0-9_-]{43}\Z')
_UNFINISHED = "('awaiting_owner','queued','claimed','running')"


def _hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _opaque(value):
    return isinstance(value, str) and _OPAQUE.fullmatch(value) is not None


def _base64(value, length):
    """Require canonical, padded standard base64, not base64url or PEM."""
    try:
        if not isinstance(value, str) or len(value) != 4 * ((length + 2) // 3):
            raise ValueError
        raw = base64.b64decode(value, validate=True)
        if len(raw) != length or base64.b64encode(raw).decode('ascii') != value:
            raise ValueError
        return raw
    except (ValueError, binascii.Error):
        raise CloudError('invalid_encoding', 'Use standard base64 for the raw Ed25519 value.') from None


def _unauthorized():
    return CloudError('device_auth', 'Device authentication is unavailable or expired.', 401)


class Devices:
    def __init__(self, store, public_origin):
        self.store, self.repo = store, store.repo
        self.public_origin = origin(public_origin)
        with self.repo.transaction() as db:
            version = db.execute("SELECT value FROM cloud_meta WHERE key='devices_schema'").fetchone()
            if version is None:
                statement = ''
                migration = Path(__file__).parent / 'migrations/002_devices.sql'
                # executescript commits implicitly; execute complete statements instead.
                for line in migration.read_text('utf-8').splitlines(True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        db.execute(statement)
                        statement = ''
                if statement.strip():
                    raise ValueError('Incomplete device migration.')
            elif version[0] != '1':
                raise ValueError('Unsupported device schema version.')

    def _device(self, identity):
        return self.store.row('SELECT * FROM cloud_devices WHERE id=?', (identity,))

    @staticmethod
    def _safe(device):
        return {**{key: device[key] for key in
                   ('id', 'name', 'status', 'fingerprint', 'last_seen')},
                'capabilities': sorted(TOOLS),
                'online': (device['status'] == 'active' and device['last_seen'] is not None
                           and 0 <= time.time() - device['last_seen'] < 15)}

    def _active(self, identity):
        device = self._device(identity)
        if device['status'] != 'active':
            raise CloudError('device_inactive', 'The device is not approved or has been revoked.', 403)
        return device

    def _cleanup(self, now):
        self.repo.db.execute('DELETE FROM cloud_device_challenges WHERE expires_at<=?', (now,))
        self.repo.db.execute('DELETE FROM cloud_device_tokens WHERE expires_at<=?', (now,))
        # Keep consumed receipts so an enrollment response can be retried after expiry.
        self.repo.db.execute('DELETE FROM cloud_device_invites WHERE device_id IS NULL AND expires_at<=?', (now,))

    def invite(self, name, key):
        name = bounded(name, 100)
        with self.repo.transaction() as db:
            previous, digest = self.store._duplicate('device_invite', key, name)
            if previous:
                raise CloudError('invite_already_issued', 'This request already issued an invite. Use a new request key to issue another.', 409)
            now = time.time()
            self._cleanup(now)
            count = db.execute('SELECT (SELECT count(*) FROM cloud_devices) + '
                               '(SELECT count(*) FROM cloud_device_invites WHERE device_id IS NULL)').fetchone()[0]
            if count >= MAX_DEVICES:
                raise CloudError('device_limit', 'The device limit has been reached.', 429)
            identity, code = str(uuid4()), secrets.token_urlsafe(32)
            db.execute('INSERT INTO cloud_device_invites VALUES(?,?,?,?,?,NULL)',
                       (identity, _hash(code), name, now, now + INVITE_TTL))
            self.store._receipt('device_invite', key, digest, identity)
            self.store.event('device.invited', identity, {'name': name, 'expires_at': now + INVITE_TTL})
            return {'code': code, 'expires_at': now + INVITE_TTL}

    def enroll(self, code, public_key):
        raw_key = _base64(public_key, 32)
        if not _opaque(code):
            raise CloudError('invalid_invite', 'The pairing invitation is unavailable or expired.', 403)
        with self.repo.transaction() as db:
            now = time.time()
            self._cleanup(now)
            rows = self.repo.rows('SELECT * FROM cloud_device_invites WHERE code_hash=?', (_hash(code),))
            if not rows:
                raise CloudError('invalid_invite', 'The pairing invitation is unavailable or expired.', 403)
            invite = rows[0]
            if invite['device_id']:
                device = self._device(invite['device_id'])
                if device['public_key'] != public_key:
                    raise CloudError('pairing_conflict', 'This invitation has already been used.', 409)
                return self._safe(device)
            if db.execute('SELECT 1 FROM cloud_devices WHERE public_key=?', (public_key,)).fetchone():
                raise CloudError('pairing_conflict', 'This public key is already registered.', 409)
            if db.execute('SELECT count(*) FROM cloud_devices').fetchone()[0] >= MAX_DEVICES:
                raise CloudError('device_limit', 'The device limit has been reached.', 429)
            identity = str(uuid4())
            fingerprint = hashlib.sha256(raw_key).hexdigest()
            db.execute("INSERT INTO cloud_devices VALUES(?,?,?,?,'pending',?,NULL)",
                       (identity, invite['name'], public_key, fingerprint, now))
            db.execute('UPDATE cloud_device_invites SET device_id=? WHERE id=?', (identity, invite['id']))
            device = self._safe(self._device(identity))
            self.store.event('device.enrolled', identity, device)
            return device

    def list(self):
        return [self._safe(row) for row in self.repo.rows('SELECT * FROM cloud_devices ORDER BY created_at,rowid')]

    def approve(self, identity):
        with self.repo.transaction() as db:
            device = self._device(identity)
            if device['status'] == 'revoked':
                raise CloudError('device_revoked', 'Revoked devices cannot be approved again.', 409)
            if device['status'] == 'pending':
                db.execute("UPDATE cloud_devices SET status='active' WHERE id=?", (identity,))
                self.store.event('device.approved', identity, {'status': 'active'})
            return self._safe(self._device(identity))

    def revoke(self, identity):
        with self.repo.transaction() as db:
            device = self._device(identity)
            db.execute('DELETE FROM cloud_device_tokens WHERE device_id=?', (identity,))
            db.execute('DELETE FROM cloud_device_challenges WHERE device_id=?', (identity,))
            if device['status'] != 'revoked':
                db.execute("UPDATE cloud_devices SET status='revoked' WHERE id=?", (identity,))
                self.store.event('device.revoked', identity, {'status': 'revoked'})
            now = time.time()
            for command in self.repo.rows('SELECT * FROM cloud_device_commands WHERE device_id=? AND status IN ' + _UNFINISHED, (identity,)):
                self._stop(command, 'unknown' if command['status'] == 'running' else 'cancelled', now, 'device_revoked')
            return self._safe(self._device(identity))

    def challenge(self, identity):
        with self.repo.transaction() as db:
            device = self._active(identity)
            now, nonce = time.time(), secrets.token_urlsafe(32)
            self._cleanup(now)
            # Keep the newest bounded set without forcing a lost-response wait.
            db.execute('DELETE FROM cloud_device_challenges WHERE nonce_hash IN '
                       '(SELECT nonce_hash FROM cloud_device_challenges WHERE device_id=? '
                       'ORDER BY created_at DESC,rowid DESC LIMIT -1 OFFSET ?)', (identity, MAX_CHALLENGES - 1))
            db.execute('INSERT INTO cloud_device_challenges VALUES(?,?,?,?,?)',
                       (_hash(nonce), identity, device['public_key'], now, now + CHALLENGE_TTL))
            return {'nonce': nonce, 'expires_at': now + CHALLENGE_TTL}

    def authenticate(self, identity, nonce, signature):
        if not _opaque(nonce):
            raise _unauthorized()
        accepted = False
        with self.repo.transaction() as db:
            device = self._active(identity)
            now = time.time()
            self._cleanup(now)
            rows = self.repo.rows('SELECT * FROM cloud_device_challenges WHERE nonce_hash=? AND device_id=?',
                                 (_hash(nonce), identity))
            if rows:
                challenge = rows[0]
                # Consume even an invalid signature, committing before reporting failure.
                db.execute('DELETE FROM cloud_device_challenges WHERE nonce_hash=?', (_hash(nonce),))
                if challenge['public_key'] == device['public_key']:
                    try:
                        Ed25519PublicKey.from_public_bytes(_base64(device['public_key'], 32)).verify(
                            _base64(signature, 64), signature_message(self.public_origin, identity, nonce))
                        accepted = True
                    except (InvalidSignature, ValueError):
                        pass
            if accepted:
                token = secrets.token_urlsafe(32)
                db.execute('DELETE FROM cloud_device_tokens WHERE token_hash IN '
                           '(SELECT token_hash FROM cloud_device_tokens WHERE device_id=? '
                           'ORDER BY created_at DESC,rowid DESC LIMIT -1 OFFSET ?)', (identity, MAX_TOKENS - 1))
                db.execute('INSERT INTO cloud_device_tokens VALUES(?,?,?,?)',
                           (_hash(token), identity, now, now + TOKEN_TTL))
        if not accepted:
            raise _unauthorized()
        return {'access_token': token, 'expires_at': now + TOKEN_TTL}

    def token(self, rawtoken):
        if not _opaque(rawtoken):
            raise _unauthorized()
        with self.repo.transaction():
            now = time.time()
            self._cleanup(now)
            rows = self.repo.rows("SELECT t.device_id FROM cloud_device_tokens t JOIN cloud_devices d ON d.id=t.device_id "
                                 "WHERE t.token_hash=? AND t.expires_at>? AND d.status='active'", (_hash(rawtoken), now))
        if not rows:
            raise _unauthorized()
        return rows[0]['device_id']

    def _command(self, identity):
        return self.store.row('SELECT * FROM cloud_device_commands WHERE id=?', (identity,))

    @staticmethod
    def _public_command(command):
        return {key: value for key, value in command.items() if key != 'result_digest'}

    def command(self, identity):
        return self._public_command(self._command(identity))

    def commands(self):
        return [self._public_command(row) for row in self.repo.rows(
            'SELECT * FROM cloud_device_commands ORDER BY created_at DESC,rowid DESC LIMIT 100')]

    def _event(self, command, status, **extra):
        # Arguments/results may contain file data. Replay only safe state metadata.
        self.store.event('device_command.' + status, command['id'],
                         {'device_id': command['device_id'], 'tool': command['tool'],
                          'status': status, **extra}, correlation=command['id'])

    def _stop(self, command, status, now, reason):
        self.repo.db.execute('UPDATE cloud_device_commands SET status=?,fence=fence+1,lease_until=NULL,completed_at=? WHERE id=?',
                             (status, now, command['id']))
        self._event(command, status, reason=reason, fence=command['fence'] + 1)

    def propose(self, device_id, tool, args, key):
        try:
            args = arguments(tool, args)
            encoded = canonical(args)
        except (TypeError, ValueError):
            raise CloudError('invalid_arguments', 'Use an exposed device capability and its exact arguments.') from None
        with self.repo.transaction() as db:
            previous, digest = self.store._duplicate('device_command', key, [device_id, tool, args])
            if previous:
                return self.command(previous)
            self._active(device_id)
            now = time.time()
            self.recover(now)
            if db.execute('SELECT count(*) FROM cloud_device_commands WHERE status IN ' + _UNFINISHED).fetchone()[0] >= MAX_UNFINISHED:
                raise CloudError('queue_full', 'The device command queue is full.', 429)
            identity = str(uuid4())
            db.execute("INSERT INTO cloud_device_commands(id,device_id,tool,args_json,status,created_at,expires_at) "
                       "VALUES(?,?,?,?,'awaiting_owner',?,?)", (identity, device_id, tool, encoded, now, now + COMMAND_TTL))
            self.store._receipt('device_command', key, digest, identity)
            command = self.command(identity)
            self._event(command, 'awaiting_owner', fence=0)
            return command

    def approve_command(self, identity):
        with self.repo.transaction() as db:
            self.recover()
            command = self._command(identity)
            if command['status'] != 'awaiting_owner':
                return self._public_command(command)
            self._active(command['device_id'])
            db.execute("UPDATE cloud_device_commands SET status='queued' WHERE id=?", (identity,))
            self._event(command, 'queued', fence=command['fence'])
            return self.command(identity)

    def cancel_command(self, identity):
        with self.repo.transaction():
            command = self._command(identity)
            if command['status'] not in TERMINAL:
                self._stop(command, 'unknown' if command['status'] == 'running' else 'cancelled', time.time(), 'owner_cancelled')
            return self.command(identity)

    def heartbeat(self, identity):
        with self.repo.transaction() as db:
            self._active(identity)
            now = time.time()
            self.recover(now)
            db.execute('UPDATE cloud_devices SET last_seen=? WHERE id=?', (now, identity))
            rows = self.repo.rows("SELECT * FROM cloud_device_commands WHERE device_id=? AND status IN ('claimed','running')", (identity,))
            if rows:
                command = rows[0]
                # Running includes a client waiting for local result-sharing approval.
                db.execute('UPDATE cloud_device_commands SET lease_until=? WHERE id=?',
                           (min(now + LEASE_TTL, command['expires_at']), command['id']))
            else:
                rows = self.repo.rows("SELECT * FROM cloud_device_commands WHERE device_id=? AND status='queued' "
                                      'ORDER BY created_at,rowid LIMIT 1', (identity,))
                command = rows[0] if rows else None
                if command:
                    db.execute("UPDATE cloud_device_commands SET status='claimed',fence=fence+1,lease_until=? WHERE id=?",
                               (min(now + LEASE_TTL, command['expires_at']), command['id']))
                    self._event(command, 'claimed', fence=command['fence'] + 1)
            return {'device': self._safe(self._device(identity)),
                    'command': self.command(command['id']) if command else None}

    @staticmethod
    def _owned(command, device_id, fence):
        if command['device_id'] != device_id or type(fence) is not int or command['fence'] != fence:
            raise CloudError('stale_command', 'The device or command fence does not match.', 409)

    def begin(self, device_id, identity, fence):
        with self.repo.transaction() as db:
            self._active(device_id)
            command, now = self._command(identity), time.time()
            self._owned(command, device_id, fence)
            if command['status'] != 'claimed' or command['lease_until'] <= now or command['expires_at'] <= now:
                raise CloudError('command_state', 'The command cannot begin in its current state.', 409)
            db.execute("UPDATE cloud_device_commands SET status='running',lease_until=? WHERE id=?",
                       (min(now + LEASE_TTL, command['expires_at']), identity))
            self._event(command, 'running', fence=fence)
            return self.command(identity)

    def finish(self, device_id, identity, fence, status, result):
        if not isinstance(status, str) or status not in TERMINAL - {'cancelled', 'expired'}:
            raise CloudError('invalid_result', 'Unsupported device result status.')
        try:
            encoded = canonical(result)
            if len(encoded.encode('utf-8')) > MAX_RESULT_BYTES:
                raise ValueError
            digest = _hash(canonical([status, result]))
        except (TypeError, ValueError, RecursionError):
            raise CloudError('invalid_result', 'The result must be JSON of at most 16000 bytes.') from None
        with self.repo.transaction() as db:
            self._active(device_id)
            command, now = self._command(identity), time.time()
            self._owned(command, device_id, fence)
            if command['status'] in TERMINAL:
                if command['status'] == status and command['result_digest'] == digest:
                    return self._public_command(command)
                raise CloudError('command_state', 'The terminal command result cannot be replaced.', 409)
            # A local starting journal may survive even if /begin never arrived.
            # Accept its conservative unknown outcome without claiming execution.
            if (command['status'] not in ('claimed', 'running') or command['lease_until'] <= now or
                    command['expires_at'] <= now or
                    (command['status'] == 'claimed' and status not in ('declined', 'unknown'))):
                raise CloudError('command_state', 'The command cannot accept this result.', 409)
            db.execute('UPDATE cloud_device_commands SET status=?,result_json=?,result_digest=?,completed_at=?,lease_until=NULL WHERE id=?',
                       (status, encoded, digest, now, identity))
            self._event(command, status, fence=fence)
            return self.command(identity)

    def recover(self, now=None):
        now = time.time() if now is None else now
        with self.repo.transaction() as db:
            self._cleanup(now)
            for command in self.repo.rows("SELECT * FROM cloud_device_commands WHERE status IN ('claimed','running') "
                                          'AND (lease_until<=? OR expires_at<=?)', (now, now)):
                if command['status'] == 'running':
                    self._stop(command, 'unknown', now,
                               'command_expired' if command['expires_at'] <= now else 'lease_expired')
                elif command['expires_at'] <= now:
                    self._stop(command, 'expired', now, 'command_expired')
                else:
                    db.execute("UPDATE cloud_device_commands SET status='queued',fence=fence+1,lease_until=NULL WHERE id=?", (command['id'],))
                    self._event(command, 'queued', reason='lease_expired', fence=command['fence'] + 1)
            for command in self.repo.rows("SELECT * FROM cloud_device_commands WHERE status IN ('awaiting_owner','queued','claimed') AND expires_at<=?", (now,)):
                self._stop(command, 'expired', now, 'command_expired')
