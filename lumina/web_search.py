"""Bounded search evidence and public-page retrieval; no inference or automatic fallback."""
import asyncio
import html
from html.parser import HTMLParser
import ipaddress
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlsplit, urljoin, parse_qs

import aiohttp


def validate_public_url(url):
    if not isinstance(url, str) or not url or len(url) > 4096 or any(ord(c) < 33 for c in url) or '\\' in url:
        raise ValueError('Use a bounded public HTTP or HTTPS URL.')
    parts = urlsplit(url)
    if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password:
        raise ValueError('Only public HTTP or HTTPS URLs without credentials are supported.')
    try:
        port = parts.port
    except ValueError:
        raise ValueError('The URL port is invalid.') from None
    if port is not None and not 1 <= port <= 65535:
        raise ValueError('The URL port is invalid.')
    host = parts.hostname.lower().rstrip('.')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('Private and local web destinations are not permitted.')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return url
    if not is_public(address):
        raise ValueError('Private and local web destinations are not permitted.')
    return url


def is_public(address):
    mapped = getattr(address, 'ipv4_mapped', None)
    return (mapped or address).is_global and not address.is_multicast and not address.is_unspecified


class PublicResolver(aiohttp.abc.AbstractResolver):
    """Validate the same addresses the connector uses, preventing a second DNS lookup."""
    def __init__(self):
        self.inner = aiohttp.resolver.ThreadedResolver()

    async def resolve(self, host, port=0, family=0):
        entries = await self.inner.resolve(host, port, family)
        if not entries or any(not is_public(ipaddress.ip_address(e['host'])) for e in entries):
            raise OSError('Private and local web destinations are not permitted.')
        return entries

    async def close(self):
        await self.inner.close()


class PublicHTTP:
    async def post_json(self,url,payload,*,headers=None,limit=512000):
        """Bounded provider request; never follow a POST redirect with data."""
        validate_public_url(url)
        resolver=PublicResolver()
        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=resolver,use_dns_cache=False),
                    timeout=aiohttp.ClientTimeout(total=15),trust_env=False) as session:
                async with session.post(url,json=payload,headers=headers,allow_redirects=False) as response:
                    if 300<=response.status<400:raise ValueError('Search API redirects are not permitted.')
                    body=bytearray()
                    async for chunk in response.content.iter_chunked(16384):
                        body.extend(chunk[:max(0,limit+1-len(body))])
                        if len(body)>limit:break
                    return {'status':response.status,'body':bytes(body[:limit]),'truncated':len(body)>limit}
        finally:await resolver.close()

    async def get(self, url, *, headers=None, limit=512000):
        resolver = PublicResolver()
        connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False)
        try:
            async with aiohttp.ClientSession(connector=connector, trust_env=False,
                    timeout=aiohttp.ClientTimeout(total=12), auto_decompress=True) as session:
                async with asyncio.timeout(15):
                    for hop in range(4):
                        validate_public_url(url)
                        async with session.get(url, headers=headers, allow_redirects=False) as response:
                            if response.status in {301, 302, 303, 307, 308}:
                                location = response.headers.get('Location')
                                if hop == 3 or not location:
                                    raise ValueError('The page exceeded its redirect limit.')
                                next_url = urljoin(url, location)
                                validate_public_url(next_url)
                                if (urlsplit(next_url).scheme, urlsplit(next_url).netloc) != (urlsplit(url).scheme, urlsplit(url).netloc):
                                    headers = None  # Never forward a provider token to another host.
                                url = next_url
                                continue
                            chunks = bytearray()
                            async for chunk in response.content.iter_chunked(16384):
                                chunks.extend(chunk[:max(0, limit + 1 - len(chunks))])
                                if len(chunks) > limit:
                                    break
                            return {'url': str(response.url), 'status': response.status,
                                    'content_type': response.content_type, 'charset': response.charset or 'utf-8',
                                    'body': bytes(chunks[:limit]), 'truncated': len(chunks) > limit}
        finally:
            await resolver.close()


class SearchProvider(Protocol):
    name: str
    async def search(self, query: str, limit: int) -> list[dict]: ...


