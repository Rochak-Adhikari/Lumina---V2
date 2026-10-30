// Explicit low-risk native surface. No model actions or arbitrary HWND inputs.
export function setupOwnedWindow({getConfig, notice}) {
  const button = document.createElement('button');
  button.type = 'button'; button.textContent = 'Windows scratchpad';
  document.querySelector('.composer-actions').append(button);
  const dialog = document.createElement('dialog');
  dialog.innerHTML = '<h2>Local Windows scratchpad</h2><p>Only changes text in Lumina’s temporary native window. No files, clipboard or other applications. Start screen sharing first and keep it running for verification.</p><textarea maxlength="2048" aria-label="Scratchpad text"></textarea><p role="status"></p><button type="button" data-action="open">Open native window</button><button type="button" data-action="set_text">Apply text</button><button type="button" data-action="clear">Click clear scratchpad</button><button type="button" data-action="stop">Stop control</button><button type="button" data-action="close">Close native window</button><button type="button" data-dismiss>Dismiss</button>';
  document.body.append(dialog);
  const selectAll = document.createElement('button');
  selectAll.type = 'button'; selectAll.dataset.action = 'select_all';
  selectAll.textContent = 'Select scratchpad text';
  dialog.querySelector('[data-action=clear]').before(selectAll);
  button.onclick = () => dialog.showModal();
  dialog.querySelector('[data-dismiss]').onclick = () => dialog.close();
  for (const item of dialog.querySelectorAll('[data-action]')) {
    item.onclick = async () => {
      const config = getConfig();
      const body = {action: item.dataset.action};
      if (body.action === 'set_text') body.text = dialog.querySelector('textarea').value;
      item.disabled = true;
      try {
        const response = await fetch('/api/owned-window', {method: 'POST', headers: {
          'Content-Type': 'application/json', 'X-Lumina-Token': config.token,
          'X-Lumina-Client': config.client_id}, body: JSON.stringify(body)});
        const result = await response.json();
        dialog.querySelector('[role=status]').textContent = result.message || result.reason || result.error || result.state || result.status || (result.ok ? 'Done' : 'Outcome unverified');
      } catch (_) { notice('Scratchpad outcome unavailable. Stop control and inspect; do not automatically retry.'); }
      finally { item.disabled = false; }
    };
  }

  const inspect = document.createElement('button');
  inspect.type = 'button'; inspect.textContent = 'Inspect Windows';
  button.after(inspect);
  const view = document.createElement('dialog');
  view.innerHTML = '<h2>Windows and accessible controls</h2><p>Read-only inspection. Selecting a window does not focus it or allow changes. Editable values are redacted. Chat: “list windows”, “inspect window 1”, or “inspect selected window”.</p><p data-capabilities>Application changes, file changes, shell commands, general input, checkbox actions and browser changes are disabled.</p><p data-perception>No shared observation checked yet.</p><button type="button" data-list>Find windows</button><select aria-label="Discovered windows"></select><button type="button" data-select>Inspect selected window</button><button type="button" data-refresh>Refresh controls</button><p role="status"></p><ul></ul><button type="button" data-dismiss>Dismiss</button>';
  document.body.append(view);
  inspect.onclick = () => view.showModal();
  const select = view.querySelector('select'), list = view.querySelector('ul');
  const approval=document.createElement('section');
  approval.hidden=true;
  const review=document.createElement('pre');review.style.whiteSpace='pre-wrap';
  const approve=document.createElement('button'),deny=document.createElement('button');
  approve.type=deny.type='button';approve.textContent='Approve exact fixture edit';deny.textContent='Reject';
  approval.append(review,approve,deny);list.after(approval);
  let proposed=null;
  let requestSequence = 0;
  async function request(body) {
    const config = getConfig();
    const response = await fetch('/api/windows', {method: 'POST', headers: {
      'Content-Type': 'application/json', 'X-Lumina-Token': config.token,
      'X-Lumina-Client': config.client_id}, body: JSON.stringify(body)});
    return response.json();
  }
  async function show(body, delivered = null) {
    const sequence = ++requestSequence;
    let waiting=true,pollTimer;
    const outcome=result=>{
      if(result.requires_confirmation)return 'Awaiting your approval.';
      if(result.state==='succeeded')return 'Verified: the fixture matches the approved result.';
      if(['failed','cancelled'].includes(result.state)&&result.semantic==='unknown')return 'Outcome uncertain: the operation may have occurred. Do not retry.';
      return result.reason||result.error||result.state||result.status||'Outcome unavailable';
    };
    async function progress(){
      if(!waiting||sequence!==requestSequence)return;
      try{
        const result=await request({action:'external_status',action_id:body.action_id});
        if(waiting&&sequence===requestSequence)view.querySelector('[role=status]').textContent=outcome(result);
      }catch(_){if(waiting&&sequence===requestSequence)view.querySelector('[role=status]').textContent='Status unavailable; outcome unverified.';}
      if(waiting&&sequence===requestSequence)pollTimer=setTimeout(progress,250);
    }
    proposed=null;approval.hidden=true;
    list.replaceChildren();
    for (const b of view.querySelectorAll('button:not([data-dismiss]):not([data-control-stop])')) b.disabled = true;
    try {
      if(body.action==='external_approve'){
        view.querySelector('[role=status]').textContent='Approval submitted; awaiting control status.';
        pollTimer=setTimeout(progress,250);
      }
      const result = delivered || await request(body);
      waiting=false;clearTimeout(pollTimer);
      if (sequence !== requestSequence) return;
      const status = {admission_stopped: 'Control stopped. Pending inspection cleanup may still be running.',
        inspection_resumed: 'Read-only inspection resumed. Desktop actions remain stopped.',
        inspection_resume_blocked: 'Inspection cannot resume yet. Cleanup may still be running.'};
      view.querySelector('[role=status]').textContent = result.message || status[result.status] || result.error || result.toggle_unavailable || (result.truncated ? 'Showing a limited control tree.' : 'Read-only inspection complete.');
      if(result.capabilities){
        view.querySelector('[data-capabilities]').textContent = `Windows: ${result.capabilities.window_inspection.replaceAll('_',' ')}. Scratchpad: Lumina’s temporary window only. Third-party editing: disabled. File changes, shell, raw input, UIA Toggle and browser changes: disabled.`;
      }
      if(result.perception){
        view.querySelector('[data-perception]').textContent = `Shared observation: ${result.perception.observation}. Vision analysis: ${result.perception.analysis}. Results below come from structured UI inspection; no visual match is claimed.`;
      }
      if(body.action.startsWith('external_')){
        view.querySelector('[role=status]').textContent=outcome(result);
      }
      if(result.requires_confirmation&&result.review){
        proposed=result;approval.hidden=false;
        const toggle=result.review.operation==='toggle_external_fixture';
        approve.textContent=toggle?'Approve exact checkbox change':result.review.operation?'Approve exact button action':'Approve exact fixture edit';
        const state=value=>value.split(':')[0]==='1'?'On':'Off';
        const change=toggle?`Checkbox: ${state(result.review.before)} → ${state(result.review.after)}\nThe decoy must remain Off. Restoration requires a separate approval.`:result.review.operation?`${result.review.operation==='increment_external_fixture'?'Increment counter once':'Reset counter'}\nCounter: ${result.review.before.split(':')[0]} → ${result.review.after.split(':')[0]}\nThe decoy counter must remain 0.`:`Set value to: ${result.review.value}`;
        review.textContent=`Only the registered disposable fixture\nWindow: ${result.review.window}\nControl: ${result.review.control}\n${change}\nApproval expires and cannot authorize another action.`;
      }
      if (result.windows) {
        select.replaceChildren();
        for (const row of result.windows) {
          const option = document.createElement('option');
          option.value = row.id; option.textContent = row.name || 'Unnamed window';
          select.append(option);
        }
      }
      for (const control of result.controls || []) {
        const item = document.createElement('li');
        item.textContent = `${control.role}: ${control.name || 'Unnamed'} — ${(control.patterns || []).join(', ') || 'No supported patterns'}${control.enabled ? '' : ' (disabled)'}`;
        const details = document.createElement('button');
        details.type = 'button'; details.textContent = 'Refresh this control';
        details.onclick = () => show({action: 'control', control: control.id});
        item.append(details);
        if((result.fixture_controls||[]).includes(control.id)){
          for(const [restore,label] of [[false,'Propose test edit'],[true,'Propose restoration']]){
            const edit=document.createElement('button');edit.type='button';edit.textContent=label;
            edit.onclick=()=>show({action:'external_propose',control:control.id,restore});item.append(edit);
          }
        }
        const allowed=(result.fixture_buttons||[]).find(row=>row.id===control.id);
        if(allowed){
          const invoke=document.createElement('button');invoke.type='button';
          invoke.textContent=allowed.operation==='increment_external_fixture'?'Propose counter increment':'Propose counter reset';
          invoke.onclick=()=>show({action:'external_button_propose',control:control.id,operation:allowed.operation});item.append(invoke);
        }
        if((result.fixture_toggles||[]).includes(control.id)){
          const toggle=document.createElement('button');toggle.type='button';toggle.textContent='Propose checkbox change';
          toggle.onclick=()=>show({action:'external_toggle_propose',control:control.id});item.append(toggle);
        }
        list.append(item);
      }
    } catch (_) { if (sequence === requestSequence) view.querySelector('[role=status]').textContent = 'Window inspection unavailable.'; }
    finally { waiting=false;clearTimeout(pollTimer);if (sequence === requestSequence) for (const b of view.querySelectorAll('button')) b.disabled = false; }
  }
  view.querySelector('[data-list]').onclick = () => show({action: 'list'});
  window.addEventListener('lumina-event', event => {
    const message=event.detail;
    if(message.type!=='window_inspection'||message.client_id!==getConfig()?.client_id)return;
    if(!view.open)view.showModal();
    show({action:message.data.inspection_action},message.data);
  });
  approve.onclick=()=>{if(proposed){const p=proposed;show({action:'external_approve',action_id:p.action_id,confirmation:p.confirmation,request:p.request});}};
  deny.onclick=()=>{if(proposed)show({action:'external_deny',action_id:proposed.action_id});};
  view.querySelector('[data-select]').onclick = () => show({action: 'select', window: select.value});
  view.querySelector('[data-refresh]').onclick = () => show({action: 'refresh'});
  const resume = document.createElement('button');
  resume.type = 'button'; resume.textContent = 'Resume inspection only';
  resume.onclick = () => show({action: 'resume'});
  view.querySelector('[data-refresh]').after(resume);
  const stop = document.createElement('button');
  stop.dataset.controlStop = '';
  stop.type = 'button'; stop.textContent = 'Stop control';
  stop.onclick = () => show({action: 'stop'});
  resume.after(stop);
  document.getElementById('stop').addEventListener('click',()=>{
    requestSequence++;proposed=null;approval.hidden=true;list.replaceChildren();
    for(const b of view.querySelectorAll('button'))b.disabled=false;
    if(view.open)view.querySelector('[role=status]').textContent='Control stopped. Late outcomes require fresh inspection.';
  });
  view.querySelector('[data-dismiss]').onclick = () => view.close();
  view.addEventListener('close', () => {
    if(proposed)request({action:'external_deny',action_id:proposed.action_id}).catch(()=>{});
    proposed=null;approval.hidden=true;
    requestSequence++;
    for (const b of view.querySelectorAll('button')) b.disabled = false;
    list.replaceChildren(); select.replaceChildren();
    request({action: 'clear'}).catch(() => {});
  });
}
