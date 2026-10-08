"""Private, disposable Windows capture worker. Binary stdout, no image files."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import io
import json
import struct
import sys


class CaptureError(Exception):
    pass


def enable_dpi():
    """Called only in the worker, before creating any capture backend."""
    user = ctypes.WinDLL('user32', use_last_error=True)
    try:
        fn = user.SetProcessDpiAwarenessContext
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = wintypes.BOOL
        if fn(ctypes.c_void_p(-4)):
            return 'per_monitor_v2'
    except AttributeError:
        pass
    try:
        shcore = ctypes.WinDLL('shcore')
        if shcore.SetProcessDpiAwareness(2) == 0:
            return 'per_monitor'
    except (AttributeError, OSError):
        pass
    raise CaptureError('dpi_awareness_unavailable')


def windows():
    user = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.EnumWindows.restype = wintypes.BOOL
    for name in ('IsWindowVisible', 'IsIconic', 'GetWindowTextLengthW'):
        getattr(user, name).argtypes = [wintypes.HWND]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    found = []

    @callback_type
    def visit(hwnd, _):
        if not user.IsWindowVisible(hwnd) or user.IsIconic(hwnd):
            return True
        title = ctypes.create_unicode_buffer(user.GetWindowTextLengthW(hwnd) + 1)
        user.GetWindowTextW(hwnd, title, len(title))
        rect, pid = wintypes.RECT(), wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if title.value and user.GetWindowRect(hwnd, ctypes.byref(rect)):
            w, h = rect.right - rect.left, rect.bottom - rect.top
            if w > 0 and h > 0:
                found.append({'id': f'{int(hwnd)}:{pid.value}', 'title': title.value,
                              'hwnd': int(hwnd), 'pid': pid.value,
                              'bounds': {'left': rect.left, 'top': rect.top,
                                         'width': w, 'height': h}})
        return True

    if not user.EnumWindows(visit, 0):
        raise CaptureError('window_enumeration_failed')
    return found


def bounds_for(request, monitors, window_sources):
    target, source = request['target'], request['source']
    if target == 'window':
        item = next((x for x in window_sources if x['id'] == source), None)
        if item is None:
            raise CaptureError('stale_window')
        bounds = dict(item['bounds'])
    else:
        try:
            index = int(source)
            if index < 1 or index >= len(monitors):
                raise ValueError()
            bounds = dict(monitors[index])
        except (ValueError, IndexError):
            raise CaptureError('monitor_unavailable') from None
    crop = request.get('region')
    if crop is not None:
        x, y, w, h = crop
        if (w <= 0 or h <= 0 or x < bounds['left'] or y < bounds['top'] or
                x + w > bounds['left'] + bounds['width'] or
                y + h > bounds['top'] + bounds['height']):
            raise CaptureError('region_outside_source')
        bounds = {'left': x, 'top': y, 'width': w, 'height': h}
    if not 0 < bounds['width'] * bounds['height'] <= 32_000_000:
        raise CaptureError('capture_size_limit')
    return bounds


def execute(request, *, backend_factory=None, image_module=None, window_reader=windows,
            dpi_setter=enable_dpi):
    dpi = dpi_setter()
    if backend_factory is None:
        import mss
        backend_factory = mss.mss
    if image_module is None:
        from PIL import Image
        image_module = Image
    with backend_factory() as backend:
        monitors = backend.monitors
        window_sources = window_reader() if request['operation'] == 'sources' or request.get('target') == 'window' else []
        if request['operation'] == 'sources':
            return {'ok': True, 'timestamp': datetime.now(timezone.utc).isoformat(),
                    'coordinate_space': 'physical_virtual_desktop', 'dpi_awareness': dpi,
                    'monitors': [{'id': str(i), 'bounds': dict(m)} for i, m in enumerate(monitors) if i],
                    'windows': window_sources}, b''
        bounds = bounds_for(request, monitors, window_sources)
        started = datetime.now(timezone.utc).isoformat()
        shot = backend.grab(bounds)
        timestamp = datetime.now(timezone.utc).isoformat()
        if request['target'] == 'window':
            before = next(x for x in window_sources if x['id'] == request['source'])
            after = next((x for x in window_reader() if x['id'] == request['source']), None)
            if before != after:
                raise CaptureError('stale_window')
        with image_module.frombytes('RGB', shot.size, shot.rgb) as image:
            if all(high == 0 for low, high in image.getextrema()):
                raise CaptureError('black_frame_protection_unknown')
            with io.BytesIO() as output:
                image.save(output, format='JPEG', quality=85)
                jpeg = output.getvalue()
        if len(jpeg) > 32 * 1024 * 1024:
            raise CaptureError('frame_size_limit')
        return {'ok': True, 'target': request['target'], 'source': request['source'],
                'bounds': bounds, 'width': shot.width, 'height': shot.height,
                'capture_started_at': started, 'timestamp': timestamp,
                'coordinate_space': 'physical_virtual_desktop', 'dpi_awareness': dpi,
                'mime_type': 'image/jpeg', 'byte_count': len(jpeg),
                'capture_method': 'visible_desktop', 'occlusion_possible': request['target'] == 'window',
                'protection_status': 'unknown', 'uploaded': False}, jpeg


def main():
    try:
        metadata, jpeg = execute(json.loads(sys.argv[1]))
    except ImportError:
        metadata, jpeg = {'ok': False, 'error': 'unavailable'}, b''
    except CaptureError as exc:
        metadata, jpeg = {'ok': False, 'error': str(exc)}, b''
    except Exception:
        metadata, jpeg = {'ok': False, 'error': 'capture_failed'}, b''
    encoded = json.dumps(metadata).encode('utf-8')
    sys.stdout.buffer.write(struct.pack('!I', len(encoded)) + encoded + jpeg)
    sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
