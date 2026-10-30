// Explicit local controls. Results are textContent, never executable markup.
export function setupCapabilities({getConfig,notice}){
  const $=id=>document.getElementById(id),panel=$('capabilities-panel');
  const fields={
    file_controller:{inspect:['path'],create_text:['path','text'],edit_text:['path','expected_hash','text'],append_text:['path','expected_hash','text'],history:[],undo:['operation_id'],largest:['path'],usage:['path'],plan_organization:['path'],apply_plan:['plan_id'],restore_plan:['operation_id'],plan_archive:['path','destination'],create_archive:['plan_id'],cancel:[]},
    plugins:{list:[],inspect:['path'],install:['path','trusted_code'],enable:['id'],disable:['id'],uninstall:['id'],run:['id','input'],cancel:[]},
    desktop_conveniences:{known_folders:[],wallpaper_get:[],wallpaper_set:['path'],wallpaper_restore:['operation_id']},
    communication_resolve:{resolve:['provider','query']},communication_history:{list:[],receipt:['request_id']}
  };
  const names={file_controller:'Files & recovery',plugins:'Extensions',desktop_conveniences:'Desktop',communication_resolve:'Resolve recipient',communication_history:'Message receipts'};
  function view(result){
    $('capabilities-result').textContent=JSON.stringify(result,null,2);
    $('capabilities-result').scrollTop=0;
    if(result.sha256)$('capability-expected_hash').value=result.sha256;
    if(result.operation_id)$('capability-operation_id').value=result.operation_id;
    if(result.plan_id)$('capability-plan_id').value=result.plan_id;
    if(result.text!==undefined)$('capability-text').value=result.text;
    const list=$('capabilities-items');list.replaceChildren();
    for(const item of result.plugins||[]){
      const id=item.manifest?.id;if(!id)continue;
      const button=document.createElement('button');button.type='button';
      button.textContent=`${id} · ${item.manifest.version} · ${item.health||'not installed'}`;
      button.onclick=()=>{$('capability-id').value=id;$('capability-path').value=item.path||'';};list.append(button);
    }
    for(const record of result.operations||[]){
      const button=document.createElement('button');button.type='button';button.textContent=`${record.action} · ${record.status} · ${record.path||record.moved||record.operation_id}`;
      button.onclick=()=>{$('capability-operation_id').value=record.operation_id;};list.append(button);
    }
  }
  function actionFields(){
    const selected=fields[$('capability-tool').value][$('capability-action').value];
    for(const element of panel.querySelectorAll('[data-field]'))element.hidden=!selected.includes(element.dataset.field);
    $('capabilities-help').textContent=$('capability-tool').value==='plugins'?
      'Install registers only; enable is separate. Code changes disable the extension. Python extensions run with your Windows account authority: process isolation is not a security sandbox. Builtin text-lab is an offline example.':
      'Read operations run locally. Changes show an exact confirmation. Keep operation IDs for recovery; changed targets are never silently restored.';
  }
  function toolActions(){
    const select=$('capability-action');select.replaceChildren();
    for(const action of Object.keys(fields[$('capability-tool').value])){const option=document.createElement('option');option.value=action;option.textContent=action.replaceAll('_',' ');select.append(option);}
    actionFields();
  }
  async function refresh(){
    try{const r=await fetch('/api/phase3',{headers:{'X-Lumina-Token':getConfig()?.token||''},cache:'no-store'});
      const data=await r.json();if(!r.ok)throw Error('Capability status unavailable.');
      $('capabilities-status').textContent=Object.entries(data.capabilities).filter(([k])=>names[k]).map(([k,v])=>`${names[k]}: ${v.status||'unavailable'}`).join(' · ');
    }catch(error){$('capabilities-status').textContent=error.message;}
  }
  for(const [id,name] of Object.entries(names)){const option=document.createElement('option');option.value=id;option.textContent=name;$('capability-tool').append(option);}
  $('capability-tool').onchange=toolActions;$('capability-action').onchange=actionFields;toolActions();
  $('capabilities-open').onclick=()=>{panel.showModal();refresh();};$('capabilities-close').onclick=()=>panel.close();
  $('capabilities-form').onsubmit=async event=>{
    event.preventDefault();const tool=$('capability-tool').value,action=$('capability-action').value,args={action};
    try{
      for(const key of fields[tool][action]){const input=$('capability-'+key);args[key]=key==='input'?JSON.parse(input.value||'{}'):key==='trusted_code'?input.checked:input.value;}
      $('capabilities-result').textContent='Working…';
      const r=await fetch('/api/phase3',{method:'POST',headers:{'Content-Type':'application/json','X-Lumina-Token':getConfig()?.token||''},body:JSON.stringify({tool,args})});
      const result=await r.json();if(!r.ok)throw Error(result.error||'Operation failed.');view(result);await refresh();
    }catch(error){notice(error.message);$('capabilities-result').textContent=error.message;}
  };
  window.addEventListener('lumina-event',event=>{if(event.detail.type==='phase3_result'||event.detail.type==='capability_result'&&names[event.detail.tool]){view(event.detail.data);if(panel.open)refresh();}});
}
