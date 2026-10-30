"""Fixed test-registered external Edit and counter buttons. No HTTP enrollment.

UIA discovery stays in the existing read-only helper. The fixed standard Edit
uses bounded WM_SETTEXT: direct COM ElementFromHandle did not finish within the
native validation deadline. This is not an automatic fallback to arbitrary
input. A browser token cannot register a process or arbitrary value.
"""
import asyncio
import concurrent.futures
import ctypes as c
from ctypes import wintypes as w
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
import re
import time

from .computer_action import ActionAdapter, TargetEvidence, ExecutionResult, Verification

INITIAL = 'Lumina external fixture initial'
EDITED = 'Lumina isolated external edit'


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class ExternalRegistration:
    pid: int
    window: int
    control: int
    nonce: str
    increment: int | None = None
    reset: int | None = None
    counter: int | None = None
    toggle: int | None = None
    toggle_decoy: int | None = None
    toggle_label: int | None = None


class ExternalWindowsAdapter(ActionAdapter):
    operations = ('set_external_fixture','increment_external_fixture','reset_external_fixture','toggle_external_fixture')

    def __init__(self, authority, observations, service, process, registration, *, clock=time.monotonic):
        if (type(registration) is not ExternalRegistration or
                process.pid != registration.pid or registration.pid == os.getpid() or process.returncode is not None or
                any(type(v) is not int or v <= 0 for v in (registration.pid, registration.window, registration.control)) or
                not re.fullmatch('[0-9a-f]{32}', registration.nonce) or
                service.authority is not authority):
            raise ValueError('invalid_external_registration')
        extra=(registration.increment,registration.reset,registration.counter)
        if any(v is not None for v in extra) and (
                any(type(v) is not int or v<=0 for v in extra) or
                len(set((*extra,registration.control,registration.window)))!=5):
            raise ValueError('invalid_fixture_buttons')
        extra_toggle=(registration.toggle,registration.toggle_decoy,registration.toggle_label)
        if any(v is not None for v in extra_toggle) and (
                any(type(v) is not int or v<=0 for v in extra_toggle) or
                len(set((*extra_toggle,registration.control,registration.window,*[v for v in extra if v is not None])))!=5+len([v for v in extra if v is not None])):
            raise ValueError('invalid_fixture_toggle')
        self.authority, self.observations, self.service = authority, observations, service
        self.process, self.registration, self.clock = process, registration, clock
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='Lumina-external-edit')
        self.pending, self.bindings, self.receipts = set(), {}, {}
        self.managed_jobs=set()
        self._active = {}
        self.target = None
        self.selected_hwnd=registration.control
        self.current_value=None
        self.window_id = self.control_id = None
        self.discovered_at = None
        self.birth = None
        self.closed = False
        authority.register_revoker(lambda reason: self.bindings.clear())

    async def _work(self, function):
        self.pending = {f for f in self.pending if not f.done()}
        if self.closed or len(self.pending) >= 8:
            raise PermissionError('external_unavailable')
        future = self.executor.submit(function)
        self.pending.add(future)
        awaited=asyncio.wrap_future(future)
        # The worker can reject a revoked grant after its awaiter was cancelled.
        # Retrieve that exception without claiming the worker was cancelled.
        awaited.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        try:
            # Cancellation of an awaiter never marks the native worker settled.
            return await asyncio.wait_for(asyncio.shield(awaited),5)
        finally:
            self.pending = {f for f in self.pending if not f.done()}

    @contextmanager
    def _native(self, authorization=None):
        """Re-query exact process/window/control before the bounded native call."""
        r = self.registration
        hwnd=self.selected_hwnd
        is_toggle=hwnd==r.toggle and hwnd is not None
        is_button=hwnd in (r.increment,r.reset) and hwnd is not None
        control_number=4500 if is_toggle else (4300 if hwnd==r.increment else 4301) if is_button else 4242
        expected_class='Button' if is_button or is_toggle else 'Edit'
        if hwnd not in (r.control,r.increment,r.reset,r.toggle) or hwnd is None:
            raise ValueError('external_unregistered_control')
        if self.process.returncode is not None:
            raise ValueError('external_process_exited')
        u, k = c.WinDLL('user32', use_last_error=True), c.WinDLL('kernel32', use_last_error=True)
        for name, args, result in (
            ('GetWindowThreadProcessId', [w.HWND,c.POINTER(w.DWORD)],w.DWORD),
            ('GetParent',[w.HWND],w.HWND), ('GetDlgCtrlID',[w.HWND],c.c_int),
            ('GetPropW',[w.HWND,w.LPCWSTR],w.HANDLE),
            ('GetWindowLongW',[w.HWND,c.c_int],w.LONG),
            ('IsWindowEnabled',[w.HWND],w.BOOL), ('IsWindowVisible',[w.HWND],w.BOOL),
            ('GetClassNameW',[w.HWND,w.LPWSTR,c.c_int],c.c_int),
            ('GetWindowRect',[w.HWND,c.POINTER(w.RECT)],w.BOOL),
            ('SendMessageTimeoutW',[w.HWND,w.UINT,w.WPARAM,w.LPARAM,w.UINT,w.UINT,c.POINTER(c.c_size_t)],c.c_ssize_t)):
            fn=getattr(u,name); fn.argtypes=args; fn.restype=result
        k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD]; k.OpenProcess.restype=w.HANDLE
        k.GetProcessTimes.argtypes=[w.HANDLE,*([c.POINTER(w.FILETIME)]*4)]
        k.CloseHandle.argtypes=[w.HANDLE]
        handle = k.OpenProcess(0x1000, False, r.pid)
        if not handle: raise ValueError('external_process_missing')
        try:
            times=[w.FILETIME() for _ in range(4)]
            if not k.GetProcessTimes(handle, *(c.byref(t) for t in times)):
                raise ValueError('external_process_identity')
            birth=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
            if self.birth is not None and self.birth != birth: raise ValueError('external_process_replaced')
            self.birth=birth
        finally:
            k.CloseHandle(handle)
        geometry=[]
        checks=[(r.window,'LuminaExternalFixture-'+r.nonce),(hwnd,expected_class)]
        if is_button:checks.append((r.counter,'Static'))
        if is_toggle:checks.extend(((r.toggle_decoy,'Button'),(r.toggle_label,'Static')))
        for checked, class_name in checks:
            pid=w.DWORD(); u.GetWindowThreadProcessId(checked,c.byref(pid))
            name=c.create_unicode_buffer(256); u.GetClassNameW(checked,name,len(name))
            rect=w.RECT()
            if pid.value != r.pid or name.value != class_name or not u.GetWindowRect(checked,c.byref(rect)):
                raise ValueError('external_identity_changed')
            geometry.append([rect.left,rect.top,rect.right,rect.bottom])
        if (u.GetParent(hwnd) != r.window or u.GetDlgCtrlID(hwnd) != control_number or
                u.GetPropW(hwnd,'LuminaM4RegisteredControl' if is_toggle else 'LuminaM3RegisteredControl' if is_button else 'LuminaM2RegisteredControl') !=
                int(r.nonce[:8],16)+(control_number if is_button or is_toggle else 0)):
            raise ValueError('external_parent_changed')
        if is_button and (u.GetParent(r.counter)!=r.window or u.GetDlgCtrlID(r.counter)!=4400 or
                u.GetPropW(r.counter,'LuminaM3RegisteredControl')!=int(r.nonce[:8],16)+4400):
            raise ValueError('external_counter_changed')
        if is_toggle:
            for checked,number in ((r.toggle_decoy,4501),(r.toggle_label,4502)):
                if (u.GetParent(checked)!=r.window or u.GetDlgCtrlID(checked)!=number or
                    u.GetPropW(checked,'LuminaM4RegisteredControl')!=int(r.nonce[:8],16)+number):
                    raise ValueError('external_toggle_identity_changed')
        style=u.GetWindowLongW(hwnd,-16)
        if ((not is_button and not is_toggle and style & (0x20|0x800)) or
                (is_button and style & 0xf != 0) or not u.IsWindowEnabled(hwnd) or
                (is_toggle and (style & 0xf != 3 or u.GetWindowLongW(r.toggle_decoy,-16)&0xf != 3)) or
                not u.IsWindowEnabled(r.window) or not u.IsWindowVisible(hwnd)):
            raise ValueError('external_control_unavailable')  # ES_PASSWORD / ES_READONLY
        def read():
            text=c.create_unicode_buffer(256); out=c.c_size_t()
            if not u.SendMessageTimeoutW(r.toggle_label if is_toggle else r.counter if is_button else hwnd,0xD,len(text),c.addressof(text),0x22,1000,c.byref(out)):
                raise TimeoutError('external_readback_timeout')
            if is_toggle:
                parts=self.toggle_parts(text.value)
                for checked,expected in ((hwnd,parts[0]),(r.toggle_decoy,0)):
                    state=c.c_size_t()
                    if not u.SendMessageTimeoutW(checked,0xF0,0,0,0x22,1000,c.byref(state)) or state.value!=expected:
                        raise ValueError('external_toggle_readback_mismatch')
            return text.value
        def set_value(value):
            if is_button or is_toggle:raise PermissionError('external_wrong_effect')
            buffer=c.create_unicode_buffer(value); out=c.c_size_t()
            self._admit_effect(authorization,target,value)
            # Separate process/queue, system message marshalling, no raw input.
            # Timeout cannot prove that the receiving process had no effect.
            if not u.SendMessageTimeoutW(hwnd,0xC,0,c.addressof(buffer),0x22,1000,c.byref(out)) or not out.value:
                raise TimeoutError('external_effect_unsettled')
        def click(value):
            if value is not None:raise PermissionError('external_wrong_effect')
            self._admit_effect(authorization,target,value)
            out=c.c_size_t()
            # BM_CLICK is fixed here; its LRESULT is not a success signal.
            if not u.SendMessageTimeoutW(hwnd,0xF5,0,0,0x22,1000,c.byref(out)):
                raise TimeoutError('external_effect_unsettled')
        value=read()
        if is_toggle:self.toggle_parts(value)
        elif is_button:self.counter_parts(value)
        elif value not in (INITIAL,EDITED): raise ValueError('external_precondition')
        revision=digest(json.dumps([birth,style,geometry,digest(value),r.nonce]))
        target=TargetEvidence(self.window_id,self.control_id,revision,0,foreground=False,
                              patterns=self.operations)
        # There is deliberately no native-message setter for the checkbox.
        yield target, value, read, click if is_button else set_value

    def _read(self):
        with self._native() as (target,value,read,set_value):
            return target, digest(value)

    async def refresh(self, window, control):
        result = await self.service.execute('inspect_control',window=window,control=control)
        if not result.get('ok'): raise ValueError('external_discovery_failed')
        rows=result.get('controls',[])
        if (len(rows)!=1 or result.get('window')!=window or
                not window.startswith(f'{self.registration.window}:{self.registration.pid}:')):
            raise ValueError('external_window_mismatch')
        row=rows[0]; hwnd=row.get('native_hwnd')
        is_button=hwnd in self.button_operations()
        is_toggle=hwnd==self.registration.toggle and hwnd is not None
        if (row.get('id')!=control or (hwnd!=self.registration.control and not is_button and not is_toggle) or
                row.get('process_id')!=self.registration.pid or row.get('role')!=('ControlType.CheckBox' if is_toggle else 'ControlType.Button' if is_button else 'ControlType.Edit') or
                row.get('class_name')!=('Button' if is_button or is_toggle else 'Edit') or ('Toggle' if is_toggle else 'Invoke' if is_button else 'Value') not in row.get('patterns',[]) or
                row.get('password') or not row.get('enabled') or row.get('readonly') or row.get('offscreen')):
            raise ValueError('external_control_mismatch')
        if is_toggle and (type(row.get('toggle')) is not int or row['toggle'] not in (0,1)):
            raise ValueError('external_toggle_state')
        self.window_id,self.control_id,self.selected_hwnd=window,control,hwnd
        def inspect():
            with self._native() as (target,value,_,__):return target,value
        self.target,self.current_value=await self._work(inspect)
        self.discovered_at=self.clock()
        if is_toggle and self.toggle_parts(self.current_value)[0]!=row['toggle']:
            raise ValueError('external_toggle_state_drift')
        return {'target':self.target,'digest':digest(self.current_value)}

    def button_operations(self):
        r=self.registration
        return {} if r.increment is None else {r.increment:'increment_external_fixture',r.reset:'reset_external_fixture'}

    @staticmethod
    def toggle_parts(value):
        if not isinstance(value,str) or not re.fullmatch(r'[01]:0:(0|[1-9][0-9]{0,5})',value):
            raise ValueError('external_toggle_precondition')
        return [int(part) for part in value.split(':')]

    def toggle_postcondition(self,value):
        state,_,revision=self.toggle_parts(value)
        return f'{1-state}:0:{revision+1}'

    @staticmethod
    def counter_parts(value):
        if not isinstance(value,str) or not re.fullmatch(r'(0|[1-9][0-9]{0,2}):0:(0|[1-9][0-9]{0,5})',value):
            raise ValueError('external_counter_precondition')
        return [int(part) for part in value.split(':')]

    def button_postcondition(self,operation,value):
        count,decoy,revision=self.counter_parts(value)
        if ((operation=='increment_external_fixture' and count!=0) or
                (operation=='reset_external_fixture' and count!=1) or
                operation not in self.button_operations().values()):
            raise ValueError('external_counter_precondition')
        return f'{1 if operation=="increment_external_fixture" else 0}:0:{revision+1}'

    def validate_proposal(self, operation, target, text, expected_digest):
        is_edit=operation=='set_external_fixture' and self.selected_hwnd==self.registration.control
        valid=(text in (INITIAL,EDITED) and expected_digest==digest(text)) if is_edit else (
            self.button_operations().get(self.selected_hwnd)==operation and text is None and
            expected_digest==digest(self.button_postcondition(operation,self.current_value)))
        if operation=='toggle_external_fixture':
            from .fixture_toggle import NATIVE_TOGGLE_READY
            if not NATIVE_TOGGLE_READY:raise PermissionError('native_toggle_not_validated')
            valid=(self.registration.toggle is not None and self.selected_hwnd==self.registration.toggle and text is None and
                   expected_digest==digest(self.toggle_postcondition(self.current_value)))
        if (not valid or target!=self.target or self.discovered_at is None or
                not 0 <= self.clock()-self.discovered_at < 15 or self.closed):
            raise ValueError('external_scope_invalid')

    def bind(self, action, lease, scope):
        self.authority.validate(lease)
        self.validate_proposal(action.operation,action.target,action.text,action.expected_digest)
        if digest(json.dumps(scope,sort_keys=True,separators=(',',':'),allow_nan=False))!=lease.digest:
            raise ValueError('external_scope_mismatch')
        observation=self.observations.latest()
        if observation is None or observation.session_id!=action.session_id:
            raise ValueError('external_session_invalid')
        evidence=self.observations.evidence(session_id=action.session_id,
                                            minimum_sequence=action.observation_sequence)
        # Keep the disabled Toggle transport's stricter existing contract.
        self.bindings[action.action_id]=(action,lease,observation if action.operation=='toggle_external_fixture' else evidence)

    async def revalidate(self, action):
        self.validate_proposal(action.operation,action.target,action.text,action.expected_digest)
        target,_=await self._work(self._read)
        return target

    async def dispatch(self, action, cancelled):
        if action.operation=='toggle_external_fixture':
            from .fixture_toggle import execute
            binding=self.bindings.pop(action.action_id,None)
            if binding is None or binding[0] is not action or action.action_id in self.receipts:
                return ExecutionResult('failed')
            authorization=(*binding,cancelled);self._active[action.action_id]=authorization
            try:
                await execute(self,authorization)
                _,value=await self._work(self._read)
                self.receipts[action.action_id]=value
                return ExecutionResult('complete')
            finally:self._active.pop(action.action_id,None)
        def mutate():
            binding=self.bindings.pop(action.action_id,None)
            if binding is None or binding[0] is not action or action.action_id in self.receipts:
                return ExecutionResult('failed')
            authorization=(*binding,cancelled)
            self._active[action.action_id]=authorization
            try:
                with self._native(authorization) as (target,value,read,set_value):
                    # The setter itself validates its one-shot authorization.
                    set_value(action.text)
                    self.receipts[action.action_id]=digest(read())
                    return ExecutionResult('complete')
            finally:
                self._active.pop(action.action_id,None)
        return await self._work(mutate)

    def _admit_effect(self, authorization, target, value, *, submit=True):
        if authorization is None:
            raise PermissionError('external_authorization_required')
        action,lease,evidence,cancelled=authorization
        if (self._active.get(action.action_id) is not authorization or
                action.action_id in self.receipts or value!=action.text):
            raise PermissionError('external_authorization_mismatch')
        self.authority.validate(lease)
        self.validate_proposal(action.operation,action.target,action.text,action.expected_digest)
        if action.operation=='toggle_external_fixture':
            origin=evidence.capture_not_before_monotonic
            fresh=(not evidence._revoked.is_set() and origin is not None and
                   0 <= time.monotonic()-origin < self.observations.freshness_seconds)
        else:
            fresh=evidence.valid(time.monotonic())
        if (cancelled.is_set() or target!=action.target or not fresh or
                self.clock()>=action.expires_at):
            raise PermissionError('external_target_or_session_changed')
        self.authority.validate(lease)
        if submit:self.receipts[action.action_id]='possibly_submitted'
        # No cancellation claim about a native call once this admission passed.

    async def verify(self, action, outcome):
        target,value=await self._work(self._read)
        matched=(target.window_id==action.target.window_id and target.control_id==action.target.control_id and
                 self.receipts.get(action.action_id)==value==action.expected_digest)
        return Verification(action.action_id,target.window_id,target.control_id,value,
                            'matched' if matched else 'inconclusive')

    async def cancel(self, action_id):
        self.bindings.pop(action_id,None)
        active=self._active.get(action_id)
        if active is not None: active[3].set()
        return all(f.done() for f in self.pending) and not self.managed_jobs and self.receipts.get(action_id)!='possibly_submitted'

    async def cleanup(self, action_id):
        return await self.cancel(action_id)

    async def close(self):
        self.closed=True
        self.bindings.clear()
        self.executor.shutdown(wait=False,cancel_futures=True)
        settled=all(f.done() for f in self.pending) and not self.managed_jobs and 'possibly_submitted' not in self.receipts.values()
        if not settled: self.authority.note_external_uncertainty()
        return {'ok':settled,'settled':settled}