class _DDGResults(HTMLParser):
    def __init__(self):
        super().__init__(); self.results = []; self.current = None; self.field = None; self.depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs); classes = attrs.get('class', '').split()
        if tag == 'a' and 'result__a' in classes:
            if len(self.results) >= 30:
                return
            self.current = {'title': '', 'url': attrs.get('href', ''), 'snippet': '', 'published_at': None}
            self.results.append(self.current); self.field = 'title'; self.depth = 1
        elif self.current is not None and 'result__snippet' in classes:
            self.field = 'snippet'; self.depth = 1
        elif self.field:
            self.depth += 1

    def handle_endtag(self, tag):
        if self.field:
            self.depth -= 1
            if self.depth <= 0:
                self.field = None

    def handle_data(self, data):
        if self.field and self.current is not None:
            self.current[self.field] += data[:2000]


class DuckDuckGo:
    name = 'duckduckgo'
    def __init__(self, http): self.http = http
    async def search(self, query, limit):
        from urllib.parse import urlencode
        response = await self.http.get('https://html.duckduckgo.com/html/?' + urlencode({'q': query}))
        _check_response(response)
        text = response['body'].decode('utf-8', errors='replace')
        if response['status'] == 202 or 'anomaly.js' in text:
            raise SearchFailure('rate_limited', 'Search provider requested a human verification. No bypass was attempted.')
        parser = _DDGResults(); parser.feed(text)
        for entry in parser.results:
            entry['url'] = urljoin(response['url'], entry['url'])
            parts = urlsplit(entry['url'])
            if parts.hostname == 'duckduckgo.com' or (parts.hostname and parts.hostname.endswith('.duckduckgo.com')):
                entry['url'] = parse_qs(parts.query).get('uddg', [entry['url']])[0]
        if not parser.results and 'no-results' not in text and 'No results found' not in text:
            raise SearchFailure('malformed_response', 'Search provider returned an unsupported page.')
        return parser.results[:limit]


class BingRSS:
    """Zero-key public Bing RSS search; availability and relevance are best effort.

    Results are Bing snippets, not fetched page contents. No upstream fallback.
    """
    name = 'bing_rss'

    def __init__(self, http): self.http = http

    async def search(self, query, limit):
        from urllib.parse import urlencode
        response = await self.http.get('https://www.bing.com/search?' +
                urlencode({'format': 'rss', 'q': query}), headers={'Accept': 'application/rss+xml, application/xml, text/xml'})
        _check_response(response)
        if response['status'] == 202:
            raise SearchFailure('rate_limited', 'Search provider requested verification. No bypass was attempted.')
        try:
            # Decode before checking declarations so UTF-16 cannot conceal a DTD.
            # This endpoint emits UTF-8; reject other encodings rather than guessing.
            text = response['body'].decode('utf-8-sig')
            if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', text, re.I):
                raise ValueError()
            root = ET.fromstring(text)
            channel = root.find('channel')
            if root.tag != 'rss' or channel is None:
                raise ValueError()
            return [{'title': item.findtext('title'), 'url': item.findtext('link'),
                     'snippet': item.findtext('description') or '', 'published_at': None}
                    for item in channel.findall('item')[:limit]]
        except (ValueError, ET.ParseError):
            raise SearchFailure('malformed_response', 'Search provider returned invalid RSS data.') from None


class Brave:
    name = 'brave'
    def __init__(self, http, key): self.http, self.key = http, key
    async def search(self, query, limit):
        from urllib.parse import urlencode
        response = await self.http.get('https://api.search.brave.com/res/v1/web/search?' +
                urlencode({'q': query, 'count': limit}), headers={'X-Subscription-Token': self.key, 'Accept': 'application/json'})
        _check_response(response)
        try:
            body = json.loads(response['body'])
            results = body.get('web', {}).get('results', [])
            if not isinstance(results, list): raise ValueError()
            return [{'title': item['title'], 'url': item['url'], 'snippet': item.get('description', ''),
                     'published_at': None} for item in results[:limit]]
        except (ValueError, TypeError, KeyError, AttributeError):
            raise SearchFailure('malformed_response', 'Search provider returned invalid result data.') from None


