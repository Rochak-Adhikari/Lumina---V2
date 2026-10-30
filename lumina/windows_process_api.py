"""Fixed disposable-process Win32 primitives. No PID opening or arbitrary command.

Only NativeFixtureLifetime calls these. Python is a trusted boundary, not an OS
sandbox. Children execute fixed isolated sleep/exit code; no user code or input.
"""
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys


class _Startup(C.Structure):
    _fields_ = [('cb', W.DWORD), ('reserved', W.LPWSTR), ('desktop', W.LPWSTR),
        ('title', W.LPWSTR), *[(n, W.DWORD) for n in ('x','y','xs','ys','xc','yc','fill','flags')],
        ('show', W.WORD), ('reserved2size', W.WORD), ('reserved2', C.c_void_p),
        ('stdin', W.HANDLE), ('stdout', W.HANDLE), ('stderr', W.HANDLE)]


class _StartupEx(C.Structure):
    _fields_ = [('info', _Startup), ('attributes', C.c_void_p)]


class _ProcessInfo(C.Structure):
    _fields_ = [('process', W.HANDLE), ('thread', W.HANDLE), ('pid', W.DWORD), ('tid', W.DWORD)]


class _BasicLimits(C.Structure):
    _fields_ = [('process_time', C.c_longlong), ('job_time', C.c_longlong), ('flags', W.DWORD),
        ('min_ws', C.c_size_t), ('max_ws', C.c_size_t), ('active_limit', W.DWORD),
        ('affinity', C.c_size_t), ('priority', W.DWORD), ('scheduling', W.DWORD)]


class _Limits(C.Structure):
    _fields_ = [('basic', _BasicLimits), ('io', C.c_ulonglong * 6),
        ('process_memory', C.c_size_t), ('job_memory', C.c_size_t),
        ('peak_process', C.c_size_t), ('peak_job', C.c_size_t)]


class _Accounting(C.Structure):
    _fields_ = [('times', C.c_longlong * 4), ('faults', W.DWORD),
        ('total', W.DWORD), ('active', W.DWORD), ('terminated', W.DWORD)]


class Handle:
    """Owned original capability. Never reconstruct from PID or serialized value."""
    def __init__(self, value):
        if not value:
            raise OSError('missing_native_handle')
        self._value, self.closed = value, False

    @property
    def value(self):
        if self.closed:
            raise OSError('native_handle_closed')
        return self._value


@dataclass(frozen=True)
class Member:
    process: Handle
    thread: Handle
    pid: int
    role: str


