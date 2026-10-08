"""Connection-owned, explicitly selected local sharing; online delivery is optional.

Only the latest reduced JPEG is held in memory. Each Windows capture opens and
disposes the existing bounded helper. No scheduler, recorder or model is needed.
"""
import asyncio
import io
import secrets
import time
from PIL import Image
from .screen_processor import ScreenProcessor


def reduced_jpeg(data):
    if len(data) > 32 * 1024 * 1024:
        raise ValueError('frame_size_limit')
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'JPEG' or image.width * image.height > 32_000_000:
            raise ValueError('invalid_frame')
        image.load()
        image.thumbnail((1280, 720))
        with io.BytesIO() as output:
            image.convert('RGB').save(output, format='JPEG', quality=72)
            return output.getvalue()


class ScreenSharing:
    def __init__(self, connection):
        self.connection = connection
        self.capture = ScreenProcessor()
        self.share_id = None
        self.mode = 'local'
        self.source = None
        self.frame = None
        self.frame_count = 0
        self.last_at = 0
        self.busy = False
        self.task = None
        self.epoch = 0

    def log(self, status, **details):
        self.connection.rt.session_log.write('screen_share', status=status, **details)

    async def stop(self, reason='user_stop'):
        self.epoch += 1
        active = self.share_id is not None
        self.share_id = None
        self.connection.sharing = False
        task = self.task
        if task and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.frame = None
        # Clear helper bytes too; it otherwise retains a full-resolution frame.
        self.capture._last_frame = None
        if active:
            self.log('stopped', reason=reason, frames=self.frame_count)

    async def start(self, body):
        await self.stop('replaced')
        epoch = self.epoch
        mode, method = body.get('mode', 'local'), body.get('capture', 'browser')
        if mode not in {'local', 'provider'} or method not in {'windows', 'browser'}:
            raise ValueError('invalid_share_mode')
        selection = None
        if method == 'windows':
            target, source = body.get('target'), body.get('source')
            if target not in {'monitor', 'window'} or not isinstance(source, str):
                raise ValueError('Choose a listed screen source.')
            sources = await self.capture.sources()
            if not sources.get('ok'):
                return {'ok': False, 'error': 'Windows screen sources are unavailable.', 'code': sources.get('error', 'capture_failed')}
            if not any(item['id'] == source for item in sources.get('monitors' if target == 'monitor' else 'windows', [])):
                return {'ok': False, 'error': 'The selected screen source no longer exists. Choose it again.', 'code': 'stale_source'}
            selection = {'target': target, 'source': source}
        if epoch != self.epoch:
            return {'ok': False, 'error': 'Screen sharing was cancelled.', 'code': 'cancelled'}
        self.share_id = secrets.token_urlsafe(24)
        identity = self.share_id
        self.mode, self.source = mode, selection
        self.frame_count, self.last_at = 0, 0
        self.connection.share_owned_live = False
        warning = None
        if mode == 'provider':
            from .providers.base import ProviderUnavailable
            self.connection.share_owned_live = self.connection.live is None
            try:
                await self.connection.ensure_live()
            except ProviderUnavailable:
                self.mode = 'local'
                warning = 'Online screen reasoning is unavailable. Local preview remains active; no frames are being uploaded.'
                self.log('provider_unavailable', stage='start')
        if self.share_id != identity:
            return {'ok': False, 'error': 'Screen sharing was cancelled.', 'code': 'cancelled'}
        self.connection.sharing = True
        self.log('started', mode=self.mode, capture=method, target=body.get('target'))
        return {'ok': True, 'share_id': identity, 'mode': self.mode, 'warning': warning, 'max_seconds': None, 'max_fps': 1}

    async def accept(self, identity, data=None):
        if not identity or identity != self.share_id:
            return {'ok': False, 'error': 'Screen sharing is not active.', 'code': 'inactive'}
        if self.busy or (self.frame_count and time.monotonic() - self.last_at < .9):
            return {'ok': False, 'error': 'Screen frames are limited to one per second.', 'code': 'rate_limited'}
        self.busy = True
        self.task = asyncio.current_task()
        try:
            if data is None:
                if self.source is None:
                    raise ValueError('No Windows source was selected.')
                result = await self.capture.capture(**self.source)
                if not result.get('ok'):
                    self.log('failed', stage='capture', code=result.get('error', 'capture_failed'))
                    return {'ok': False, 'error': 'The selected Windows source could not be captured. Choose it again.', 'code': result.get('error')}
                data = self.capture.last_frame
            frame = await asyncio.to_thread(reduced_jpeg, data)
            if identity != self.share_id:
                return {'ok': False, 'error': 'Screen sharing was cancelled.', 'code': 'cancelled'}
            self.frame = frame
            self.capture._last_frame = None
            warning = None
            if self.mode == 'provider':
                try:
                    if self.connection.live is None:
                        raise RuntimeError('provider_unavailable')
                    async with asyncio.timeout(5):
                        await self.connection.live.send_image(frame)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.mode = 'local'
                    warning = 'Online screen reasoning stopped. Local preview is still active; no frames are being uploaded.'
                    self.log('provider_unavailable', stage='frame')
            if identity != self.share_id:
                return {'ok': False, 'error': 'Screen sharing was cancelled.', 'code': 'cancelled'}
            self.frame_count += 1
            self.last_at = time.monotonic()
            if self.frame_count == 1:
                self.log('first_frame', mode=self.mode, bytes=len(frame))
            return {'ok': True, 'mode': self.mode, 'frame_count': self.frame_count, 'warning': warning}
        finally:
            self.busy = False
            self.task = None

    async def close(self):
        await self.stop('connection_closed')
        await self.capture.close()
