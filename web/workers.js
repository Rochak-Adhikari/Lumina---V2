import {workerAction} from './worker-actions.js';
const $=id=>document.getElementById(id);
export function setupWorkerPanel({getConfig,notice}){
  let sessions=[],selected=null,pending=false;
  function render(){
    const select=$('worker-select');
    select.replaceChildren(...sessions.map(s=>new Option(`${s.instruction.slice(0,65)} — ${s.status}`,s.worker_id)));
    if(!sessions.some(s=>s.worker_id===selected))selected=sessions.at(-1)?.worker_id;
    if(selected)select.value=selected;
    const s=sessions.find(s=>s.worker_id===selected);
    $('worker-cancel').disabled=!s||s.capabilities?.cancel===false||['CANCELLED','TERMINATED'].includes(s.status);
    $('worker-remove').disabled=!s;
    if(!s){for(const id of ['worker-meta','worker-error','worker-terminal','worker-changes','worker-tests','worker-events'])$(id).textContent='';$('worker-meta').textContent='No workers in this panel.';return;}
    $('worker-meta').textContent=`${s.status} · ${Math.round(s.elapsed)} seconds · ${s.workspace} · ${s.transport}`;
    $('worker-error').textContent=s.error||'';
    const terminal=$('worker-terminal'),atEnd=terminal.scrollTop+terminal.clientHeight>=terminal.scrollHeight-30;
    terminal.textContent=s.output||'Waiting for process output…';if(atEnd)terminal.scrollTop=terminal.scrollHeight;
    $('worker-changes').textContent=s.changed_files.length?`Confirmed changes: ${s.changed_files.join(', ')}`:'No confirmed file changes.';
    $('worker-tests').textContent=s.test_results.length?JSON.stringify(s.test_results):'No test execution reported.';
    $('worker-events').textContent=s.events.map(e=>`${new Date(e.timestamp*1000).toLocaleTimeString()} ${e.type}`).join('\n');
  }
  async function refresh(){
    if(pending)return;pending=true;
    try{const response=await fetch('/api/workers');const data=await response.json();sessions=data.workers;render();}catch(e){notice('Worker state could not be refreshed.');}finally{pending=false;}
  }
  function open(){if(!$('workers-panel').open)$('workers-panel').showModal();refresh();}
  $('workers-open').onclick=open;$('workers-close').onclick=()=>$('workers-panel').close();
  $('worker-select').onchange=()=>{selected=$('worker-select').value;render();};
  async function post(path,body){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Lumina-Token':getConfig().token},body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw Error(data.error||'Worker action failed.');return data;}
  async function lifecycle(action){
    const s=sessions.find(s=>s.worker_id===selected);if(!s)return;
    try{await workerAction(post,action,s);await refresh();}catch(e){notice(e.message);}
  }
  $('worker-cancel').onclick=()=>lifecycle('cancel');
  $('worker-remove').onclick=()=>lifecycle('remove');
  setInterval(()=>{if($('workers-panel').open)refresh();},1000);
  return {event(event){
    if(event.type==='worker_panel_open')open();
    if(event.type==='worker_event'){
      const e=event.data,s=sessions.find(s=>s.worker_id===e.worker_id);
      if(s&&e.type==='worker.output'){s.output=(s.output+e.text).slice(-100000);if(selected===s.worker_id)render();}
      else refresh();
    }
  }};
}
