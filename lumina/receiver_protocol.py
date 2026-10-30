"""Fixed cooperative fixture protocol, not a general application executor.

The caller owns the private pipe. Tokens do not authenticate a human or defend
against hostile code in either process. All admission/revocation/state changes
linearize under one receiver lock. Records never evict: capacity fails closed.
"""
import copy
import math
import re
import threading
import time

OPERATION = 'set_fixture_ready'
CONTEXT = {'owner', 'session', 'session_key', 'epoch', 'generation'}
PAYLOAD = CONTEXT | {'attempt', 'fixture', 'grant', 'scope', 'operation',
                     'expected_revision', 'expected_value', 'desired', 'expires'}


def opaque(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]{16,128}', value) is not None


class FixtureState:
    """Actual disposable application state; readback never consults receipts."""
    def __init__(self):
        self.value, self.revision = 'empty', 0

    def read(self):
        return {'value': self.value, 'revision': self.revision}

    def set_ready(self):
        self.value = 'ready'
        self.revision += 1


class Receiver:
    def __init__(self, fixture, *, clock=time.monotonic, capacity=128):
        if not opaque(fixture) or type(capacity) is not int or not 1 <= capacity <= 128:
            raise ValueError('invalid_receiver')
        self.fixture, self.clock, self.capacity = fixture, clock, capacity
        self.state = FixtureState()
        self.lock = threading.Lock()
        self.context = None
        self.revoked = False
        self.grants, self.records = {}, {}

    def _payload(self, p):
        if type(p) is not dict or set(p) != PAYLOAD:
            return False
        if not all(opaque(p[k]) for k in ('attempt','fixture','grant','owner','session_key','epoch')):
            return False
        return (type(p['session']) is str and 0 < len(p['session']) <= 128 and
                type(p['scope']) is str and re.fullmatch('[0-9a-f]{64}', p['scope']) is not None and
                type(p['generation']) is int and p['generation'] > 0 and
                type(p['expected_revision']) is int and 0 <= p['expected_revision'] < 128 and
                p['expected_value'] in ('empty','ready') and p['desired'] == 'ready' and
                p['operation'] == OPERATION and type(p['expires']) in (int,float) and math.isfinite(p['expires']))

    def handle(self, request):
        with self.lock:
            return copy.deepcopy(self._handle(request))

    def _handle(self, request):
        def denied(reason):
            return {'status':'rejected','reason':reason,'fixture':self.fixture}
        if type(request) is not dict or type(request.get('kind')) is not str:
            return denied('schema')
        kind = request['kind']
        if kind == 'open':
            if (set(request) != {'kind','fixture','context'} or request['fixture'] != self.fixture or
                    type(request['context']) is not dict or set(request['context']) != CONTEXT):
                return denied('schema')
            ctx = request['context']
            if (not all(opaque(ctx[k]) for k in ('owner','session_key','epoch')) or
                    type(ctx['session']) is not str or not 0 < len(ctx['session']) <= 128 or
                    type(ctx['generation']) is not int or ctx['generation'] <= 0):
                return denied('context')
            if self.context is not None or self.revoked:
                return denied('already_enrolled')
            self.context = copy.deepcopy(ctx)
            return {'status':'opened','fixture':self.fixture}
        if kind in ('read','revoke'):
            if set(request) != {'kind','fixture'} or request['fixture'] != self.fixture:
                return denied('schema')
            if kind == 'revoke':
                self.revoked = True
                self.grants.clear()
                return {'status':'revoked','fixture':self.fixture,'revision':self.state.revision}
            return {'status':'state','fixture':self.fixture,**self.state.read()}
        if kind == 'query':
            if set(request) != {'kind','fixture','attempt'} or request['fixture'] != self.fixture or not opaque(request['attempt']):
                return denied('schema')
            row = self.records.get(request['attempt'])
            return row['receipt'] if row else {'status':'absent','fixture':self.fixture,'attempt':request['attempt']}
        if kind not in ('authorize','apply') or set(request) != {'kind','payload'} or not self._payload(request['payload']):
            return denied('schema')
        p = request['payload']
        if p['fixture'] != self.fixture:
            return denied('fixture')
        existing = self.records.get(p['attempt'])
        if existing:
            if existing['payload'] != p:
                return denied('attempt_conflict')
            return {**existing['receipt'],'status':'already_processed'}
        if self.revoked or self.context is None:
            return denied('revoked_or_unenrolled')
        if {k:p[k] for k in CONTEXT} != self.context:
            return denied('context')
        if not self.clock() < p['expires'] <= self.clock()+5:
            return denied('expired')
        if kind == 'authorize':
            previous = self.grants.get(p['attempt'])
            if previous is not None and previous != p:
                return denied('attempt_conflict')
            if (len(self.records) >= self.capacity or
                    (self.grants and p['attempt'] not in self.grants)):
                return denied('capacity')
            self.grants[p['attempt']] = copy.deepcopy(p)
            return {'status':'authorized','fixture':self.fixture,'attempt':p['attempt']}
        # Exact grant validation, consumption, mutation and receipt are one lock
        # interval. A revoke acknowledgement cannot precede a later stale apply.
        if self.grants.get(p['attempt']) != p:
            return denied('grant')
        self.grants.pop(p['attempt'])
        before = self.state.read()
        matched = before == {'value':p['expected_value'],'revision':p['expected_revision']}
        if matched:
            self.state.set_ready()
        receipt = {'status':'applied' if matched else 'rejected',
                   'reason':'applied' if matched else 'revision',
                   'attempt':p['attempt'],'operation':OPERATION,'fixture':self.fixture,
                   'scope':p['scope'],'prior':before,'result':self.state.read()}
        self.records[p['attempt']] = {'payload':copy.deepcopy(p),'receipt':receipt}
        return receipt
