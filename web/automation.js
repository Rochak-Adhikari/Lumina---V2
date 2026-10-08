// Explicit user controls; merely opening this panel never creates background work.
export function setupAutomation({getConfig,notice}){
  const $=id=>document.getElementById(id), panel=$('automation-panel');
  let timer=null, loading=false;
  async function invoke(tool,args){
    const response=await fetch('/api/phase2',{method:'POST',headers:{'Content-Type':'application/json','X-Lumina-Token':getConfig().token},body:JSON.stringify({tool,args})});
    const result=await response.json();
    $('automation-result').textContent=result.confirmation_required?'Review the exact action in the confirmation dialog.':result.error||result.message||result.status||'Result received.';
    if(!response.ok)throw Error(result.error||'The operation failed.');
    return result;
  }
  function button(label,run){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=async()=>{b.disabled=true;try{await run();await refresh();}catch(e){notice(e.message);}finally{b.disabled=false;}};return b;}
  function evidence(container,items){
    for(const item of (items||[]).slice(0,10)){
      const row=document.createElement('p');row.textContent=item.title||item.message||item.text||item.status||'Event';
      if(item.url){try{const url=new URL(item.url);if(['https:','http:'].includes(url.protocol)){const link=document.createElement('a');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';link.textContent=' Source';row.append(link);}}catch{}}
      container.append(row);
    }
  }
  function resultView(tool,result){
    const id={computer_settings:'automation-settings-result',computer_control:'automation-controls-result',youtube_video:'automation-video-result'}[tool];
    if(!id)return;
    const container=$(id);container.replaceChildren();
    const summary=document.createElement('p');summary.textContent=result.error||result.message||(result.confirmation_required?'Review the confirmation to continue.':result.status||'Observed result');container.append(summary);
    if(result.undo_id)$('automation-undo-id').value=result.undo_id;
    if(result.snapshot)$('automation-snapshot').value=result.snapshot;
    for(const target of result.targets||result.windows||[]){
      const row=button(target.name||target.id,async()=>{
        if(tool==='computer_settings'){$('automation-setting-target').value=target.id;const r=await invoke(tool,{action:'get',kind:$('automation-setting-kind').value,target:target.id});resultView(tool,r);}
        else{$('automation-window').value=target.id;const r=await invoke(tool,{action:'inspect',window:target.id});resultView(tool,r);}
      });container.append(row);
    }
    for(const control of result.controls||[]){
      if(!control.enabled||control.password||!control.patterns?.length)continue;
      const row=button(`${control.name||control.automation_id||control.role} · ${control.patterns.join(', ')}`,async()=>{$('automation-control').value=control.id;});container.append(row);
    }
    if(result.state){const row=document.createElement('p');const value=result.state.value;row.textContent='Current value: '+(typeof value==='object'?`${Math.round(value.volume*100)}% · ${value.mute?'muted':'unmuted'}`:value);container.append(row);}
    if(result.verified!==undefined){const row=document.createElement('p');row.textContent=result.verified?'Read-back verified.':'Outcome is unverified; inspect before retrying.';container.append(row);}
    if(result.title||result.metadata?.title||result.metadata?.snippet?.title)evidence(container,[{title:result.title||result.metadata?.title||result.metadata?.snippet?.title,url:result.url}]);
    if(result.provider||result.source){const row=document.createElement('p');row.textContent=`Source: ${result.provider||result.source}${result.language?' · '+result.language:''}${result.sampled?' · sampled excerpts':''}`;container.append(row);}
    evidence(container,result.results);
    for(const section of result.sections||[])evidence(container,section.excerpts);
    if(!result.sections)evidence(container,result.segments?.slice(0,75));
    if(result.segments?.length>75&&!result.sections){const row=document.createElement('p');row.textContent=`Showing 75 of ${result.segments.length} transcript segments. Use summary context for coverage across the video.`;container.append(row);}
  }
  async function refresh(){
    if(!panel.open||loading)return;loading=true;
    try{
      const response=await fetch('/api/phase2',{headers:{'X-Lumina-Token':getConfig().token}}), data=await response.json();
      if(!response.ok||!data.ok)throw Error(data.error||'Automation status unavailable.');
      $('automation-status').textContent='Only watches you create run. '+Object.entries(data.capabilities||{}).map(([name,value])=>`${name.replaceAll('_',' ')}: ${value.status||'unavailable'}`).join(' · ');
      const watches=$('automation-watches');watches.replaceChildren();
      for(const watch of data.watches||[]){
        const card=document.createElement('article'),title=document.createElement('strong'),detail=document.createElement('p');
        title.textContent=watch.query;detail.textContent=`${watch.status} · ${watch.interval||watch.interval_seconds} seconds · ${watch.outcome||'baseline pending'}`;
        card.append(title,detail,button('Inspect',async()=>{const r=await invoke('background_monitor',{action:'inspect',id:watch.id});$('automation-result').textContent=r.error||`${r.watch.query}: ${r.watch.outcome}; next check ${r.watch.next_at}. ${r.watch.failures} consecutive failures.`;}),button(watch.status==='paused'?'Resume':'Pause',()=>invoke('background_monitor',{action:watch.status==='paused'?'resume':'pause',id:watch.id})),button('Remove',()=>invoke('background_monitor',{action:'remove',id:watch.id})));watches.append(card);
      }
      if(!watches.children.length)watches.textContent='No watches configured.';
      const inbox=$('automation-inbox');inbox.replaceChildren();
      for(const event of data.events||[]){const card=document.createElement('article');evidence(card,[event]);evidence(card,event.evidence);card.append(button('Dismiss',()=>invoke('proactive',{action:'dismiss',id:event.id||event.delivery_id})));inbox.append(card);}
      if(!inbox.children.length)inbox.textContent='No notifications.';
      $('automation-notification-state').textContent=data.enabled?'Notifications enabled':'Notifications disabled';
    }catch(e){$('automation-status').textContent=e.message;}finally{loading=false;}
  }
  $('automation-open').onclick=()=>{panel.showModal();refresh();timer=setInterval(refresh,5000);};
  panel.addEventListener('close',()=>{clearInterval(timer);timer=null;});
  $('automation-close').onclick=()=>panel.close();
  $('automation-watch-form').onsubmit=async e=>{e.preventDefault();try{await invoke('background_monitor',{action:'create',query:$('automation-query').value,interval:Number($('automation-interval').value),notify:true});await refresh();}catch(error){notice(error.message);}};
  $('automation-enable').onclick=async()=>{try{await invoke('proactive',{action:'configure',enabled:true});await refresh();}catch(e){notice(e.message);}};
  $('automation-disable').onclick=async()=>{try{await invoke('proactive',{action:'configure',enabled:false});await refresh();}catch(e){notice(e.message);}};
  $('automation-snooze').onclick=async()=>{try{await invoke('proactive',{action:'snooze',minutes:60});await refresh();}catch(e){notice(e.message);}};
  $('automation-quiet-form').onsubmit=async e=>{e.preventDefault();try{await invoke('proactive',{action:'configure',timezone:$('automation-timezone').value,quiet_start:$('automation-quiet-start').value,quiet_end:$('automation-quiet-end').value});await refresh();}catch(error){notice(error.message);}};
  $('automation-settings-form').onsubmit=async e=>{e.preventDefault();try{const action=$('automation-setting-action').value,kind=$('automation-setting-kind').value,args={action,kind};if(action!=='list_targets')args.target=$('automation-setting-target').value;if(action==='set')args.value=kind==='audio'?{volume:Number($('automation-setting-value').value)/100,mute:$('automation-audio-mute').checked}:kind==='window'?$('automation-setting-value').value:Number($('automation-setting-value').value);const r=await invoke('computer_settings',args);resultView('computer_settings',r);}catch(error){notice(error.message);}};
  $('automation-undo').onclick=async()=>{try{await invoke('computer_settings',{action:'undo',undo_id:$('automation-undo-id').value});}catch(error){notice(error.message);}};
  $('automation-windows').onclick=async()=>{try{const r=await invoke('computer_control',{action:'list_windows'});resultView('computer_control',r);}catch(error){notice(error.message);}};
  $('automation-control-form').onsubmit=async e=>{e.preventDefault();try{const action=$('automation-control-action').value,args={action};if(action==='inspect')args.window=$('automation-window').value;else{args.focus=true;args.snapshot=$('automation-snapshot').value;args.control=$('automation-control').value;if(action==='type')args.text=$('automation-control-text').value;}const r=await invoke('computer_control',args);$('automation-control-text').value='';if(r.snapshot)$('automation-snapshot').value=r.snapshot;resultView('computer_control',r);}catch(error){notice(error.message);}};
  $('automation-youtube-form').onsubmit=async e=>{e.preventDefault();try{const args={action:$('automation-youtube-action').value,url:$('automation-youtube-url').value};if($('automation-transcript-path').value&&['transcript','summarize'].includes(args.action))args.transcript_path=$('automation-transcript-path').value;const r=await invoke('youtube_video',args);resultView('youtube_video',r);}catch(error){notice(error.message);}};
  window.addEventListener('lumina-event',event=>{if(event.detail.type!=='phase2_result')return;const {tool,data}=event.detail;const id={computer_settings:'automation-settings-result',computer_control:'automation-controls-result',youtube_video:'automation-video-result'}[tool];if(id)resultView(tool,data);if(data.undo_id)$('automation-undo-id').value=data.undo_id;if(panel.open)refresh();});
  return {refresh};
}
