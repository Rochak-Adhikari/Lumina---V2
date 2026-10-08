"""Retain Windows handles before cancelling a verified tmux pane.

Handles identify processes even if Windows subsequently reuses a numeric PID.
Only descendants born after their parent are included.
"""
import ctypes
from ctypes import wintypes as w


class ProcessTree:
    def __init__(self,pid):
        self.handles=[]
        self.k=ctypes.WinDLL('kernel32',use_last_error=True)
        k=self.k
        k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
        k.CloseHandle.argtypes=[w.HANDLE]
        k.TerminateProcess.argtypes=[w.HANDLE,w.UINT]
        k.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]
        k.GetProcessTimes.argtypes=[w.HANDLE,ctypes.POINTER(w.FILETIME),ctypes.POINTER(w.FILETIME),ctypes.POINTER(w.FILETIME),ctypes.POINTER(w.FILETIME)]
        class Entry(ctypes.Structure):
            _fields_=[('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),('heap',ctypes.c_size_t),('module',w.DWORD),('threads',w.DWORD),('parent',w.DWORD),('priority',w.LONG),('flags',w.DWORD),('name',w.WCHAR*260)]
        k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];k.CreateToolhelp32Snapshot.restype=w.HANDLE
        k.Process32FirstW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)]
        k.Process32NextW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)]
        def retain(number):
            handle=k.OpenProcess(0x100001|0x1000,False,number)
            if not handle:
                if ctypes.get_last_error()==87:return None
                raise OSError('Cannot verify the worker process for cancellation.')
            times=[w.FILETIME() for _ in range(4)]
            if not k.GetProcessTimes(handle,*[ctypes.byref(t) for t in times]):
                k.CloseHandle(handle);raise OSError('Cannot verify worker creation time.')
            return handle,(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
        try:
            root=retain(pid)
            if root is None:return
            self.handles.append(root[0]);known={pid:root[1]}
            snapshot=k.CreateToolhelp32Snapshot(2,0)
            if snapshot==ctypes.c_void_p(-1).value:raise OSError('Cannot inspect worker descendants.')
            rows=[]
            try:
                entry=Entry();entry.size=ctypes.sizeof(entry)
                more=k.Process32FirstW(snapshot,ctypes.byref(entry))
                while more:
                    rows.append((entry.pid,entry.parent));more=k.Process32NextW(snapshot,ctypes.byref(entry))
            finally:k.CloseHandle(snapshot)
            for _ in range(len(rows)):
                added=False
                for child,parent in rows:
                    if child in known or parent not in known:continue
                    item=retain(child)
                    if item is None:continue
                    handle,born=item
                    if born<known[parent]:k.CloseHandle(handle);continue
                    known[child]=born;self.handles.append(handle);added=True
                if not added:break
        except BaseException:self.close();raise

    def terminate(self):
        # Stop the root first so it cannot deliberately create another worker.
        for handle in self.handles:
            if self.k.WaitForSingleObject(handle,0)!=0 and not self.k.TerminateProcess(handle,1):
                if self.k.WaitForSingleObject(handle,0)!=0:raise OSError('Worker process refused termination.')
        for handle in self.handles:
            if self.k.WaitForSingleObject(handle,3000)!=0:raise TimeoutError('Worker process did not stop.')

    def close(self):
        for handle in self.handles:self.k.CloseHandle(handle)
        self.handles=[]
