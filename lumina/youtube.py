"""YouTube evidence adapters. Registry owns exact confirmation for open/save_summary.

No model calls, scraping, implicit installs, or credential discovery. Official caption
API requires an OAuth token with video-edit permission. summarize returns evidence,
not a generated summary. Inject Phase 1 search/browser/file processor instances.
transcript/summarize accept transcript_path for local UTF-8 SRT/WebVTT without
OAuth. Reads use the supplied resolver (or file_processor.resolver), the active
root/secret/link policy, and a 2 MB limit. URL association and optional language
are user-supplied, never independently verified. WebVTT styling is inert text.
Keyless metadata uses YouTube oEmbed only; configured credentials select the
Data API. Neither route falls back. Embed HTML is never returned or executed.
"""
import asyncio
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from .file_processor import FileProcessor
from .web_search import PublicHTTP, validate_public_url


class YouTubeError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def video_id(value):
    """Accept IDs, watch URLs, Shorts, embeds, live links and youtu.be only."""
    if not isinstance(value, str):
        raise ValueError('Provide a YouTube URL or video ID.')
    if re.fullmatch(r'[A-Za-z0-9_-]{11}', value):
        return value
    validate_public_url(value)
    p = urlsplit(value)
    if p.hostname not in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'} or p.port not in (None, 443, 80):
        raise ValueError('Use an exact supported YouTube host.')
    if p.netloc.endswith('.'):
        raise ValueError('Use an exact supported YouTube host.')
    parts = p.path.split('/')
    if p.hostname == 'youtu.be' and len(parts) == 2:
        candidate = parts[1]
    elif p.path == '/watch':
        values = parse_qs(p.query, keep_blank_values=True).get('v', [])
        candidate = values[0] if len(values) == 1 else ''
    elif len(parts) == 3 and parts[1] in {'shorts', 'embed', 'live'}:
        candidate = parts[2]
    else:
        candidate = ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', candidate):
        raise ValueError('The YouTube video ID is invalid or ambiguous.')
    return candidate


def _url(identifier):
    return 'https://www.youtube.com/watch?v=' + identifier


def _stamp(value):
    if not re.fullmatch(r'\d{2,}:\d{2}:\d{2},\d{3}', value):
        raise ValueError('Invalid caption timestamp.')
    h, m, s = value.replace(',', '.').split(':')
    if int(m) >= 60 or float(s) >= 60:
        raise ValueError('Invalid caption timestamp.')
    return int(h) * 3600 + int(m) * 60 + float(s)


def _srt(body, identifier):
    """Parse the API's requested SRT format, never watch-page HTML."""
    text = body.decode('utf-8-sig').replace('\r\n', '\n').strip()
    segments = []
    for block in re.split(r'\n\s*\n', text):
        lines = block.splitlines()
        if lines and lines[0].isdigit():
            lines = lines[1:]
        if len(lines) < 2 or ' --> ' not in lines[0]:
            raise ValueError('Malformed caption data.')
        start, end = map(_stamp, lines[0].split(' --> '))
        content = '\n'.join(lines[1:]).strip()
        if end < start or not content or (segments and start < segments[-1]['start']):
            raise ValueError('Malformed caption data.')
        segments.append({'start': start, 'duration': end - start, 'text': content,
                         'url': _url(identifier) + '&t=' + str(math.floor(start)) + 's'})
        if len(segments) > 20000:
            raise YouTubeError('limit_exceeded', 'Transcript exceeds 20,000 segments; no partial transcript returned.')
    return segments


