"""Measured machine CPU utilization; no synthetic fallback values."""
import ctypes
import os
import threading


class MachineLoad:
    def __init__(self):
        self.previous=None
        self.lock=threading.Lock()

    @staticmethod
    def counters():
        if os.name!='nt':return None
        from ctypes import wintypes
        idle,kernel,user=wintypes.FILETIME(),wintypes.FILETIME(),wintypes.FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle),ctypes.byref(kernel),ctypes.byref(user)):
            return None
        values=[(v.dwHighDateTime<<32)|v.dwLowDateTime for v in (idle,kernel,user)]
        return values[0],values[1]+values[2]

    def sample(self):
        with self.lock:
            try:current=self.counters()
            except (OSError,AttributeError):current=None
            previous=self.previous;self.previous=current
            if current is None or previous is None:return None
            idle,total=(current[i]-previous[i] for i in (0,1))
            if total<=0 or idle<0:return None
            return round(max(0,min(100,100*(total-idle)/total)),1)
