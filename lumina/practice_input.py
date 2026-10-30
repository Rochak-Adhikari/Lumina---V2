"""Explicit two-window P2.2 fixture only. No HTTP/model/default registration.

Uses the existing owned-window thread, observation stream and control authority.
This module is import-safe; Win32 loads only after trusted fixture creation.
"""
import asyncio
import ctypes
from ctypes import wintypes as w
from dataclasses import dataclass, replace, asdict
import math
import hashlib
import io
import json
import os
import secrets
import time

from .computer_action import ActionAdapter, TargetEvidence, ObservationRef, Verification, Focus, Text, Key, Chord, Click, Scroll, Move, SafeError
from .computer_geometry import TargetSnapshot, WindowIdentity, validate_target, validate_observation, to_absolute
from .computer_windows import ComputerError
from .observations import ObservationStream, DesktopTransform
from .owned_windows import OwnedWindowsAdapter
from .windows_input import _InputFacade, SubmissionReceipt, input_plan

TEXTS = ('LUMINA P2.2', 'synthetic 123', 'Unicode test: Ω 😀')
KEYS = ('Tab','Enter','Space','Backspace','Home','End','ArrowLeft','ArrowRight')
CHORDS = (('Control','A'), ('Shift','ArrowRight'))
START_DEADLINE = 1793285891.0  # 2026-10-29 14:58:11 UTC; this development approval only.


