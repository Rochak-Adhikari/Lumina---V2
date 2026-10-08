"""Supervised Phase 1 browser. No legacy action imports or global browser state.

Integration contract: execute('prepare', operation='navigate'|'click'|'type',
tab_id=..., snapshot=..., url=... OR locator={role,name}|{label}, text=...).
Show the returned exact ``request`` through the CURRENT runtime policy; only
after approval call execute('execute_confirmed', confirmation=..., request=...).
Tokens are freshness checks, NOT evidence of human consent. Never expose the
execute_confirmed entry point directly to a model without the parent policy gate.
Direct navigate/click/type calls only prepare; they cannot perform a mutation.

Confirmed navigation permits public documents, bounded redirects and read assets.
Fetch/XHR, forms, WebSockets, downloads and uploads remain blocked. GET alone
does not prove an endpoint is read-only; this is supervised public browsing,
not a sandbox for hostile websites. Inspection never grants network authority.
Screenshots are returned in memory only; no private content is uploaded.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.util
import json
import os
import time
import uuid
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from .web_search import PublicResolver, validate_public_url


class BrowserProvider(Protocol):
    """Provider-neutral surface consumed by a registry, not a Playwright object."""

    async def execute(self, action: str, **args) -> dict: ...
    async def close(self) -> dict: ...
    def status(self) -> dict: ...


class BrowserError(ValueError):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code, self.details = code, details


def _ok(status, **data):
    return {"ok": True, "status": status, "error": None, **data}


class BrowserController:
    """Own one visible Chromium context using a resolver-approved dedicated profile.

    profile=None selects 'LuminaBrowserProfile' under the resolver's current root.
    Existing directories require this module's identity marker; never fall back.
    Test doubles may override _launch; no string-dispatch transport injection or
    allow-local switch is exposed. Network routing remains mandatory for doubles.
    """

    timeout_seconds = 20
    snapshot_seconds = 60
    marker_name = 'LUMINA_AUTOMATION_PROFILE.json'

    def __init__(self, resolver, profile=None):
        self.resolver = resolver
        self.profile = profile if profile is not None else 'LuminaBrowserProfile'
        self._context = self._driver = None
        self._profile_path = self._profile_id = self._lock_path = None
        self._lock_fd = None
        self._session = None
        self._tabs = {}
        self._epochs = {}
        self._snapshots = {}
        self._pending = {}
        self._permit = None
        self._documents = {}
        self._lock = asyncio.Lock()
        self._state = 'configured'

    def status(self):
        available = self._context is not None or importlib.util.find_spec('playwright') is not None
        return _ok(self._state if available else 'unavailable', provider='playwright-chromium',
                   ready=self._context is not None, session_id=self._session,
                   profile=str(self._profile_path or self.profile), profile_id=self._profile_id,
                   visible=True, network_policy='supervised-public-read',
                   uploads=False, downloads=False)

    async def execute(self, action, **args):
        """String actions: start/status/list_tabs/new_tab/inspect/screenshot/close_tab,
        prepare/navigate/click/type/execute_confirmed/close. Unexpected args fail.
        Cancellation propagates after owned transport teardown; timeout is a dict.
        """
        async with self._lock:
            try:
                return await asyncio.wait_for(self._dispatch(action, args), self.timeout_seconds)
            except asyncio.CancelledError:
                await self._finish_teardown()
                raise
            except (TimeoutError, asyncio.TimeoutError):
                await self._finish_teardown()
                return self._error('TIMEOUT', 'Browser operation timed out; session was closed.')
            except BrowserError as exc:
                if action == 'start':await self._finish_teardown()
                return self._error(exc.code, str(exc), **exc.details)
            except (ImportError, ModuleNotFoundError):
                await self._finish_teardown()
                self._state = 'unavailable'
                return self._error('UNAVAILABLE', 'Playwright is unavailable; no browser was installed.')
            except Exception as exc:
                # Provider errors can contain private URLs, typed content or credentials.
                await self._finish_teardown()
                self._state = 'failed'
                if action=='start' and any(phrase in str(exc).lower() for phrase in ('processsingleton','profile appears to be in use','opening in existing browser session','user data directory is already in use')):
                    return self._error('PROFILE_BUSY','This browser profile is still in use. Close its existing supervised browser before retrying.',
                        lock_source='chromium',reason='browser_profile_in_use',profile=str(self._profile_path))
                return self._error('PROVIDER_FAILED', 'Browser provider failed; session was closed.')

    @staticmethod
    def _error(code, message, **details):
        return {'ok': False, 'status': 'error', 'code': code, 'error': message, **details}

    async def close(self):
        return await self.execute('close')

    async def _dispatch(self, action, args):
        if action in ('status', 'start', 'close', 'list_tabs', 'new_tab'):
            self._keys(args, set())
            if action == 'status':
                return self.status()
            if action == 'close':
                await self._finish_teardown()
                return _ok('closed')
            if action == 'start':
                return await self._start()
            self._ready()
            if action == 'new_tab':
                page = await self._context.new_page()  # Always about:blank.
                return _ok('created', tab_id=self._register(page), session_id=self._session)
            return _ok('tabs', session_id=self._session,
                       tabs=[{'tab_id': key, 'url': page.url} for key, page in self._tabs.items()
                             if not page.is_closed()])
        self._ready()
        if action in ('navigate', 'click', 'type'):
            return await self._prepare(action, args)
        if action == 'prepare':
            copied = dict(args)
            operation = copied.pop('operation', None)
            return await self._prepare(operation, copied)
        if action == 'execute_confirmed':
            self._keys(args, {'confirmation', 'request'})
            return await self._confirmed(args)
        if action in ('inspect', 'screenshot', 'close_tab'):
            self._keys(args, {'tab_id'})
            tab_id = args.get('tab_id')
            page = self._page(tab_id)
            if action == 'close_tab':
                self._invalidate(tab_id)
                await page.close()
                return _ok('closed', tab_id=tab_id)
            if action == 'screenshot':
                data = await page.screenshot(type='png', full_page=False, timeout=5000)
                if len(data) > 10 * 1024 * 1024:
                    raise BrowserError('LIMIT', 'Screenshot exceeds the in-memory limit.')
                return _ok('screenshot', tab_id=tab_id, mime_type='image/png',
                           encoding='base64', data=base64.b64encode(data).decode('ascii'))
            return await self._inspect(tab_id, page)
        raise BrowserError('INVALID_ACTION', 'Unsupported browser action.')

    @staticmethod
    def _keys(args, allowed):
        if set(args) - allowed:
            raise BrowserError('INVALID_ARGUMENT', 'Unexpected browser arguments.')

    def _ready(self):
        if self._context is None:
            raise BrowserError('NOT_STARTED', 'Start a dedicated browser session first.')

    def _page(self, tab_id):
        if not isinstance(tab_id, str) or tab_id not in self._tabs or self._tabs[tab_id].is_closed():
            raise BrowserError('TAB_NOT_FOUND', 'Choose an open tab ID from this session.')
        return self._tabs[tab_id]

    def _claim_profile(self):
        path = self.resolver.path(self.profile, must_exist=False)
        if path.name.casefold() in ('default', 'user data', 'chrome', 'chromium') or path.name.casefold().startswith('profile '):
            raise BrowserError('UNSAFE_PROFILE', 'A dedicated automation profile is required.')
        marker = path / self.marker_name
        if path.exists():
            marker = self.resolver.path(str(marker), must_exist=False)
            try:
                identity = json.loads(marker.read_text(encoding='utf-8'))
                if identity.get('owner') != 'lumina.browser_control.v1':
                    raise ValueError()
                uuid.UUID(identity['id'])
            except (ValueError, KeyError, OSError, TypeError, AttributeError):
                raise BrowserError('UNSAFE_PROFILE', 'Existing profile lacks a valid automation identity.')
        else:
            path.mkdir(parents=True, exist_ok=False)
            identity = {'owner': 'lumina.browser_control.v1', 'id': str(uuid.uuid4())}
            marker = self.resolver.path(str(marker), must_exist=False)
            with marker.open('x', encoding='utf-8') as stream:
                json.dump(identity, stream)
        lock_path = self.resolver.path(str(path / 'LUMINA_BROWSER.lock'), must_exist=False)
        try:
            fd = self._open_windows_profile_lock(lock_path) if os.name=='nt' else os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError as exc:
            if isinstance(exc,FileExistsError) or getattr(exc,'winerror',None) in (32,33):
                raise BrowserError('PROFILE_BUSY','The automation profile is held by another process. Close that LUMINA browser session before retrying.',
                    reason='live_lock_holder',lock_source='lumina',profile=str(path),lock_path=str(lock_path)) from None
            raise BrowserError('PROFILE_LOCK_FAILED','The automation profile lock cannot be opened.',reason='lock_unavailable',os_error=getattr(exc,'winerror',exc.errno)) from None
        self._lock_fd, self._lock_path = fd, lock_path
        self._profile_path, self._profile_id = path, identity['id']

    @staticmethod
    def _open_windows_profile_lock(path):
        # Exclusive OS handle, deleted on close/crash. A legacy empty sentinel
        # is recoverable only when no other process still holds it open.
        import ctypes
        from ctypes import wintypes
        import msvcrt
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype=wintypes.HANDLE
        handle=kernel.CreateFileW(str(path),0xC0010000,0,None,4,0x04000080,None)
        if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        try:return msvcrt.open_osfhandle(handle,os.O_RDWR|os.O_BINARY)
        except Exception:
            kernel.CloseHandle.argtypes=[wintypes.HANDLE]
            kernel.CloseHandle(handle)
            raise

    async def _launch(self, path):
        from playwright.async_api import async_playwright
        self._driver = await async_playwright().start()
        # Offline from process birth prevents restored pages sending requests before
        # our routes exist. Unsupported routing APIs fail startup while still offline.
        return await self._driver.chromium.launch_persistent_context(
            str(path), headless=False, offline=True, accept_downloads=False,
            service_workers='block', viewport={'width': 1280, 'height': 800},
            args=['--disable-extensions', '--disable-background-networking',
                  '--disable-component-update', '--disable-sync', '--no-first-run'])

    async def _start(self):
        if self._context is not None:
            tab_id = next((key for key, page in self._tabs.items() if not page.is_closed()), None)
            if tab_id is None:
                tab_id = self._register(await self._context.new_page())
            return {**self.status(), 'tab_id': tab_id}
        self._claim_profile()
        self._context = await self._launch(self._profile_path)
        await self._context.route('**/*', self._route)
        await self._context.route_web_socket('**/*', lambda socket: socket.close())
        self._session = str(uuid.uuid4())
        # Never resume persisted tabs. Routing/offline cover their destruction.
        restored=list(self._context.pages)
        # Keep one owned window alive: closing the final headed page can terminate
        # Chromium before new_page, intermittently breaking startup on Windows.
        page = await self._context.new_page()
        for previous in restored:
            await previous.close()
        self._context.on('page', self._unexpected_page)
        await self._context.set_offline(False)
        tab_id = self._register(page)
        self._state = 'ready'
        return _ok('ready', session_id=self._session, tab_id=tab_id,
                   profile=str(self._profile_path), profile_id=self._profile_id, visible=True)

    def _unexpected_page(self, page):
        # Popups have no request permit. Give them stable identities for inspection.
        self._register(page)

    def _register(self, page):
        for key, value in self._tabs.items():
            if value is page:
                return key
        tab_id = str(uuid.uuid4())
        self._tabs[tab_id], self._epochs[tab_id] = page, 0
        def navigated(frame):
            if frame == page.main_frame:
                self._epochs[tab_id] += 1
                self._invalidate(tab_id)
        page.on('framenavigated', navigated)
        page.on('close', lambda: self._documents.pop(page.main_frame, None))
        page.on('download', lambda download: download.cancel())
        page.on('dialog', lambda dialog: dialog.dismiss())
        return tab_id

    async def _route(self, route):
        request = route.request
        permit = self._permit
        try:
            validate_public_url(request.url)
            if request.method not in ('GET', 'HEAD') or request.post_data is not None:
                raise ValueError('Writes are disabled')
            frame = request.frame  # Service workers have no frame and are blocked.
            document = request.is_navigation_request()
            if document:
                if not (permit and request.method == 'GET' and frame == permit['page'].main_frame):
                    raise ValueError('Unapproved navigation')
                if (permit.get('used') or request.redirected_from is not None
                        or request.url != permit['url']):
                    raise ValueError('Unapproved destination')
                permit['used'] = True
            elif (frame not in self._documents or
                  request.resource_type not in {'stylesheet', 'script', 'image', 'font', 'media', 'manifest'}):
                raise ValueError('Only document read assets are allowed')
            url = request.url
            for hop in range(10):
                validate_public_url(url)
                status, headers, body = await self._fetch_read(url, request.method)
                if status not in (301, 302, 303, 307, 308):
                    break
                url = self._navigation_url(urljoin(url, headers['location']))
                if document:
                    # Chromium bypasses routing on HTTP redirect hops, including
                    # fulfilled 3xx responses. Finish an inert document, then
                    # navigate explicitly (abort races Chromium's error page).
                    permit['redirect_url'] = url
                    await route.fulfill(status=200, content_type='text/html', body='<!doctype html><title>Redirecting</title>')
                    return
            else:
                raise ValueError('Too many redirects')
            if 300 <= status < 400 and status != 304:
                raise ValueError('Unsupported redirect')
            if 'attachment' in headers.get('content-disposition', '').lower():
                raise ValueError('Downloads are disabled')
            if document:
                self._documents[frame] = request.url
            await route.fulfill(status=status, headers=headers, body=body)
        except Exception:
            await route.abort('blockedbyclient')

    async def _fetch_read(self, url, method):
        """Pin DNS validation to the connection, including every redirect hop.

        Never use continue_ or route.fetch: Chromium's separate DNS lookup and
        automatic redirect handling would bypass the public destination check.
        Browser credentials are intentionally not forwarded to the read transport.
        """
        import aiohttp
        resolver = PublicResolver()
        try:
            connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False)
            async with aiohttp.ClientSession(connector=connector, trust_env=False,
                    cookie_jar=aiohttp.DummyCookieJar(), timeout=aiohttp.ClientTimeout(total=12)) as session:
                async with session.request(method, url, allow_redirects=False) as response:
                    body = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        body.extend(chunk)
                        if len(body) > 16 * 1024 * 1024:
                            raise ValueError('Read response exceeds limit')
                    headers = {k.lower(): v for k, v in response.headers.items()
                               if k.lower() not in {'content-encoding', 'content-length', 'refresh',
                                                    'transfer-encoding', 'connection', 'set-cookie'}}
                    return response.status, headers, bytes(body)
        finally:
            await resolver.close()

    def _invalidate(self, tab_id):
        self._snapshots = {k: v for k, v in self._snapshots.items() if v['tab_id'] != tab_id}
        self._pending = {k: v for k, v in self._pending.items() if v['request']['tab_id'] != tab_id}

    async def _identity(self, tab_id, page):
        epoch = self._epochs[tab_id]
        url = page.url
        # Bounded DOM digest also catches changed labels, values, destinations and
        # state. Input properties are included because fill need not mutate HTML.
        value = await page.evaluate('''() => {
            const html = document.documentElement?.outerHTML || '';
            if (html.length > 2000000) return null;
            const values = Array.from(document.querySelectorAll('input,textarea,select'))
                .slice(0, 2001).map(e => [e.value, e.checked, e.selectedIndex]);
            if (values.length > 2000) return null;
            return JSON.stringify([html, values]);
        }''')
        if value is None:
            raise BrowserError('LIMIT', 'Page is too large for a safe snapshot.')
        if epoch != self._epochs[tab_id] or url != page.url:
            raise BrowserError('STALE_SNAPSHOT', 'Page changed while inspecting.')
        return (url, epoch, hashlib.sha256(value.encode()).hexdigest())

    async def _inspect(self, tab_id, page):
        self._invalidate(tab_id)
        identity = await self._identity(tab_id, page)
        tree = await page.locator('body').aria_snapshot(timeout=5000)
        if identity != await self._identity(tab_id, page):
            raise BrowserError('STALE_SNAPSHOT', 'Page changed while inspecting.')
        token = str(uuid.uuid4())
        self._snapshots[token] = {'tab_id': tab_id, 'identity': identity, 'at': time.monotonic()}
        return _ok('snapshot', session_id=self._session, tab_id=tab_id, snapshot=token,
                   url=page.url, content=tree[:24000], truncated=len(tree) > 24000,
                   expires_in_seconds=self.snapshot_seconds, untrusted_content=True)

    async def _check_snapshot(self, tab_id, token):
        snapshot = self._snapshots.get(token) if isinstance(token, str) else None
        if not snapshot or snapshot['tab_id'] != tab_id or time.monotonic() - snapshot['at'] > self.snapshot_seconds:
            raise BrowserError('STALE_SNAPSHOT', 'Inspect this tab again before preparing an action.')
        page = self._page(tab_id)
        if await self._identity(tab_id, page) != snapshot['identity']:
            self._invalidate(tab_id)
            raise BrowserError('STALE_SNAPSHOT', 'Page URL, document or controls changed.')
        return page

    @staticmethod
    def _url(value):
        if not isinstance(value, str) or len(value) > 4096 or any(c.isspace() or ord(c) < 32 for c in value) or '\\' in value:
            raise BrowserError('INVALID_URL', 'An exact HTTP(S) URL is required.')
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise BrowserError('INVALID_URL', 'Use an HTTP(S) URL without credentials or a fragment.')
        # Use canonical URLs so network matching does not silently widen approval.
        if not parsed.path:
            raise BrowserError('INVALID_URL', 'Include the URL path, for example https://example.com/.')
        return value

    @staticmethod
    def _navigation_url(value):
        """Normalize domains, not search terms or guessed .com destinations."""
        try:
            if not isinstance(value, str):
                raise ValueError()
            value = value.strip()
            if '://' not in value:
                if '.' not in value.split('/')[0]:
                    raise ValueError()
                value = 'https://' + value
            validate_public_url(value)
            parts = urlsplit(value)
            if parts.username is not None or parts.password is not None:
                raise ValueError()
            host = parts.hostname.encode('idna').decode('ascii').lower().rstrip('.')
            if '%' in host or ('.' not in host and ':' not in host):
                raise ValueError()
            host = '[' + host + ']' if ':' in host else host
            port = parts.port
            authority = host if port is None or (parts.scheme, port) in {('https', 443), ('http', 80)} else f'{host}:{port}'
            return urlunsplit((parts.scheme, authority,
                              quote(parts.path or '/', safe="/%:@!$&'()*+,;=-._~"),
                              quote(parts.query, safe="/%?:@!$&'()*+,;=-._~"), ''))
        except (ValueError, UnicodeError):
            raise BrowserError('INVALID_URL', 'Use a public HTTP(S) URL or domain without credentials.') from None

    @staticmethod
    def _locator(page, spec):
        if not isinstance(spec, dict):
            raise BrowserError('INVALID_LOCATOR', 'Use an exact role/name or label locator.')
        if set(spec) == {'label'} and isinstance(spec['label'], str) and 0 < len(spec['label']) <= 500:
            return page.get_by_label(spec['label'], exact=True)
        if set(spec) == {'role', 'name'} and all(isinstance(v, str) and 0 < len(v) <= 500 for v in spec.values()):
            return page.get_by_role(spec['role'], name=spec['name'], exact=True)
        raise BrowserError('INVALID_LOCATOR', 'Use an exact role/name or label locator.')

    async def _unique(self, page, spec):
        locator = self._locator(page, spec)
        count = await locator.count()
        if count != 1:
            candidates = []
            for index in range(min(count, 10)):
                candidates.append({'index': index, 'description': (await locator.nth(index).aria_snapshot(timeout=2000))[:1000]})
            raise BrowserError('AMBIGUOUS_TARGET' if count else 'TARGET_NOT_FOUND',
                               'Choose a unique accessible control.', candidates=candidates, count=count)
        handle = await locator.element_handle(timeout=3000)
        if handle is None:
            raise BrowserError('STALE_TARGET', 'Control disappeared.')
        if await handle.evaluate("e => e.matches('input[type=file]')"):
            await handle.dispose()
            raise BrowserError('UPLOAD_DISABLED', 'File upload controls are not supported.')
        return handle

    async def _prepare(self, operation, args):
        if operation not in ('navigate', 'click', 'type'):
            raise BrowserError('INVALID_ACTION', 'Prepare supports navigate, click and type.')
        expected = {'tab_id', 'snapshot'} | ({'url'} if operation == 'navigate' else {'locator'}) | ({'text'} if operation == 'type' else set())
        if set(args) != expected:
            raise BrowserError('INVALID_ARGUMENT', 'Provide exactly the arguments required by this action.')
        tab_id, token = args['tab_id'], args['snapshot']
        page = await self._check_snapshot(tab_id, token)
        if operation == 'navigate':
            args = {**args, 'url': self._navigation_url(args['url'])}
        else:
            if operation == 'type' and (not isinstance(args['text'], str) or len(args['text']) > 10000):
                raise BrowserError('INVALID_ARGUMENT', 'Text must be a string of at most 10000 characters.')
            handle = await self._unique(page, args['locator'])
            await handle.dispose()
        # Deep copy: caller mutation must never change an approved request.
        request = json.loads(json.dumps({'operation': operation, **args}))
        confirmation = str(uuid.uuid4())
        self._pending.clear()  # Only one exact pending request per owned session.
        self._pending[confirmation] = {'request': request}
        return _ok('confirmation_required', confirmation=confirmation,
                   request=json.loads(json.dumps(request)), requires_confirmation=True)

    async def _confirmed(self, args):
        token = args.get('confirmation')
        pending = self._pending.pop(token, None) if isinstance(token, str) else None
        if not pending or args.get('request') != pending['request']:
            raise BrowserError('CONFIRMATION_MISMATCH', 'Exact pending request confirmation is required.')
        request = pending['request']
        tab_id = request['tab_id']
        page = await self._check_snapshot(tab_id, request['snapshot'])
        operation = request['operation']
        handle = None
        try:
            if operation != 'navigate':
                handle = await self._unique(page, request['locator'])
                await self._check_snapshot(tab_id, request['snapshot'])
            self._invalidate(tab_id)  # Consume before effects, including failures.
            if operation == 'navigate':
                await self._navigate(page, request['url'])
            elif operation == 'click':
                if await handle.evaluate("e => !!e.form && (e.type === 'submit' || e.type === 'image')"):
                    raise BrowserError('SUBMISSION_DISABLED', 'Form submissions are not supported.')
                if await handle.evaluate("e => e.matches('a[download]')"):
                    raise BrowserError('DOWNLOAD_DISABLED', 'Downloads are not supported.')
                href = await handle.evaluate("e => e.matches('a[href]:not([download])') ? e.href : null")
                if href:
                    # Follow the inspected link without dispatching script handlers,
                    # pings, target=_blank popups or incidental form submissions.
                    await self._navigate(page, self._navigation_url(href))
                else:
                    await handle.click(timeout=3000, no_wait_after=True)
            else:
                await handle.fill(request['text'], timeout=3000)
            return _ok('executed', operation=operation, tab_id=tab_id, url=page.url,
                       external_requests='public-read-assets-only; submissions-blocked')
        finally:
            self._permit = None
            if handle is not None:
                await handle.dispose()

    async def _navigate(self, page, url):
        self._documents.pop(page.main_frame, None)
        try:
            for _ in range(10):
                self._permit = {'url': url, 'page': page}
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=10000)
                except Exception:
                    if 'redirect_url' not in self._permit:
                        raise BrowserError('NAVIGATION_BLOCKED', 'Navigation failed or its destination was blocked.') from None
                if 'redirect_url' in self._permit:
                    url = self._permit['redirect_url']
                    continue
                if self._documents.get(page.main_frame) != page.url.split('#', 1)[0]:
                    raise BrowserError('UNEXPECTED_NAVIGATION', 'Navigation did not reach an approved public document.')
                return
            raise BrowserError('REDIRECT_LIMIT', 'Navigation exceeded the public redirect limit.')
        finally:
            self._permit = None

    async def _finish_teardown(self):
        # Cancellation cannot leave a late launch/action alive. Repeated cancellation
        # is deferred until driver stop completes; no detached cleanup task escapes.
        task = asyncio.create_task(self._teardown())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:raise asyncio.CancelledError()

    async def _teardown(self):
        self._permit = None
        context, driver = self._context, self._driver
        self._context = self._driver = None
        try:
            if context is not None:
                try:
                    await asyncio.wait_for(context.close(), 5)
                except Exception:
                    pass
        finally:
            try:
                if driver is not None:
                    await driver.stop()
            finally:
                self._tabs.clear()
                self._epochs.clear()
                self._snapshots.clear()
                self._pending.clear()
                self._documents.clear()
                self._session = None
                self._state = 'closed'
                if self._lock_fd is not None:
                    os.close(self._lock_fd)
                    self._lock_fd = None
                    if os.name!='nt':self._lock_path.unlink(missing_ok=True)
