from urllib.parse import quote
from .base import request,CommunicationError


class Discord:
    def __init__(self,settings):
        self.token=settings['DISCORD_BOT_TOKEN'];self.destination=settings.get('DISCORD_CHANNEL_ID','')
    async def api(self,method,path,payload=None):
        return await request(method,'https://discord.com/api/v10/'+path,headers={'Authorization':'Bot '+self.token},json=payload)
    async def validate(self):await self.api('GET','users/@me')
    def channel(self,destination):
        value=destination or self.destination
        if not value.isdecimal():raise CommunicationError('destination_required','Choose a configured Discord channel ID.')
        return value
    async def read(self,destination='',query=''):
        channel=self.channel(destination)
        messages=await self.api('GET',f'channels/{channel}/messages?limit=50')
        return [{'id':channel+':'+m['id'],'destination':channel,'content':m.get('content',''),'sender':m.get('author',{}).get('username',''),'date':m.get('timestamp')} for m in messages if query.casefold() in m.get('content','').casefold()]
    async def get(self,message_id):
        pieces=message_id.split(':')
        if len(pieces)!=2 or not all(p.isdecimal() for p in pieces):raise CommunicationError('invalid_id','Use the channel and message ID returned by Discord reading.')
        m=await self.api('GET',f'channels/{pieces[0]}/messages/{pieces[1]}')
        return {'id':message_id,'destination':pieces[0],'content':m.get('content',''),'sender':m.get('author',{}).get('username','')}
    async def prepare(self,destination,content,subject='',message_id=''):
        if message_id:destination=(await self.get(message_id))['destination']
        channel=self.channel(destination)
        await self.api('GET','channels/'+channel)
        if not 1<=len(content)<=2000:raise CommunicationError('invalid_content','Discord text must contain 1–2000 characters.')
        return {'destination':channel,'content':content,'message_id':message_id}
    async def send(self,destination,content,message_id=''):
        payload={'content':content,'allowed_mentions':{'parse':[]}}
        if message_id:payload['message_reference']={'message_id':message_id.split(':')[1]}
        m=await self.api('POST',f'channels/{destination}/messages',payload)
        return {'id':m['id'],'destination':destination}