@dataclass(frozen=True)
class PracticeAuthorization:
    """Trusted local harness scope, never model/HTTP approval or an HWND grant.

    The reviewed runner binds this to the owner's record, hashes and exclusive
    consumed-run file before constructing Runtime. This object grants no right
    to reuse that record; it is not authentication against hostile Python.
    """
    run_id: str
    issued_at: float
    expires_at: float
    diagnostic_only: bool = False

    def validate(self):
        if (type(self.diagnostic_only) is not bool or type(self.run_id) is not str or len(self.run_id)!=32 or
            any(c not in '0123456789abcdef' for c in self.run_id) or
            any(type(v) not in (int,float) or not math.isfinite(v)
                for v in (self.issued_at,self.expires_at)) or
            not 0 < self.expires_at-self.issued_at <= 86400 or
            not self.issued_at <= time.time() < self.expires_at):
            raise PermissionError('practice_authorization_expired_or_invalid')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class PracticeWindow(OwnedWindowsAdapter):
    def __init__(self, session, index):
        super().__init__(session.authority, ObservationStream(), arm=lambda: None)
        self.session, self._practice_index = session, index
        self.practice_clicks = 0
        self.stream = self.observations
        self.stream.start(secrets.token_hex(16))
        self.seq = 0
        self.native_api = None
        self.release_events = {}

    def _prepare_practice(self, u):
        # Construction only, before arming. Same owned fixture, not an input fallback.
        u.SetWindowPos.argtypes = [w.HWND,w.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.UINT]
        offset=min(650,max(0,int(u.GetSystemMetrics(0))-680))
        u.SetWindowPos(self.hwnd, None, 40 + self._practice_index * offset, 100, 640, 520, 0x14)
        u.SetWindowTextW(self.hwnd, 'LUMINA P2.2 practice ' + self.identity)
        u.SetWindowTextW(self.clear_control, 'Practice counter')
        kernel = ctypes.WinDLL('kernel32')
        kernel.GetModuleHandleW.argtypes, kernel.GetModuleHandleW.restype = [w.LPCWSTR], w.HMODULE
        instance = kernel.GetModuleHandleW(None)
        self.word = u.CreateWindowExW(0,'EDIT','LUMINA',0x50000000,250,270,65,32,self.hwnd,101,instance,None)
        self.rows = u.CreateWindowExW(0,'EDIT','\r\n'.join(f'P2.2 row {i:02}' for i in range(1,41)),
            0x50A01844,16,310,600,120,self.hwnd,102,instance,None)
        if not self.word or not self.rows: raise OSError('practice_controls_failed')
        self.native_api = WinInput(self)
        self.native_api.observe_controls()

    def bounds(self, handle=None):
        rect=w.RECT()
        if not self.user.GetWindowRect(handle or self.hwnd,ctypes.byref(rect)):
            raise ComputerError('target_lost')
        return (rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top)

    def point(self, control):
        b=self.bounds(getattr(self,control)); root=self.bounds()
        return ((b[0]+b[2]//2-root[0])/root[2],(b[1]+b[3]//2-root[1])/root[3])

    def snapshot(self, obs):
        self.native_api.identity_check()
        b=self.bounds(); api=self.native_api
        evidence=TargetEvidence(str(self.hwnd),self.identity,digest(b),0,
            foreground=self.user.GetForegroundWindow()==self.hwnd,
            enabled=bool(self.user.IsWindowEnabled(self.hwnd)),patterns=('owned_input',))
        return TargetSnapshot(evidence,api.identity,ObservationRef(obs.session_id,obs.source_id,obs.sequence),
            b,api.virtual_bounds(),digest(b),digest(api.virtual_bounds()),str(api.monitor()),
            (float(api.dpi()),float(api.dpi())),visible=bool(self.user.IsWindowVisible(self.hwnd)) and not self.user.IsIconic(self.hwnd))

    async def capture(self):
        # Reuse the existing target-only renderer and stream. No second loop.
        from .screen_capture_worker import render_window
        from PIL import Image
        origin=time.monotonic()
        def render():
            self.native_api.identity_check()
            b=self.bounds()
            shot=render_window(f'{self.hwnd}:{os.getpid()}',dict(zip(('left','top','width','height'),b)))
            if self.bounds()!=b: raise ComputerError('geometry_changed')
            with Image.frombytes('RGB',shot.size,shot.rgb) as img, io.BytesIO() as output:
                if all(high==0 for low,high in img.getextrema()):
                    raise ComputerError('practice_capture_unavailable')
                img.save(output,format='JPEG',quality=85)
                return b,output.getvalue()
        b,image=await self._call(render)
        self.seq+=1
        return self.stream.publish(image,session_id=self.stream.session_id,source_id=self.identity,
            source_type='window',sequence=self.seq,captured_at=None,received_at='native-practice',
            received_monotonic=time.monotonic(),capture_not_before_monotonic=origin,timing_basis='native_request',
            original_dimensions=b[2:],processed_dimensions=b[2:],desktop=DesktopTransform(*b,1.,1.))

    async def readback(self):
        def read():
            self.native_api.identity_check()
            buf=ctypes.create_unicode_buffer(2049)
            self.user.GetWindowTextW(self.control,buf,len(buf))
            start,end,length=self._selection()
            ws,we=w.DWORD(),w.DWORD()
            self.user.SendMessageW(self.word,0xB0,ctypes.addressof(ws),ctypes.addressof(we))
            return dict(text=buf.value,selection=[start,end],word_selection=[ws.value,we.value],clicks=self.practice_clicks,
                row=int(self.user.SendMessageW(self.rows,0x00CE,0,0)),
                foreground=self.user.GetForegroundWindow()==self.hwnd,
                focus=int(self.native_api.u.GetFocus() or 0),pointer=self.native_api.pointer())
        return await self._call(read)


class PracticeSession:
    """One Runtime-owned approval scope. Reuses authority; no automatic rearm."""
    def __init__(self, runtime, principal):
        self.authorization = principal if type(principal) is PracticeAuthorization else None
        if self.authorization is not None:
            self.authorization.validate()
        elif type(principal) is not object or time.time()>=START_DEADLINE:
            raise PermissionError('practice_authorization_expired')
        self.runtime,self.principal,self.authority=runtime,principal,runtime.control_authority
        self.windows=[]; self.started=None; self.admissions=0; self.revoked=False
        self.pending=set(); self.adapters=[]; self.closed=False; self.focus_hwnd=None
        self.diagnostic_step=0
        self.authority.register_revoker(self.revoke)

    def revoke(self,reason=None): self.revoked=True

    def check(self, *, cleanup=False):
        if self.started is None or time.monotonic()-self.started>=900:
            raise PermissionError('practice_expired')
        if not cleanup:
            if self.authorization is not None: self.authorization.validate()
            self.authority.check()
            if self.revoked or self.admissions>=96: raise PermissionError('practice_revoked_or_budget')
        elif self.admissions>=100: raise PermissionError('practice_cleanup_budget')

    def count(self, *, cleanup=False):
        self.check(cleanup=cleanup); self.admissions+=1

    @property
    def diagnostic_only(self):
        return self.authorization is not None and self.authorization.diagnostic_only

    def claim_diagnostic_action(self, window, action):
        """One prefix, consumed before the API call; exceptions cannot replay it."""
        if not self.diagnostic_only: return
        step=self.diagnostic_step
        valid=(step<2 and type(action) is Focus and window is self.windows[step] and
               action.window==str(window.hwnd) or
               step==2 and type(action) is Move and window is self.windows[1])
        if not valid: raise ComputerError('diagnostic_prefix_exhausted_or_out_of_order')
        self.diagnostic_step+=1

    def controller(self, window, principal):
        if principal is not self.principal or window not in self.windows:
            raise PermissionError('practice_owner_required')
        if any(a.window is window for a in self.adapters):
            raise PermissionError('practice_controller_already_created')
        from .computer_control import IsolatedComputerControl
        return IsolatedComputerControl(window.stream,NativePracticeAdapter(self,window),
            authority=self.authority,owner='p2.2-'+window.identity)

    async def open(self, principal):
        if self.authorization is not None: self.authorization.validate()
        if (principal is not self.principal or self.started is not None or
                self.authorization is None and time.time()>=START_DEADLINE):
            raise PermissionError('practice_creation_denied')
        WinInput.preflight_desktop()
        WinInput.preflight_token()
        self.started=time.monotonic()
        from .screen_capture_worker import enable_dpi
        enable_dpi()  # Dedicated disposable test process only, before any HWND.
        # No automatic authority resume. Caller is the trusted owner harness.
        self.authority.check()
        for i in range(2):
            WinInput.preflight_desktop()
            self.count()
            win=PracticeWindow(self,i); self.windows.append(win)
            owner='p2.2-practice-owner'; scope=digest([win.identity,i])
            lease=self.authority.issue('create-'+win.identity,owner,scope)
            self.authority.begin(lease,owner,scope,operation_class='native_fixture_creation')
            try:
                self.authority.submitting(lease)
                await win.open()
                self.authority.validate(lease)
                win.native_api.identity_check()
                self.authority.finish(lease,settled=True,cleanup=True,outcome='complete',semantic='verified_success')
            except BaseException:
                self.authority.finish(lease,settled=False,cleanup=False,outcome='unknown')
                raise
        return self.windows

    async def close(self):
        if self.closed: return True
        self.authority.stop()
        for adapter in self.adapters:
            executor=adapter._executor
            if executor.active or any(not f.done() for f in adapter.window.pending): return False
            if (executor.held or executor.touched) and not await executor.cleanup('shutdown'): return False
        results=[]
        for win in self.windows:
            results.append(await win.close())
            win.stream.stop()
        self.closed=all(r.get('settled') for r in results)
        return self.closed


class NativePracticeAdapter(_InputFacade, ActionAdapter):
    operation='owned_input'
    def __init__(self, session, window):
        if type(session) is not PracticeSession or type(window) is not PracticeWindow or window not in session.windows:
            raise TypeError('owned_practice_required')
        self.session,self.window=session,window
        self.authority,self.observations=session.authority,window.stream
        self._controller=None; self._receipts={}; self._executor=PracticeExecutor(self)
        self.lease=None; self.expected={}
        session.adapters.append(self)

    def bind(self, action, lease, scope):
        self.authority.validate(lease); self.lease=lease

    def validate_proposal(self, proposal, target):
        self.session.check()
        if target.control_id != self.window.identity or target.window_id != str(self.window.hwnd):
            raise ComputerError('practice_target_denied')
        a=proposal.action
        if self.session.diagnostic_only and type(a) not in (Focus,Move):
            raise ComputerError('diagnostic_operation_denied')
        allowed=(type(a) is Focus and a.window==target.window_id or type(a) is Move or
            type(a) is Click and a.button=='left' and a.count in (1,2) or
            type(a) is Scroll and a.axis=='vertical' and abs(a.amount)<=3 or
            type(a) is Text and a.text in TEXTS or type(a) is Key and a.key in KEYS or
            type(a) is Chord and a.keys in CHORDS)
        if not allowed: raise ComputerError('practice_operation_denied')

    def validate_after(self, action, binding):
        self.session.check()
        obs=self.observations.latest()
        if obs is None or obs.source_id!=binding.inference.reference.source_id:
            raise ComputerError('practice_observation_lost')
        now=self.window.snapshot(obs)
        expected=binding.target
        if type(action.desktop.action) is Focus:
            expected=replace(expected,evidence=replace(expected.evidence,foreground=True))
        if isinstance(validate_target(expected,now),SafeError):
            self.authority.stop()
            raise ComputerError('practice_target_changed')
        if isinstance(validate_observation(obs,now,time.monotonic()),SafeError):
            self.authority.stop()
            raise ComputerError('practice_observation_lost')


class PracticeExecutor:
    available=True
    def __init__(self, adapter):
        self.adapter=adapter; self.held=set(); self.touched=(); self.active=False
        self.release_attempted=False; self.release_baseline={}
        self.move_diagnostics=None

    def check_ready(self):
        self.adapter.session.check()
        if self.active or self.held: raise ComputerError('practice_cleanup_unresolved')
        self.adapter.window.native_api.check_modifiers()

    def grounding_snapshot(self, obs): return self.adapter.window.snapshot(obs)
    async def revalidate(self, action): return self.grounding_snapshot(self.adapter.observations.latest()).evidence

    async def submit(self, request, cancelled):
        self.move_diagnostics=None
        a=self.adapter; win=a.window; api=win.native_api
        diagnostic=a.session.diagnostic_only and type(request.action.desktop.action) is Move
        if diagnostic:
            binding=request.binding
            predicate=a.expected.get(request.action.expected_digest)
            self.move_diagnostics=dict(action_id=request.action.action_id,
                expected_pointer=list(predicate['pointer']) if predicate and 'pointer' in predicate else None,
                last_observed_pointer=None,samples=0,matched=False,submission=None,
                stage='prechecks',submission_status='not_entered',sample_trace=[],
                requested_normalized=list(request.action.desktop.action.point),
                observation=asdict(binding.current.reference),
                geometry=dict(transform=asdict(binding.current.desktop),
                    frame_size=list(binding.current.frame_size),
                    capture_start=binding.current.origin,received=binding.current.received,
                    target=asdict(binding.target)))
        a.validate_proposal(request.action.desktop,request.action.target)
        events=input_plan(request)
        # Runtime owns pending native work through existing owned receiver queue.
        def send():
            self.check_ready(); a.authority.validate(a.lease)
            if cancelled.is_set(): return SubmissionReceipt('not_submitted')
            current=win.snapshot(a.observations.latest())
            focus=type(request.action.desktop.action) is Focus
            if isinstance(validate_target(request.binding.target,current,allow_unfocused=focus),SafeError):
                raise ComputerError('practice_target_changed')
            api.validate_events(events,request.action.desktop.action)
            a.session.count()
            self.active=True
            self.touched=tuple(dict.fromkeys(e.value for e in events if e.kind=='down')); self.held=set(self.touched)
            self.release_baseline=dict(getattr(win,'release_events',{})); self.release_attempted=False
            try:
                a.authority.validate(a.lease)
                if cancelled.is_set():
                    self.held.clear(); self.touched=()
                    return SubmissionReceipt('not_submitted')
                a.session.claim_diagnostic_action(win,request.action.desktop.action)
                if diagnostic:
                    api.last_move_submission=None
                    self.move_diagnostics.update(stage='submission',submission_status='return_unavailable')
                try:
                    count=api.submit(events)
                except BaseException:
                    if diagnostic:self.move_diagnostics['submission_status']='exception_return_unavailable'
                    raise
                else:
                    if diagnostic:self.move_diagnostics['submission_status']='acknowledged' if count==len(events) else 'not_fully_acknowledged'
                finally:
                    if diagnostic:
                        import copy
                        self.move_diagnostics['submission']=copy.deepcopy(getattr(api,'last_move_submission',None))
                if focus and count==len(events): a.session.focus_hwnd=win.hwnd
                # Windows reports count, not an independently proven prefix.
                if count==len(events): self.held.clear()
                return SubmissionReceipt('submitted' if count==len(events) else 'unknown',count)
            finally: self.active=False
        return await win._call(send)

    async def verify(self, action, outcome):
        a=self.adapter
        predicate=a.expected.get(action.expected_digest)
        # Bounded numeric evidence from the actual verifier samples, not a
        # later cursor query. No text/readback dictionary or screenshot retained.
        diagnostic=a.session.diagnostic_only and type(action.desktop.action) is Move
        if not diagnostic:self.move_diagnostics=None
        if diagnostic:
            if self.move_diagnostics is None or self.move_diagnostics['action_id']!=action.action_id:
                raise ComputerError('diagnostic_action_mismatch')
            self.move_diagnostics['stage']='verification'
        elif type(action.desktop.action) is Move:
            import copy
            self.move_diagnostics={'action_id':action.action_id,
                'expected_pointer':list(predicate['pointer']) if predicate and 'pointer' in predicate else None,
                'last_observed_pointer':None,'samples':0,'matched':False,
                'submission':copy.deepcopy(getattr(a.window.native_api,'last_move_submission',None))}
        matched=False
        started=time.monotonic()
        for _ in range(20):
            await asyncio.sleep(.025)
            a.session.check()
            try:
                state=await a.window.readback()
            except BaseException:
                if diagnostic:
                    self.move_diagnostics['sample_trace'].append(dict(
                        elapsed=time.monotonic()-started,available=False,pointer=None))
                    self.move_diagnostics['stage']='readback_unavailable'
                raise
            matched=predicate is not None and digest(predicate)==action.expected_digest and all(
                (state.get('row',-1)>v if k=='row_greater_than' else state.get(k)==v) for k,v in predicate.items())
            if self.move_diagnostics is not None:
                pointer=state.get('pointer')
                self.move_diagnostics.update(samples=self.move_diagnostics['samples']+1,matched=matched,
                    last_observed_pointer=list(pointer) if type(pointer) in (list,tuple) and len(pointer)==2
                        and all(type(v) is int for v in pointer) else None)
                if diagnostic:
                    self.move_diagnostics['sample_trace'].append(dict(elapsed=time.monotonic()-started,
                        available=self.move_diagnostics['last_observed_pointer'] is not None,
                        pointer=self.move_diagnostics['last_observed_pointer']))
            if matched: break
        await a.window.capture()
        if diagnostic:self.move_diagnostics['stage']='verified' if matched else 'verification_failed'
        return Verification(action.action_id,action.target.window_id,action.target.control_id,
            action.expected_digest if matched else digest(state),'matched' if matched else 'inconclusive')

    async def cancel(self, action_id):
        return not self.active and all(f.done() for f in self.adapter.window.pending)

    async def cleanup(self, action_id):
        a=self.adapter; win=a.window
        if self.active or any(not f.done() for f in win.pending): return False
        def release():
            api=win.native_api
            api.identity_check()
            if api.u.GetForegroundWindow()!=win.hwnd: return False
            if self.held:
                if self.release_attempted: return False
                # Unknown Unicode prefix cannot be safely reconstructed/replayed.
                if any(t[0]=='unicode' for t in self.held): return False
                if any(api.u.GetAsyncKeyState(k)&0x8000 for k in (16,17,18,91,92)
                       if ('key', {16:'Shift',17:'Control',18:'Alt',91:'Win',92:'Win'}[k]) not in self.held):
                    return False
                a.session.count(cleanup=True)
                from .windows_input import InputEvent
                self.release_attempted=True
                api.submit(tuple(InputEvent('up',t) for t in reversed(self.touched) if t in self.held))
            if not api.released(self.touched): return False
            if not api.release_observed(self.touched,self.release_baseline): return False
            self.held.clear(); self.touched=(); return True
        return await win._call(release)


class WinInput:
    """Fixed API surface bound to a freshly created owned fixture only."""
    @staticmethod
    def preflight_token():
        """Non-elevated token required before even allocating the first HWND."""
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        a=ctypes.WinDLL('advapi32',use_last_error=True)
        k.GetCurrentProcess.restype=w.HANDLE
        k.CloseHandle.argtypes,k.CloseHandle.restype=[w.HANDLE],w.BOOL
        a.OpenProcessToken.argtypes=[w.HANDLE,w.DWORD,ctypes.POINTER(w.HANDLE)]
        a.GetTokenInformation.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD)]
        token=w.HANDLE();elevation=w.DWORD();needed=w.DWORD()
        if not a.OpenProcessToken(k.GetCurrentProcess(),8,ctypes.byref(token)):
            raise PermissionError('practice_token_unavailable')
        try:
            if not a.GetTokenInformation(token,20,ctypes.byref(elevation),ctypes.sizeof(elevation),ctypes.byref(needed)) or elevation.value:
                raise PermissionError('elevated_practice_denied')
        finally:
            if not k.CloseHandle(token): raise PermissionError('practice_token_close_failed')

    @staticmethod
    def preflight_desktop():
        """Read-only check before allocating windows; never switches desktops."""
        probe=object.__new__(WinInput)
        probe.u=ctypes.WinDLL('user32',use_last_error=True)
        u=probe.u; k=ctypes.WinDLL('kernel32')
        k.GetCurrentThreadId.restype=w.DWORD
        u.GetThreadDesktop.argtypes,u.GetThreadDesktop.restype=[w.DWORD],w.HANDLE
        u.OpenInputDesktop.argtypes,u.OpenInputDesktop.restype=[w.DWORD,w.BOOL,w.DWORD],w.HANDLE
        u.GetUserObjectInformationW.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD)]
        u.CloseDesktop.argtypes=[w.HANDLE]
        handle=u.OpenInputDesktop(0,False,1)
        try:
            thread=probe.desktop(u.GetThreadDesktop(k.GetCurrentThreadId()))
            active=probe.desktop(handle)
            if thread!=active:
                raise PermissionError('practice_input_desktop_unavailable')
            return {'thread_desktop':thread,'input_desktop':active,'desktops_match':True}
        finally:
            if handle:u.CloseDesktop(handle)

    def __init__(self, window):
        self.window=window; self.u=window.user
        u=self.u; k=ctypes.WinDLL('kernel32',use_last_error=True)
        signatures={'SetForegroundWindow':([w.HWND],w.BOOL),'GetFocus':([],w.HWND),
            'IsWindowVisible':([w.HWND],w.BOOL),'IsIconic':([w.HWND],w.BOOL),
            'GetAsyncKeyState':([ctypes.c_int],ctypes.c_short),
            'GetCursorPos':([ctypes.POINTER(w.POINT)],w.BOOL),
            'WindowFromPoint':([w.POINT],w.HWND),
            'GetDpiForWindow':([w.HWND],w.UINT),'MonitorFromWindow':([w.HWND,w.DWORD],w.HANDLE),
            'GetClassNameW':([w.HWND,w.LPWSTR,ctypes.c_int],ctypes.c_int)}
        for name,(args,ret) in signatures.items():getattr(u,name).argtypes,getattr(u,name).restype=args,ret
        k.GetCurrentProcess.restype=w.HANDLE
        k.GetProcessTimes.argtypes=[w.HANDLE,*([ctypes.POINTER(w.FILETIME)]*4)]
        times=[w.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(k.GetCurrentProcess(),*[ctypes.byref(t) for t in times]):raise OSError('creation_identity_unavailable')
        creation=str(times[0].dwHighDateTime<<32|times[0].dwLowDateTime)
        self.identity=WindowIdentity(window.hwnd,os.getpid(),creation,'LuminaOwned-'+window.identity,window.identity,'owned-thread-'+str(window.thread_id))
        u.GetThreadDesktop.argtypes,u.GetThreadDesktop.restype=[w.DWORD],w.HANDLE
        u.OpenInputDesktop.argtypes,u.OpenInputDesktop.restype=[w.DWORD,w.BOOL,w.DWORD],w.HANDLE
        u.GetUserObjectInformationW.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD)]
        u.CloseDesktop.argtypes=[w.HANDLE]
        self.desktop_name=self.desktop(u.GetThreadDesktop(window.thread_id))
        self.identity=replace(self.identity,desktop_id=self.desktop_name)
        adv=ctypes.WinDLL('advapi32',use_last_error=True)
        adv.OpenProcessToken.argtypes=[w.HANDLE,w.DWORD,ctypes.POINTER(w.HANDLE)]
        adv.GetTokenInformation.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD)]
        token=w.HANDLE(); elevation=w.DWORD(); needed=w.DWORD()
        if not adv.OpenProcessToken(k.GetCurrentProcess(),8,ctypes.byref(token)):raise OSError('token_unavailable')
        k.CloseHandle.argtypes=[w.HANDLE]
        try:
            if not adv.GetTokenInformation(token,20,ctypes.byref(elevation),4,ctypes.byref(needed)) or elevation.value:
                raise PermissionError('elevated_practice_denied')
        finally:k.CloseHandle(token)

    def desktop(self, handle):
        buf=ctypes.create_unicode_buffer(256); needed=w.DWORD()
        if not handle or not self.u.GetUserObjectInformationW(handle,2,buf,ctypes.sizeof(buf),ctypes.byref(needed)):
            raise ComputerError('desktop_unavailable')
        return buf.value

    def observe_controls(self):
        """Owned control events supplement OS readback; no global hook."""
        lib=ctypes.WinDLL('comctl32',use_last_error=True)
        callback=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,w.HWND,w.UINT,w.WPARAM,w.LPARAM,ctypes.c_size_t,ctypes.c_size_t)
        lib.DefSubclassProc.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
        lib.DefSubclassProc.restype=ctypes.c_ssize_t
        lib.SetWindowSubclass.argtypes=[w.HWND,callback,ctypes.c_size_t,ctypes.c_size_t]
        lib.SetWindowSubclass.restype=w.BOOL
        @callback
        def observe(hwnd,msg,wp,lp,identity,data):
            if msg in (0x101,0x105,0x202):
                key=1 if msg==0x202 else int(wp)
                counts=self.window.release_events
                counts[key]=counts.get(key,0)+1
            return lib.DefSubclassProc(hwnd,msg,wp,lp)
        self._subclass=observe; self._subclass_lib=lib
        for hwnd in (self.window.control,self.window.clear_control,self.window.word,self.window.rows):
            if not lib.SetWindowSubclass(hwnd,observe,1,0):raise OSError('practice_observer_failed')

    def release_observed(self,tokens,baseline):
        keys={0xE7 if t[0]=='unicode' else self.vk(t) for t in tokens}
        return all(self.window.release_events.get(k,0)>baseline.get(k,0) for k in keys)

    def identity_check(self):
        win=self.window; pid=w.DWORD(); buf=ctypes.create_unicode_buffer(256)
        tid=self.u.GetWindowThreadProcessId(win.hwnd,ctypes.byref(pid))
        self.u.GetClassNameW(win.hwnd,buf,len(buf))
        desktop=self.u.OpenInputDesktop(0,False,1)
        try:
            if self.desktop(desktop)!=self.desktop_name: raise ComputerError('desktop_changed')
        finally:
            if desktop:self.u.CloseDesktop(desktop)
        if (win.closed.is_set() or not self.u.IsWindow(win.hwnd) or pid.value!=os.getpid() or
                tid!=win.thread_id or buf.value!=self.identity.class_name):raise ComputerError('practice_identity_lost')
        for child in (win.control,win.clear_control,win.word,win.rows):
            if not self.u.IsWindow(child) or self.u.GetParent(child)!=win.hwnd:
                raise ComputerError('practice_child_lost')

    def virtual_bounds(self): return tuple(int(self.u.GetSystemMetrics(i)) for i in (76,77,78,79))
    def dpi(self): return self.u.GetDpiForWindow(self.window.hwnd)
    def monitor(self): return self.u.MonitorFromWindow(self.window.hwnd,0)
    def pointer(self):
        p=w.POINT()
        if not self.u.GetCursorPos(ctypes.byref(p)): raise ComputerError('pointer_unavailable')
        return [p.x,p.y]

    def diagnostic_environment(self):
        """Read-only pre-submission metadata, never a clip/DPI mutation.

        GetClipCursor uses screen coordinates; retain the thread DPI awareness
        alongside it, rather than assuming the result proves physical mapping.
        Errors are availability facts, not permission to alter the desktop.
        """
        result={'coordinate_space':'win32_screen_coordinates',
                'clip_status':'unavailable','clip_rect':None,'dpi_awareness':None}
        try:
            clip=self.u.GetClipCursor
            clip.argtypes=[ctypes.POINTER(w.RECT)];clip.restype=w.BOOL
            rect=w.RECT()
            if clip(ctypes.byref(rect)):
                result.update(clip_status='available',clip_rect=[rect.left,rect.top,rect.right,rect.bottom])
        except (AttributeError,OSError): pass
        try:
            context=self.u.GetThreadDpiAwarenessContext
            context.argtypes=[];context.restype=ctypes.c_void_p
            awareness=self.u.GetAwarenessFromDpiAwarenessContext
            awareness.argtypes=[ctypes.c_void_p];awareness.restype=ctypes.c_int
            value=int(awareness(context()))
            if value in (0,1,2):result['dpi_awareness']=value
        except (AttributeError,OSError): pass
        return result

    def check_modifiers(self):
        expected=self.window.session.focus_hwnd
        if expected is not None and self.u.GetForegroundWindow()!=expected:
            self.window.session.revoke('focus_lost')
            self.window.authority.request_stop()
            raise ComputerError('practice_focus_lost')
        if any(self.u.GetAsyncKeyState(k)&0x8000 for k in (1,2,4,16,17,18,91,92)):
            self.window.session.revoke('physical_modifier_conflict')
            self.window.authority.request_stop()
            raise ComputerError('physical_modifier_conflict')

    def validate_events(self, events, action):
        self.identity_check(); self.check_modifiers()
        win=self.window
        if type(action) is Focus: return
        if self.u.GetForegroundWindow()!=win.hwnd: raise ComputerError('practice_focus_lost')
        if type(action) in (Text,Key,Chord) and self.u.GetFocus()!=win.control:
            raise ComputerError('practice_edit_focus_required')
        for e in events:
            if e.kind=='move':
                hit=self.u.WindowFromPoint(w.POINT(*e.value))
                allowed=(win.control,win.clear_control,win.word,win.rows)
                if hit not in allowed:raise ComputerError('practice_hit_test_failed')
                if type(action) is Click and (action.count==2 and hit!=win.word or action.count==1 and hit not in (win.control,win.clear_control)):
                    raise ComputerError('practice_click_target_denied')
                if type(action) is Scroll and hit!=win.rows:raise ComputerError('practice_scroll_target_denied')

    def released(self, touched):
        return not any(self.u.GetAsyncKeyState(self.vk(t))&0x8000 for t in touched if t[0]!='unicode') and not (self.u.GetAsyncKeyState(0xE7)&0x8000)

    @staticmethod
    def vk(token):
        kind,key=token
        if kind=='button': return {'left':1}[key]
        return {'Tab':9,'Enter':13,'Space':32,'Backspace':8,'Home':36,'End':35,
            'ArrowLeft':37,'ArrowRight':39,'Control':17,'Shift':16,'A':65}[key]

    def submit(self, events):
        self.last_move_submission=None
        if len(events)==1 and events[0].kind=='focus':
            # C17: one ordinary request, no foreground-lock bypass or retry.
            # Both API acknowledgement and independent foreground readback
            # must agree; refusal/drift revokes the entire practice session.
            self.identity_check(); self.check_modifiers()
            accepted=bool(self.u.SetForegroundWindow(self.window.hwnd))
            matched=self.u.GetForegroundWindow()==self.window.hwnd
            if not accepted or not matched:
                self.window.session.revoke('focus_refused_or_drifted')
                self.window.authority.request_stop()
                return 0
            return 1
        class M(ctypes.Structure):
            _fields_=[('dx',w.LONG),('dy',w.LONG),('data',w.DWORD),('flags',w.DWORD),('time',w.DWORD),('extra',ctypes.c_size_t)]
        class K(ctypes.Structure):
            _fields_=[('vk',w.WORD),('scan',w.WORD),('flags',w.DWORD),('time',w.DWORD),('extra',ctypes.c_size_t)]
        class U(ctypes.Union): _fields_=[('mouse',M),('key',K)]
        class I(ctypes.Structure): _fields_=[('type',w.DWORD),('data',U)]
        values=[]
        for e in events:
            v=I()
            if e.kind=='move':
                bounds=self.virtual_bounds()
                point=to_absolute(e.value,bounds)
                if isinstance(point,SafeError):raise ComputerError(point.code)
                v.data.mouse=M(*point,0,0xC001,0,0)
                self.last_move_submission={'physical':list(e.value),'absolute':list(point),
                    'virtual_bounds':list(bounds),'flags':0xC001,'accepted':None}
                if getattr(getattr(self,'window',None),'session',None) is not None and self.window.session.diagnostic_only:
                    self.last_move_submission['environment']=self.diagnostic_environment()
            elif e.kind=='scroll': v.data.mouse=M(0,0,(e.value[1]*120)&0xffffffff,0x800,0,0)
            elif e.value[0]=='button':v.data.mouse=M(0,0,0,2 if e.kind=='down' else 4,0,0)
            else:
                v.type=1; unicode=e.value[0]=='unicode'
                vk=0 if unicode else self.vk(e.value)
                flags=(4 if unicode else 1 if vk in (35,36,37,39) else 0)|(2 if e.kind=='up' else 0)
                v.data.key=K(vk,e.value[1] if unicode else 0,flags,0,0)
            values.append(v)
        array=(I*len(values))(*values)
        self.u.SendInput.argtypes=[w.UINT,ctypes.POINTER(I),ctypes.c_int]; self.u.SendInput.restype=w.UINT
        accepted=int(self.u.SendInput(len(values),array,ctypes.sizeof(I)))
        if self.last_move_submission is not None:self.last_move_submission['accepted']=accepted
        return accepted
