"""Connection-owned, explicitly selected local sharing; online delivery is optional.

Only the latest reduced JPEG is held in memory. Each Windows capture opens and
disposes the existing bounded helper. No scheduler, recorder or model is needed.
"""
import asyncio
import io
import secrets
import time
from datetime import datetime, timezone
from PIL import Image
from .screen_processor import ScreenProcessor
from .observations import DesktopTransform, ObservationStream


def processed_frame(data):
    if len(data) > 32 * 1024 * 1024:
        raise ValueError('frame_size_limit')
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'JPEG' or image.width * image.height > 32_000_000:
            raise ValueError('invalid_frame')
        image.load()
        original = image.size
        image.thumbnail((1280, 720))
        with io.BytesIO() as output:
            image.convert('RGB').save(output, format='JPEG', quality=72)
            return output.getvalue(), original, image.size


def reduced_jpeg(data):
    return processed_frame(data)[0]


class ScreenSharing:
    def __init__(self, connection, *, clock=time.monotonic, wall_clock=None,
                 freshness_seconds=3.0):
        self.connection = connection
        self.clock = clock
        self.wall_clock = wall_clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.observations = ObservationStream(clock=clock, freshness_seconds=freshness_seconds)
        self.capture = ScreenProcessor()
        self.share_id = None
        self.mode = 'local'
        self.source = None
        self.method = None
        self.ticket = None
        self.ticket_at = None
        self.client_sequence = 0
        self.frame_count = 0
        self.last_at = 0
        self.busy = False
        self.task = None
        self.epoch = 0
        self.closed = False
        self.delivery = None
        self.delivery_lock = asyncio.Lock()
        self.online_requested = False
        self.delivery_skipped = 0
        self.delivered_sequence = 0
        self.started_at = None
        self.provider_epoch = 0

    def status(self):
        if (self.share_id and not self.frame_count and self.started_at is not None and
                self.clock() - self.started_at > 15 and self.observations.capture_state == 'waiting'):
            self.observations.fail('capture')
            self.observations.error = 'first_frame_timeout'
        return {'ok': True, 'share_id': self.share_id, 'mode': self.mode,
                'initialized': self.frame_count > 0 and self.share_id is not None,
                'perception': self.observations.status(), 'capture_busy': self.busy,
                'delivery_busy': bool(self.delivery and not self.delivery.done()),
                'delivery_skipped': self.delivery_skipped,
                'delivered_sequence': self.delivered_sequence}

    def pause(self, identity):
        if not identity or identity != self.share_id:
            return {'ok': False, 'code': 'inactive', 'error': 'Sharing session changed.'}
        self.epoch += 1  # In-flight processing cannot reactivate a paused source.
        self.observations.pause()
        self.connection.sharing = False
        return self.status()

    def prepare_frame(self, identity):
        """Renew a browser ticket before exposure, never re-date retained pixels."""
        if not identity or identity != self.share_id or self.method != 'browser':
            return {'ok': False, 'code': 'inactive', 'error': 'Sharing session changed.'}
        if self.busy:
            return {'ok': False, 'code': 'rate_limited', 'error': 'A frame is still processing.'}
        return {**self.status(), 'capture_ticket': self.next_ticket()}

    async def send_current(self, expected_session=None):
        """No capture or permission acquisition; only the selected fresh observation."""
        epoch, provider_epoch, live = self.epoch, self.provider_epoch, self.connection.live
        async with self.delivery_lock:
            if (epoch != self.epoch or provider_epoch != self.provider_epoch or
                    live is not self.connection.live):
                return None
            if expected_session is not None and expected_session != self.share_id:
                return None
            observation = self.observations.latest()
            if not self.online_requested or observation is None or self.connection.live is None:
                return None
            image = observation.image
            if image is None:
                return None
            async with asyncio.timeout(5):
                await live.send_image(image)
            # A late transport result cannot revive a paused/replaced delivery
            # context. Bytes already submitted are not recalled by this check.
            if (observation.session_id != self.share_id or epoch != self.epoch or
                    provider_epoch != self.provider_epoch or live is not self.connection.live):
                return None
            self.delivered_sequence = observation.sequence
            self.observations.analysis_state = 'sent_unconfirmed'
            return observation

    async def deliver(self, identity):
        epoch, provider_epoch, live = self.epoch, self.provider_epoch, self.connection.live
        try:
            if self.connection.live is None and identity == self.share_id:
                self.provider_unavailable()
                return
            await self.send_current(identity)
        except asyncio.CancelledError:
            raise
        except Exception:
            if (identity == self.share_id and epoch == self.epoch and
                    provider_epoch == self.provider_epoch and live is self.connection.live):
                self.provider_unavailable()
                self.log('provider_unavailable', stage='frame')

    @property
    def frame(self):
        current = self.observations.latest(require_fresh=False)
        return current.image if current else None

    def provider_unavailable(self):
        self.provider_epoch += 1
        self.mode = 'local'
        self.observations.analysis_state = 'unavailable'

    def next_ticket(self):
        self.ticket, self.ticket_at = secrets.token_urlsafe(24), self.clock()
        return self.ticket

    def log(self, status, **details):
        self.connection.rt.session_log.write('screen_share', status=status, **details)

    async def stop(self, reason='user_stop'):
        self.epoch += 1
        epoch = self.epoch
        active = self.share_id is not None
        self.share_id = None
        self.ticket = self.ticket_at = None
        self.observations.stop()
        self.connection.sharing = False
        self.online_requested = False
        tasks = [t for t in (self.task, self.delivery) if t and t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # Clear helper bytes too; it otherwise retains a full-resolution frame.
        if epoch == self.epoch:
            self.capture._last_frame = None
        if active:
            self.log('stopped', reason=reason, frames=self.frame_count)
        return epoch

    async def start(self, body):
        if self.closed:
            return {'ok': False, 'code': 'closed', 'error': 'Screen sharing is closed.'}
        epoch = await self.stop('replaced')
        mode, method = body.get('mode', 'local'), body.get('capture', 'browser')
        if mode not in {'local', 'provider'} or method not in {'windows', 'browser'}:
            raise ValueError('invalid_share_mode')
        selection = None
        window_render = body.get('window_render', False)
        if type(window_render) is not bool or (window_render and (method != 'windows' or body.get('target') != 'window')):
            raise ValueError('Window rendering requires a Windows window source')
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
            if window_render:
                selection['window_render'] = True
        if epoch != self.epoch or self.closed:
            return {'ok': False, 'error': 'Screen sharing was cancelled.', 'code': 'cancelled'}
        self.share_id = secrets.token_urlsafe(24)
        identity = self.share_id
        self.mode, self.source = mode, selection
        self.online_requested = mode == 'provider'
        self.delivery_skipped = self.delivered_sequence = 0
        self.method = method
        self.client_sequence = 0
        self.observations.start(identity, analysis=mode == 'provider')
        self.frame_count, self.last_at = 0, 0
        self.started_at = self.clock()
        self.connection.share_owned_live = False
        warning = None
        if mode == 'provider':
            from .providers.base import ProviderUnavailable
            self.connection.share_owned_live = self.connection.live is None
            try:
                await self.connection.ensure_live()
            except ProviderUnavailable:
                if self.share_id != identity:
                    return {'ok': False, 'code': 'cancelled', 'error': 'Screen sharing was cancelled.'}
                self.provider_unavailable()
                warning = 'Online screen reasoning is unavailable. Local preview remains active; no frames are being uploaded.'
                self.log('provider_unavailable', stage='start')
            except BaseException:
                if self.share_id == identity:
                    await self.stop('start_failed')
                raise
        if self.share_id != identity:
            return {'ok': False, 'error': 'Screen sharing was cancelled.', 'code': 'cancelled'}
        self.connection.sharing = False  # Initialization is not evidence of capture.
        self.started_at = self.clock()
        if self.mode == 'provider':
            self.observations.analysis_state = 'ready'
        self.log('starting', session_id=identity, mode=self.mode, capture=method, target=body.get('target'))
        return {'ok': True, 'share_id': identity, 'mode': self.mode, 'warning': warning,
                'status': 'starting', 'initialized': False,
                'max_seconds': None, 'max_fps': 1, 'capture_ticket': self.next_ticket(),
                'perception': self.observations.status()}

    async def accept(self, identity, data=None, *, metadata=None, received=None):
        if not identity or identity != self.share_id:
            return {'ok': False, 'error': 'Screen sharing is not active.', 'code': 'inactive'}
        if self.busy or (self.frame_count and self.clock() - self.last_at < .9):
            return {'ok': False, 'error': 'Screen frames are limited to one per second.', 'code': 'rate_limited'}
        received_mono, received_wall = received or (self.clock(), self.wall_clock())
        capture_origin, captured_at, basis = None, None, 'unknown'
        original_override = None
        if data is not None and self.method != 'browser':
            return {'ok': False, 'error': 'Source mismatch.', 'code': 'invalid_source'}
        if metadata is not None:
            # Values already syntactically validated at the HTTP boundary.
            sequence = metadata['sequence']
            if (self.method != 'browser' or metadata['ticket'] != self.ticket or
                    sequence <= self.client_sequence):
                return {'ok': False, 'error': 'Frame identity expired.', 'code': 'expired_frame'}
            capture_origin, basis = self.ticket_at, 'browser_ticket'
            captured_at = metadata['captured_at']
            original_override = metadata['dimensions']
            self.client_sequence = sequence
            self.ticket = None
        elif data is not None and self.client_sequence:
            return {'ok': False, 'error': 'Frame metadata is required.', 'code': 'expired_frame'}
        self.busy = True
        epoch = self.epoch
        self.task = asyncio.current_task()
        stage = 'capture' if data is None else 'processing'
        try:
            if data is None:
                if self.source is None:
                    raise ValueError('No Windows source was selected.')
                capture_origin, basis = self.clock(), 'native_request'
                result = await self.capture.capture(**self.source)
                if identity != self.share_id or epoch != self.epoch:
                    return {'ok': False, 'error': 'Screen sharing was cancelled.', 'code': 'cancelled'}
                if not result.get('ok'):
                    self.observations.fail('capture')
                    self.log('failed', stage='capture', code=result.get('error', 'capture_failed'))
                    return {'ok': False, 'error': 'The selected Windows source could not be captured. Choose it again.', 'code': result.get('error')}
                data = self.capture.last_frame
                captured_at = result.get('timestamp')
                received_mono, received_wall = self.clock(), self.wall_clock()
            stage = 'processing'
            frame, original, dimensions = await asyncio.to_thread(processed_frame, data)
            if identity != self.share_id or epoch != self.epoch:
                return {'ok': False, 'error': 'Screen sharing was cancelled.', 'code': 'cancelled'}
            desktop = None
            if self.method == 'windows' and result.get('coordinate_space') == 'physical_virtual_desktop':
                bounds = result.get('bounds', {})
                if (all(type(bounds.get(k)) is int for k in ('left', 'top', 'width', 'height'))
                        and (bounds['width'], bounds['height']) == original):
                    desktop = DesktopTransform(**bounds, scale_x=original[0] / dimensions[0],
                                               scale_y=original[1] / dimensions[1])
            self.frame_count += 1
            self.last_at = self.clock()
            self.observations.publish(
                frame, session_id=identity,
                source_id=self.source['source'] if self.source else identity + ':browser',
                source_type=self.source['target'] if self.source else 'browser',
                sequence=self.frame_count, captured_at=captured_at,
                received_at=received_wall, received_monotonic=received_mono,
                capture_not_before_monotonic=capture_origin, timing_basis=basis,
                original_dimensions=original_override or original,
                processed_dimensions=dimensions, desktop=desktop,
                capture_method='browser' if self.method == 'browser' else result.get('capture_method', 'unknown'))
            self.capture._last_frame = None
            self.connection.sharing = True
            # One bounded delivery, no queue. Slow providers cannot stall capture.
            if self.mode == 'provider':
                if self.delivery is None or self.delivery.done():
                    self.delivery = asyncio.create_task(self.deliver(identity))
                else:
                    self.delivery_skipped += 1
            if identity != self.share_id:
                return {'ok': False, 'error': 'Screen sharing was cancelled.', 'code': 'cancelled'}
            if self.frame_count == 1:
                self.log('first_frame', mode=self.mode, session_id=identity,
                         sequence=self.frame_count, captured_at=captured_at, received_at=received_wall)
            return {**self.status(), 'frame_count': self.frame_count,
                    'capture_ticket': self.next_ticket(), 'perception': self.observations.status()}
        except asyncio.CancelledError:
            if identity == self.share_id:
                self.observations.fail(stage)
            raise
        except (ValueError, OSError, TypeError):
            if identity == self.share_id:
                self.observations.fail(stage)
            return {'ok': False, 'code': 'invalid_frame', 'error': 'The frame could not be processed.'}
        finally:
            self.capture._last_frame = None
            self.busy = False
            self.task = None

    async def close(self):
        self.closed = True
        await self.stop('connection_closed')
        await self.capture.close()