class WindowsFixtureAPI:
    def __init__(self):
        if os.name != 'nt':
            raise OSError('windows_required')
        self.k = C.WinDLL('kernel32', use_last_error=True)
        self.a = C.WinDLL('advapi32', use_last_error=True)
        self._signature(self.k, 'CreateJobObjectW', [C.c_void_p,W.LPCWSTR], W.HANDLE)
        self._signature(self.k, 'SetInformationJobObject', [W.HANDLE,C.c_int,C.c_void_p,W.DWORD], W.BOOL)
        self._signature(self.k, 'QueryInformationJobObject', [W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.c_void_p], W.BOOL)
        self._signature(self.k, 'InitializeProcThreadAttributeList', [C.c_void_p,W.DWORD,W.DWORD,C.POINTER(C.c_size_t)], W.BOOL)
        self._signature(self.k, 'UpdateProcThreadAttribute', [C.c_void_p,W.DWORD,C.c_size_t,C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p], W.BOOL)
        self._signature(self.k, 'DeleteProcThreadAttributeList', [C.c_void_p], None)
        self._signature(self.k, 'CreateProcessW', [W.LPCWSTR,W.LPWSTR,C.c_void_p,C.c_void_p,W.BOOL,W.DWORD,C.c_void_p,W.LPCWSTR,C.POINTER(_StartupEx),C.POINTER(_ProcessInfo)], W.BOOL)
        self._signature(self.k, 'WaitForSingleObject', [W.HANDLE,W.DWORD], W.DWORD)
        self._signature(self.k, 'GetExitCodeProcess', [W.HANDLE,C.POINTER(W.DWORD)], W.BOOL)
        self._signature(self.k, 'GetProcessTimes', [W.HANDLE,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p], W.BOOL)
        self._signature(self.k, 'GetProcessId', [W.HANDLE], W.DWORD)
        self._signature(self.k, 'IsProcessInJob', [W.HANDLE,W.HANDLE,C.POINTER(W.BOOL)], W.BOOL)
        self._signature(self.k, 'TerminateJobObject', [W.HANDLE,W.UINT], W.BOOL)
        self._signature(self.k, 'CloseHandle', [W.HANDLE], W.BOOL)
        self._signature(self.k, 'GetCurrentProcess', [], W.HANDLE)
        self._signature(self.a, 'OpenProcessToken', [W.HANDLE,W.DWORD,C.POINTER(W.HANDLE)], W.BOOL)
        self._signature(self.a, 'GetTokenInformation', [W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.POINTER(W.DWORD)], W.BOOL)
        # Inspect only this process's token, never another application or token.
        token = W.HANDLE()
        self._ok(self.a.OpenProcessToken(self.k.GetCurrentProcess(), 8, C.byref(token)))
        try:
            elevated, size = W.DWORD(), W.DWORD()
            self._ok(self.a.GetTokenInformation(token, 20, C.byref(elevated), C.sizeof(elevated), C.byref(size)))
            if elevated.value:
                raise PermissionError('non_elevated_fixture_required')
        finally:
            self._ok(self.k.CloseHandle(token))

    @staticmethod
    def _signature(dll, name, args, result):
        f = getattr(dll, name); f.argtypes, f.restype = args, result

    @staticmethod
    def _ok(ok):
        if not ok:
            raise OSError(C.get_last_error(), 'native_fixture_api_failed')

    def new_job(self):
        return Handle(self.k.CreateJobObjectW(None, None))  # private, non-inheritable

    def configure(self, job):
        limits = _Limits()
        limits.basic.flags = 0x2000 | 0x8  # KILL_ON_JOB_CLOSE, ACTIVE_PROCESS
        limits.basic.active_limit = 2
        self._ok(self.k.SetInformationJobObject(job.value, 9, C.byref(limits), C.sizeof(limits)))
        observed = _Limits(); length = W.DWORD()
        self._ok(self.k.QueryInformationJobObject(job.value, 9, C.byref(observed), C.sizeof(observed), C.byref(length)))
        if (length.value != C.sizeof(observed) or observed.basic.flags != limits.basic.flags or
                observed.basic.active_limit != 2):
            raise PermissionError('native_job_limits_unverified')

    def create(self, job, role, parent=None):
        if role not in ('root', 'child') or (role == 'child') != (parent is not None):
            raise ValueError('fixed_fixture_only')
        # Both original handles are returned to this creator. Specified parent
        # is our retained root, never an existing PID. No suspended orphan gap.
        count = 1
        size = C.c_size_t()
        self.k.InitializeProcThreadAttributeList(None, count, 0, C.byref(size))
        if not size.value:
            raise OSError('attributes_unavailable')
        buf = C.create_string_buffer(size.value)
        self._ok(self.k.InitializeProcThreadAttributeList(buf, count, 0, C.byref(size)))
        try:
            if parent:
                # The selected parent already carries this private job. Use
                # inherited membership, not a second explicit assignment.
                parent_value = W.HANDLE(parent.process.value)
                self._ok(self.k.UpdateProcThreadAttribute(buf, 0, 0x20000, C.byref(parent_value), C.sizeof(parent_value), None, None))
            else:
                jobs = (W.HANDLE * 1)(job.value)
                self._ok(self.k.UpdateProcThreadAttribute(buf, 0, 0x2000D, jobs, C.sizeof(jobs), None, None))
            startup = _StartupEx(); startup.info.cb = C.sizeof(startup); startup.attributes = C.addressof(buf)
            info = _ProcessInfo()
            # This fixture has no console or I/O. Use the GUI interpreter from
            # the same installed Python, avoiding console-host descendants.
            executable_path = Path(sys._base_executable).resolve().with_name('pythonw.exe')
            if not executable_path.is_file():
                raise OSError('fixed_windowless_interpreter_unavailable')
            executable = str(executable_path)
            # Exact immutable program, no files, stdin, network, spawning or
            # external commands. Isolated Python ignores user startup/settings.
            program = 'import time; time.sleep(2)' if role == 'root' else 'import time; time.sleep(8)'
            command = C.create_unicode_buffer(subprocess.list2cmdline([executable, '-I', '-S', '-B', '-c', program]))
            system = os.environ.get('SystemRoot', r'C:\Windows')
            environment = C.create_unicode_buffer('SystemRoot='+system+'\0WINDIR='+system+'\0\0')
            self._ok(self.k.CreateProcessW(executable, command, None, None, False,
                0x00080000 | 0x08000000 | 0x00000400, environment,
                str(Path(executable).parent), C.byref(startup), C.byref(info)))
            return Member(Handle(info.process), Handle(info.thread), info.pid, role)
        finally:
            self.k.DeleteProcThreadAttributeList(buf)

    def birth(self, member):
        times = [C.c_ulonglong() for _ in range(4)]
        self._ok(self.k.GetProcessTimes(member.process.value, *(C.byref(v) for v in times)))
        if self.k.GetProcessId(member.process.value) != member.pid:
            raise OSError('native_instance_mismatch')
        return times[0].value

    def in_job(self, member, job):
        result = W.BOOL()
        self._ok(self.k.IsProcessInJob(member.process.value, job.value, C.byref(result)))
        return bool(result.value)

    def state(self, member):
        result = self.k.WaitForSingleObject(member.process.value, 0)
        if result == 258:
            return 'running', None
        if result != 0:
            raise OSError('native_wait_failed')
        code = W.DWORD()
        self._ok(self.k.GetExitCodeProcess(member.process.value, C.byref(code)))
        return 'exited', code.value  # 259 is valid after a signaled wait.

    def accounting(self, job):
        data = _Accounting(); length = W.DWORD()
        self._ok(self.k.QueryInformationJobObject(job.value, 1, C.byref(data), C.sizeof(data), C.byref(length)))
        if length.value != C.sizeof(data):
            raise OSError('incomplete_job_accounting')
        return {'total': data.total, 'active': data.active, 'terminated': data.terminated}

    def terminate(self, job):
        self._ok(self.k.TerminateJobObject(job.value, 1))

    def close(self, handle):
        self._ok(self.k.CloseHandle(handle.value))
        handle.closed = True