class SearXNG:
    """Explicit public instance; no API key, instance discovery or paid fallback.

    Configure LUMINA_SEARCH_PROVIDER=searxng and LUMINA_SEARXNG_URL to
    an instance base URL (optionally ending in /search) with JSON enabled.
    The instance operator controls its upstream engines and their costs.
    """
    name = 'searxng'

    def __init__(self, http, url):
        validate_public_url(url)
        parts = urlsplit(url)
        if parts.query or parts.fragment:
            raise ValueError('Use an instance URL without a query or fragment.')
        self.http = http
        self.url = url.rstrip('/')
        if not self.url.endswith('/search'):
            self.url += '/search'

    async def search(self, query, limit):
        from urllib.parse import urlencode
        response = await self.http.get(self.url + '?' + urlencode({'q': query, 'format': 'json'}),
                                       headers={'Accept': 'application/json'})
        if response['status'] == 403:
            raise SearchFailure('provider_blocked', 'SearXNG refused the request; JSON search may be disabled on this instance.')
        _check_response(response)
        try:
            body = json.loads(response['body'])
            results = body['results']
            if not isinstance(results, list):
                raise ValueError()
            if not results and body.get('unresponsive_engines'):
                raise SearchFailure('provider_failed', 'SearXNG engines failed; no search evidence was returned.')
            return [{'title': item['title'], 'url': item['url'],
                     'snippet': item.get('content', ''), 'published_at': None}
                    for item in results[:limit]]
        except (ValueError, TypeError, KeyError, AttributeError):
            raise SearchFailure('malformed_response', 'Search provider returned invalid result data.') from None


class SearchFailure(Exception):
    def __init__(self, code, message): self.code = code; super().__init__(message)


class TavilyKeyless:
    """Official free keyless Search endpoint. Never reads or transmits API keys.

    Refuses quota/payment challenges without following their suggested actions.
    """
    name='tavily_keyless'
    def __init__(self,http):self.http=http
    @staticmethod
    def precise_query(query):
        # Preserve explicit phrases/operators; quote product/version identifiers
        # so 5700X does not drift to newer 9800X3D news in a price query.
        def token(match):
            word=match[0]
            if word.startswith('"') or ':' in word:return word
            return '"'+word+'"' if len(word)>=4 and re.search('[a-zA-Z]',word) and re.search('[0-9]',word) else word
        return re.sub(r'"[^"]*"|[\w:.+-]+',token,query)
    async def search(self,query,limit):
        response=await self.http.post_json('https://api.tavily.com/search',
            {'query':self.precise_query(query),'max_results':limit,'search_depth':'basic','include_answer':False,'include_raw_content':False,'topic':'general','auto_parameters':False},
            headers={'X-Tavily-Access-Mode':'keyless','X-Client-Source':'lumina'})
        if response['status']==402:
            raise SearchFailure('free_limit_reached','Free search allowance is exhausted. No payment or paid fallback was attempted.')
        _check_response(response)
        try:
            body=json.loads(response['body'])
            if body.get('error'):
                raise SearchFailure('provider_unavailable','Free search is unavailable or rate limited. No account or payment was used.')
            results=body['results']
            if not isinstance(results,list):raise ValueError()
            return [{'title':r['title'],'url':r['url'],'snippet':r.get('content',''),
                     'published_at':r.get('published_date')} for r in results[:limit]]
        except (ValueError,TypeError,KeyError,AttributeError):
            raise SearchFailure('malformed_response','Free search returned invalid result data.') from None


def _check_response(response):
    if response['status'] == 429:
        raise SearchFailure('rate_limited', 'Search provider is rate limited; try again later.')
    if response['status'] == 401:
        raise SearchFailure('authorization_required', 'Search provider authorization failed.')
    if response['status'] == 403:
        raise SearchFailure('provider_blocked', 'Search provider refused the request (HTTP 403); this does not establish an API-key problem.')
    if response['status'] >= 400:
        raise SearchFailure('provider_failed', 'Search provider could not complete the request.')
    if response['truncated']:
        raise SearchFailure('response_too_large', 'Search provider response exceeded the size limit.')


