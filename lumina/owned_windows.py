"""One ephemeral Windows surface, not an adapter for arbitrary HWNDs or input.

Only its creating thread owns the native handles. Queue entries are private
Python capabilities, never WM_APP payloads supplied by a webpage. No persistence,
clipboard, shell, global input or external application targeting exists here.
"""
import asyncio
import concurrent.futures
import ctypes
from ctypes import wintypes as w
import hashlib
import json
import os
import queue
import secrets
import threading
import time

from .computer_action import ActionAdapter, ExecutionResult, TargetEvidence, Verification


def text_digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class OwnedWindowsAdapter(ActionAdapter):
    operations = ('set_owned_text', 'clear_owned_text', 'select_owned_text')

    def __init__(self, authority, observations, *, arm):
        self.authority, self.observations, self.arm = authority, observations, arm
        self.loop = asyncio.get_running_loop()
        self.identity = secrets.token_hex(16)
        self.commands = queue.Queue(maxsize=16)
        self.pending = set()
        self.closed = threading.Event()
        self.ready = concurrent.futures.Future()
        self.thread = None
        self.hwnd = self.control = None
        self.clear_control = None
        self.target = None
        self.revision = 0
        self.bindings, self.receipts = {}, {}
        self.dispatched_at = None
        self.authority.register_revoker(self._revoked)

    def _revoked(self, reason):
        # Native receiver also checks the authority's synchronous stop latch.
        self.bindings.clear()

    async def open(self):
        if os.name != 'nt' or self.thread is not None:
            raise ValueError('owned_window_unavailable')
        if (self.authority.mode not in {'disarmed', 'running'} or self.authority.quarantined or
                self.authority.stop_requested.is_set()):
            raise PermissionError('dispatch_suspended')
        self.thread = threading.Thread(target=self._run, name='Lumina-owned-window', daemon=True)
        self.thread.start()
        await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(self.ready)), 5)
        return await self.inspect()

    async def _call(self, function):
        if self.closed.is_set() or not self.hwnd:
            raise ValueError('owned_window_closed')
        future = concurrent.futures.Future()
        self.pending.add(future)
        try:
            self.commands.put_nowait((function, future))
        except queue.Full:
            self.pending.discard(future)
            raise ValueError('owned_window_busy') from None
        self.user.PostMessageW(self.hwnd, 0x8001, 0, 0)
        wrapped = asyncio.wrap_future(future)
        wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        try:
            # Cancelling the awaiter never claims the receiver request stopped.
            return await asyncio.wait_for(asyncio.shield(wrapped), 5)
        finally:
            if future.done():
                self.pending.discard(future)

    def _read(self):
        if not self.user.IsWindow(self.hwnd):
            raise ValueError('owned_target_lost')
        for handle in (self.control, self.clear_control):
            if not handle or not self.user.IsWindow(handle):
                raise ValueError('owned_target_lost')
            pid = w.DWORD()
            tid = self.user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
            if pid.value != os.getpid() or tid != self.thread_id or self.user.GetParent(handle) != self.hwnd:
                raise ValueError('owned_target_changed')
        buffer = ctypes.create_unicode_buffer(8194)
        self.user.GetWindowTextW(self.control, buffer, len(buffer))
        rect = w.RECT()
        if not self.user.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            raise ValueError('owned_target_lost')
        # Geometry is validation evidence only; it is never a click coordinate.
        revision = text_digest(json.dumps([self.revision, buffer.value, self._selection(),
                                          rect.left, rect.top, rect.right, rect.bottom]))
        target = TargetEvidence(f'{self.hwnd}:{os.getpid()}', self.identity, revision,
                                self.revision, foreground=self.user.GetForegroundWindow() == self.hwnd,
                                enabled=bool(self.user.IsWindowEnabled(self.control) and
                                             self.user.IsWindowEnabled(self.clear_control)),
                                patterns=self.operations)
        return target, text_digest(buffer.value)

    def _selection(self):
        # Same-thread, owned Edit only. Use DWORD outputs (not the packed return)
        # and UTF-16 length, including non-BMP characters, as Windows specifies.
        start, end = w.DWORD(), w.DWORD()
        self.user.SendMessageW(self.control, 0x00B0, ctypes.addressof(start), ctypes.addressof(end))
        return start.value, end.value, self.user.GetWindowTextLengthW(self.control)

    @staticmethod
    def selection_digest(digest, start, end, length):
        return text_digest(json.dumps([digest, start, end, length]))

    def _result(self, operation):
        target, digest = self._read()
        if operation == 'select_owned_text':
            digest = self.selection_digest(digest, *self._selection())
        return target, digest

    async def inspect(self):
        def inspect():
            target, digest = self._read()
            _, _, length = self._selection()
            return target, digest, self.selection_digest(digest, 0, length, length)
        self.target, digest, selection = await self._call(inspect)
        return {'ok': True, 'adapter': 'windows-owned-surface', 'window': self.target.window_id,
                'control': self.target.control_id, 'digest': digest,
                'select_all_digest': selection,
                'policy': 'reversible_local_owned_surface_only', 'persistent': False}

    def bind(self, action, lease, scope):
        self.authority.validate(lease)
        digest = text_digest(json.dumps(scope, sort_keys=True, separators=(',', ':'), allow_nan=False))
        observation = self.observations.latest()
        if (digest != lease.digest or action.operation not in self.operations or
                action.target != self.target or observation is None or
                action.session_id != observation.session_id):
            raise ValueError('owned_scope_mismatch')
        evidence = self.observations.evidence(session_id=action.session_id,
                                              minimum_sequence=action.observation_sequence)
        self.bindings[action.action_id] = (action, lease, evidence)

    async def revalidate(self, action):
        target, _ = await self._call(self._read)
        return target

    async def dispatch(self, action, cancelled):
        def apply():
            binding = self.bindings.pop(action.action_id, None)
            if binding is None or binding[0] is not action or action.action_id in self.receipts:
                return ExecutionResult('failed')
            _, lease, evidence = binding
            self.authority.validate(lease)
            current, _ = self._read()
            # Receiver-side check, after queue admission; stale queued work never
            # reaches SetWindowText. No claim of revoking an in-flight Win32 call.
            if (cancelled.is_set() or self.authority.stop_requested.is_set() or
                    time.monotonic() >= action.expires_at or current != action.target or
                    not evidence.valid(time.monotonic()) or
                    action.target.control_id != self.identity or
                    action.operation not in self.operations or
                    (action.operation in {'clear_owned_text', 'select_owned_text'} and action.text is not None) or
                    (action.operation == 'set_owned_text' and
                     (not isinstance(action.text, str) or len(action.text) > 2048 or '\x00' in action.text))):
                return ExecutionResult('failed')
            self.dispatched_at = time.monotonic()
            self.authority.validate(lease)
            self.receipts[action.action_id] = 'possibly_dispatched'
            # Both receivers are owned by this thread; HWNDs are never supplied
            # by a caller. Stop cannot retract an already-entered native call.
            if action.operation == 'clear_owned_text':
                before = self.revision
                self.user.SendMessageW(self.clear_control, 0x00F5, 0, 0)  # BM_CLICK
                ok = self.revision > before  # Callback acknowledgement, not LRESULT.
            elif action.operation == 'select_owned_text':
                self.user.SendMessageW(self.control, 0x00B1, 0, -1)  # EM_SETSEL: no return value.
                self.revision += 1
                start, end, length = self._selection()
                ok = start == 0 and end == length  # Observe the postcondition.
            else:
                ok = self.user.SetWindowTextW(self.control, action.text)
                self.revision += 1
            _, digest = self._result(action.operation)
            self.receipts[action.action_id] = digest if ok else 'unknown'
            return ExecutionResult('complete' if ok else 'unknown')
        return await self._call(apply)

    async def verify(self, action, outcome):
        # Wait for this connection's ordinary capture loop, never start another.
        consumer = self.observations.subscribe()
        try:
            while True:
                frame = await consumer.next()
                origin = frame.capture_not_before_monotonic
                if (frame.availability == 'fresh' and origin is not None and
                        self.dispatched_at is not None and origin > self.dispatched_at):
                    break
            target, digest = await self._call(lambda: self._result(action.operation))
            matched = (target.window_id == action.target.window_id and
                       target.control_id == action.target.control_id and
                       self.receipts.get(action.action_id) == digest == action.expected_digest)
            return Verification(action.action_id, target.window_id, target.control_id,
                                digest, 'matched' if matched else 'inconclusive')
        finally:
            consumer.close()

    async def cancel(self, action_id):
        self.bindings.pop(action_id, None)
        return all(f.done() for f in self.pending)

    async def cleanup(self, action_id):
        self.bindings.pop(action_id, None)
        self.pending = {f for f in self.pending if not f.done()}
        return not self.pending

    def signal_stop(self, reason='emergency_stop'):
        self.authority.request_stop()
        self.loop.call_soon_threadsafe(self.authority.stop, reason)

    async def close(self):
        self.signal_stop()
        if self.hwnd and not self.closed.is_set():
            self.user.PostMessageW(self.hwnd, 0x0010, 0, 0)
        if self.thread:
            await asyncio.to_thread(self.thread.join, 2)
        settled = not self.thread or not self.thread.is_alive()
        if not settled:
            self.authority.note_external_uncertainty()
        return {'ok': settled, 'settled': settled}

    def _run(self):
        try:
            self._windows_loop()
        except BaseException:
            if not self.ready.done():
                self.ready.set_exception(RuntimeError('owned_window_unavailable'))
            self.signal_stop()
        finally:
            self.closed.set()
            while not self.commands.empty():
                _, future = self.commands.get_nowait()
                if not future.done():
                    future.set_exception(RuntimeError('owned_window_closed'))

    def _windows_loop(self):
        self.user = u = ctypes.WinDLL('user32', use_last_error=True)
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        result_type = ctypes.c_ssize_t
        callback = ctypes.WINFUNCTYPE(result_type, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        class WNDCLASS(ctypes.Structure):
            _fields_ = [('style', w.UINT), ('proc', callback), ('cbClsExtra', ctypes.c_int),
                        ('cbWndExtra', ctypes.c_int), ('instance', w.HINSTANCE), ('icon', w.HICON),
                        ('cursor', w.HANDLE), ('background', w.HBRUSH),
                        ('menu', w.LPCWSTR), ('name', w.LPCWSTR)]
        signatures = {
            'DefWindowProcW': ([w.HWND, w.UINT, w.WPARAM, w.LPARAM], result_type),
            'CreateWindowExW': ([w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, ctypes.c_void_p], w.HWND),
            'RegisterClassW': ([ctypes.POINTER(WNDCLASS)], w.ATOM),
            'UnregisterClassW': ([w.LPCWSTR, w.HINSTANCE], w.BOOL),
            'PostMessageW': ([w.HWND, w.UINT, w.WPARAM, w.LPARAM], w.BOOL),
            'SendMessageW': ([w.HWND, w.UINT, w.WPARAM, w.LPARAM], result_type),
            'GetMessageW': ([ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT], ctypes.c_int),
            'TranslateMessage': ([ctypes.POINTER(w.MSG)], w.BOOL),
            'DispatchMessageW': ([ctypes.POINTER(w.MSG)], result_type),
            'DestroyWindow': ([w.HWND], w.BOOL), 'IsWindow': ([w.HWND], w.BOOL),
            'IsWindowEnabled': ([w.HWND], w.BOOL), 'GetParent': ([w.HWND], w.HWND),
            'GetForegroundWindow': ([], w.HWND),
            'GetWindowThreadProcessId': ([w.HWND, ctypes.POINTER(w.DWORD)], w.DWORD),
            'GetWindowRect': ([w.HWND, ctypes.POINTER(w.RECT)], w.BOOL),
            'SetWindowTextW': ([w.HWND, w.LPCWSTR], w.BOOL),
            'GetWindowTextW': ([w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int),
            'GetWindowTextLengthW': ([w.HWND], ctypes.c_int),
            'PostQuitMessage': ([ctypes.c_int], None),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(u, name); fn.argtypes, fn.restype = args, result
        k.GetModuleHandleW.argtypes, k.GetModuleHandleW.restype = [w.LPCWSTR], w.HMODULE
        k.GetCurrentThreadId.restype = w.DWORD
        self.thread_id = k.GetCurrentThreadId()
        instance = k.GetModuleHandleW(None)
        @callback
        def proc(hwnd, message, wp, lp):
            if message == 0x8001:
                try:
                    fn, future = self.commands.get_nowait()
                except queue.Empty:
                    return 0
                try:
                    future.set_result(fn())
                except BaseException:
                    future.set_exception(RuntimeError('owned_receiver_rejected'))
                return 0
            if message == 0x111:
                if wp & 0xffff == 1:
                    self.loop.call_soon_threadsafe(self.arm)
                elif wp & 0xffff == 2:
                    self.signal_stop()
                elif wp & 0xffff == 3:
                    self.signal_stop('user_takeover')
                elif wp & 0xffff == 4 and lp == self.clear_control and wp >> 16 == 0:
                    if hasattr(self, '_practice_index'):
                        self.practice_clicks += 1
                    elif u.SetWindowTextW(self.control, ''):
                        self.revision += 1
                return 0
            if message == 0x10:
                self.signal_stop(); u.DestroyWindow(hwnd); return 0
            if message == 2:
                u.PostQuitMessage(0); return 0
            return u.DefWindowProcW(hwnd, message, wp, lp)
        name = 'LuminaOwned-' + self.identity
        klass = WNDCLASS(0, proc, 0, 0, instance, None, None, 6, None, name)
        if not u.RegisterClassW(ctypes.byref(klass)):
            raise OSError('window_class_unavailable')
        try:
            self.hwnd = u.CreateWindowExW(0, name, 'LUMINA local scratchpad — no files or external input',
                                         0x10CA0000, 160, 160, 640, 360, None, None, instance, None)
            if not self.hwnd:
                raise OSError('window_unavailable')
            # Standard multiline Edit exposes UIA Text. Literal content,
            # no clipboard or keystroke injection; manual edits invalidate readback.
            self.control = u.CreateWindowExW(0, 'EDIT', '', 0x50A01044, 16, 70, 600, 190,
                                             self.hwnd, 100, instance, None)
            if self.control:
                u.SendMessageW(self.control, 0x00C5, 2048, 0)  # EM_SETLIMITTEXT
            self.clear_control = u.CreateWindowExW(0, 'BUTTON', 'Clear scratchpad', 0x50000000,
                                                   16, 270, 200, 32, self.hwnd, 4, instance, None)
            for identity, title, x, width in ((1, 'Enable local scratchpad', 16, 220),
                                            (2, 'Stop control', 250, 150), (3, 'Take over', 415, 150)):
                if not u.CreateWindowExW(0, 'BUTTON', title, 0x50000000, x, 16, width, 32,
                                         self.hwnd, identity, instance, None):
                    raise OSError('control_unavailable')
            if not self.control or not self.clear_control:
                raise OSError('control_unavailable')
            if hasattr(self, '_practice_index'):
                self._prepare_practice(u)
            self.ready.set_result(True)
            message = w.MSG()
            while True:
                status = u.GetMessageW(ctypes.byref(message), None, 0, 0)
                if status <= 0:
                    break
                u.TranslateMessage(ctypes.byref(message)); u.DispatchMessageW(ctypes.byref(message))
        finally:
            if self.hwnd and u.IsWindow(self.hwnd):
                u.DestroyWindow(self.hwnd)
            u.UnregisterClassW(name, instance)
