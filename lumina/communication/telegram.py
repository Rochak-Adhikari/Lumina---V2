from .base import request,CommunicationError


class Telegram:
    def __init__(self,settings,inbox):
        self.token=settings['TELEGRAM_BOT_TOKEN'];self.destination=settings.get('TELEGRAM_CHAT_ID','');self.inbox=inbox
    async def api(self,method,payload=None):
        result=await request('POST','https://api.telegram.org/bot'+self.token+'/'+method,json=payload or {})
        if not result.get('ok'):raise CommunicationError('request_rejected','Telegram rejected this operation.')
        return result['result']
    async def validate(self):await self.api('getMe')
    async def read(self,destination='',query=''):
        updates=await self.api('getUpdates',{'offset':self.inbox.offset('telegram'),'timeout':0,'limit':100,'allowed_updates':['message','channel_post']})
        messages=[];offset=self.inbox.offset('telegram')
        for update in updates:
            offset=max(offset,update['update_id']+1)
            m=update.get('message') or update.get('channel_post')
            if m:messages.append({'id':str(m['chat']['id'])+':'+str(m['message_id']),'destination':str(m['chat']['id']),'content':m.get('text',m.get('caption','')),'sender':m.get('from',{}).get('first_name',''),'date':m.get('date'),'chat_name':m['chat'].get('title','')})
        self.inbox.save('telegram',messages,offset)
        return self.inbox.read('telegram',destination or self.destination,query)
    async def get(self,message_id):
        m=self.inbox.get('telegram',message_id)
        if not m:raise CommunicationError('not_found','Telegram message is not in the retained bot inbox.')
        return m
    async def prepare(self,destination,content,subject='',message_id=''):
        if message_id:destination=(await self.get(message_id))['destination']
        destination=destination or self.destination
        if not destination:raise CommunicationError('destination_required','Choose a Telegram chat.')
        if not 1<=len(content)<=4096:raise CommunicationError('invalid_content','Telegram text must contain 1–4096 characters.')
        chat=await self.api('getChat',{'chat_id':destination})
        return {'destination':str(chat['id']),'content':content,'message_id':message_id}
    async def send(self,destination,content,message_id=''):
        payload={'chat_id':destination,'text':content}
        if message_id:payload['reply_parameters']={'message_id':int(message_id.rsplit(':',1)[1])}
        result=await self.api('sendMessage',payload)
        return {'id':str(result['message_id']),'destination':destination}
