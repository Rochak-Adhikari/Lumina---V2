"""Snapshot-bound UIA control; trusted runtime owns permission and consequence review.

No coordinates, shortcuts, clipboard or raw shell. Private editable values are
represented only by per-provider HMAC; never return or log typed content.

invoke/type accept focus=False (strict original foreground/input state) or
focus=True (explicitly confirmed foreground activation of this exact window).
The latter permits GUI confirmation; provider refuses any control/geometry drift
and checks new user input during activation and immediately before the action.
An OS focus denial requires fresh inspection, not input-thread attachment.

ComputerControl(provider=None, clock=time.monotonic) exposes async execute:
 list_windows(), inspect(window), invoke(snapshot,control,focus=False),
 type(snapshot,control,text,focus=False), execute_confirmed(confirmation,request),
 cancel(confirmation), status(). Windows/controls are returned IDs, not titles.
The trusted caller must present original text through a private confirmation UI,
never log text arguments, and retain only the returned request in its audit log.
Cancel a running asyncio task to kill/reap the helper; cancel(confirmation) only
revokes a pending request. Native effects already submitted cannot be rolled back.
"""
import copy
import hashlib
import hmac
import secrets
from .computer_windows import ConfirmedService, ComputerError


class ComputerControl(ConfirmedService):
    def __init__(self, provider=None, **kwargs):
        super().__init__(provider, **kwargs)
        self.snapshots = {}
        self._text_key = secrets.token_bytes(32)

    async def _dispatch(self, action, args):
        if action == 'list_windows':
            self._keys(args, set())
            return await self._call('windows')
        if action == 'inspect':
            self._keys(args, {'window'})
            result = await self._call('inspect', **args)
            if result['ok']:
                token = secrets.token_urlsafe(24)
                self.snapshots = {k: v for k, v in self.snapshots.items() if self.clock() - v[0] < 60}
                if len(self.snapshots) >= 64:
                    self.snapshots.pop(next(iter(self.snapshots)))
                self.snapshots[token] = (self.clock(), copy.deepcopy(result))
                result['snapshot'] = token
            return result
        if action in ('invoke', 'type'):
            self._keys(args, {'snapshot', 'control'} | ({'text'} if action == 'type' else set()), {'focus'})
            focus = args.get('focus', False)
            if type(focus) is not bool:
                raise ComputerError('invalid_focus')
            item = self.snapshots.get(args['snapshot'])
            if item is None or self.clock() - item[0] >= 60:
                raise ComputerError('stale_snapshot')
            snapshot = item[1]
            matches = [c for c in snapshot['controls'] if c['id'] == args['control']]
            if len(matches) != 1:
                raise ComputerError('ambiguous_or_missing_control')
            control = matches[0]
            pattern = 'Invoke' if action == 'invoke' else 'Value'
            if pattern not in control['patterns'] or not control['enabled'] or control['password']:
                raise ComputerError('unsupported_control')
            private = dict(operation=action, window=snapshot['window'], expected=snapshot, focus=focus,
                           control=copy.deepcopy(control))
            public = dict(operation=action, snapshot=args['snapshot'], window=snapshot['window'], focus=focus,
                          control=copy.deepcopy(control), consequence='caller_must_review_exact_action')
            if action == 'type':
                text = args['text']
                if not isinstance(text, str) or len(text) > 8192 or '\x00' in text:
                    raise ComputerError('invalid_text')
                private['text'] = text
                public['text_length'] = len(text)
                public['text_binding'] = hmac.new(self._text_key, text.encode(), hashlib.sha256).hexdigest()
            return self._prepare(public, private)
        if action == 'execute_confirmed':
            self._keys(args, {'confirmation', 'request'})
            request = self._consume(args['confirmation'], args['request'])
            # Invalidate all snapshots before a possible mutation, including timeout.
            self.snapshots.clear()
            return await self._call('control_apply', **{k: v for k, v in request.items() if k != 'operation'},
                                    verb=request['operation'])
        raise ComputerError('unsupported_action')