class WebSearch:
    def __init__(self, settings=None, provider=None, http=None):
        self.http = http or PublicHTTP()
        settings = settings or {}
        name = settings.get('LUMINA_SEARCH_PROVIDER', 'tavily_keyless').strip().lower()
        if name=='gemini_grounded':name='tavily_keyless' # Requested migration away from Gemini search.
        self.configured_name=name
        self.provider = provider
        self.reason = ''
        if provider is None:
            if name == 'tavily_keyless':self.provider=TavilyKeyless(self.http)
            elif name == 'duckduckgo': self.provider = DuckDuckGo(self.http)
            elif name == 'bing_rss': self.provider = BingRSS(self.http)
            elif name == 'searxng':
                try:
                    self.provider = SearXNG(self.http, settings.get('LUMINA_SEARXNG_URL', ''))
                except (ValueError, TypeError):
                    self.reason = 'Configure LUMINA_SEARXNG_URL with a public instance URL supporting JSON search.'
            elif name == 'brave' and settings.get('BRAVE_SEARCH_API_KEY'):
                self.provider = Brave(self.http, settings['BRAVE_SEARCH_API_KEY'])
            else: self.reason = 'Search is disabled or its configured provider is unavailable.'
        self._state = 'configured' if self.provider else 'unavailable'
        self._code = None
        self._semaphore = asyncio.Semaphore(2)

    def status(self):
        return {'status': self._state, 'provider': getattr(self.provider, 'name', None),
                'available': self.provider is not None, 'reason': self.reason, 'code': self._code,
                'automatic_fallback': False}

    async def search(self, query, limit=6):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 500 or type(limit) is not int or not 1 <= limit <= 10:
            return {'ok': False, 'status': 'invalid', 'error': 'Use a query of 1–500 characters and 1–10 results.'}
        if self.provider is None:
            return {'ok': False, **self.status(), 'error': self.reason}
        name = self.provider.name
        try:
            async with asyncio.timeout(18):
                async with self._semaphore:
                    raw = await self.provider.search(query.strip(), limit)
            if not isinstance(raw, list): raise ValueError()
            results = []; seen = set(); rejected = 0
            at = datetime.now(timezone.utc).isoformat()
            for item in raw[:limit]:
                try:
                    url = validate_public_url(item['url'])
                    title = item['title']; snippet = item.get('snippet', '')
                    if not isinstance(title, str) or not isinstance(snippet, str) or not title.strip(): raise ValueError()
                    if url in seen: continue
                    seen.add(url)
                    results.append({'title': html.unescape(title.strip())[:500], 'url': url,
                                    'snippet': html.unescape(re.sub('<[^>]+>', '', snippet))[:2000],
                                    'provider': name, 'retrieved_at': at, 'published_at': item.get('published_at')})
                except (ValueError, TypeError, KeyError): rejected += 1
            if raw and not results: raise ValueError()
            self._state = 'ready'; self.reason = ''; self._code = None
            tokens=set(re.findall(r'[a-z0-9]{3,}',query.casefold()))-{'the','for','and','with','search','web'}
            evidence=' '.join(item['title']+' '+item['snippet']+' '+item['url'] for item in results).casefold()
            missing=[word for word in sorted(tokens) if word not in evidence]
            warning=('No results were returned for this query.' if not results else
                     'Search results do not cover all query terms; do not infer an answer or price from unrelated links.' if missing else None)
            return {'ok': True, 'status': 'ready', 'provider': name, 'query': query.strip(),
                    'results': results, 'count': len(results), 'rejected_count': rejected,
                    'partial': bool(rejected), 'untrusted': True, 'synthesized': False,
                    'warning':warning,'unmatched_query_terms':missing}
        except asyncio.CancelledError:
            raise
        except SearchFailure as exc:
            code, error = exc.code, str(exc)
        except TimeoutError:
            code, error = 'timeout', 'Search timed out; no automatic retry was attempted.'
        except (ValueError, TypeError, KeyError, AttributeError):
            code, error = 'malformed_response', 'Search provider returned invalid results.'
        except Exception:
            code, error = 'provider_failed', 'Search is temporarily unavailable; local capabilities remain usable.'
        self._state = 'failed'; self.reason = error; self._code = code
        return {'ok': False, 'status': 'failed', 'code': code, 'error': error, 'provider': name}

    async def fetch_page(self, url):
        try:
            async with asyncio.timeout(18):
                async with self._semaphore:
                    result = await self.http.get(url)
            if result['status'] >= 400: raise ValueError('The page could not be retrieved.')
            if result['content_type'] not in {'text/html', 'text/plain', 'application/json', 'text/xml', 'application/xml'}:
                raise ValueError('That response is not a readable text page.')
            text = result['body'].decode(result['charset'], errors='replace'); title = ''
            if result['content_type'] == 'text/html':
                match = re.search(r'<title[^>]*>(.*?)</title>', text, re.I | re.S)
                title = html.unescape(re.sub('<[^>]+>', '', match[1]))[:240] if match else ''
                text = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', ' ', text, flags=re.I | re.S)
                text = ' '.join(html.unescape(re.sub('<[^>]+>', ' ', text)).split())
            return {'ok': True, 'final_url': result['url'], 'status': result['status'],
                    'content_type': result['content_type'], 'title': title, 'text': text[:20000],
                    'truncated': result['truncated'] or len(text) > 20000, 'untrusted': True}
        except asyncio.CancelledError: raise
        except (ValueError, LookupError):
            return {'ok': False, 'status': 'failed', 'error': 'That public page is invalid, blocked, or unreadable.'}
        except Exception:
            return {'ok': False, 'status': 'failed', 'error': 'Public page retrieval failed or timed out.'}

    async def close(self): pass