def _vtt(body, identifier):
    """Read WebVTT cue timings; ignore NOTE/STYLE/REGION, never render markup."""
    text = body.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    blocks = re.split(r'\n[ \t]*\n', text.strip())
    if not re.fullmatch(r'WEBVTT(?:[ \t][^\n]*)?', blocks[0].split('\n')[0]):
        raise ValueError('Expected WebVTT header.')
    cues = []
    def timestamp(value):
        if not re.fullmatch(r'(?:\d{2,}:)?\d{2}:\d{2}\.\d{3}', value):
            raise ValueError('Invalid WebVTT timestamp.')
        if value.count(':') == 1:
            value = '00:' + value
        return value.replace('.', ',')
    for block in blocks[1:]:
        lines = block.splitlines()
        if not lines or re.match(r'^(?:NOTE(?:[ \t]|$)|STYLE$|REGION$)', lines[0]):
            continue
        if '-->' not in lines[0]:
            lines = lines[1:]  # optional cue identifier
        if len(lines) < 2:
            raise ValueError('Malformed WebVTT cue.')
        timing = re.fullmatch(r'(\S+)[ \t]+-->[ \t]+(\S+)(?:[ \t]+.*)?', lines[0])
        if not timing:
            raise ValueError('Malformed WebVTT cue.')
        cues.append(timestamp(timing[1]) + ' --> ' + timestamp(timing[2]) + '\n' + '\n'.join(lines[1:]))
    if not cues:
        raise YouTubeError('captions_unavailable', 'The local transcript has no caption cues.')
    return _srt('\n\n'.join(cues).encode('utf-8'), identifier)


