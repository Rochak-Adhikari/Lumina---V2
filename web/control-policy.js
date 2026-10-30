// This is a view of backend admission. It cannot grant authority or enable adapters.
export function setupControlPolicy(){
  const $=id=>document.getElementById(id);
  const selections=[['automation-setting-action','computer_settings'],
    ['automation-control-action','computer_control'],['automation-youtube-action','youtube_video']];
  const controls=[['phase1-browser button','browser_control','start'],
    ['#automation-undo','computer_settings','undo'],['#task-submit','start_coding_agent','execute']];
  const nodes=[];
  for(const [id,tool] of selections)for(const option of $(id)?.options||[])nodes.push([option,tool,option.value]);
  for(const [selector,tool,action] of controls){
    const node=document.querySelector(selector.startsWith('#')?selector:'#'+selector);
    if(node)nodes.push([node,tool,action]);
  }
  const summary=document.createElement('section');
  summary.setAttribute('aria-label','Windows workflow availability');
  const heading=document.createElement('h3');heading.textContent='Supported Windows workflows';
  const list=document.createElement('ul');summary.append(heading,list);
  $('local-command')?.before(summary);
  const note=document.createElement('p');note.textContent='Windows inspection is read-only. General input, settings changes and undo are disabled; use the owned scratchpad for admitted changes.';
  $('automation-settings-form')?.before(note);
  function disarm(){for(const [node] of nodes){node.disabled=true;node.title='Backend capability status unavailable.';}}
  disarm();
  async function refresh(){
    try{
      const response=await fetch('/api/capabilities',{cache:'no-store'});
      if(!response.ok)throw Error('unavailable');
      const policy=(await response.json()).control_policy;
      if(!policy||!Array.isArray(policy.workflows)||!policy.tools)throw Error('unavailable');
      for(const [node,tool,action] of nodes){
        const rule=policy.tools[tool]?.[action];node.disabled=rule?.admitted!==true;
        node.title=rule?.reason||'Backend capability status unavailable.';
      }
      for(const [id] of selections){const select=$(id);if(select?.selectedOptions[0]?.disabled)select.value=[...select.options].find(o=>!o.disabled)?.value||'';}
      list.replaceChildren();
      for(const workflow of policy.workflows){const item=document.createElement('li');
        item.textContent=`${workflow.name}: ${workflow.state.replaceAll('_',' ')}. ${workflow.reason}`;list.append(item);}
    }catch(_){disarm();list.textContent='Capability status unavailable. Restricted operations remain disabled.';}
  }
  $('controls-open')?.addEventListener('click',refresh);
  $('automation-open')?.addEventListener('click',refresh);
  return {refresh};
}
