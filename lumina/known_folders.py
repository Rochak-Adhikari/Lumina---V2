"""Known-folder metadata, without granting filesystem authority.

WindowsKnownFolders(lookup=None, *, home=None, platform=None).resolve(name) ->
{name, path, source, authoritative, exists}. ``lookup`` is an optional callable
receiving the canonical name, useful for redirected-folder fixture tests.
Windows failures are explicit; only non-Windows returns conventional fallbacks.
Every consumer must still pass the returned path through its normal resolver.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import uuid


FOLDERS = {
    'desktop': ('B4BFCC3A-DB2C-424C-B029-7FE99A87C641', 'Desktop'),
    'documents': ('FDD39AD0-238F-46AF-ADB4-6C85480369C7', 'Documents'),
    'downloads': ('374DE290-123F-4565-9164-39C4925E467B', 'Downloads'),
    'pictures': ('33E28130-4E1E-4676-835A-98395C3BC3BB', 'Pictures'),
    'music': ('4BD8D571-6D19-48D3-BE97-422220080E43', 'Music'),
    'videos': ('18989B1D-99B5-455B-841C-AB7C74E4DDFC', 'Videos'),
    'profile': ('5E6C858F-0E22-4760-9AFE-EA3317B67173', ''),
    'roaming_appdata': ('3EB685DB-65F9-4CF6-A03A-E3EF65729F3D', 'AppData/Roaming'),
    'local_appdata': ('F1B32785-6FBA-4FCF-9D55-7B8E7F157091', 'AppData/Local'),
    'programs': ('A77F5D77-2E2B-44C3-A6A2-ABA601054A51', 'AppData/Roaming/Microsoft/Windows/Start Menu/Programs'),
    'common_programs': ('0139D44E-6AFE-49F2-8690-3DAFCAE6FFB8', 'ProgramData/Microsoft/Windows/Start Menu/Programs'),
}


class WindowsKnownFolders:
    def __init__(self, lookup=None, *, home=None, platform=None):
        self.lookup = lookup
        self.home = Path(home) if home is not None else Path.home()
        self.platform = os.name if platform is None else platform

    def resolve(self, name: str) -> dict:
        if not isinstance(name, str) or name.casefold() not in FOLDERS:
            raise ValueError('unknown_known_folder')
        name = name.casefold()
        if self.lookup is not None:
            path, source, authoritative = Path(self.lookup(name)), 'injected', True
        elif self.platform == 'nt':
            path, source, authoritative = self._windows(name), 'SHGetKnownFolderPath', True
        else:
            path = self.home / FOLDERS[name][1]
            source, authoritative = 'conventional_fallback', False
        if not path.is_absolute():
            raise ValueError('known_folder_not_absolute')
        return dict(name=name, path=str(path), source=source,
                    authoritative=authoritative, exists=path.is_dir())

    def locations(self) -> dict:
        return {name: self.resolve(name) for name in FOLDERS}

    @staticmethod
    def _windows(name):
        # GUID's first three fields have Windows' little-endian representation.
        class GUID(ctypes.Structure):
            _fields_ = [('data', ctypes.c_ubyte * 16)]
        shell = ctypes.WinDLL('shell32', use_last_error=True)
        ole = ctypes.WinDLL('ole32', use_last_error=True)
        get = shell.SHGetKnownFolderPath
        get.argtypes = [ctypes.POINTER(GUID), ctypes.c_uint32,
                        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        get.restype = ctypes.c_long
        ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole.CoTaskMemFree.restype = None
        guid = GUID((ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(FOLDERS[name][0]).bytes_le))
        result = ctypes.c_void_p()
        try:
            # DONT_VERIFY: obtain redirected metadata even when offline; never CREATE.
            hr = get(ctypes.byref(guid), 0x4000, None, ctypes.byref(result))
            if hr < 0 or not result.value:
                raise OSError('known_folder_unavailable')
            return Path(ctypes.wstring_at(result.value))
        finally:
            if result.value:
                ole.CoTaskMemFree(result)


def get_known_folder(name):
    return WindowsKnownFolders().resolve(name)
