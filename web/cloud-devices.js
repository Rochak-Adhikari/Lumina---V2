// Owner control plane. Proposing never executes; approval binds the displayed request.
export function setupCloudDevices({host,api,el,notice,button}){
  const section=el('section',undefined,'cloud-section');section.id='cloud-devices';section.append(el('h3','Connected devices'));
  section.append(el('p','Pair your PC or laptop, then choose exactly where work should run. Local tools remain on that device.','muted small'));
  const form=el('form');const name=el('input');name.required=true;name.maxLength=80;name.placeholder='Device name, such as My laptop';name.setAttribute('aria-label','New device name');
  const invite=el('button','Create pairing code');invite.type='submit';form.append(name,invite);
  const pairing=el('p');pairing.setAttribute('role','status');pairing.style.overflowWrap='anywhere';section.append(form,pairing);
  form.onsubmit=async e=>{e.preventDefault();invite.disabled=true;try{const r=await api('/devices/invitations',{method:'POST',body:{name:name.value},key:crypto.randomUUID()});pairing.textContent=`In Windows LUMINA, open Settings, Cloud device connection. Address: ${location.origin}. Pairing code: ${r.code}. Expires ${new Date(r.expires_at*1000).toLocaleTimeString()}. Compare fingerprints before approving.`;form.reset();}catch(err){notice(err.message);}finally{invite.disabled=false;}};
  const list=el('div');list.id='cloud-device-list';section.append(list);
  const action=el('form');const target=el('select');target.setAttribute('aria-label','Target device');target.required=true;
  const tool=el('select');tool.setAttribute('aria-label','Device action');
  const names={system_info:'Inspect machine',find_files:'Find workspace files',read_file:'Read workspace text file',list_directory:'List workspace folder',open_folder:'Open workspace folder',create_directory:'Create workspace folder',open_app:'Open an approved application'};
  for(const [value,label] of Object.entries(names)){const o=el('option',label);o.value=value;tool.append(o);}
  const arg=el('input');arg.placeholder='Workspace path, search query, or application name';arg.setAttribute('aria-label','Device action argument');arg.maxLength=1000;arg.disabled=true;
  tool.onchange=()=>{arg.disabled=tool.value==='system_info';arg.required=!arg.disabled;arg.maxLength=tool.value==='find_files'?240:1000;};
  const submit=el('button','Prepare request');submit.type='submit';action.append(target,tool,arg,submit);section.append(action);
  section.append(el('p','Files are limited to the paired workspace. Applications: Notepad, Calculator, Chrome or Edge. Approval is needed in this panel and then on the device; sharing results requires local review.','muted small'));
  const commands=el('div');commands.id='cloud-device-commands';section.append(commands);host.append(section);
  let pending=null;
  const stateText={awaiting_owner:'Review and approve this exact request.',queued:'Queued for this device; it may be offline or finishing earlier work.',claimed:'Waiting for approval on the Windows device.',running:'Started on the device; execution or local result review is pending.',succeeded:'succeeded — the device returned its approved result.',failed:'failed — inspect the result before retrying.',declined:'declined — execution or result sharing was refused locally.',cancelled:'cancelled before execution.',expired:'expired without completion.',unknown:'Outcome unknown. Inspect the device before creating a new request; LUMINA will not retry it automatically.'};
  action.onsubmit=async e=>{e.preventDefault();submit.disabled=true;try{const parameter=tool.value==='system_info'?null:tool.value==='find_files'?'query':tool.value==='open_app'?'name':'path';
      const body={device_id:target.value,tool:tool.value,args:parameter?{[parameter]:arg.value}:{}};
      if(pending&&JSON.stringify(pending.body)!==JSON.stringify(body))throw Error('Retry the unchanged request first; its receipt is uncertain.');
      pending??={body,key:crypto.randomUUID()};await api('/device-commands',{method:'POST',...pending});pending=null;await refresh();
    }catch(err){notice(err.message);if(err.status&&err.status<500&&err.status!==429)pending=null;}finally{submit.disabled=false;}};
  async function refresh(){const data=await api('/devices');const selected=target.value;target.replaceChildren();list.replaceChildren();
    for(const d of data.devices){const row=el('article');row.append(el('strong',d.name),el('p',`${d.status==='active'?(d.online?'Online':'Offline'):d.status} · ${d.last_seen?`Last seen ${new Date(d.last_seen*1000).toLocaleString()}`:'Not connected yet'}`),el('small',`Fingerprint: ${d.fingerprint}`));
      if(d.status==='pending')row.append(button('Approve matching fingerprint',async()=>{await api('/devices/'+d.id+'/approve',{method:'POST',body:{}});await refresh();}));
      if(d.status!=='revoked')row.append(button('Revoke this device',async()=>{if(!confirm(`Revoke ${d.name}? Pending requests will stop; actions already executing cannot be undone.`))return;await api('/devices/'+d.id+'/revoke',{method:'POST',body:{}});await refresh();}));list.append(row);
      if(d.status==='active'){const o=el('option',d.name+' · '+d.id.slice(0,8));o.value=d.id;target.append(o);}}
    if([...target.options].some(o=>o.value===selected))target.value=selected;
    submit.disabled=!target.options.length;if(!data.devices.length)list.append(el('p','No devices paired.'));
    commands.replaceChildren();for(const c of data.commands.slice(0,30)){const row=el('article');const d=data.devices.find(d=>d.id===c.device_id);row.append(el('strong',(d?.name||c.device_id)+' · '+(names[c.tool]||c.tool)),el('p',JSON.stringify(c.args_json)),el('p',stateText[c.status]||c.status),el('small','Request '+c.id));
      if(c.status==='awaiting_owner')row.append(button('Approve this exact request',async()=>{await api('/device-commands/'+c.id+'/approve',{method:'POST',body:{}});await refresh();}));
      if(['awaiting_owner','queued','claimed','running'].includes(c.status))row.append(button(c.status==='running'?'Stop waiting; outcome may be unknown':'Cancel request',async()=>{await api('/device-commands/'+c.id+'/cancel',{method:'POST',body:{}});await refresh();}));
      if(c.result_json){const details=el('details');details.append(el('summary','Approved device result'));const pre=el('pre',JSON.stringify(c.result_json,null,2));pre.style.cssText='white-space:pre-wrap;max-height:240px;overflow:auto;overflow-wrap:anywhere';details.append(pre);row.append(details);}commands.append(row);}
  }
  return {refresh,clear(){list.replaceChildren();commands.replaceChildren();pairing.textContent='';target.replaceChildren();pending=null;}};
}
