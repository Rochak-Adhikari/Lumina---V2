// Explicit local capture, with separate consent for online visual reasoning.
export function setupScreenShare({getConfig,notice}){
  const button=document.createElement('button'),status=document.createElement('span'),dialog=document.createElement('dialog');
  button.type='button';button.id='screen-share';button.textContent='Share screen';
  status.id='screen-share-status';status.role='status';status.textContent='Screen sharing off';
  dialog.id='screen-share-dialog';
  dialog.innerHTML='<form method="dialog"><h2>Screen sharing</h2><p>Local preview uses Windows capture. Online viewing sends the selected source to your configured reasoning provider.</p><label>Source <select id="screen-share-source"><option value="browser">Browser screen picker</option></select></label><button type="button" id="screen-share-refresh">Refresh Windows sources</button><label><input id="screen-share-online" type="checkbox">Enable online viewing</label><p id="screen-share-help" role="status">Choose a source. No microphone or system audio is captured.</p><button type="button" id="screen-share-start">Start sharing</button><button value="cancel">Close</button><img id="screen-share-preview" alt="Current locally captured screen" hidden style="max-width:100%;max-height:320px"></form>';
  dialog.style.maxWidth='680px';document.body.append(dialog);
  const renderLabel=document.createElement('label');renderLabel.innerHTML='<input type="checkbox"> Render selected Windows window contents (may omit overlays; not the visible desktop)';
  dialog.querySelector('form').insertBefore(renderLabel,dialog.querySelector('#screen-share-help'));
  const renderWindow=renderLabel.querySelector('input');
  const stopInside=document.createElement('button');stopInside.type='button';stopInside.id='screen-share-stop';stopInside.textContent='Stop sharing';stopInside.disabled=true;dialog.querySelector('form').append(stopInside);
  document.querySelector('.composer-actions').append(button);document.querySelector('.composer-actions').after(status);
  const source=dialog.querySelector('select'),online=dialog.querySelector('input'),help=dialog.querySelector('p[role=status]'),preview=dialog.querySelector('img'),start=dialog.querySelector('#screen-share-start');
  let stream=null,video=null,timer=null,epoch=0,identity=null,active=false,starting=false,previewUrl=null,selection=[],pending=new Set(),captureTicket=null,frameSequence=0;
  let phase='off',attempts=0,lastStatus=null,statusAt=0,healthTimer=null,healthBusy=false,frameBusy=false,previewBusy=false,suspended=false;
  function renderStatus(){
    const perception=lastStatus?.perception;
    const age=perception?.age_seconds==null?null:perception.age_seconds+(performance.now()-statusAt)/1000;
    const freshness=perception?.freshness_seconds||3;
    let label=phase;
    if(phase==='active'&&['failed','paused','waiting','unverified'].includes(perception?.observation))label={failed:'failed',paused:'paused',waiting:'starting',unverified:'stale'}[perception.observation];
    if(phase==='active'&&(age===null||age>=freshness))label='stale';
    status.dataset.state=label;
    const names={off:'Screen sharing off',starting:'Starting · waiting for first valid frame',active:'Screen preview active',stale:'Screen frame stale',paused:'Screen sharing paused',reconnecting:'Screen sharing reconnecting',permission:'Screen sharing permission required',failed:'Screen sharing failed'};
    status.textContent=(names[label]||label)+(age==null?'':` · last frame ${age.toFixed(1)}s old`);
    if(identity)status.textContent+=lastStatus?.mode==='provider'?' · online delivery enabled; analysis unconfirmed':perception?.analysis==='disabled'?' · local only; online analysis off':' · online unavailable; ask a visual question to reconnect';
  }
  function headers(){const c=getConfig();return {'X-Lumina-Token':c.token,'X-Lumina-Client':c.client_id};}
  async function request(path,body,raw=false,detached=false,metadata=null){
    const controller=new AbortController();if(!detached)pending.add(controller);
    const deadline=setTimeout(()=>controller.abort(new DOMException('Request timed out.','TimeoutError')),25000);
    try{
      const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{...headers(),...(body===undefined?{}:{'Content-Type':raw?'image/jpeg':'application/json'}),...(raw?{'X-Lumina-Share':identity}:{}),...(metadata?{'X-Lumina-Frame':JSON.stringify(metadata)}:{})},
        body:body===undefined?undefined:raw?body:JSON.stringify(body),signal:controller.signal});
      if(path.endsWith('/preview')){if(!response.ok)throw Error('Local preview is unavailable.');return await response.blob();}
      const data=await response.json().catch(()=>({error:'Local runtime request failed.'}));
      if(!response.ok||!data.ok){const error=Error(data.error||'Screen sharing failed.');error.code=data.code||(response.status===409?'inactive':response.status===403?'forbidden':undefined);throw error;}
      return data;
    }finally{clearTimeout(deadline);pending.delete(controller);}
  }
  function diagnostic(stage,error){
    const allowed=['NotAllowedError','NotReadableError','AbortError','TimeoutError','InvalidStateError','NotSupportedError','NetworkError','Recovered','RetriesExhausted','FrameGap'];
    request('/api/screen-share/diagnostic',{stage,code:allowed.includes(error.name)?error.name:'Error',attempt:attempts},false,true).catch(()=>{});
  }
  function release(){
    ++epoch;active=false;starting=false;clearTimeout(timer);clearInterval(healthTimer);for(const controller of pending)controller.abort();pending.clear();
    phase='off';lastStatus=null;attempts=0;frameBusy=false;previewBusy=false;suspended=false;renderStatus();
    stream?.getTracks().forEach(track=>track.stop());stream=null;if(video)video.srcObject=null;video=null;
    identity=null;captureTicket=null;frameSequence=0;button.textContent='Share screen';button.setAttribute('aria-pressed','false');status.textContent='Screen sharing off';start.disabled=false;
    online.disabled=false;source.disabled=false;stopInside.disabled=true;dialog.querySelector('#screen-share-refresh').disabled=false;
    if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=null;preview.removeAttribute('src');preview.hidden=true;
  }
  async function stop(){const id=identity;release();button.disabled=true;start.disabled=true;try{await request('/api/screen-share',{action:'stop',...(id?{share_id:id}:{})},false,true).catch(()=>{});}finally{button.disabled=false;start.disabled=false;}}
  function describe(result){
    lastStatus=result;statusAt=performance.now();renderStatus();
    if(result.warning){help.textContent=result.warning;notice(result.warning);}
  }
  async function pause(message,nextPhase='failed'){
    clearTimeout(timer);suspended=true;active=false;starting=false;phase=nextPhase;renderStatus();help.textContent=message;notice(message);
    const id=identity;
    if(id)await request('/api/screen-share',{action:'pause',share_id:id}).catch(()=>{});
  }
  async function health(generation){
    renderStatus();
    if(healthBusy||!identity||generation!==epoch)return;
    healthBusy=true;
    try{const result=await request('/api/screen-share/status');if(generation===epoch){
      if(result.share_id!==identity){await pause('The sharing session ended. Stop and start sharing again.');return;}
      describe(result);
      if(result.perception.error==='first_frame_timeout'&&starting)await pause('No valid frame arrived. Stop and choose the source again.');
    }}catch{if(generation===epoch&&phase==='active'){phase='stale';renderStatus();}}
    finally{healthBusy=false;}
  }
  async function updatePreview(generation){
    if(previewBusy||!dialog.open)return;previewBusy=true;
    try{const blob=await request('/api/screen-share/preview');if(generation!==epoch)return;
      if(previewUrl)URL.revokeObjectURL(previewUrl);preview.src=previewUrl=URL.createObjectURL(blob);preview.hidden=false;
    }catch(error){if(generation!==epoch)return;diagnostic('preview',error);help.textContent='Preview could not refresh. Capture continues; check the frame status.';}
    finally{if(generation===epoch)previewBusy=false;}
  }
  async function frame(generation){
    if(generation!==epoch||!identity||frameBusy||suspended)return;
    frameBusy=true;
    try{
      let result;
      if(stream){
        if(stream.getVideoTracks()[0]?.muted||!video.videoWidth||!video.videoHeight||video.readyState<2){const error=Error('The browser source has no usable frames.');error.code='frame_gap';throw error;}
        const prepared=await request('/api/screen-share',{action:'prepare_frame',share_id:identity});
        if(generation!==epoch)return;captureTicket=prepared.capture_ticket;
        const canvas=document.createElement('canvas'),scale=Math.min(1,1280/video.videoWidth,720/video.videoHeight);
        const metadata={ticket:captureTicket,sequence:++frameSequence,captured_at:new Date().toISOString(),dimensions:[video.videoWidth,video.videoHeight]};
        canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);
        canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);
        const jpeg=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.72));
        if(generation!==epoch)return;if(!jpeg)throw Error('Screen encoding failed.');
        result=await request('/api/screen-share/frame',jpeg,true,false,metadata);
      }else result=await request('/api/screen-share/capture',{share_id:identity});
      if(generation!==epoch||suspended)return;if(attempts)diagnostic('frame',{name:'Recovered'});captureTicket=result.capture_ticket;attempts=0;starting=false;active=true;phase=result.perception?.observation==='fresh'?'active':'stale';describe(result);
      void updatePreview(generation);
      timer=setTimeout(()=>frame(generation),1100);
    }catch(error){
      if(generation!==epoch||suspended)return;
      diagnostic('frame',error);
      const recoverable=['rate_limited','timeout','worker_failed','capture_failed','frame_gap','expired_frame'].includes(error.code)||['TypeError','TimeoutError','NetworkError'].includes(error.name);
      if(recoverable&&attempts<3){attempts++;phase='reconnecting';renderStatus();help.textContent=`Frame interrupted. Recovery attempt ${attempts} of 3.`;timer=setTimeout(()=>frame(generation),attempts*1000);}
      else {diagnostic('frame',{name:'RetriesExhausted'});await pause(error.message+' Stop and start sharing to choose or authorize the source again.',error.name==='NotAllowedError'?'permission':error.code==='frame_gap'?'paused':'failed');}
    }finally{if(generation===epoch)frameBusy=false;}
  }
  async function sources(){
    source.disabled=true;start.disabled=true;
    try{
      const result=await request('/api/screen-share/sources');selection=[];source.replaceChildren();
      for(const [type,items] of [['monitor',result.monitors||[]],['window',result.windows||[]]])for(const item of items){
        const index=selection.push({target:type,source:item.id})-1;
        source.add(new Option(type==='monitor'?'Monitor '+item.id+' · '+item.bounds.width+' × '+item.bounds.height:item.title,String(index)));
      }
      source.add(new Option('Browser screen picker','browser'));help.textContent='Choose a source. No microphone or system audio is captured.';
    }catch(error){diagnostic('source_list',error);help.textContent='Windows sources unavailable. The browser picker may still work.';}
    finally{source.disabled=false;start.disabled=active;}
  }
  button.onclick=()=>{if(identity||starting){void stop();return;}dialog.showModal();void sources();};
  stopInside.onclick=()=>void stop();
  dialog.querySelector('#screen-share-refresh').onclick=sources;
  start.onclick=async()=>{
    if(identity||starting)return;starting=true;phase='starting';renderStatus();start.disabled=true;source.disabled=true;online.disabled=true;stopInside.disabled=false;dialog.querySelector('#screen-share-refresh').disabled=true;const generation=++epoch;let stage='picker';
    try{
      const chosen=source.value==='browser'?null:selection[Number(source.value)];
      if(source.value==='browser'){
        phase='permission';renderStatus();
        if(!navigator.mediaDevices?.getDisplayMedia)throw new DOMException('Browser capture is unavailable. Choose a Windows source.','NotSupportedError');
        const picked=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:1},audio:false});
        if(generation!==epoch){picked.getTracks().forEach(track=>track.stop());return;}
        stream=picked;const track=stream.getVideoTracks()[0];
        track.addEventListener('ended',()=>{if(generation===epoch)void pause('The browser ended capture. Stop and start sharing to authorize a source again.','permission');},{once:true});
        track.addEventListener('mute',()=>{if(generation===epoch){phase='paused';renderStatus();}});
        track.addEventListener('unmute',()=>{if(generation===epoch&&identity&&!frameBusy){clearTimeout(timer);suspended=false;attempts=0;void frame(generation);}});
        video=document.createElement('video');video.muted=true;video.srcObject=stream;
        let playTimer;try{await Promise.race([video.play(),new Promise((_,reject)=>{playTimer=setTimeout(()=>reject(new DOMException('Browser source did not start.','TimeoutError')),10000);})]);}finally{clearTimeout(playTimer);}
      }else if(!chosen)throw Error('Choose an available source.');
      if(generation!==epoch)return;stage='start';phase='starting';renderStatus();
      const result=await request('/api/screen-share',{action:'start',mode:online.checked?'provider':'local',capture:chosen?'windows':'browser',...chosen,window_render:chosen?.target==='window'&&renderWindow.checked});
      if(generation!==epoch){await request('/api/screen-share',{action:'stop',share_id:result.share_id},false,true).catch(()=>{});return;}
      identity=result.share_id;captureTicket=result.capture_ticket;frameSequence=0;active=false;button.textContent='Stop sharing';button.setAttribute('aria-pressed','true');describe(result);healthTimer=setInterval(()=>void health(generation),1000);void frame(generation);
    }catch(error){if(generation===epoch){diagnostic(stage,error);await stop();phase=error.name==='NotAllowedError'?'permission':'failed';renderStatus();help.textContent=error.name==='NotAllowedError'?'Capture was cancelled or blocked by the browser. Start sharing again to grant permission.':error.message;notice(help.textContent);}}
    finally{if(generation===epoch)start.disabled=!!identity||starting;}
  };
  dialog.addEventListener('close',()=>{if(starting)void stop();});
  window.addEventListener('lumina-event',event=>{
    if(event.detail.type==='screen_share_stopped')release();
    if(event.detail.type==='screen_share_local')describe({...lastStatus,mode:'local',warning:event.detail.text});
    if(event.detail.type==='connection_closed'){release();phase='permission';renderStatus();help.textContent='Runtime connection ended. Conversation is preserved; start sharing again after reconnection.';}
  });
  window.addEventListener('pagehide',release);
  return {stop,isActive:()=>active};
}
