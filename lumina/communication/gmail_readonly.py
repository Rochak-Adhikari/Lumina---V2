"""Read-only Gmail with server-verified scopes and unranked inbox context."""
import asyncio
import json
from pathlib import Path
from .gmail import Gmail, _fail

READONLY='https://www.googleapis.com/auth/gmail.readonly'
IDENTITY={'openid','email','profile','https://www.googleapis.com/auth/userinfo.email',
          'https://www.googleapis.com/auth/userinfo.profile'}


class ReadonlyGmail(Gmail):
    def __init__(self,settings):
        settings=dict(settings)
        filename=settings.get('GMAIL_TOKEN_FILE')
        if filename:
            # A selected account file must never mix with another account's env tokens.
            try:
                path=Path(filename).expanduser()
                if path.stat().st_size>1_000_000:raise ValueError()
                data=json.loads(path.read_text('utf-8-sig'))
                settings={key:data[source] for key,source in (
                    ('GMAIL_ACCESS_TOKEN','token'),('GMAIL_REFRESH_TOKEN','refresh_token'),
                    ('GMAIL_CLIENT_ID','client_id'),('GMAIL_CLIENT_SECRET','client_secret'))
                    if isinstance(data.get(source),str) and data[source]}
                if not settings:raise ValueError()
            except Exception:
                raise _fail('authorization_required','Unable to load the selected Gmail OAuth token file.') from None
        self._verified_token=None
        super().__init__(settings)

    async def _authorize(self,force=False):
        await super()._authorize(force)
        if self._verified_token==self._token:return
        info=await self._request('GET','https://oauth2.googleapis.com/tokeninfo',params={'access_token':self._token})
        scopes=set(str(info.get('scope','')).split())
        if READONLY not in scopes or scopes-IDENTITY-{READONLY}:
            raise _fail('authorization_required','Authorize Gmail with gmail.readonly only; broader or unverified permissions are not accepted.')
        self._verified_token=self._token

    async def _api(self,method,path,**kwargs):
        if method!='GET':raise _fail('read_only','Gmail is read-only; sending, archiving and deletion are unavailable.')
        return await super()._api(method,path,**kwargs)

    async def prepare(self,**kwargs):
        raise _fail('read_only','Gmail is read-only; sending and replying are unavailable.')

    async def send(self,**kwargs):
        raise _fail('read_only','Gmail is read-only; sending and replying are unavailable.')

    async def review(self,query='in:inbox',page_token=''):
        if not isinstance(query,str) or len(query)>2048 or not isinstance(page_token,str):
            raise _fail('invalid_input','Invalid Gmail query or page token.')
        params={'q':query,'maxResults':20}
        if page_token:params['pageToken']=page_token
        listing=await self._api('GET','/messages',params=params)
        gate=asyncio.Semaphore(4)
        async def fetch(item):
            async with gate:
                try:
                    message=await self.get(item['id'])
                    headers=message.get('payload',{}).get('headers',[])
                    return {key:message.get(key) for key in ('id','threadId','snippet','internalDate','labelIds','content')} | {
                        'headers':headers,'content_may_be_truncated':len(message.get('content',''))>=32768}
                except Exception:return {'id':item.get('id'),'unavailable':True}
        messages=await asyncio.gather(*(fetch(item) for item in listing.get('messages',[])))
        return {'messages':messages,'count':len(messages),'next_page_token':listing.get('nextPageToken'),
                'partial':bool(listing.get('nextPageToken')) or any(m.get('unavailable') for m in messages),
                'ordering':'provider order; no importance ranking','query':query}
