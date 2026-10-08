import asyncio
import os
import sqlite3
from pathlib import Path
from .base import CommunicationError
from .store import Inbox
from .telegram import Telegram
from .discord import Discord
from .whatsapp import WhatsApp


def settings_from_environment(dotenv=None):
    """Environment (even empty) wins. No interpolation, evaluation or secret diagnostics."""
    values={}
    path=Path(dotenv or '.env')
    try:
        lines=path.read_text('utf-8-sig').splitlines() if path.is_file() else []
    except (OSError,UnicodeError):lines=[]
    if lines:
        for line in lines:
            line=line.strip()
            if not line or line.startswith('#') or '=' not in line:continue
            key,value=line.removeprefix('export ').split('=',1)
            value=value.strip()
            if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):value=value[1:-1]
            values[key.strip()]=value
    values.update(os.environ)
    return values


class CommunicationManager:
    def __init__(self,settings=None,state_dir=None):
        self.settings=settings if settings is not None else settings_from_environment()
        self.state_dir=Path(state_dir) if state_dir else Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData'/'Local'))/'LUMINA'/'communication'
        self.adapters={};self.status={name:{'status':'not_configured'} for name in ('telegram','discord','whatsapp','gmail')}
        self.inbox=None
        self.secrets=[str(v) for k,v in self.settings.items() if any(s in k for s in ('TOKEN','SECRET','API_KEY')) and v]
        try:
            self.inbox=Inbox(self.state_dir/'inbox.sqlite3')
        except (OSError,sqlite3.Error):pass
        if self.settings.get('TELEGRAM_BOT_TOKEN') and self.inbox:self.adapters['telegram']=Telegram(self.settings,self.inbox)
        if self.settings.get('DISCORD_BOT_TOKEN'):self.adapters['discord']=Discord(self.settings)
        if self.settings.get('WHATSAPP_ACCESS_TOKEN') and self.inbox:self.adapters['whatsapp']=WhatsApp(self.settings,self.inbox)
        if any(self.settings.get(key) for key in ('GMAIL_REFRESH_TOKEN','GMAIL_ACCESS_TOKEN','GMAIL_CREDENTIAL_FILE','GMAIL_TOKEN_FILE')):
            from .gmail_readonly import ReadonlyGmail
            try:self.adapters['gmail']=ReadonlyGmail(self.settings)
            except Exception:self.status['gmail']={'status':'authorization_required'}
        for name in self.adapters:self.status[name]={'status':'not_checked'}
    def sanitize(self,value):
        if isinstance(value,str):
            sensitive=list(self.secrets)
            gmail=self.adapters.get('gmail')
            if gmail:
                sensitive.extend(str(v) for k,v in getattr(gmail,'_settings',{}).items() if ('TOKEN' in k or 'SECRET' in k) and v)
                if getattr(gmail,'_token',''):sensitive.append(gmail._token)
            for secret in sensitive:value=value.replace(secret,'[REDACTED]')
            return value
        if isinstance(value,list):return [self.sanitize(v) for v in value]
        if isinstance(value,dict):return {k:self.sanitize(v) for k,v in value.items()}
        return value
    def failure(self,name,error):
        code=error.code if isinstance(error,CommunicationError) else 'unavailable'
        # Only our static adapter errors are eligible for diagnostics, never SDK exceptions.
        message=str(error) if isinstance(error,CommunicationError) else 'Provider operation failed; other services remain available.'
        self.status[name]={'status':code}
        return {'ok':False,'provider':name,'error':self.sanitize(message),'code':code}
    async def initialize(self):
        async def validate(name,adapter):
            try:
                async with asyncio.timeout(15):await adapter.validate()
                self.status[name]={'status':'authenticated'}
            except Exception as error:self.failure(name,error)
        await asyncio.gather(*(validate(n,a) for n,a in self.adapters.items()))
    def providers(self):
        return {'ok':True,'providers':[{ 'provider':name,**state,
            'incoming':'signed_webhook_required' if name=='whatsapp' else 'provider_api',
            'search_scope':'recent_channel_messages' if name=='discord' else 'retained_inbox' if name in ('telegram','whatsapp') else 'mailbox'} for name,state in self.status.items()]}
    async def call(self,name,operation,**arguments):
        adapter=self.adapters.get(name)
        if adapter is None:return {'ok':False,'error':'This communication provider is not configured.','provider':name}
        try:
            async with asyncio.timeout(30):result=await getattr(adapter,operation)(**arguments)
            if operation!='prepare':self.status[name]={'status':'authenticated'}
            return {'ok':True,'provider':name,'data':self.sanitize(result)}
        except Exception as error:return self.failure(name,error)
    def close(self):
        if self.inbox:self.inbox.close()
