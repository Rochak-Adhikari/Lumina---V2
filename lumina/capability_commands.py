"""Deterministic read/prepare commands for observed Phase Two capabilities.

No model calls, invented IDs, or direct mutation bypasses. Follow-ups use tool
evidence held by this runtime and all changes pass through the same registry.
"""
import re


class CapabilityCommands:
    def __init__(self, runtime):
        self.rt=runtime
        self.video=None
        self.window=None

    def observe(self,name,args,result):
        if not result.get('ok'):return
        if name=='youtube_video' and args.get('action') in {'metadata','transcript','summarize','open'}:
            from .youtube import video_id
            try:self.video='https://www.youtube.com/watch?v='+video_id(args.get('url',''))
            except ValueError:pass
        if name=='computer_control' and args.get('action')=='inspect':
            self.window=result.get('window')

    async def run(self,text):
        clean=text.strip(' \t\r\n“”"').rstrip('.?!');lower=clean.casefold()
        name=args=None
        if re.fullmatch(r'(?:show(?: me)?|list|check)(?: the)? status of (?:every |all )?phase [12] capabilit(?:y|ies)',lower):
            phase='1' if 'phase 1' in lower else '2'
            data=self.rt.tools.phase1_status() if phase=='1' else self.rt.tools.phase2.status()
            self.rt.message('user',text)
            lines=[key.replace('_',' ')+': '+str(value.get('status',value.get('state','unavailable'))) for key,value in data.items()]
            self.rt.broadcast({'type':'file_content','path':'Phase '+phase+' capability status','text':'\n'.join(lines)})
            self.rt.message('assistant','The current status of all five Phase '+phase+' capabilities is displayed, sir.')
            self.rt.set_state('IDLE',current_tool=None,task=None);return True
        if lower in {'list my audio endpoints','list audio endpoints','show my audio endpoints'}:
            name,args='computer_settings',{'action':'list_targets','kind':'audio'}
        elif lower in {'read my current mouse speed','read my mouse speed'}:
            name,args='computer_settings',{'action':'get','kind':'mouse_speed','target':'system'}
        elif lower in {'list controllable windows','list my windows','list windows'}:
            name,args='computer_control',{'action':'list_windows'}
        elif lower in {'list my background watches','list background watches'}:
            name,args='background_monitor',{'action':'list'}
        elif lower in {'enable proactive notifications','disable proactive notifications'}:
            name,args='proactive',{'action':'configure','enabled':lower.startswith('enable')}
        else:
            metadata=re.fullmatch(r'(?:get|show)(?: me)? metadata for\s+(\S+)',clean,re.I)
            opened=re.fullmatch(r'open\s+(this video|that video|https?://\S+)\s+in\s+(?:the\s+)?supervised\s+browser',clean,re.I)
            inspect=re.fullmatch(r'inspect\s+(?:the\s+)?(.+?)\s+window',clean,re.I)
            watch=re.fullmatch(r'(inspect|pause|resume|remove)\s+(?:that|the)\s+watch',clean,re.I)
            create_watch=re.fullmatch(r'watch\s+for\s+(.+?)\s+every\s+(\d+|one|two|five|ten|fifteen|thirty)\s+(minute|hour)s?',clean,re.I)
            if metadata:name,args='youtube_video',{'action':'metadata','url':metadata[1]}
            elif create_watch:
                numbers={'one':1,'two':2,'five':5,'ten':10,'fifteen':15,'thirty':30}
                amount=int(create_watch[2]) if create_watch[2].isdigit() else numbers[create_watch[2].lower()]
                name,args='background_monitor',{'action':'create','query':create_watch[1],'interval':amount*(60 if create_watch[3].lower()=='minute' else 3600)}
            elif opened:
                url=self.video if opened[1].casefold() in {'this video','that video'} else opened[1]
                if not url:
                    self.rt.message('assistant','Give me the video URL first, sir.');return True
                name,args='youtube_video',{'action':'open','url':url}
            elif inspect:
                result=await self.rt.handle_tool_call('computer_control',{'action':'list_windows'})
                if not result.get('ok'):self.rt.report_local_result('computer_control',result);return True
                candidates=[w for w in result.get('windows',[]) if inspect[1].casefold() in w.get('name',w.get('title','')).casefold()]
                if len(candidates)!=1:
                    self.rt.broadcast({'type':'phase2_result','tool':'computer_control','data':result})
                    self.rt.message('assistant','Choose the exact window in Automation, sir; '+str(len(candidates))+' matching windows were found.');return True
                name,args='computer_control',{'action':'inspect','window':candidates[0]['id']}
            elif lower in {'list the text fields and buttons in that window','inspect that window'}:
                if not self.window:self.rt.message('assistant','Inspect a specific window first, sir.');return True
                name,args='computer_control',{'action':'inspect','window':self.window}
            elif watch:
                result=await self.rt.handle_tool_call('background_monitor',{'action':'list'})
                watches=result.get('watches',[])
                if not result.get('ok') or len(watches)!=1:
                    self.rt.message('assistant','Choose the exact watch in Automation, sir.');return True
                name,args='background_monitor',{'action':watch[1].lower(),'id':watches[0]['id']}
            elif re.search(r'\b(?:supervised browser|phase [12] capabilit)',lower):
                # These are never application names, even when phrased differently.
                return False
        if name is None:return False
        self.rt.message('user',text)
        result=await self.rt.handle_tool_call(name,args)
        self.rt.report_local_result(name,result)
        return True
