"""Runtime-owned durable monitors and notification outbox.

start enables ticks; the runtime must schedule tick and await close. No threads or
background tasks are created. notify receives an event dictionary and must return
an explicit successful receipt (as ReminderService does). Synchronous callbacks
must be nonblocking. Delivery claims are persisted before invoking notify;
interrupted/ambiguous deliveries become unknown and are never automatically retried.
Deduplication retains the latest 512 events; producers must not replay older history.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import inspect
import json
import math
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from .reminders import ReminderService, UTC, _result as _reminder_result, _success
from .web_search import validate_public_url

EVENT_TYPES = frozenset({'task_completed', 'task_failed', 'reminder_due',
                         'monitor_changed', 'worker_completed', 'worker_failed',
                         'provider_failed', 'provider_recovered'})
MAX_EVENTS = 512
MAX_WATCHES = 100
MAX_BYTES = 4_000_000


def _result(ok, status, error=None, **fields):
    if not ok and error is None:
        error = {
            'disabled': 'Notifications are disabled. Enable them explicitly in settings.',
            'busy': 'Automation state is busy; try again shortly.',
            'closed': 'Automation service is closed.',
            'not_found': 'The requested watch or notification was not found.',
            'unknown': 'Delivery could not be confirmed and will not be retried automatically.',
            'storage_error': 'Automation state could not be read or written safely.',
        }.get(status, 'Automation could not complete the request safely.')
    return _reminder_result(ok, status, error, **fields)


def _number(value, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError('Number outside supported bounds')
    return value


def _text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('Invalid or oversized text')
    return value.strip()


class AutomationService(ReminderService):
    """execute('background_monitor'|'proactive', action, **args).

    search is a WebSearch instance or provider-name -> WebSearch mapping.
    quiet_start/end are local HH:MM strings (None disables quiet hours).
    enqueue is trusted runtime input, deliberately not an execute action.
    The master enabled preference gates all notifications, including monitors.
    Both obey
    quiet hours, snooze, busy suppression and cooldown. Removed/paused watches
    cannot deliver queued notifications. All operations use one OS file lock.
    """
    def __init__(self, root, resolver, search, notify=None, busy=None, *,
                 timezone='Asia/Kathmandu', callback_timeout=20):
        from pathlib import Path
        super().__init__(Path(root) / 'lumina-automation.json', timezone,
                         notify=notify, resolver=resolver, callback_timeout=callback_timeout)
        self.search = search
        self.busy = busy
        self._closed = False
        self._running = False
        self._ticks = set()

    def _default(self):
        return {'watches': [], 'events': [], 'settings': {
            'enabled': False, 'timezone': self.timezone, 'quiet_start': None,
            'quiet_end': None, 'cooldown': 60, 'snooze_until': None,
            'last_delivery': None}}

    def _save(self, state):
        # Reuse the atomic fsync/replace implementation and lock inode contract.
        if len(json.dumps(state, allow_nan=False).encode('utf-8')) > MAX_BYTES:
            raise ValueError('Automation state capacity exceeded')
        super()._save(state)

    def _load(self):
        path = self._path(self.path)
        if not path.exists():
            return self._default()
        if path.stat().st_size > MAX_BYTES:
            raise ValueError('Oversized automation state')
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('version') != 1:
            raise ValueError('Unsupported automation state')
        state = data['jobs']
        if not isinstance(state, dict) or set(state) != {'watches', 'events', 'settings'}:
            raise ValueError('Invalid automation state')
        if len(state['watches']) > MAX_WATCHES or len(state['events']) > MAX_EVENTS:
            raise ValueError('Automation state capacity exceeded')
        self._settings(state['settings'])
        for field in ('snooze_until', 'last_delivery'):
            if state['settings'][field] is not None:
                self._instant(state['settings'][field], self.timezone)
        seen = set()
        for watch in state['watches']:
            UUID(watch['id'])
            if watch['id'] in seen or watch['status'] not in {'active', 'paused'}:
                raise ValueError('Invalid stored watch')
            seen.add(watch['id'])
            _text(watch['query'], 500)
            _text(watch['provider'], 100)
            _number(watch['interval'], 1, 604800)
            _number(watch['failures'], 0, 10)
            if type(watch['notifications']) is not bool or len(watch['history']) > 32:
                raise ValueError('Invalid watch preferences or history')
            if watch['baseline'] is not None and (not isinstance(watch['baseline'], str) or len(watch['baseline']) != 64):
                raise ValueError('Invalid baseline')
            self._instant(watch['next_at'], self.timezone)
        recovered = False
        identities, deliveries = set(), set()
        for event in state['events']:
            UUID(event['id'])
            _text(event['delivery_id'], 200)
            _text(event['message'], 1000)
            self._instant(event['created_at'], self.timezone)
            if event['id'] in identities or event['delivery_id'] in deliveries or event['priority'] not in {'low', 'normal'}:
                raise ValueError('Invalid event identity or priority')
            identities.add(event['id'])
            deliveries.add(event['delivery_id'])
            if len(event.get('evidence', [])) > 10:
                raise ValueError('Oversized evidence')
            if event['type'] not in EVENT_TYPES or event['status'] not in {'pending', 'delivering', 'delivered', 'unknown', 'dismissed'}:
                raise ValueError('Invalid stored event')
            if event['status'] == 'delivering':
                event['status'] = 'unknown'
                recovered = True
        if recovered:
            self._save(state)
        return state

    @staticmethod
    def _settings(settings):
        if type(settings['enabled']) is not bool:
            raise ValueError('enabled must be boolean')
        ZoneInfo(settings['timezone'])
        _number(settings['cooldown'], 0, 86400)
        for key in ('quiet_start', 'quiet_end'):
            value = settings[key]
            if value is not None:
                if not isinstance(value, str) or len(value) != 5 or value[2] != ':':
                    raise ValueError('Quiet times must be HH:MM')
                hour, minute = map(int, value.split(':'))
                if not 0 <= hour < 24 or not 0 <= minute < 60:
                    raise ValueError('Invalid quiet time')
        if (settings['quiet_start'] is None) != (settings['quiet_end'] is None):
            raise ValueError('Supply both quiet times or neither')

    def _append(self, state, event):
        existing = next((e for e in state['events'] if e['delivery_id'] == event['delivery_id']), None)
        if existing:
            return existing
        while len(state['events']) >= MAX_EVENTS:
            index = next((i for i, e in enumerate(state['events']) if e['status'] != 'pending'), None)
            if index is None:
                raise ValueError('Notification queue full')
            state['events'].pop(index)
        state['events'].append(event)
        return event

    async def enqueue(self, event):
        """Accept bounded real runtime events; never executes supplied instructions."""
        try:
            if not isinstance(event, dict) or set(event) - {'type', 'delivery_id', 'message', 'priority'}:
                raise ValueError('Unsupported event fields')
            if event.get('type') not in EVENT_TYPES or event.get('type') == 'monitor_changed':
                raise ValueError('Unsupported external event type')
            priority = event.get('priority', 'low')
            if priority not in {'low', 'normal'}:
                raise ValueError('Unsupported priority')
            item = dict(id=str(uuid4()), delivery_id=_text(event.get('delivery_id'), 200),
                        type=event['type'], message=_text(event.get('message'), 1000),
                        priority=priority, status='pending', created_at=datetime.now(UTC).isoformat())
            with self._locked():
                state = self._load()
                if not state['settings']['enabled']:
                    return _result(False, 'disabled')
                item = self._append(state, item)
                self._save(state)
                return _result(True, item['status'], event=deepcopy(item))
        except BlockingIOError:
            return _result(False, 'busy')
        except (ValueError, TypeError, KeyError) as exc:
            return _result(False, 'invalid', str(exc))
        except Exception:
            return _result(False, 'storage_error')

    async def execute(self, tool, action, **args):
        if action == 'status' and not args and tool in {'background_monitor', 'proactive'}:
            return self.status()
        allowed = {
            'background_monitor': {'create': {'query', 'provider', 'interval', 'notifications'},
                'list': set(), 'inspect': {'id'}, 'pause': {'id'}, 'resume': {'id'}, 'remove': {'id'}},
            'proactive': {'configure': {'enabled', 'timezone', 'quiet_start', 'quiet_end', 'cooldown'},
                'snooze': {'minutes'}, 'list': set(), 'inspect': {'id'}, 'dismiss': {'id'}}}
        try:
            if tool not in allowed or action not in allowed[tool] or set(args) - allowed[tool][action]:
                raise ValueError('Unsupported action or fields')
            with self._locked():
                state = self._load()
                now = datetime.now(UTC)
                items = state['watches' if tool == 'background_monitor' else 'events']
                if action == 'list':
                    return _result(True, 'listed', **{'watches' if tool == 'background_monitor' else 'events': deepcopy(items)})
                if action == 'configure':
                    settings = {**state['settings'], **args}
                    for key in ('quiet_start', 'quiet_end'):
                        if settings[key] == '':
                            settings[key] = None
                    self._settings(settings)
                    state['settings'] = settings
                    item = settings
                elif action == 'snooze':
                    minutes = _number(args.get('minutes'), 0, 10080)
                    state['settings']['snooze_until'] = (now + timedelta(minutes=minutes)).isoformat()
                    item = state['settings']
                elif action == 'create':
                    if len(items) >= MAX_WATCHES:
                        raise ValueError('Monitor capacity exceeded')
                    preference = args.get('notifications', True)
                    if type(preference) is not bool:
                        raise ValueError('notifications must be boolean')
                    item = dict(id=str(uuid4()), query=_text(args.get('query'), 500),
                                provider=_text(args.get('provider'), 100),
                                interval=_number(args.get('interval', 300), 1, 604800),
                                notifications=preference, status='active', baseline=None,
                                outcome='pending', failures=0, next_at=now.isoformat(),
                                history=[], created_at=now.isoformat())
                    items.append(item)
                else:
                    item = next((i for i in items if i['id'] == args.get('id')), None)
                    if item is None:
                        return _result(False, 'not_found')
                    if action == 'inspect':
                        return _result(True, 'inspected', **{'watch' if tool == 'background_monitor' else 'event': deepcopy(item)})
                    if action == 'remove':
                        items.remove(item)
                        for event in state['events']:
                            if event.get('watch_id') == item['id'] and event['status'] == 'pending':
                                event['status'] = 'dismissed'
                    elif action in {'pause', 'resume'}:
                        item['status'] = 'paused' if action == 'pause' else 'active'
                        if action == 'resume':
                            item['next_at'] = now.isoformat()
                    elif action == 'dismiss':
                        item['status'] = 'dismissed'
                self._save(state)
                return _result(True, action, **{'watch' if tool == 'background_monitor' else 'event': deepcopy(item)})
        except BlockingIOError:
            return _result(False, 'busy')
        except (ValueError, TypeError, KeyError) as exc:
            return _result(False, 'invalid', str(exc))
        except Exception:
            return _result(False, 'storage_error')

    async def _search(self, watch):
        search = self.search.get(watch['provider']) if isinstance(self.search, dict) else self.search
        if search is None:
            raise ValueError('Provider unavailable')
        async with asyncio.timeout(self.callback_timeout):
            result = search.search(watch['query'], limit=10)
            if inspect.isawaitable(result):
                result = await result
        if not isinstance(result, dict) or result.get('ok') is not True or result.get('provider') != watch['provider'] or result.get('partial'):
            raise ValueError('Provider failed or returned incomplete evidence')
        raw = result.get('results')
        if not isinstance(raw, list) or len(raw) > 10:
            raise ValueError('Invalid structured results')
        canonical = {}
        for hit in raw:
            url = validate_public_url(hit['url'])
            parts = urlsplit(url)
            query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query)
                                     if not k.lower().startswith('utm_') and k.lower() not in {'fbclid', 'gclid'}))
            url = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or '/', query, ''))
            title = ' '.join(_text(hit['title'], 500).split())
            snippet = ' '.join(hit.get('snippet', '').split())[:2000]
            entry = {'url': url, 'title': title, 'snippet': snippet}
            # Deterministic selection even if duplicate URLs have different snippets.
            if url not in canonical or json.dumps(entry, sort_keys=True) < json.dumps(canonical[url], sort_keys=True):
                canonical[url] = entry
        evidence = [canonical[key] for key in sorted(canonical)]
        fingerprint = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
        return fingerprint, evidence

    def _suppressed(self, settings, now):
        if settings['snooze_until'] and self._instant(settings['snooze_until'], self.timezone) > now:
            return True
        if settings['last_delivery'] and (now - self._instant(settings['last_delivery'], self.timezone)).total_seconds() < settings['cooldown']:
            return True
        start, end = settings['quiet_start'], settings['quiet_end']
        if start is None:
            return False
        local = now.astimezone(ZoneInfo(settings['timezone'])).strftime('%H:%M')
        return start <= local < end if start < end else local >= start or local < end

    async def tick(self, now=None):
        task = asyncio.current_task()
        self._ticks.add(task)
        try:
            return await self._tick(now)
        finally:
            self._ticks.discard(task)

    async def _tick(self, now=None):
        if self._closed:
            return _result(False, 'closed')
        try:
            instant = datetime.now(UTC) if now is None else self._instant(now, self.timezone)
            with self._locked():
                state = self._load()
                for watch in state['watches']:
                    if watch['status'] != 'active' or self._instant(watch['next_at'], self.timezone) > instant:
                        continue
                    try:
                        fingerprint, evidence = await self._search(watch)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        watch['failures'] = min(watch['failures'] + 1, 10)
                        watch['outcome'] = 'provider_failure'
                        delay = min(watch['interval'] * 2 ** watch['failures'], 86400)
                    else:
                        watch['failures'] = 0
                        delay = watch['interval']
                        previous = watch['baseline']
                        watch['outcome'] = ('no_results' if not evidence else 'baseline' if previous is None
                                            else 'no_change' if previous == fingerprint else 'changed')
                        # Empty results do not erase a known baseline or trigger alerts.
                        if evidence:
                            if previous is not None and previous != fingerprint:
                                if watch['notifications']:
                                    self._append(state, dict(id=str(uuid4()), delivery_id=str(uuid4()),
                                        watch_id=watch['id'], type='monitor_changed', priority='low',
                                        message='Monitor update: ' + watch['query'], evidence=evidence,
                                        status='pending', created_at=instant.isoformat()))
                            watch['baseline'] = fingerprint
                    watch['next_at'] = (instant + timedelta(seconds=delay)).isoformat()
                    watch['history'] = (watch['history'] + [{'at': instant.isoformat(), 'outcome': watch['outcome']}])[-32:]
                    # Outbox and baseline are one atomic transaction, before delivery.
                    self._save(state)
                busy = await self._call(lambda _: self.busy(), {}) if self.busy else False
                if not state['settings']['enabled'] or busy or self._suppressed(state['settings'], instant) or self.notify is None:
                    return _result(True, 'suppressed')
                active = {w['id'] for w in state['watches'] if w['status'] == 'active'}
                pending = [e for e in state['events'] if e['status'] == 'pending' and
                           (e.get('watch_id') in active if e.get('watch_id') else state['settings']['enabled'])]
                if not pending:
                    return _result(True, 'idle')
                first = pending[0]
                batch = [e for e in pending if e['priority'] == 'low'][:10] if first['priority'] == 'low' else [first]
                delivery_id = hashlib.sha256('|'.join(e['delivery_id'] for e in batch).encode()).hexdigest()
                notice = {'type': 'notification', 'delivery_id': delivery_id,
                          'message': '\n'.join(e['message'] for e in batch)[:2000],
                          'events': deepcopy(batch)}
                for event in batch:
                    event['status'] = 'delivering'
                    event['notification_id'] = delivery_id
                state['settings']['last_delivery'] = instant.isoformat()
                self._save(state)
                outcome = 'unknown'
                try:
                    receipt = await self._call(self.notify, notice)
                    if _success(receipt) and receipt['status'] != 'allowed' and receipt.get('delivery_id', delivery_id) == delivery_id:
                        outcome = 'delivered'
                finally:
                    for event in batch:
                        event['status'] = outcome
                    self._save(state)
                return _result(outcome == 'delivered', outcome, delivery_id=delivery_id)
        except asyncio.CancelledError:
            raise
        except BlockingIOError:
            return _result(False, 'busy')
        except Exception:
            return _result(False, 'failed', 'Automation tick failed safely; inspect durable state')

    async def start(self):
        self._closed = False
        self._running = True
        return _result(True, 'started', scheduling='runtime_tick')

    async def close(self):
        self._closed = True
        self._running = False
        tasks = [task for task in self._ticks if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return _result(True, 'closed')

    def status(self):
        try:
            with self._locked():
                state = self._load()
                issues = []
                failed = sum(w['outcome'] == 'provider_failure' for w in state['watches'] if w['status'] == 'active')
                unknown = sum(e['status'] == 'unknown' for e in state['events'])
                if failed:
                    issues.append({'code': 'provider_failure', 'message': 'Search failed for one or more watches; bounded retry is scheduled.', 'count': failed})
                if unknown:
                    issues.append({'code': 'delivery_unknown', 'message': 'Some notification deliveries are unconfirmed; inspect or dismiss them.', 'count': unknown})
                if self.notify is None:
                    issues.append({'code': 'notifier_unavailable', 'message': 'No notification callback is configured.'})
                if not state['settings']['enabled']:
                    issues.append({'code': 'notifications_disabled', 'message': 'All notifications are disabled by the master preference.'})
                return _result(True, 'running' if self._running else 'stopped',
                               scheduling='runtime_tick', settings=deepcopy(state['settings']),
                               watches=len(state['watches']), pending=sum(e['status'] == 'pending' for e in state['events']),
                               unknown=unknown, issues=issues)
        except BlockingIOError:
            return _result(False, 'busy')
        except Exception:
            return _result(False, 'storage_error')
