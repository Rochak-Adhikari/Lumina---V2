// Presentation only: move the existing nodes, preserving their handlers and state.
export function setupChatLayout(){
  const $=id=>document.getElementById(id);
  const drawer=document.querySelector('.environment');
  const heading=document.querySelector('.console-heading');
  const toggle=document.createElement('button');
  toggle.type='button';toggle.id='knowledge-toggle';toggle.textContent='Knowledge Graph';
  toggle.setAttribute('aria-controls','knowledge-drawer');toggle.setAttribute('aria-expanded','false');
  toggle.title='Open Knowledge Graph';heading.append(toggle);
  drawer.id='knowledge-drawer';drawer.setAttribute('aria-label','Knowledge Graph');
  const drawerHead=document.createElement('div');drawerHead.className='knowledge-drawer-head';
  const title=document.createElement('h2');title.textContent='Knowledge Graph';
  const close=document.createElement('button');close.type='button';close.id='knowledge-close';
  close.textContent='×';close.setAttribute('aria-label','Close Knowledge Graph');close.title='Close Knowledge Graph (Escape)';
  drawerHead.append(title,close);drawer.prepend(drawerHead);document.body.append(drawer);
  let opened=false,returnFocus=null;
  function setDrawer(value,{restore=true,focus=true}={}){
    if(opened===value)return;
    opened=value;
    if(opened)returnFocus=document.activeElement;
    drawer.inert=!opened;drawer.setAttribute('aria-hidden',String(!opened));
    drawer.classList.toggle('is-open',opened);toggle.setAttribute('aria-expanded',String(opened));
    // Keep the very same toggle reachable when the drawer covers its old place.
    if(opened)drawerHead.insertBefore(toggle,close);else heading.append(toggle);
    title.hidden=opened;
    toggle.title=opened?'Close Knowledge Graph':'Open Knowledge Graph';
    if(opened&&focus)close.focus({preventScroll:true});
    if(!opened&&restore)(returnFocus?.isConnected?returnFocus:toggle).focus({preventScroll:true});
  }
  // Nonmodal: chat and navigation remain usable. Off-screen controls cannot focus.
  drawer.inert=true;drawer.setAttribute('aria-hidden','true');
  toggle.addEventListener('click',()=>setDrawer(!opened));
  close.addEventListener('click',()=>setDrawer(false));
  const knowledgeNav=document.querySelector('[data-focus="query"]');
  knowledgeNav?.setAttribute('aria-controls',drawer.id);
  knowledgeNav?.addEventListener('click',()=>{
    setDrawer(true,{focus:false});
    requestAnimationFrame(()=>{if(opened)$('query').focus({preventScroll:true});});
  },{capture:true});
  document.addEventListener('pointerdown',event=>{
    if(opened&&!drawer.contains(event.target)&&!toggle.contains(event.target)&&!knowledgeNav?.contains(event.target))
      setDrawer(false,{restore:false});
  });
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&opened&&!document.querySelector('dialog[open]')){
      event.preventDefault();setDrawer(false);
    }
  });
  // Close an overlay when keyboard focus leaves it, instead of obscuring the
  // newly focused chat/navigation control. Native modal dialogs keep their rules.
  drawer.addEventListener('focusout',event=>{
    const next=event.relatedTarget;
    if(opened&&next&&!drawer.contains(next)&&next!==toggle&&!document.querySelector('dialog[open]'))
      setDrawer(false,{restore:false});
  });

  const composer=$('composer'),actions=composer.querySelector('.composer-actions');
  const primary=document.createElement('div');primary.className='composer-primary';
  primary.append($('message'),composer.querySelector('.send'));composer.prepend(primary);
  const group=(name,className)=>{
    const host=document.createElement('div');host.className=className;
    host.setAttribute('role','group');host.setAttribute('aria-label',name);return host;
  };
  const attach=group('Attachments','composer-attachments');attach.append($('attach'),$('file-upload'));
  const voice=group('Voice','composer-voice');
  voice.append($('mic'),$('spoken').closest('label'),$('mic-settings'));
  const visual=group('Visual awareness','composer-visual');visual.append($('screen-share'));
  const tools=document.createElement('details');tools.className='composer-tools';
  const summary=document.createElement('summary');summary.textContent='Tools';summary.title='Windows scratchpad and inspection';
  const extra=group('Additional tools','composer-tools-menu');
  tools.append(summary,extra);
  // Existing native-surface entry buttons have no IDs; preserve the actual
  // remaining nodes rather than replacing their click handlers with new calls.
  for(const node of [...actions.children])if(node!==$('stop'))extra.append(node);
  const interrupt=group('Interruption','composer-interrupt');interrupt.append($('stop'));
  actions.append(attach,voice,visual,tools,interrupt);
  const iconControl=(control,label,shape)=>{
    control.classList.add('compact-control');
    const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${shape}</svg>`;
    control.style.setProperty('--control-icon',`url("data:image/svg+xml,${encodeURIComponent(svg)}")`);
    control.setAttribute('aria-label',label);control.title=label;
  };
  iconControl($('mic-settings'),'Microphone settings','<path d="M4 7h16M4 17h16M8 4v6M16 14v6"/>');
  iconControl($('screen-share'),'Share screen','<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>');
  iconControl(summary,'Tools','<rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/>');
  iconControl($('stop'),'Stop speech, request and computer control','<rect x="6" y="6" width="12" height="12" rx="2" fill="white"/>');
  // Sharing owns its changing label. Mirror it without replacing its handler
  // or children, so the same icon announces Stop sharing while active.
  const shareLabel=new MutationObserver(()=>{
    const label=$('screen-share').textContent.trim();
    $('screen-share').setAttribute('aria-label',label);$('screen-share').title=label;
  });
  shareLabel.observe($('screen-share'),{childList:true,subtree:true,characterData:true});
  window.addEventListener('pagehide',()=>shareLabel.disconnect(),{once:true});
  const status=document.querySelector('.input-options');status.classList.add('composer-status');
  status.prepend($('screen-share-status'));status.append($('mic-hint'));
  for(const button of composer.querySelectorAll('button'))if(!button.title)
    button.title=button.getAttribute('aria-label')||button.textContent.trim();
  document.addEventListener('pointerdown',event=>{if(tools.open&&!tools.contains(event.target))tools.open=false;});
  tools.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();tools.open=false;summary.focus();}});
  tools.addEventListener('focusout',event=>{if(event.relatedTarget&&!tools.contains(event.relatedTarget))tools.open=false;});
  extra.addEventListener('click',event=>{if(event.target.closest('button'))tools.open=false;});

  const input=$('message');
  document.body.style.setProperty('--navigation-count',document.querySelectorAll('.nav-rail>button:not(#sidebar-toggle)').length);
  input.rows=1;
  function sizeInput(){input.style.height='auto';input.style.height=Math.min(input.scrollHeight,140)+'px';}
  input.addEventListener('input',sizeInput);
  // The app emits input after its existing asynchronous send clears the field.
  composer.addEventListener('submit',()=>{requestAnimationFrame(sizeInput);});
  input.addEventListener('blur',sizeInput);
  const resize=new ResizeObserver(sizeInput);resize.observe(primary);
  window.addEventListener('pagehide',()=>resize.disconnect(),{once:true});
  const telemetry=document.querySelector('.orb-telemetry');
  if(telemetry)document.querySelector('.reference-intelligence').append(telemetry);
  document.body.classList.add('chat-layout');sizeInput();
}
