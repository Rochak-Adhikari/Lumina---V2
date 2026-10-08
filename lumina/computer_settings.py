"""Typed settings. All writes/undo prepare exact, expiring confirmation requests.

Kinds: brightness (WMI InstanceName), window (opaque window identity),
mouse_speed (target='system'), audio (Core Audio endpoint IDs; volume/mute).
Window values are normal/minimized/maximized. No default audio selection changes.

ComputerSettings(provider=None, clock=time.monotonic) exposes async execute:
 list_targets(kind), get(kind,target), set(kind,target,value), undo(undo_id),
 execute_confirmed(confirmation,request), cancel(confirmation), status().
set/undo only prepare. The trusted caller must enforce current permissions and
show the complete exact request. Undo is in-memory, bounded to 128 verified
changes; restart discards undo rather than persisting approvals or device state.
Only verified results receive undo_id. Never automatically retry unknown results.
"""
import copy
import secrets
import math
from .computer_windows import ConfirmedService, ComputerError


class ComputerSettings(ConfirmedService):
    def __init__(self, provider=None, **kwargs):
        super().__init__(provider, **kwargs)
        self.undo_records = {}

    async def _dispatch(self, action, args):
        if action == 'list_targets':
            self._keys(args, {'kind'})
            self._kind(args['kind'])
            return await self._call('settings_list', **args)
        if action == 'get':
            self._keys(args, {'kind', 'target'})
            self._kind(args['kind'])
            self._target(args['target'])
            return await self._call('settings_get', **args)
        if action == 'set':
            self._keys(args, {'kind', 'target', 'value'})
            self._kind(args['kind'])
            self._target(args['target'])
            self._value(args['kind'], args['value'])
            before = await self._call('settings_get', kind=args['kind'], target=args['target'])
            if not before['ok']:
                return before
            request = dict(operation='set', **copy.deepcopy(args), before=before['state'])
            return self._prepare(request, request)
        if action == 'undo':
            self._keys(args, {'undo_id'})
            record = self.undo_records.get(args['undo_id'])
            if record is None:
                raise ComputerError('unknown_undo')
            current = await self._call('settings_get', kind=record['kind'], target=record['target'])
            if not current['ok']:
                return current
            if current['state'] != record['after']:
                raise ComputerError('stale_undo')
            request = dict(operation='undo', undo_id=args['undo_id'], kind=record['kind'],
                           target=record['target'], before=record['after'], value=record['before']['value'])
            return self._prepare(request, request)
        if action == 'execute_confirmed':
            self._keys(args, {'confirmation', 'request'})
            request = self._consume(args['confirmation'], args['request'])
            result = await self._call('settings_apply', kind=request['kind'], target=request['target'],
                                      expected=request['before'], value=request['value'])
            if result.get('ok') and result.get('verified'):
                if request['operation'] == 'undo':
                    self.undo_records.pop(request['undo_id'], None)
                else:
                    token = secrets.token_urlsafe(24)
                    if len(self.undo_records) >= 128:
                        self.undo_records.pop(next(iter(self.undo_records)))
                    self.undo_records[token] = dict(kind=request['kind'], target=request['target'],
                                                    before=request['before'], after=result['state'])
                    result['undo_id'] = token
            return result
        raise ComputerError('unsupported_action')

    @staticmethod
    def _target(target):
        if not isinstance(target, str) or not target or len(target) > 2048 or '\x00' in target:
            raise ComputerError('invalid_target')

    @staticmethod
    def _kind(kind):
        if kind not in ('brightness', 'window', 'mouse_speed', 'audio'):
            raise ComputerError('unsupported_setting')

    @staticmethod
    def _value(kind, value):
        if kind == 'audio':
            if (isinstance(value, dict) and set(value) == {'volume', 'mute'}
                    and type(value['mute']) is bool and type(value['volume']) in (int, float)
                    and math.isfinite(value['volume']) and 0 <= value['volume'] <= 1):
                return
            raise ComputerError('unsupported_or_invalid_value')
        valid = ((kind == 'brightness' and type(value) is int and 0 <= value <= 100)
                 or (kind == 'mouse_speed' and type(value) is int and 1 <= value <= 20)
                 or (kind == 'window' and value in ('normal', 'minimized', 'maximized')))
        if not valid:
            raise ComputerError('unsupported_or_invalid_value')
