import {setupAutomation} from './automation.js';
import {setupContinuity} from './continuity.js';
import {ReferenceOrb as Orb} from './reference-orb.js';
import {EnvironmentGraph,branchColor} from './graph.js';
import {BrowserAudio} from './audio.js';
import {setupDevices,microphoneError} from './devices.js';
import {setupControls} from './controls.js';
import {VoiceActivity} from './voice.js';
import {ConversationLease} from './call.js';
import {setupTelemetry} from './telemetry.js';
import {setupScreenShare} from './screen-share.js';

const $=id=>document.getElementById(id);
let config,ws,orb,environment,currentState,graphRevision=-1,messageSignature='',recording=false,micPending=false,connected=false,reconnectTimer,graphPromise=null;
let selectedPath='',noticeTimer;
const transcript={user:'',assistant:''};
function notice(text){$('notice').textContent=text;$('notice').hidden=false;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>$('notice').hidden=true,8000);}
function send(data){if(ws?.readyState!==WebSocket.OPEN){notice('The local runtime is disconnected. Reconnecting.');return false;}ws.send(data instanceof ArrayBuffer?data:JSON.stringify(data));return true;}
const audio=new BrowserAudio(send);const controls=setupControls({send,notice,getConfig:()=>config,prepareAudio:()=>audio.initialize()});
setupAutomation({getConfig:()=>config,notice});
setupContinuity({getConfig:()=>config,notice});
const screenShare=setupScreenShare({getConfig:()=>config,notice,prepareAudio:()=>audio.initialize()});
async function analysisEvent(message){
  if(message.type==='client_ready'){config.client_id=message.client_id;send({type:'spoken_setting',enabled:$('spoken').checked});return;}
  if(message.type==='analysis_progress'){$('live-transcript').textContent=message.stage==='processing'?'Processing your file…':'Analyzing…';return;}
  if(message.type==='analysis_transcript'){$('live-transcript').textContent=($('live-transcript').dataset.analysis===String(message.speech_id)?$('live-transcript').textContent:'')+message.text;$('live-transcript').dataset.analysis=String(message.speech_id);return;}
  if(message.type==='analysis_audio'&&$('spoken').checked&&!turnPending&&!audio.capturing){await audio.play(message);return;}
  if(message.type==='analysis_complete'){audio.complete(message.speech_id);$('live-transcript').textContent='';}
}
window.addEventListener('lumina-event',event=>{analysisEvent(event.detail).catch(error=>{audio.interrupt();notice(error.message);send({type:'audio_error'});});});
$('spoken').addEventListener('change',()=>send({type:'spoken_setting',enabled:$('spoken').checked}));
setupTelemetry(audio);
let vad=null,listenTimer,callLease=null,turnPending=false,answerStartedAt=0,turnStartedAt=0;
audio.onPlaybackStart=()=>{answerStartedAt=performance.now();};
audio.onPlaybackEnd=()=>{callLease?.answered(answerStartedAt);};
function closeCall(){send({type:'voice_stop'});audio.interrupt();stopMic();}
function armTurn(){vad=new VoiceActivity(()=>{
  callLease?.speech();turnStartedAt=performance.now();turnPending=true;audio.interrupt();
  send({type:'speech_start',started_at:turnStartedAt});
},finishTurn,()=>audio.sources.size?.055:.012);audio.onPCM=chunk=>vad?.feed(chunk);}
function microphoneReady(){audio.monitoring=true;recording=true;micPending=false;callLease=new ConversationLease(closeCall);armTurn();
 listenTimer=setInterval(()=>callLease?.tick(),100);$('mic').disabled=false;$('mic').classList.add('recording');setMicLabel(true);$('mic').setAttribute('aria-pressed','true');$('mic-hint').textContent='Listening · microphone on';}
