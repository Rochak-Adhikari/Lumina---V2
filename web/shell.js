// Presentation shortcuts delegate to the existing controls and their permission policy.
const icons=['M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9','M4 4h16v12H9l-5 4V4','M9 3h6v6H9zM2 16h6v6H2zM16 16h6v6h-6zM12 9v4M5 16v-3h14v3','M15 15l6 6M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0','M4 6h16M4 12h16M4 18h16M8 3v6M16 9v6M10 15v6','M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2'];
document.querySelectorAll('.nav-rail button>span:first-child').forEach((host,index)=>{
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.5');
  const workspace=host.parentElement.dataset.open==='workspace-open';
  const key=host.parentElement.dataset.open||host.parentElement.dataset.focus;
  const paths={workspace:icons[0],message:icons[1],'workers-open':icons[2],query:icons[3],'controls-open':icons[4],'settings-open':icons[5],'automation-open':'M12 3a9 9 0 1 0 9 9M12 6v6l4 2M17 3h4v4'};
  const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',workspace?'M3 5h7l2 3h9v13H3z':paths[key]||icons[0]);svg.append(path);host.replaceChildren(svg);
});
// The existing search is semantic; describe what it actually searches.
document.querySelector('.search-heading h3').textContent='Search your knowledge';
document.getElementById('query').placeholder='Search concepts and source files';
document.querySelector('label[for="query"]').textContent='Search concepts and source files';
document.querySelector('#local-search button').textContent='Find concepts';
document.getElementById('graph').setAttribute('aria-label','Interactive semantic knowledge graph');
document.querySelectorAll('[data-open]').forEach(button=>button.addEventListener('click',()=>document.getElementById(button.dataset.open)?.click()));
document.querySelectorAll('[data-focus]').forEach(button=>button.addEventListener('click',()=>{
  const target=document.getElementById(button.dataset.focus);
  target?.focus({preventScroll:true});target?.scrollIntoView({block:'nearest'});
  document.querySelectorAll('.nav-rail [aria-current]').forEach(item=>item.removeAttribute('aria-current'));
  button.setAttribute('aria-current','page');
}));
document.querySelector('[data-config]').addEventListener('click',()=>{
  document.getElementById('settings-open').click();
  const details=document.getElementById('config-details').closest('details');
  details.open=true;details.scrollIntoView({block:'nearest'});
});