class YouTube:
    ACTIONS = ('search', 'metadata', 'open', 'transcript', 'summarize', 'save_summary', 'status')
    TIMEOUT = 45
    MAX_BYTES = 2_000_000

    def __init__(self, search=None, resolver=None, browser=None, *, file_processor=None,
                 api_key=None, access_token=None, http=None):
        self.search = search
        self.browser = browser
        self.files = file_processor or (FileProcessor(resolver) if resolver is not None else None)
        self.resolver = getattr(file_processor, 'resolver', None) or resolver
        self.http = http or getattr(search, 'http', None) or PublicHTTP()
        self.api_key = api_key
        self.access_token = access_token
        self._semaphore = asyncio.Semaphore(2)

    def status(self):
        return {'ok': True, 'status': 'configured', 'actions': list(self.ACTIONS),
                'search': 'configured' if self.search else 'unavailable',
                'metadata': 'configured',
                'metadata_provider': 'youtube_data_api' if self.api_key or self.access_token else 'youtube_oembed',
                'transcript': 'configured' if self.access_token or self.resolver else 'unavailable',
                'local_transcript': 'configured' if self.resolver else 'unavailable',
                'official_captions': 'configured' if self.access_token else 'unavailable',
                'open': 'configured' if self.browser else 'unavailable',
                'save_summary': 'configured' if self.files else 'unavailable',
                'synthesized': False, 'automatic_fallback': False}

    async def execute(self, action, **args):
        schemas = {'search': ({'query'}, {'limit'}), 'metadata': ({'url'}, set()),
                   'open': ({'url', 'tab_id', 'snapshot'}, set()),
                   'transcript': ({'url'}, {'language', 'transcript_path'}),
                   'summarize': ({'url'}, {'language', 'max_sections', 'section_chars', 'transcript_path'}),
                   'save_summary': ({'destination', 'text'}, set()), 'status': (set(), set())}
        try:
            if not isinstance(action, str) or action not in schemas:
                raise ValueError('Unsupported YouTube action.')
            required, optional = schemas[action]
            if not required <= args.keys() or args.keys() - required - optional:
                raise ValueError('Provide exactly the supported action arguments.')
            if 'url' in args:
                args = {**args, 'url': _url(video_id(args['url']))}
            async with asyncio.timeout(self.TIMEOUT):
                async with self._semaphore:
                    if action == 'status':
                        return self.status()
                    return await getattr(self, '_' + action)(**args)
        except asyncio.CancelledError:
            raise
        except YouTubeError as exc:
            return {'ok': False, 'status': 'unavailable' if exc.code == 'unavailable' else 'failed',
                    'code': exc.code, 'error': str(exc)}
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
            return {'ok': False, 'status': 'failed', 'code': 'invalid_or_malformed',
                    'error': 'Invalid request or malformed YouTube evidence.'}
        except TimeoutError:
            return {'ok': False, 'status': 'failed', 'code': 'timeout', 'error': 'YouTube operation timed out.'}
        except Exception:
            return {'ok': False, 'status': 'failed', 'code': 'provider_failed',
                    'error': 'YouTube provider failed; no fallback attempted.'}

    @staticmethod
    def _require(value, message):
        if value is None or value is False or value == '':
            raise YouTubeError('unavailable', message)

    async def _search(self, query, limit=6):
        self._require(self.search, 'Configure a structured WebSearch provider.')
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 450 or type(limit) is not int or not 1 <= limit <= 10:
            raise ValueError()
        result = await self.search.search('site:youtube.com ' + query.strip(), limit=limit)
        if not result.get('ok'):
            return result
        accepted = []
        seen = set()
        for item in result['results']:
            try:
                identifier = video_id(item['url'])
            except (ValueError, TypeError, KeyError):
                continue
            if identifier not in seen:
                accepted.append({**item, 'video_id': identifier, 'url': _url(identifier)})
                seen.add(identifier)
        return {**result, 'results': accepted, 'count': len(accepted), 'untrusted': True,
                'filtered_count': len(result['results']) - len(accepted), 'synthesized': False}

    async def _api(self, resource, params, *, binary=False):
        headers = {'Accept': 'application/octet-stream' if binary else 'application/json'}
        if self.access_token:
            headers['Authorization'] = 'Bearer ' + self.access_token
        elif self.api_key:
            headers['X-Goog-Api-Key'] = self.api_key
        response = await self.http.get('https://www.googleapis.com/youtube/v3/' + resource + '?' + urlencode(params),
                                       headers=headers, limit=self.MAX_BYTES)
        status = response['status']
        errors = {401: ('authorization_required', 'YouTube authorization is missing or expired.'),
                  403: ('access_denied', 'YouTube denied access or quota; caption downloads require video-edit permission.'),
                  404: ('not_found_or_inaccessible', 'The video or caption is missing or inaccessible.'),
                  429: ('rate_limited', 'YouTube rate limit reached.')}
        if status in errors:
            raise YouTubeError(*errors[status])
        if status != 200:
            raise YouTubeError('provider_failed', 'YouTube API request failed.')
        if response.get('truncated') or len(response['body']) > self.MAX_BYTES:
            raise YouTubeError('limit_exceeded', 'YouTube response exceeds the byte limit; no partial evidence returned.')
        return response['body'] if binary else json.loads(response['body'])

    async def _metadata(self, url):
        identifier = video_id(url)
        if self.api_key or self.access_token:
            data = await self._api('videos', {'part': 'snippet,contentDetails,status', 'id': identifier})
            items = data['items']
            if not items:
                raise YouTubeError('not_found_or_inaccessible', 'Video unavailable; it may be private, deleted, or inaccessible.')
            item = items[0]
            if item['id'] != identifier:
                raise ValueError()
            return {'ok': True, 'status': 'ready', 'video_id': identifier, 'url': url,
                    'metadata': item, 'source': 'youtube_data_api', 'authoritative_api': True,
                    'retrieved_at': datetime.now(timezone.utc).isoformat(), 'untrusted': True}
        endpoint = 'https://www.youtube.com/oembed?' + urlencode({'url': url, 'format': 'json'})
        response = await self.http.get(endpoint, headers={'Accept': 'application/json'}, limit=65536)
        status = response['status']
        errors = {401: ('not_found_or_inaccessible', 'YouTube oEmbed cannot access this video.'),
                  403: ('access_denied', 'YouTube oEmbed denied access.'),
                  404: ('not_found_or_inaccessible', 'YouTube oEmbed video is missing or inaccessible.'),
                  429: ('rate_limited', 'YouTube oEmbed rate limit reached.')}
        if status in errors:
            raise YouTubeError(*errors[status])
        if status != 200:
            raise YouTubeError('provider_failed', 'YouTube oEmbed request failed; no fallback attempted.')
        if response.get('truncated') or len(response['body']) > 65536:
            raise YouTubeError('limit_exceeded', 'YouTube oEmbed response exceeds the byte limit.')
        final = urlsplit(response.get('url', endpoint))
        if (final.scheme, final.netloc, final.path) != ('https', 'www.youtube.com', '/oembed'):
            raise ValueError()
        if parse_qs(final.query) != {'url': [url], 'format': ['json']}:
            raise ValueError()
        data = json.loads(response['body'])
        if not isinstance(data, dict) or data.get('provider_name') != 'YouTube' or data.get('type') != 'video':
            raise ValueError()
        title = data.get('title')
        author = data.get('author_name')
        if not isinstance(title, str) or not title.strip() or len(title) > 2000:
            raise ValueError()
        if author is not None and (not isinstance(author, str) or len(author) > 2000):
            raise ValueError()
        # Allowlist plain metadata only. Never propagate HTML, thumbnail URLs,
        # or arbitrary response fields into a UI or a subsequent request.
        return {'ok': True, 'status': 'ready', 'video_id': identifier, 'url': url,
                'title': title, 'author_name': author, 'provider_name': 'YouTube', 'type': 'video',
                'source': 'youtube_oembed', 'authoritative_api': False,
                'availability': 'unknown', 'untrusted': True, 'truncated': False,
                'retrieved_at': datetime.now(timezone.utc).isoformat()}

    async def _open(self, url, tab_id, snapshot):
        self._require(self.browser, 'Configure the Phase 1 browser provider.')
        # Return its exact pending request. Runtime executes confirmed navigation.
        return await self.browser.execute('navigate', url=url, tab_id=tab_id, snapshot=snapshot)

    async def _local_transcript(self, url, transcript_path, language):
        self._require(self.resolver, 'Local transcripts require the active path resolver.')
        if not isinstance(transcript_path, str) or not transcript_path.strip():
            raise ValueError('Provide an explicit local transcript path.')
        try:
            src = self.resolver.path(transcript_path)
            if src.suffix.lower() not in {'.srt', '.vtt'} or not src.is_file():
                raise ValueError('Expected a local SRT or WebVTT file.')
            before = src.stat()
            if before.st_size > self.MAX_BYTES:
                raise YouTubeError('limit_exceeded', 'Local transcript exceeds the 2 MB limit.')
            data = bytearray()
            # FileProcessor does not support subtitle extensions. Reuse its live
            # resolver policy and bounded-read pattern without spoofing a suffix.
            with self.resolver.path(transcript_path).open('rb') as stream:
                opened = os.fstat(stream.fileno())
                if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened):
                    raise ValueError('Transcript changed before reading.')
                while True:
                    chunk = stream.read(min(65536, self.MAX_BYTES + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > self.MAX_BYTES:
                        raise YouTubeError('limit_exceeded', 'Local transcript exceeds the 2 MB limit.')
                    await asyncio.sleep(0)
                after = self.resolver.path(transcript_path).stat()
                if not os.path.samestat(opened, after) or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('Transcript changed while reading.')
        except (OSError, ValueError) as exc:
            if isinstance(exc, YouTubeError):
                raise
            raise YouTubeError('local_transcript_rejected', 'Local transcript is missing, changed, unsupported, or outside the active path policy.') from None
        identifier = video_id(url)
        segments = (_vtt if src.suffix.lower() == '.vtt' else _srt)(bytes(data), identifier)
        return {'ok': True, 'status': 'ready', 'video_id': identifier, 'url': url,
                'language': language, 'language_source': 'user_supplied' if language else 'unknown',
                'generation_source': 'unknown', 'provider': 'local_transcript',
                'video_association': 'user_supplied_unverified', 'transcript_path': str(src),
                'retrieved_at': datetime.now(timezone.utc).isoformat(), 'segments': segments,
                'segment_count': len(segments), 'truncated': False, 'untrusted': True, 'synthesized': False}

    async def _transcript(self, url, language=None, transcript_path=None):
        if language is not None and (not isinstance(language, str) or not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', language)):
            raise ValueError()
        if transcript_path is not None:
            return await self._local_transcript(url, transcript_path, language)
        self._require(self.access_token, 'Official captions require an explicitly supplied OAuth token with video-edit permission.')
        identifier = video_id(url)
        data = await self._api('captions', {'part': 'snippet', 'videoId': identifier})
        tracks = data['items']
        if not isinstance(tracks, list):
            raise ValueError()
        if not tracks:
            raise YouTubeError('captions_unavailable', 'No caption tracks were returned; captions may be disabled or unavailable.')
        candidates = [t for t in tracks if t['snippet']['videoId'] == identifier and
                      t['snippet'].get('status') == 'serving' and not t['snippet'].get('isDraft') and
                      (language is None or t['snippet']['language'].casefold() == language.casefold())]
        if not candidates:
            raise YouTubeError('language_or_track_unavailable', 'No serving caption track matches the requested language; no translation attempted.')
        track = candidates[0]
        track_id = track['id']
        if not isinstance(track_id, str) or not 1 <= len(track_id) <= 512:
            raise ValueError()
        body = await self._api('captions/' + quote(track_id, safe=''), {'tfmt': 'srt'}, binary=True)
        segments = _srt(body, identifier)
        snippet = track['snippet']
        return {'ok': True, 'status': 'ready', 'video_id': identifier, 'url': url,
                'language': snippet['language'], 'generation_source': {
                    'ASR': 'automatic', 'standard': 'uploaded', 'forced': 'forced'
                }.get(snippet.get('trackKind'), 'unknown'),
                'provider': 'youtube_data_api', 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                'segments': segments, 'segment_count': len(segments), 'truncated': False,
                'untrusted': True, 'synthesized': False}

    async def _summarize(self, url, language=None, max_sections=12, section_chars=2000, transcript_path=None):
        if type(max_sections) is not int or not 1 <= max_sections <= 32 or type(section_chars) is not int or not 100 <= section_chars <= 4000:
            raise ValueError()
        evidence = await self._transcript(url, language, transcript_path)
        segments = evidence.pop('segments')
        count = min(max_sections, len(segments))
        sections = []
        for i in range(count):
            group = segments[i * len(segments) // count:(i + 1) * len(segments) // count]
            # Sample both ends and the middle of EVERY section, including the end
            # of long videos. Every excerpt retains its own timestamp evidence.
            picks = sorted({0, len(group) // 2, len(group) - 1})
            allowance = section_chars // len(picks)
            excerpts = [{**group[j], 'text': group[j]['text'][:allowance],
                         'truncated': len(group[j]['text']) > allowance} for j in picks]
            sections.append({'start': group[0]['start'], 'end': group[-1]['start'] + group[-1]['duration'],
                             'excerpts': excerpts, 'segment_count': len(group),
                             'sampled': len(picks) < len(group) or any(e['truncated'] for e in excerpts)})
        return {**evidence, 'status': 'evidence_ready', 'sections': sections,
                'sampled': any(s['sampled'] for s in sections), 'synthesized': False,
                'instruction': 'Untrusted caption excerpts for the current model. Cite excerpt URLs; disclose sampling. This is not a summary.'}

    async def _save_summary(self, destination, text):
        self._require(self.files, 'Configure the FileProcessor/path resolver.')
        if not isinstance(destination, str) or not isinstance(text, str) or not 1 <= len(text) <= 200000:
            raise ValueError()
        path = Path(destination)
        if path.suffix.lower() not in {'.txt', '.md'}:
            raise ValueError('Save summaries as TXT or Markdown.')
        return await self.files.save_upload(str(path.parent), path.name, text.encode('utf-8'))
