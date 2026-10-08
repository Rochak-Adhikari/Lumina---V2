"""Optional Windows current-user DPAPI storage; never falls back to plaintext."""
import ctypes
import json
import os
from pathlib import Path
import tempfile
from ctypes import wintypes

from .base import CommunicationError


KEYS = {"GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN", "GMAIL_ACCESS_TOKEN"}
MAGIC = b"LUMINA-GMAIL-DPAPI-1\n"


def _protect(data, decrypt=False):
    if os.name != "nt":
        raise ValueError("Windows required")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    # CRYPTPROTECT_UI_FORBIDDEN, no machine-wide protection flag.
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise ValueError("Credential protection failed")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def load(filename):
    try:
        if os.name != "nt":
            raise ValueError()
        path = Path(filename)
        if not path.exists():
            return {}
        if path.is_symlink() or path.stat().st_size > 1024 * 1024:
            raise ValueError()
        blob = path.read_bytes()
        if not blob.startswith(MAGIC):
            raise ValueError()
        value = json.loads(_protect(blob[len(MAGIC):], decrypt=True))
        if not isinstance(value, dict) or set(value) - KEYS or not all(isinstance(v, str) for v in value.values()):
            raise ValueError()
        return value
    except Exception:
        raise CommunicationError("gmail_credentials", "Unable to load protected Gmail credentials.") from None


def save(filename, credentials):
    temporary = None
    try:
        if not isinstance(credentials, dict) or set(credentials) - KEYS or not all(isinstance(v, str) for v in credentials.values()):
            raise ValueError()
        protected = MAGIC + _protect(json.dumps(credentials).encode("utf-8"))
        path = Path(filename)
        if path.is_symlink():
            raise ValueError()
        # Only ciphertext ever reaches disk; replacement is atomic.
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(protected)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except Exception:
        raise CommunicationError("gmail_credentials", "Unable to save protected Gmail credentials.") from None
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass
