// Local, on-demand inspector. Evidence is rendered as text, never HTML.
export function setupContinuity({getConfig,notice}){
  const $=id=>document.getElementById(id),panel=$('continuity-panel');
  let selected=null,busy=false;
  async function read(action,extra={}){
    const response=await fetch('/api/continuity?'+new URLSearchParams({action,...extra}),{headers:{'X-Lumina-Token':getConfig().token}});
    const result=await response.json();
    if(!response.ok||result.ok===false)throw Error(result.error||'Memory is unavailable.');
    return result;
  }
  function button(label,run){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=()=>run().catch(e=>notice(e.message));return b;}
  function element(tag,text){const node=document.createElement(tag);node.textContent=text;return node;}
  function detail(result){
    const host=$('continuity-detail');host.replaceChildren();
    if(result.record){
      const r=result.record;
      host.append(element('h3',r.object_value||r.description||r.chosen_option||r.title||r.pattern||r.prediction||r.name||result.kind));
      const metrics=document.createElement('dl');
      for(const [label,value] of Object.entries({'Status':r.status||'recorded','Privacy':r.privacy_class,
        'Confidence':result.confidence,'Stability':result.stability,'Freshness':result.freshness,'User confirmed':r.confirmed_by_user==null?null:(r.confirmed_by_user?'Yes':'No')})){
        if(value!=null)metrics.append(element('dt',label),element('dd',typeof value==='number'?value.toFixed(2):String(value)));
      }
      host.append(metrics,element('h4','Source evidence'));
      for(const e of result.evidence||[]){host.append(element('p',e.source_type+' · '+e.extraction_method+' · '+new Date(e.observed_at).toLocaleString()));if(e.source)host.append(element('p',`${e.source.source_path} · section ${e.source.section} · ${e.source.temporal} · source date unknown`),element('blockquote',e.source.quote));}
      if(!result.evidence?.length)host.append(element('p','No accessible source evidence.'));
      if(result.history?.length){host.append(element('h4','Belief history'));for(const h of result.history)host.append(element('p',h.object_value+' · '+h.status+' · '+new Date(h.valid_from).toLocaleString()));}
      if(result.contradictions?.length)host.append(element('p',result.contradictions.length+' conflicting relationship(s) are recorded. Review the evidence before relying on this belief.'));
      for(const [label,key] of [['Reasoning','reasoning'],['Expected outcome','expected_outcome']])if(r[key])host.append(element('h4',label),element('p',r[key]));
    }
    const raw=document.createElement('details');raw.append(element('summary','Inspect complete evidence and relationships'),element('pre',JSON.stringify(result,null,2)));host.append(raw);
  }
  function clearSelection(){selected=null;$('continuity-detail').replaceChildren();for(const id of ['continuity-edit','continuity-resolve','continuity-remove'])$(id).hidden=true;}
  async function explain(id){
    const result=await read('explain',{id});selected=result.record;
    detail(result);
    $('continuity-value').value=result.record.object_value||'';
    $('continuity-edit').hidden=result.kind!=='fact';
    $('continuity-resolve').hidden=!['goal','open_loop','commitment'].includes(result.kind);
    $('continuity-resolve').dataset.kind=result.kind;
    $('continuity-remove').hidden=!['fact','decision','goal','open_loop','commitment','episode','prediction','behavior_pattern'].includes(result.kind);
  }
  async function refresh(){
    if(busy)return;busy=true;
    try{
      clearSelection();
      const [status,state,result]=await Promise.all([read('status'),read('continuation'),read('recall',{query:$('continuity-query').value})]);
      $('continuity-status').textContent='Local memory · '+status.status+' · '+status.counts.fact+' facts · '+status.counts.event+' events';
      $('continuity-state').textContent=state.active_task?.description||state.open_loops?.[0]?.description||'No recorded unfinished work in this workspace.';
      const list=$('continuity-results');list.replaceChildren();
      for(const item of result.items||[]){const row=document.createElement('div');row.className='continuity-row';const label=document.createElement('span');
        label.textContent=item.kind+' · '+(item.record.object_value||item.record.description||item.record.chosen_option||item.record.title||item.record.prediction||item.record.pattern||item.id);
        row.append(label,button('Evidence',()=>explain(item.id)));list.append(row);}
      $('continuity-note').textContent=result.truncated?'Results were shortened to fit the context limit.':(result.uncertainties||[]).join(' ');
    }catch(e){$('continuity-status').textContent=e.message;}finally{busy=false;}
  }
  async function mutate(tool,arguments_){
    const response=await fetch('/api/continuity',{method:'POST',headers:{'Content-Type':'application/json','X-Lumina-Token':getConfig().token},body:JSON.stringify({tool,arguments:arguments_})});
    const result=await response.json();
    if(result.confirmation_required){panel.close();notice('Review the exact memory change in the confirmation dialog.');}
    else if(!response.ok||!result.ok)throw Error(result.error||'The change was not applied.');
  }
  $('continuity-open').onclick=()=>{panel.showModal();refresh();};
  $('continuity-close').onclick=()=>panel.close();
  $('continuity-refresh').onclick=refresh;
  $('continuity-search').onsubmit=e=>{e.preventDefault();refresh();};
  $('continuity-timeline').onclick=()=>read('timeline').then(r=>{clearSelection();detail(r);const raw=$('continuity-detail').querySelector('details');if(raw)raw.open=true;}).catch(e=>notice(e.message));
  $('continuity-edit').onsubmit=e=>{e.preventDefault();if(selected)mutate('memory_correct',{id:selected.id,new_value:$('continuity-value').value}).catch(e=>notice(e.message));};
  $('continuity-invalidate').onclick=()=>selected&&mutate('memory_forget',{id:selected.id,mode:'invalidate'}).catch(e=>notice(e.message));
  $('continuity-delete').onclick=()=>selected&&mutate('memory_forget',{id:selected.id,mode:'delete'}).catch(e=>notice(e.message));
  $('continuity-resolve').onclick=()=>selected&&mutate('memory_resolve',{id:selected.id,status:$('continuity-resolve').dataset.kind==='goal'?'completed':$('continuity-resolve').dataset.kind==='commitment'?'fulfilled':'resolved'}).catch(e=>notice(e.message));
  window.addEventListener('lumina-event',e=>{if(e.detail.type==='continuity_open'){if(!panel.open)panel.showModal();refresh();}if(e.detail.type==='continuity_inspect'){if(!panel.open)panel.showModal();explain(e.detail.id).catch(error=>notice(error.message));}if(e.detail.type==='continuity_result'&&panel.open)refresh();});
}