function setMicLabel(active){const label=active?'End call':'Talk to LUMINA';$('mic').querySelector('.mic-label').textContent=label;$('mic').setAttribute('aria-label',label);$('mic').title=label;}
const headlines={IDLE:['Here. At your command.','Your space, a little more connected.'],LISTENING:['I am listening.','Finish speaking when you are ready.'],THINKING:['One moment.','Working through your request.'],EXECUTING:['Looking through your files.','Only within your configured folder.'],SPEAKING:['Here is what I found.','You can interrupt me at any time.'],INTERRUPTED:['You have my attention.','Ready when you are.'],WAITING_FOR_USER:['Ready for your next move.','Local capabilities remain available.'],ERROR:['A connection needs attention.','Local capabilities remain available.']};
function selectNode(node){if(node.record_id){window.dispatchEvent(new CustomEvent('lumina-event',{detail:{type:'continuity_inspect',id:node.record_id}}));return;}selectedPath=node.path;$('selection-type').textContent=node.type==='folder'?'Folder':'File';$('selection-name').textContent=node.filename;$('selection-path').textContent=node.path;$('selection').hidden=false;}
function renderState(state){
  currentState=state;controls.state(state);orb?.setState(state.state);$('state-tag').textContent=state.state.toLowerCase().replaceAll('_',' ');
  const [headline,subline]=headlines[state.state]||headlines.IDLE;$('headline').textContent=headline;$('subline').textContent=subline;
  $('connection').textContent=state.provider_status==='local'?'Local mode':state.provider_status==='connected'?'Online provider connected':state.provider_status==='connecting'?'Connecting online':'Online provider unavailable';
  $('runtime-health').textContent='connected';$('connection-dot').classList.remove('offline');
  $('footer-mode').textContent=state.current_tool?`Running ${state.current_tool}`:config.provider==='local'?'Local tools only.':'Local permissions enforced. No automatic fallback.';
  const signature=JSON.stringify(state.messages);if(signature!==messageSignature&&state.messages.length){messageSignature=signature;$('conversation').replaceChildren();for(const message of state.messages){const article=document.createElement('article');article.className=message.role;const author=document.createElement('span');author.className='message-author';author.textContent=message.role==='user'?(config.user_name||'You'):message.role==='local'?'Local search':message.role==='system'?'Runtime':config.assistant_name;const p=document.createElement('p');p.textContent=message.text;article.append(author,p);$('conversation').append(article);}$('conversation').scrollTop=$('conversation').scrollHeight;}
  if(graphRevision<0)loadGraph();
  const result=state.last_tool_result;if(result?.ok&&Array.isArray(result.results)&&result.results.every(item=>typeof item.filename==='string'&&typeof item.path==='string')){$('results').replaceChildren();for(const item of result.results.slice(0,25)){const button=document.createElement('button');button.className='result';button.textContent=`${item.type==='folder'?'▱':'▤'} ${item.filename} ${item.match_type}`;button.onclick=()=>selectNode(item);$('results').append(button);}}
}
async function loadGraph(){if(graphPromise)return graphPromise;graphPromise=(async()=>{try{const requested=$('graph-source').value;const response=await fetch('/api/knowledge?source='+requested,{headers:{'X-Lumina-Token':config.token}});if(!response.ok)throw Error();const data=await response.json();if(requested!==$('graph-source').value)return;const counts=environment?.update(data);graphRevision=currentState?.graph_revision||0;$('node-count').textContent=counts?`${counts.drawn} of ${counts.total} nodes${counts.trimmed?' — trimmed to best-connected nodes':''}`:'0 concepts';if(!environment?.searchQuestion)$('search-summary').textContent=data.unavailable?'This graph source is unavailable.':`${data.source==='continuity'?'Canonical memory · evidence-backed · ':'Notes · '}Stable neon colours identify concepts; edge colours identify relations.${data.truncated?' Bounded projection; some records omitted.':''}`;$('legend').textContent=[...new Set((data.edges||[]).map(e=>e.relation||e.type))].join(' · ');}catch{notice('The knowledge graph could not load.');}finally{graphPromise=null;}})();return graphPromise;}
$('graph-source').onchange=async()=>{if(graphPromise)await graphPromise;loadGraph();};
$('graph-inspect').onchange=()=>{const node=environment?.nodes.find(n=>n.id===$('graph-inspect').value);if(node)selectNode(node);};
const knowledgeRefresh=setInterval(()=>{if(config&&connected&&!document.hidden)loadGraph();},15000);
window.addEventListener('pagehide',()=>clearInterval(knowledgeRefresh),{once:true});
window.addEventListener('lumina-event',event=>{if(event.detail.type==='continuity_result')loadGraph();});
function stopMic(){clearInterval(listenTimer);callLease=null;turnPending=false;audio.stopCapture();audio.monitoring=false;audio.onPCM=null;vad?.reset();vad=null;recording=false;micPending=false;$('mic').classList.remove('recording');setMicLabel(false);$('mic').setAttribute('aria-pressed','false');$('mic').disabled=false;$('mic-hint').textContent='Microphone off';}
async function finishTurn(){if(!recording)return;if(!vad?.active){armTurn();return;}if(/^(stop|hang up)[.!?]*$/.test(vad.text)){closeCall();return;}const stamp=turnStartedAt;await audio.finishCapture();if(!recording||stamp!==turnStartedAt)return;send({type:'mic_end',started_at:stamp});armTurn();$('mic-hint').textContent='Microphone on · continue when ready';}
async function connect(){try{const response=await fetch('/api/config',{cache:'no-store'});if(!response.ok)throw Error();Object.assign(config,await response.json());}catch{notice('The local runtime is unavailable. Your message is preserved.');reconnectTimer=setTimeout(connect,2000);return;}ws=new WebSocket(`ws://${location.host}/ws?token=${encodeURIComponent(config.token)}`);ws.onopen=()=>{connected=true;};ws.onclose=()=>{connected=false;audio.minimumSpeechId=0;window.dispatchEvent(new CustomEvent('lumina-event',{detail:{type:'connection_closed'}}));audio.interrupt();stopMic();$('runtime-health').textContent='disconnected';$('connection').textContent='Runtime disconnected';$('connection-dot').classList.add('offline');reconnectTimer=setTimeout(connect,2000);};ws.onmessage=async event=>{const message=JSON.parse(event.data);try{controls.event(message);if(message.type==='knowledge_filter'){try{const hits=environment?.search(message.query);$('search-summary').textContent=`${hits} direct concept hits; context dimmed.`;}catch{}}if(message.type==='interrupt')audio.interrupt(message.speech_id);switch(message.type){case'state':renderState(message.data);break;case'audio':if(!turnPending&&!audio.capturing)await audio.play(message);break;case'turn_complete':audio.complete(message.speech_id);break;case' interrupt':audio.interrupt();break;case'transcript':transcript[message.role]+=message.text;if(message.role==='user')vad?.setTranscript(transcript.user);$('live-transcript').textContent=(transcript.user?`You: ${transcript.user}\n`:'')+transcript.assistant;break;case'transcript_clear':transcript.user='';transcript.assistant='';$('live-transcript').textContent='';break;case'speech_ready':if(recording&&message.started_at===turnStartedAt){turnPending=false;audio.startCapture();}break;case'mic_ready':if(micPending){await audio.prepareMicrophone();if(!micPending){audio.stopCapture();break;}microphoneReady();}else send({type:'mic_end'});break;case'voice_closed':audio.interrupt();stopMic();break;case'notice':notice(message.text);break;}}catch(error){audio.interrupt();stopMic();notice(error.message||'Audio failed.');send({type:'audio_error'});}};}
async function api(path){const response=await fetch(path,{method:'POST',headers:{'X-Lumina-Token':config.token}});if(!response.ok)throw Error('The runtime could not finish this action.');await loadGraph();}
$('composer').addEventListener('submit',async event=>{
 event.preventDefault();const text=$('message').value.trim();if(!text)return;
 if(!connected){notice('The local runtime is reconnecting. Your message is still here; send it once connected.');return;}
 let voice=$('spoken').checked&&config.voice_available;
 if(voice){try{await audio.initialize();}catch(error){voice=false;notice(error.message+' Sending your message as text.');send({type:'client_audio_error',phase:'output_setup',code:error.name});}}
 audio.interrupt();if(recording){send({type:'mic_end'});stopMic();}
 if(send({type:'text',text,voice}))$('message').value='';
});
$('attach').addEventListener('click',()=>$('file-upload').click());
$('file-upload').addEventListener('change',async event=>{const files=[...event.target.files||[]];if(!files.length)return;for(const file of files){const body=new FormData();body.append('file',file,file.name);try{const response=await fetch('/api/files/upload',{method:'POST',headers:{'X-Lumina-Token':config.token},body});const result=await response.json();if(!response.ok||!result.ok)throw Error(result.error||'The file could not be uploaded.');notice(`${file.name} is in the workspace and ready to inspect.`);}catch(error){notice(`${file.name}: ${error.message}`);}}event.target.value='';await loadGraph();});
$('message').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();$('composer').requestSubmit();}});
$('local-search').addEventListener('submit',event=>{event.preventDefault();const hits=environment?.search($('query').value);$('search-summary').textContent=`${hits} direct concept hits; context dimmed.`;});
$('mic').addEventListener('click',async()=>{if(recording){closeCall();return;}if(!config.voice_available){notice('Voice needs a configured audio provider.');return;}try{audio.interrupt();micPending=true;$('mic').disabled=true;$('mic-hint').textContent='Preparing microphone.';await audio.initialize();send({type:'mic_start'});}catch(error){stopMic();notice(microphoneError(error)||'Microphone permission is required.');send({type:'audio_error'});}});
$('stop').addEventListener('click',()=>{audio.interrupt();stopMic();send({type:'interrupt'});});$('spoken').addEventListener('change',()=>{if(!$('spoken').checked){audio.interrupt();stopMic();send({type:'voice_stop'});}});$('refresh').addEventListener('click',async()=>{try{$('refresh').disabled=true;await api('/api/refresh');}catch(e){notice(e.message);}finally{$('refresh').disabled=false;}});$('overview').addEventListener('click',async()=>{try{environment?.search('');$('results').replaceChildren();}catch(e){notice(e.message);}});$('fit').addEventListener('click',()=>environment?.fit());$('close-selection').addEventListener('click',()=>$('selection').hidden=true);$('copy-path').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(selectedPath);notice('Path copied.');}catch{notice('Clipboard unavailable.');}});
setupDevices(notice,()=>{if(recording||micPending){send({type:'mic_end'});stopMic();}});
// A user-opened call survives tab/window switching. The bounded conversation
// lease, explicit Stop, connection loss and actual page unload still close it.
window.addEventListener('pagehide',()=>{audio.interrupt();stopMic();ws?.close();clearTimeout(reconnectTimer);});
async function boot(){try{config=await(await fetch('/api/config')).json();config.voice_available=(await(await fetch('/api/capabilities')).json()).voice;$('root-label').textContent=config.root;$('root-label').title=config.root;for(const id of['microphone','speaker'])if(!localStorage.getItem('lumina.'+id))localStorage.setItem('lumina.'+id,config[id+'_device']);for(const [label,value] of [['Filesystem root',config.root],['Provider',config.provider],['Text model',config.model],['Live model',config.live_model],['Voice',config.voice],['Worker',config.worker||'none'],['Graph limit',config.graph_limit+' entities']]){const dt=document.createElement('dt');dt.textContent=label;const dd=document.createElement('dd');dd.textContent=value;$('config-details').append(dt,dd);}try{orb=new Orb($('orb'));}catch{notice('WebGL could not start.');}try{environment=new EnvironmentGraph($('graph'),selectNode);}catch{notice('The 3D graph could not start.');}connect();await loadGraph();}catch{notice('Cannot reach the local runtime. Start LUMINA and reload this page.');}}
boot();
