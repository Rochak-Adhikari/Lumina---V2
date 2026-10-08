import asyncio
import aiohttp


class CommunicationError(Exception):
    def __init__(self, code, message):
        self.code=code
        super().__init__(message)


async def request(method,url,headers=None,params=None,json=None,data=None):
    """One bounded attempt. Never replay ambiguous external sends or echo API errors."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
            async with session.request(method,url,headers=headers,params=params,json=json,data=data,allow_redirects=False) as response:
                if response.status==429:raise CommunicationError('rate_limited','Provider rate limit reached. Wait before retrying; this action was not retried.')
                if response.status==401:raise CommunicationError('authorization_required','Provider authorization is invalid or expired.')
                if response.status==403:raise CommunicationError('permission_denied','Provider denied access to this account or destination.')
                if response.status>=500:raise CommunicationError('unavailable','Provider unavailable. Delivery may be uncertain for a send; check before retrying.')
                if not 200<=response.status<300:raise CommunicationError('request_rejected','Provider rejected the request or destination.')
                raw=bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    raw.extend(chunk)
                    if len(raw)>2_000_000:raise CommunicationError('too_large','Provider response exceeded the safe size limit.')
                import json as codec
                return codec.loads(raw)
    except CommunicationError:raise
    except (aiohttp.ClientError,asyncio.TimeoutError):
        raise CommunicationError('connection_failed','Provider connection failed. Delivery may be uncertain for a send; check before retrying.') from None
    except (ValueError,TypeError):raise CommunicationError('invalid_response','Provider returned an invalid response.') from None
