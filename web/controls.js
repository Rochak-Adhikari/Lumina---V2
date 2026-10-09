const $=id=>document.getElementById(id);
import {setupWorkerPanel} from './workers.js';
import {workerAction} from './worker-actions.js';
export function setupControls({send,notice,getConfig,prepareAudio=async()=>{}}){
  const workers=setupWorkerPanel({getConfig,notice});
  let previewUrl=null;
  let selectedUpload=null, workspaceRequest=0;
  try{selectedUpload=JSON.parse(localStorage.getItem('lumina.uploadSelection')||'null');}catch{}
  if(!selectedUpload||typeof selectedUpload.path!=='string'||typeof selectedUpload.name!=='string')selectedUpload=null;
  function selectUpload(file){
    selectedUpload=file;
    try{if(file)localStorage.setItem('lumina.uploadSelection',JSON.stringify(file));else localStorage.removeItem('lumina.uploadSelection');}catch{}
    $('workspace-selected').textContent=file?`Selected: ${file.name}`:'No file selected.';
    $('workspace-read').disabled=$('workspace-analyze').disabled=!file;
    if(file)$('phase1-file-path').value=file.path;
    if(file&&getConfig()?.token)post('/api/files/select',{selection:file.path}).catch(error=>notice(error.message));
    for(const row of $('workspace-files').children)row.setAttribute('aria-pressed',String(row.dataset.path===file?.path));
  }
  async function refreshWorkspace(){
    const request=++workspaceRequest;
    $('workspace-status').textContent='Loading uploads…';
    try{
      const response=await fetch('/api/files?query='+encodeURIComponent($('workspace-query').value),{headers:{'X-Lumina-Token':getConfig().token}});
      const data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||'Upload workspace is unavailable.');
      if(request!==workspaceRequest)return;
      $('workspace-root').textContent=data.root||'';$('workspace-files').replaceChildren();
      for(const file of data.files||[]){
        const row=document.createElement('button'),name=document.createElement('strong'),meta=document.createElement('small');
        row.type='button';row.className='workspace-file';row.dataset.path=file.path;
        name.textContent=file.name;meta.textContent=`${file.bytes} bytes · ${file.modified}`;
        row.append(name,meta);row.onclick=()=>selectUpload(file);$('workspace-files').append(row);
      }
      if(selectedUpload&&!$('workspace-query').value&&!data.truncated&&!data.files.some(file=>file.path===selectedUpload.path))selectUpload(null);
      else selectUpload(selectedUpload);
      $('workspace-status').textContent=`${data.files.length} uploaded file${data.files.length===1?'':'s'}${data.truncated?' shown; narrow your search to see more.':data.files.length?' available.':'. Upload files to get started.'}`;
    }catch(error){if(request===workspaceRequest){$('workspace-status').textContent='Could not load uploads. '+error.message;$('workspace-read').disabled=$('workspace-analyze').disabled=true;}}
  }
  $('workspace-open').onclick=()=>{$('upload-workspace').showModal();refreshWorkspace();};
  $('workspace-close').onclick=()=>$('upload-workspace').close();
  $('workspace-refresh').onclick=refreshWorkspace;
  $('workspace-search').onsubmit=e=>{e.preventDefault();refreshWorkspace();};
  $('workspace-upload').onclick=()=>$('workspace-upload-input').click();
  $('workspace-upload-input').onchange=async e=>{
    $('workspace-upload').disabled=true;
    try{for(const file of e.target.files){
      const body=new FormData();body.append('file',file,file.name);
      try{const response=await fetch('/api/files/upload',{method:'POST',headers:{'X-Lumina-Token':getConfig().token},body});const result=await response.json();if(!response.ok||!result.ok)throw Error(result.error||'Upload failed.');selectUpload({name:result.name||file.name,path:result.path,id:result.id});}
      catch(error){notice(`${file.name}: ${error.message}`);}
    }}finally{e.target.value='';$('workspace-upload').disabled=false;await refreshWorkspace();}
  };
  async function useUpload(action){
    if(!selectedUpload)return;
    const file=selectedUpload;
    $('workspace-output').textContent=`${action==='extract'?'Reading':'Analyzing'} ${file.name}…`;
    const result=await phase1Invoke('process_file',{path:file.path,action,...(action==='analyze'?{question:$('workspace-question').value||'Summarize this document.'}:{})});
    $('workspace-output').textContent=result.confirmation_required?'Review the confirmation to continue.':phase1Text(result);
  }
  $('workspace-read').onclick=()=>useUpload('extract');$('workspace-analyze').onclick=()=>useUpload('analyze');
  selectUpload(selectedUpload);
  let confirmation=null,state,announcements=[],announcementTexts={},announcementInFlight=null;
  async function post(path,data){
    const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Lumina-Token':getConfig().token},body:JSON.stringify(data)});
    const result=await response.json();if(!response.ok||result.error)throw Error(result.error||'The request failed.');return result;
  }
  function details(title,text){$('details-title').textContent=title;$('details-text').textContent=text;if(!$('details').open)$('details').showModal();}
  function showConfirmation(data){confirmation=data.confirmation_id;$('confirmation-title').textContent='Confirm action';$('confirmation-message').textContent=data.message||'Review this action before continuing.';$('confirmation-target').textContent=data.target||'';if(!$('confirmation').open)$('confirmation').showModal();}
  function phase1Text(result){
    if(result?.analysis)return result.analysis+(result.analysis_truncated?'\n\nOnly part of the document was analyzed.':'');
    if(result?.text)return result.text+(result.truncated?'\n\nExtraction was truncated.':'');
    if(result?.results)return (result.warning?result.warning+'\n\n':'')+(result.results.map(item=>`${item.title}\n${item.url}\n${item.snippet||''}`).join('\n\n')||'No public results returned.');
    const copy={...result};if(copy.data)copy.data='[image retained locally]';return JSON.stringify(copy,null,2).slice(0,7000);
  }
  async function phase1Status(){
    try{
      const response=await fetch('/api/capabilities');const data=await response.json();const phase=data.phase1||{};
      $('phase1-status').textContent=Object.entries(phase).map(([name,value])=>`${name.replaceAll('_',' ')}: ${value.status||value.state||'unavailable'}`).join(' · ');
    }catch{$('phase1-status').textContent='Phase One status is unavailable while the runtime is disconnected.';}
  }
  async function phase1Invoke(tool,args){
    try{const result=await post('/api/phase1',{tool,args});if(result.confirmation_required)showConfirmation(result);else $('phase1-output').textContent=phase1Text(result);await phase1Status();return result;}
    catch(error){$('phase1-output').textContent=error.message;notice(error.message);return {ok:false,error:error.message};}
  }
  async function loadLogs(){
    try{
      const response=await fetch('/api/session-logs',{headers:{'X-Lumina-Token':getConfig().token}});const data=await response.json();
      $('session-log-list').replaceChildren();
      for(const item of data.logs||[]){const row=document.createElement('div');row.className='session-log-item';const label=document.createElement('span');label.textContent=`${item.name} · ${item.bytes} bytes`;const button=document.createElement('button');button.type='button';button.textContent='Read';button.onclick=async()=>{const result=await fetch('/api/session-logs/'+encodeURIComponent(item.name),{headers:{'X-Lumina-Token':getConfig().token}});$('session-log-view').hidden=false;$('session-log-view').textContent=await result.text();};row.append(label,button);$('session-log-list').append(row);}
      if(!data.logs?.length)$('session-log-list').textContent='No session logs are available yet.';
    }catch(error){$('session-log-list').textContent=error.message;}
  }
  async function tasks(){
    try{
      const data=await(await fetch('/api/tasks')).json();
      $('task-worker').replaceChildren(...data.workers.map(w=>new Option(w,w)));
      $('task-submit').disabled=!data.workers.length;
      $('worker-status').textContent=data.workers.length?'Choose a worker and give it a task.':'No agent worker is configured. Local commands remain available.';
      $('task-list').replaceChildren();
      for(const task of data.tasks){
        const article=document.createElement('article'),label=document.createElement('p');label.textContent=`${task.worker}: ${task.status.replaceAll('_',' ').toLowerCase()}. ${task.summary}`;article.append(label);
        const result=document.createElement('button');result.textContent='Read result';result.onclick=async()=>{try{const data=await post('/api/tasks',{action:'result',task_id:task.task_id});details('Agent result',data.result||'No result is available yet.');}catch(e){notice(e.message);}};article.append(result);
        if(!['CANCELLED'].includes(task.status)){
          const cancel=document.createElement('button');cancel.textContent='Stop agent';cancel.onclick=async()=>{try{await workerAction(post,'cancel',task);await tasks();}catch(e){notice(e.message);}};article.append(cancel);
        }
        const remove=document.createElement('button');remove.textContent='Remove inactive agent';remove.onclick=async()=>{try{await workerAction(post,'remove',task);await tasks();}catch(e){notice(e.message);}};article.append(remove);
        if(['WAITING_FOR_USER','COMPLETED','ERROR'].includes(task.status)){
          const reply=document.createElement('textarea');reply.placeholder='Your reply to this worker';reply.setAttribute('aria-label','Reply to '+task.worker);reply.maxLength=12000;
          const submit=document.createElement('button');submit.textContent=task.status==='RUNNING'?'Send reply':'Resume task';submit.onclick=async()=>{try{await post('/api/tasks',{action:task.status==='RUNNING'?'message':'resume',task_id:task.task_id,message:reply.value});await tasks();}catch(e){notice(e.message);}};article.append(reply,submit);
        }
        $('task-list').append(article);
      }
    }catch(e){notice(e.message);}
  }
  $('controls-open').onclick=()=>{$('controls').showModal();tasks();phase1Status();loadLogs();};$('controls-close').onclick=()=>$('controls').close();
  $('details-close').onclick=()=>$('details').close();
  $('local-command').onsubmit=e=>{e.preventDefault();send({type:'text',text:$('local-command-text').value,voice:false});$('controls').close();};
  $('phase1-refresh').onclick=phase1Status;
  $('phase1-web-search').onsubmit=async e=>{e.preventDefault();const query=$('phase1-query').value.trim();if(query)await phase1Invoke('web_search',{query});};
  $('phase1-browser').onsubmit=async e=>{e.preventDefault();const url=$('phase1-url').value.trim();if(!url)return;const started=await phase1Invoke('browser_control',{action:'start'});if(!started.ok)return;const inspected=await phase1Invoke('browser_control',{action:'inspect',tab_id:started.tab_id});if(inspected.ok)await phase1Invoke('browser_control',{action:'navigate',tab_id:started.tab_id,snapshot:inspected.snapshot,url:new URL(/^https?:\/\//i.test(url)?url:'https://'+url).href});};
  $('phase1-screen').onclick=()=>phase1Invoke('screen_capture',{action:'capture',target:'monitor',source:'1'});
  $('phase1-reminder').onclick=async()=>{const message=$('phase1-reminder-text').value.trim(),seconds=Number($('phase1-reminder-seconds').value);if(!message||!Number.isFinite(seconds)||seconds<1||seconds>31536000){notice('Enter a reminder and a valid delay in seconds.');return;}await phase1Invoke('reminder',{action:'create',message,due_at:new Date(Date.now()+seconds*1000).toISOString()});};
  $('phase1-reminder-list').onclick=()=>phase1Invoke('reminder',{action:'list'});
  $('phase1-file-read').onclick=()=>phase1Invoke('process_file',{path:$('phase1-file-path').value,action:'extract'});
  $('phase1-file-analyze').onclick=()=>phase1Invoke('process_file',{path:$('phase1-file-path').value,action:'analyze',question:$('phase1-question').value||'Summarize this document.'});
  $('phase1-screen-analyze').onclick=()=>phase1Invoke('screen_capture',{action:'analyze',question:$('phase1-question').value||'Describe what is visible on my screen.',target:'monitor',source:'1'});
  async function preview(){try{const response=await fetch('/api/screen-preview',{headers:{'X-Lumina-Token':getConfig().token}});if(!response.ok)return;if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=URL.createObjectURL(await response.blob());$('phase1-preview').src=previewUrl;$('phase1-preview').hidden=false;}catch{notice('Screen preview is unavailable.');}}
  window.addEventListener('pagehide',()=>{if(previewUrl)URL.revokeObjectURL(previewUrl);});
  $('phase1-logs').onclick=loadLogs;$('session-log-refresh').onclick=loadLogs;
  $('task-start').onsubmit=async e=>{e.preventDefault();$('task-submit').disabled=true;try{const payload={action:'start',worker:$('task-worker').value,message:$('task-message').value};if($('task-workspace').value.trim())payload.workspace=$('task-workspace').value.trim();await post('/api/tasks',payload);$('task-message').value='';await tasks();$('controls').close();workers.event({type:'worker_panel_open'});}catch(error){notice(error.message);}finally{$('task-submit').disabled=!$('task-worker').options.length;}};
  async function confirm(approve){const id=confirmation;if(!id)return;let speak=approve&&$('spoken').checked;if(speak){try{await prepareAudio();}catch(error){speak=false;notice(error.message+' The answer will still appear as text.');}}confirmation=null;$('confirmation').close();$('phase1-output').textContent=approve?'Processing…':'Cancelled.';try{const result=await post('/api/confirm',{confirmation_id:id,approve,client_id:getConfig().client_id,speak});if(result?.ok)$('phase1-output').textContent=phase1Text(result);await phase1Status();}catch(e){$('phase1-output').textContent=e.message;notice(e.message);}}
  $('confirmation-approve').onclick=()=>confirm(true);$('confirmation-deny').onclick=()=>confirm(false);
  $('confirmation').addEventListener('cancel',e=>{e.preventDefault();confirm(false);});
  function speakNext(){
    if(announcementInFlight||state?.state!=='IDLE'||!$('spoken').checked||!announcements.length)return;
    if(state.live_connected){announcementInFlight=announcements[0];send({type:'announce',id:announcementInFlight});return;}

  }
  return {
    state(value){state=value;speakNext();},
    event(message){
      window.dispatchEvent(new CustomEvent('lumina-event',{detail:message}));
      workers.event(message);
      if(message.type==='workspace_open'){$('upload-workspace').showModal();refreshWorkspace();}
      if(message.type==='attachment'){selectUpload({name:message.name,path:message.path,id:message.id});refreshWorkspace();notice(message.name+' is saved in Workspace.');}
      if(message.type==='screen_preview')preview();
      if(message.type==='capability_result'){$('phase1-output').textContent=phase1Text(message.data);if(message.tool==='process_file')$('workspace-output').textContent=phase1Text(message.data);if(message.tool==='screen_capture')preview();}
      if(message.type==='analysis_progress'){$('phase1-output').textContent=message.stage==='processing'?'Processing…':'Analyzing…';$('workspace-output').textContent=$('phase1-output').textContent;}
      if(message.type==='analysis_transcript'){const output=$('workspace-output');if(output.dataset.speech!==String(message.speech_id)){output.textContent='';output.dataset.speech=String(message.speech_id);}output.textContent+=message.text;}
      if(message.type==='confirmation_resolved'&&confirmation===message.confirmation_id){confirmation=null;$('confirmation').close();}
      if(message.type==='announcement_ack'){if(message.status!=='busy')announcements=announcements.filter(id=>id!==message.id);announcementInFlight=null;if(message.status!=='busy')speakNext();}
      if(message.type==='voice_closed')announcementInFlight=null;
      if(message.type==='confirmation')showConfirmation(message.data);
      if(message.type==='file_content')details(message.path,message.text);
      if(message.type==='agent_result'){notice(message.data.summary);if($('controls').open)tasks();}
      if(message.type==='announcement'){announcementTexts[message.id]=message.text||'';announcements.push(message.id);announcements=announcements.slice(-20);speakNext();}
    }
  };
}
