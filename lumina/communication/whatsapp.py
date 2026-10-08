import hashlib
import hmac
import json
import re
from .base import request,CommunicationError


class WhatsApp:
    def __init__(self,settings,inbox):
        self.token=settings['WHATSAPP_ACCESS_TOKEN'];self.phone=settings.get('WHATSAPP_PHONE_NUMBER_ID','');self.version=settings.get('WHATSAPP_API_VERSION','')
        self.destination=settings.get('WHATSAPP_RECIPIENT','');self.secret=settings.get('WHATSAPP_APP_SECRET','');self.verify_token=settings.get('WHATSAPP_VERIFY_TOKEN','');self.inbox=inbox
        self.billing_enabled=settings.get('WHATSAPP_ALLOW_PAID_SENDS','').lower()=='true'
    async def api(self,method,path,payload=None):
        if not re.fullmatch(r'v\d+\.\d+',self.version) or not self.phone.isdecimal():raise CommunicationError('configuration_required','Configure the supported WhatsApp Graph API version and phone-number ID.')
        return await request(method,'https://graph.facebook.com/'+self.version+'/'+path,headers={'Authorization':'Bearer '+self.token},json=payload)
    async def validate(self):await self.api('GET',self.phone+'?fields=id')
    async def read(self,destination='',query=''):
        if not self.secret:raise CommunicationError('webhook_required','WhatsApp incoming messages require a configured signed webhook relay.')
        return self.inbox.read('whatsapp',destination or self.destination,query)
    async def get(self,message_id):
        m=self.inbox.get('whatsapp',message_id)
        if not m:raise CommunicationError('not_found','WhatsApp message is not in the webhook inbox.')
        return m
    def ingest(self,raw,signature):
        if not self.secret or len(raw)>1_000_000:raise CommunicationError('invalid_webhook','Webhook could not be verified.')
        expected='sha256='+hmac.new(self.secret.encode(),raw,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,signature):raise CommunicationError('invalid_webhook','Webhook could not be verified.')
        messages=[]
        for entry in json.loads(raw).get('entry',[]):
            for change in entry.get('changes',[]):
                value=change.get('value',{})
                if value.get('metadata',{}).get('phone_number_id')!=self.phone:continue
                for m in value.get('messages',[]):messages.append({'id':m['id'],'destination':m['from'],'content':m.get('text',{}).get('body',''),'type':m.get('type'),'date':m.get('timestamp')})
        self.inbox.save('whatsapp',messages)
    async def prepare(self,destination,content,subject='',message_id=''):
        if not self.billing_enabled:raise CommunicationError('billing_not_enabled','WhatsApp sending requires explicit WHATSAPP_ALLOW_PAID_SENDS configuration because provider charges may apply.')
        if message_id:destination=(await self.get(message_id))['destination']
        destination=destination or self.destination
        if not re.fullmatch(r'\+?\d{7,15}',destination):raise CommunicationError('destination_required','Configure or supply the WhatsApp recipient number.')
        if not 1<=len(content)<=4096:raise CommunicationError('invalid_content','WhatsApp text must contain 1–4096 characters.')
        return {'destination':destination,'content':content,'message_id':message_id}
    async def send(self,destination,content,message_id=''):
        payload={'messaging_product':'whatsapp','to':destination,'type':'text','text':{'body':content}}
        if message_id:payload['context']={'message_id':message_id}
        result=await self.api('POST',self.phone+'/messages',payload)
        return {'id':result['messages'][0]['id'],'destination':destination}
