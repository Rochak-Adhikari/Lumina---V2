"""Durable one-time notifications, with no scheduled action execution.

The parent supplies its PathResolver and callbacks accepting an event dict.
Policy may return bool or {ok, status}; notify must return {ok, status}.
Only explicit successful results acknowledge delivery. Exceptions, cancellation,
malformed receipts and interrupted delivery claims become terminal 'unknown'.
Pending missed jobs are delivered on the next tick; nothing retries automatically.
The delivery_id is stable and may also be deduplicated by the parent's notifier.
"""

import asyncio
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone as dt_timezone
import inspect
import json
import math
import os
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo


UTC = dt_timezone.utc
STATES = {'pending', 'delivering', 'delivered', 'cancelled', 'blocked', 'failed', 'unknown'}


def _result(ok, status, error=None, **fields):
    return {'ok': ok, 'status': status, 'error': error, **fields}


def _success(value):
    return (isinstance(value, dict) and value.get('ok') is True
            and value.get('status') in {'ok', 'success', 'allowed', 'delivered', 'notified'}
            and not value.get('error'))


class ReminderService:
    """Use execute(create/list/inspect/update/snooze/cancel), tick, start, close.

    create: message, due_at (ISO-8601 or datetime), optional timezone.
    inspect/cancel: id. update: id, message and/or due_at/timezone (pending only).
    snooze: id, minutes (positive) OR due_at; unknown outcomes cannot be rearmed.
    Naive local times use the configured zone; ambiguous/nonexistent local times
    must be supplied with an explicit UTC offset. start polls until close.
    tick returns due-event outcomes as well as invoking the injected notifier.
    All state operations acquire the same nonblocking OS file lock, held through
    policy and notification; competing/reentrant operations return busy.
    Async callbacks time out after callback_timeout seconds; synchronous callbacks
    must be nonblocking. A notification timeout is unknown, never safe to retry.
    """

    def __init__(self, path, timezone='Asia/Kathmandu', notify=None, policy=None,
                 *, resolver, poll_interval=1.0, callback_timeout=15.0):
        self.resolver = resolver
        self.path = Path(resolver.path(str(path), must_exist=False))
        self.timezone = timezone
        ZoneInfo(timezone)
        if not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError('poll_interval must be positive and finite')
        if not math.isfinite(callback_timeout) or callback_timeout <= 0:
            raise ValueError('callback_timeout must be positive and finite')
        self.notify, self.policy = notify, policy
        self.poll_interval = poll_interval
        self.callback_timeout = callback_timeout
        self._task = None
        self._last = _result(True, 'idle')

    def _path(self, path):
        return Path(self.resolver.path(str(path), must_exist=False))

    @contextmanager
    def _locked(self):
        target = self._path(self.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self._path(str(target) + '.lock')
        # Never unlink this inode: all instances must lock the same authority.
        with open(lock_path, 'a+b') as handle:
            handle.seek(0, os.SEEK_END)
            if not handle.tell():
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise BlockingIOError('Reminder authority is busy') from exc
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _save(self, jobs):
        target = self._path(self.path)
        temporary = self._path(str(target) + '.' + str(uuid4()) + '.tmp')
        try:
            with open(temporary, 'x', encoding='utf-8') as handle:
                json.dump({'version': 1, 'jobs': jobs}, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            if os.name != 'nt':
                fd = os.open(target.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _instant(value, zone):
        dt = datetime.fromisoformat(value) if isinstance(value, str) else value
        if not isinstance(dt, datetime):
            raise ValueError('due_at must be an ISO datetime')
        tz = ZoneInfo(zone)
        if dt.tzinfo is None:
            candidates = {dt.replace(tzinfo=tz, fold=fold).astimezone(UTC)
                          for fold in (0, 1)
                          if dt.replace(tzinfo=tz, fold=fold).astimezone(UTC)
                          .astimezone(tz).replace(tzinfo=None) == dt}
            if len(candidates) != 1:
                raise ValueError('Ambiguous or nonexistent local time; supply an offset')
            dt = candidates.pop()
        return dt.astimezone(UTC)

    @staticmethod
    def _message(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 4096:
            raise ValueError('message must contain 1–4096 characters')
        return value

    def _load(self):
        target = self._path(self.path)
        if not target.exists():
            return []
        try:
            data = json.loads(target.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('version') != 1:
                raise ValueError('Unsupported state')
            jobs = data['jobs']
            if not isinstance(jobs, list):
                raise ValueError('Invalid jobs')
            ids, deliveries = set(), set()
            for job in jobs:
                if not isinstance(job, dict) or job['status'] not in STATES:
                    raise ValueError('Invalid job')
                for field, seen in [('id', ids), ('delivery_id', deliveries)]:
                    if str(UUID(job[field])) != job[field] or job[field] in seen:
                        raise ValueError('Invalid identity')
                    seen.add(job[field])
                self._message(job['message'])
                ZoneInfo(job['timezone'])
                for field in ('due_at', 'created_at', 'updated_at'):
                    if datetime.fromisoformat(job[field]).utcoffset() is None:
                        raise ValueError('Missing timezone')
        except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
            quarantine = self._path(str(target) + '.corrupt.' + str(uuid4()))
            os.replace(target, quarantine)
            raise ValueError('Corrupt reminder state quarantined at ' + str(quarantine))
        recovered = False
        for job in jobs:
            if job['status'] == 'delivering':
                job.update(status='unknown', error='Interrupted delivery; no automatic retry',
                           updated_at=datetime.now(UTC).isoformat())
                recovered = True
        if recovered:
            self._save(jobs)
        return jobs

    async def execute(self, action, **args):
        try:
            with self._locked():
                jobs = self._load()
                now = datetime.now(UTC).isoformat()
                if action == 'list':
                    if args:
                        raise ValueError('list takes no arguments')
                    return _result(True, 'listed', jobs=deepcopy(jobs))
                if action == 'create':
                    if set(args) - {'message', 'due_at', 'timezone'}:
                        raise ValueError('Only one-time notification fields are supported')
                    zone = args.get('timezone', self.timezone)
                    job = dict(id=str(uuid4()), delivery_id=str(uuid4()),
                               message=self._message(args.get('message')),
                               due_at=self._instant(args.get('due_at'), zone).isoformat(),
                               timezone=zone, status='pending', created_at=now, updated_at=now,
                               error=None)
                    jobs.append(job)
                else:
                    allowed = {'inspect': {'id'}, 'cancel': {'id'},
                               'update': {'id', 'message', 'due_at', 'timezone'},
                               'snooze': {'id', 'minutes', 'due_at'}}
                    if action not in allowed or set(args) - allowed[action]:
                        raise ValueError('Unsupported action or arguments')
                    job = next((j for j in jobs if j['id'] == args.get('id')), None)
                    if job is None:
                        return _result(False, 'not_found', 'Reminder not found')
                    if action == 'inspect':
                        return _result(True, 'inspected', job=deepcopy(job))
                    if action == 'cancel':
                        if job['status'] not in {'pending', 'blocked', 'failed', 'cancelled'}:
                            return _result(False, 'conflict', 'Delivery cannot be undone')
                        job['status'] = 'cancelled'
                    elif action == 'update':
                        if job['status'] != 'pending':
                            return _result(False, 'conflict', 'Only pending jobs can be updated')
                        zone = args.get('timezone', job['timezone'])
                        due = self._instant(args.get('due_at', job['due_at']), zone)
                        job.update(message=self._message(args.get('message', job['message'])),
                                   timezone=zone, due_at=due.isoformat())
                    elif action == 'snooze':
                        if job['status'] not in {'pending', 'blocked', 'failed'}:
                            return _result(False, 'conflict', 'This outcome cannot be rearmed')
                        if ('minutes' in args) == ('due_at' in args):
                            raise ValueError('Supply exactly one of minutes or due_at')
                        if 'minutes' in args:
                            minutes = args['minutes']
                            if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or not math.isfinite(minutes) or minutes <= 0:
                                raise ValueError('minutes must be positive and finite')
                            due = datetime.now(UTC) + timedelta(minutes=minutes)
                        else:
                            due = self._instant(args['due_at'], job['timezone'])
                        if due <= datetime.now(UTC):
                            raise ValueError('Snooze must be in the future')
                        job.update(due_at=due.isoformat(), status='pending', error=None,
                                   delivery_id=str(uuid4()))
                    job['updated_at'] = now
                self._save(jobs)
                return _result(True, job['status'], job=deepcopy(job))
        except BlockingIOError:
            return _result(False, 'busy', 'Reminder authority is busy')
        except (ValueError, TypeError, OverflowError, KeyError) as exc:
            return _result(False, 'invalid', str(exc))
        except Exception:
            return _result(False, 'storage_error', 'Reminder state could not be accessed safely')

    async def _call(self, callback, event):
        # Synchronous callbacks must be nonblocking; async callbacks are bounded.
        async with asyncio.timeout(self.callback_timeout):
            value = callback(deepcopy(event))
            return await value if inspect.isawaitable(value) else value

    async def tick(self, now=None):
        """Catch up pending jobs. Missing notifier leaves them pending for the parent."""
        events = []
        try:
            instant = datetime.now(UTC) if now is None else self._instant(now, self.timezone)
            with self._locked():
                jobs = self._load()
                for job in sorted(jobs, key=lambda j: j['due_at']):
                    due = self._instant(job['due_at'], job['timezone'])
                    if job['status'] != 'pending' or due > instant:
                        continue
                    event = {'type': 'reminder_due', 'id': job['id'],
                             'delivery_id': job['delivery_id'], 'message': job['message'],
                             'due_at': job['due_at'], 'timezone': job['timezone'],
                             'missed': due < instant}
                    if self.notify is None:
                        events.append(_result(False, 'unavailable', 'No notifier configured', event=event))
                        continue
                    try:
                        permission = await self._call(self.policy, event) if self.policy else False
                        permitted = permission is True or _success(permission)
                    except Exception:
                        permitted = False
                    if not permitted:
                        job.update(status='blocked', error='Execution-time policy denied or failed')
                    else:
                        job.update(status='delivering', error=None,
                                   updated_at=datetime.now(UTC).isoformat())
                        self._save(jobs)  # Persist BEFORE any possible notification side effect.
                        try:
                            receipt = await self._call(self.notify, event)
                            if (isinstance(receipt, dict) and 'delivery_id' in receipt
                                    and receipt['delivery_id'] != event['delivery_id']):
                                job.update(status='unknown', error='Notifier receipt identity did not match')
                            elif _success(receipt) and receipt['status'] != 'allowed':
                                job.update(status='delivered', error=None)
                            elif (isinstance(receipt, dict) and receipt.get('ok') is False
                                  and receipt.get('status') in {'failed', 'denied', 'blocked', 'error', 'unavailable'}):
                                job.update(status='failed', error='Notifier reported failure')
                            else:
                                job.update(status='unknown', error='Notifier outcome is unknown')
                        except asyncio.CancelledError:
                            job.update(status='unknown', error='Delivery interrupted; no automatic retry',
                                       updated_at=datetime.now(UTC).isoformat())
                            self._save(jobs)
                            self._last = _result(False, 'delivery_failed', job['error'])
                            raise
                        except Exception:
                            job.update(status='unknown', error='Notifier raised; outcome is unknown')
                    job['updated_at'] = datetime.now(UTC).isoformat()
                    self._save(jobs)
                    events.append(_result(job['status'] == 'delivered', job['status'], job['error'], event=event))
            ok = all(event['ok'] for event in events)
            self._last = _result(ok, 'ticked' if ok else 'delivery_failed',
                                 None if ok else 'One or more notifications were not delivered', events=events)
        except BlockingIOError:
            self._last = _result(False, 'busy', 'Reminder authority is busy', events=events)
        except Exception:
            self._last = _result(False, 'storage_error', 'Reminder tick could not complete safely', events=events)
        return deepcopy(self._last)

    async def start(self):
        if self._task and not self._task.done():
            return _result(True, 'running')
        initial = await self.tick()
        if initial['status'] == 'storage_error':
            return initial
        self._task = asyncio.create_task(self._run())
        return _result(True, 'started', initial=initial)

    async def _run(self):
        while True:
            await asyncio.sleep(self.poll_interval)
            await self.tick()

    async def close(self):
        task = self._task
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self._task = None
        return _result(True, 'closed')

    def status(self):
        running = bool(self._task and not self._task.done())
        fields = dict(timezone=self.timezone, notifier_configured=self.notify is not None,
                      policy_configured=self.policy is not None, last_tick=deepcopy(self._last),
                      running=running, automatic_retry=False)
        try:
            with self._locked():
                jobs = self._load()
                counts = {state: 0 for state in sorted(STATES)}
                for job in jobs:
                    counts[job['status']] += 1
                overdue = sum(j['status'] == 'pending' and
                              self._instant(j['due_at'], j['timezone']) <= datetime.now(UTC)
                              for j in jobs)
            attention = sum(counts[state] for state in ('failed', 'blocked', 'unknown'))
            configured = self.notify is not None and self.policy is not None
            healthy = configured and not attention and (running or not counts['pending'])
            return _result(healthy, 'running' if running else 'stopped',
                           None if healthy else 'Reminder delivery needs attention',
                           **fields, counts=counts, overdue_count=overdue,
                           needs_attention=bool(attention or not configured or (not running and counts['pending'])),
                           recovery='Snooze failed or blocked jobs explicitly; unknown outcomes require review and cannot be rearmed.')
        except BlockingIOError:
            return _result(False, 'busy', 'Reminder authority is busy', **fields)
        except Exception:
            return _result(False, 'storage_error', 'Reminder state could not be accessed safely', **fields)
