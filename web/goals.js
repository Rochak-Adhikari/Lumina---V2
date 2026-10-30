// Existing Controls/task channel; never creates approval or permission client-side.
export function setupGoals({getConfig,notice}) {
  const section=document.createElement('section');
  section.innerHTML='<h3>Local goals</h3><p>First select a window in Inspect Windows, or open and enable Lumina’s scratchpad. Each goal has a two-minute scope. Other applications, file changes, shell commands and message sending remain unavailable.</p><form><label class="field">Goal<select name="kind"><option value="inspect_window">Inspect selected window and verify controls</option><option value="scratchpad_text">Write and select exact scratchpad text</option></select></label><label class="field">Scratchpad text (local only)<textarea name="text" maxlength="2048" autocomplete="off"></textarea></label><label class="field">Step planning<select name="planning"><option value="local">Local bounded recipe</option><option value="configured">Configured model within the same scope</option></select></label><button>Review goal scope</button></form><section data-review hidden><pre style="white-space:pre-wrap;overflow-wrap:anywhere"></pre><button type="button" data-approve>Approve this exact goal</button><button type="button" data-reject>Dismiss review</button></section><button type="button" data-refresh>Refresh goals</button><p role="status"></p><div data-goals></div>';
  document.getElementById('task-start').before(section);
  const form=section.querySelector('form'),review=section.querySelector('[data-review]');
  const status=section.querySelector('[role=status]'),list=section.querySelector('[data-goals]');
  let pending=null,sequence=0;
  const headers=()=>({'Content-Type':'application/json','X-Lumina-Token':getConfig().token,
                      'X-Lumina-Client':getConfig().client_id});
  async function request(body){
    const response=await fetch('/api/tasks',{method:'POST',headers:headers(),body:JSON.stringify(body)});
    const result=await response.json();
    if(!response.ok)throw Error(result.error||'Goal request unavailable.');
    return result;
  }
  function show(result){
    pending=result.review?result:null;review.hidden=!pending;
    if(pending){
      const r=result.review;
      review.querySelector('pre').textContent=`${r.goal}\nTarget: ${r.target}\nSteps: ${r.steps.join(' → ')}\nPlanning: ${r.planning}\nExpires in ${r.expires_in} seconds.\n${r.limits}`+
        (r.literal_text!==null?`\n\nReview literal text, including whitespace:\n${JSON.stringify(r.literal_text)}\n\n${r.literal_text}`:'');
    }
    status.textContent=result.reason||result.task?.summary||'Review the exact scope before starting.';
  }
  async function refresh(){
    try{
      const response=await fetch('/api/tasks',{headers:headers()});
      const data=await response.json();list.replaceChildren();
      for(const task of data.tasks.filter(t=>t.kind==='local_goal')){
        const card=document.createElement('article'),title=document.createElement('p'),progress=document.createElement('pre');
        title.textContent=`${task.instruction} — ${task.status.replaceAll('_',' ')}. ${task.summary}`;
        progress.style.whiteSpace='pre-wrap';
        progress.textContent=`Task: ${task.task_id}\nCurrent step: ${task.goal.step||'none'} · ${task.goal.phase}\nReason: ${task.goal.reason||'none'}\nVerified: ${task.goal.verified_steps.length}/${task.goal.total_steps}\nObservation: ${task.goal.observation} · Vision: ${task.goal.analysis} · Planner: ${task.goal.provider}\nPending planner calls: ${task.goal.pending_planner}\nSupported steps: ${task.goal.supported_actions.join(', ')}\n`+
          task.goal.verified_steps.map(s=>`${s.step}: verified at ${s.observed_at}\n${JSON.stringify(s.evidence)}`).join('\n');
        card.append(title,progress);
        for(const [action,label] of (task.status==='RUNNING'? [['goal_pause','Pause'],['goal_cancel','Cancel goal']]:
            task.status==='WAITING_FOR_USER'?[['goal_review','Review remaining scope'],['goal_cancel','Cancel goal']]:[])){
          const b=document.createElement('button');b.type='button';b.textContent=label;
          b.onclick=async()=>{try{show(await request({action,task_id:task.task_id}));await refresh();}catch(e){notice(e.message);}};
          card.append(b);
        }
        list.append(card);
      }
    }catch(_){status.textContent='Goal status unavailable; completion is unverified.';}
  }
  form.addEventListener('input',()=>{sequence++;pending=null;review.hidden=true;});
  form.onsubmit=async event=>{
    event.preventDefault();const ticket=++sequence;
    const kind=form.elements.kind.value;
    try{const result=await request({action:'goal_prepare',kind,planning:form.elements.planning.value,
        ...(kind==='scratchpad_text'?{text:form.elements.text.value}:{})});
      if(ticket===sequence)show(result);await refresh();
    }catch(e){notice(e.message);}
  };
  section.querySelector('[data-approve]').onclick=async()=>{
    if(!pending)return;const p=pending;pending=null;review.hidden=true;
    try{show(await request({action:'goal_approve',task_id:p.task_id,confirmation_id:p.confirmation_id}));await refresh();}
    catch(e){notice(e.message);}
  };
  section.querySelector('[data-reject]').onclick=()=>{sequence++;pending=null;review.hidden=true;};
  section.querySelector('[data-refresh]').onclick=refresh;
  document.getElementById('controls-open').addEventListener('click',refresh);
  document.getElementById('stop').addEventListener('click',()=>{sequence++;pending=null;review.hidden=true;});
  return {event(message){
    if(message.client_id!==getConfig()?.client_id)return;
    if(message.type==='goal_review'){
      if(!document.getElementById('controls').open)document.getElementById('controls').showModal();
      show(message.data);refresh();
    }
    if(message.type==='agent_result'&&message.data.kind==='local_goal')refresh();
  }};
}
