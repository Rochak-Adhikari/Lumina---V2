// Explicit local capture, with separate consent for online visual reasoning.
export function setupScreenShare({getConfig,notice}){
  const button=document.createElement('button'),status=document.createElement('span'),dialog=document.createElement('dialog');
  button.type='button';button.id='screen-share';button.textContent='Share screen';
  status.id='screen-share-status';status.role='status';status.textContent='Screen sharing off';
  dialog.id='screen-share-dialog';
  dialog.innerHTML='<form method="dialog"><h2>Screen sharing</h2><p>Local preview uses Windows capture. Online viewing sends the selected source to your configured reasoning provider.</p><label>Source <select id="screen-share-source"><option value="browser">Browser screen picker</option></select></label><button type="button" id="screen-share-refresh">Refresh Windows sources</button><label><input id="screen-share-online" type="checkbox">Enable online viewing</label><p id="screen-share-help" role="status">Choose a source. No microphone or system audio is captured.</p><button type="button" id="screen-share-start">Start sharing</button><button value="cancel">Close</button><img id="screen-share-preview" alt="Current locally captured screen" hidden style="max-width:100%;max-height:320px"></form>';
  dialog.style.maxWidth='680px';document.body.append(dialog);
  const stopInside=document.createElement('button');stopInside.type='button';stopInside.id='screen-share-stop';stopInside.textContent='Stop sharing';stopInside.disabled=true;dialog.querySelector('form').append(stopInside);
  document.querySelector('.composer-actions').append(button);document.querySelector('.composer-actions').after(status);
  const source=dialog.querySelector('select'),online=dialog.querySelector('input'),help=dialog.querySelector('p[role=status]'),preview=dialog.querySelector('img'),start=dialog.querySelector('#screen-share-start');
  let stream=null,video=null,timer=null,epoch=0,identity=null,active=false,starting=false,previewUrl=null,selection=[],pending=new Set();
  function headers(){const c=getConfig();return {'X-Lumina-Token':c.token,'X-Lumina-Client':c.client_id};}
  async function request(path,body,raw=false,detached=false){
    const controller=new AbortController();if(!detached)pending.add(controller);
    const deadline=setTimeout(()=>controller.abort(new DOMException('Request timed out.','TimeoutError')),25000);
    try{
      const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{...headers(),...(body===undefined?{}:{'Content-Type':raw?'image/jpeg':'application/json'}),...(raw?{'X-Lumina-Share':identity}:{})},
        body:body===undefined?undefined:raw?body:JSON.stringify(body),signal:controller.signal});
      if(path.endsWith('/preview')){if(!response.ok)throw Error('Local preview is unavailable.');return await response.blob();}
      const data=await response.json().catch(()=>({error:'Local runtime request failed.'}));
      if(!response.ok||!data.ok){const error=Error(data.error||'Screen sharing failed.');error.code=data.code;throw error;}
      return data;
    }finally{clearTimeout(deadline);pending.delete(controller);}
  }
  function diagnostic(stage,error){
    const allowed=['NotAllowedError','NotReadableError','AbortError','TimeoutError','InvalidStateError','NotSupportedError','NetworkError'];
    request('/api/screen-share/diagnostic',{stage,code:allowed.includes(error.name)?error.name:'Error'},false,true).catch(()=>{});
  }
  function release(){
    ++epoch;active=false;starting=false;clearTimeout(timer);for(const controller of pending)controller.abort();pending.clear();
    stream?.getTracks().forEach(track=>track.stop());stream=null;if(video)video.srcObject=null;video=null;
    identity=null;button.textContent='Share screen';button.setAttribute('aria-pressed','false');status.textContent='Screen sharing off';start.disabled=false;
    online.disabled=false;source.disabled=false;stopInside.disabled=true;dialog.querySelector('#screen-share-refresh').disabled=false;
    if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=null;preview.removeAttribute('src');preview.hidden=true;
  }
  async function stop(){const id=identity;release();button.disabled=true;start.disabled=true;try{await request('/api/screen-share',{action:'stop',...(id?{share_id:id}:{})},false,true).catch(()=>{});}finally{button.disabled=false;start.disabled=false;}}
  function describe(result){
    status.textContent=result.mode==='provider'?'Sharing with online reasoning · microphone unchanged':'Local screen preview active · no upload';
    if(result.warning){help.textContent=result.warning;notice(result.warning);}
  }
  async function frame(generation){
    if(generation!==epoch||!active)return;
    try{
      let result;
      if(stream){
        if(!video.videoWidth||!video.videoHeight){timer=setTimeout(()=>frame(generation),250);return;}
        const canvas=document.createElement('canvas'),scale=Math.min(1,1280/video.videoWidth,720/video.videoHeight);
        canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);
        canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);
        const jpeg=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.72));
        if(generation!==epoch)return;if(!jpeg)throw Error('Screen encoding failed.');
        result=await request('/api/screen-share/frame',jpeg,true);
      }else result=await request('/api/screen-share/capture',{share_id:identity});
      if(generation!==epoch)return;describe(result);
      if(dialog.open){
        const blob=await request('/api/screen-share/preview');if(generation!==epoch)return;
        if(previewUrl)URL.revokeObjectURL(previewUrl);preview.src=previewUrl=URL.createObjectURL(blob);preview.hidden=false;
      }
      timer=setTimeout(()=>frame(generation),1100);
    }catch(error){
      if(generation!==epoch)return;
      if(error.code==='rate_limited'){timer=setTimeout(()=>frame(generation),1100);return;}
      diagnostic('frame',error);await stop();notice(error.message);help.textContent=error.message;
    }
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
  button.onclick=()=>{if(active||starting){void stop();return;}dialog.showModal();void sources();};
  stopInside.onclick=()=>void stop();
  dialog.querySelector('#screen-share-refresh').onclick=sources;
  start.onclick=async()=>{
    if(active||starting)return;starting=true;start.disabled=true;source.disabled=true;online.disabled=true;stopInside.disabled=false;dialog.querySelector('#screen-share-refresh').disabled=true;const generation=++epoch;let stage='picker';
    try{
      const chosen=source.value==='browser'?null:selection[Number(source.value)];
      if(source.value==='browser'){
        if(!navigator.mediaDevices?.getDisplayMedia)throw new DOMException('Browser capture is unavailable. Choose a Windows source.','NotSupportedError');
        const picked=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:1},audio:false});
        if(generation!==epoch){picked.getTracks().forEach(track=>track.stop());return;}
        stream=picked;stream.getVideoTracks()[0].addEventListener('ended',()=>void stop(),{once:true});
        video=document.createElement('video');video.muted=true;video.srcObject=stream;await video.play();
      }else if(!chosen)throw Error('Choose an available source.');
      if(generation!==epoch)return;stage='start';
      const result=await request('/api/screen-share',{action:'start',mode:online.checked?'provider':'local',capture:chosen?'windows':'browser',...chosen});
      if(generation!==epoch){await request('/api/screen-share',{action:'stop',share_id:result.share_id},false,true).catch(()=>{});return;}
      identity=result.share_id;active=true;starting=false;button.textContent='Stop sharing';button.setAttribute('aria-pressed','true');status.textContent='Capturing the first frame…';if(result.warning){help.textContent=result.warning;notice(result.warning);}void frame(generation);
    }catch(error){if(generation===epoch){diagnostic(stage,error);await stop();help.textContent=error.name==='NotAllowedError'?'Capture was cancelled or blocked by the browser. Choose a Windows source to try local capture.':error.message;notice(help.textContent);}}
    finally{if(generation===epoch)starting=false;start.disabled=active;}
  };
  dialog.addEventListener('close',()=>{if(starting)void stop();});
  document.getElementById('stop').addEventListener('click',()=>void stop());
  window.addEventListener('lumina-event',event=>{
    if(event.detail.type==='screen_share_stopped')release();
    if(event.detail.type==='screen_share_local')describe({mode:'local',warning:event.detail.text});
    if(event.detail.type==='connection_closed')release();
  });
  window.addEventListener('pagehide',release);
  return {stop,isActive:()=>active};
}
