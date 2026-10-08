import {frame,reactor,gauge,circuits} from './reference-art.js';
// Apply the supplied artwork to existing live DOM nodes. No prototype runtime is mounted.
const $=id=>document.getElementById(id);
function art(host,markup){const template=document.createElement('template');template.innerHTML=markup;host.prepend(template.content);}
document.body.classList.add('reference-ui');
const presence=document.querySelector('.presence');
const intelligence=document.createElement('section');intelligence.className='reference-intelligence';intelligence.setAttribute('aria-label','Personal intelligence');
presence.prepend(intelligence);
for(const selector of ['.presence-heading','#orb','.orb-caption'])intelligence.append(document.querySelector(selector));
const conversation=document.createElement('section');conversation.className='reference-conversation';conversation.setAttribute('aria-label','Conversation console');presence.append(conversation);
for(const selector of ['.console-heading','#conversation','#live-transcript','#composer','.input-options'])conversation.append(document.querySelector(selector));
art(intelligence,frame(650,426)+circuits(650,426));art(conversation,frame(650,349));
const environment=document.querySelector('.environment');art(environment,frame(831,710));
const search=document.querySelector('.search-panel');art(search,frame(831,155));
const brand=document.querySelector('.wordmark');brand.querySelector('.logo').remove();art(brand,frame(355,95)+reactor());
art(document.querySelector('.nav-rail'),frame(150,783));
art(document.querySelector('.environment-tabs'),frame(831,53));
const provider=document.querySelector('.top-status');art(provider,frame(191,83));
// CPU and agents are inserted by the existing measured telemetry component.
function decorateMetrics(){document.querySelectorAll('.header-readout:not([data-framed])').forEach(node=>{node.dataset.framed='true';art(node,frame(188,83)+gauge('#ff2946'));});}
decorateMetrics();const observer=new MutationObserver(decorateMetrics);observer.observe(document.querySelector('.topbar'),{childList:true});
window.addEventListener('pagehide',()=>observer.disconnect(),{once:true});
const toggle=$('sidebar-toggle');
function setCollapsed(collapsed){document.body.classList.toggle('sidebar-collapsed',collapsed);toggle.setAttribute('aria-expanded',String(!collapsed));toggle.setAttribute('aria-label',collapsed?'Expand sidebar':'Collapse sidebar');toggle.title=collapsed?'Expand sidebar':'Collapse sidebar';toggle.textContent=collapsed?'»':'«';}
let saved=false;try{saved=localStorage.getItem('lumina.sidebarCollapsed')==='true';}catch{}
setCollapsed(saved);
toggle.addEventListener('click',()=>{const collapsed=!document.body.classList.contains('sidebar-collapsed');setCollapsed(collapsed);try{localStorage.setItem('lumina.sidebarCollapsed',String(collapsed));}catch{}});
document.querySelectorAll('.nav-rail [data-focus],.nav-rail [data-open]').forEach(button=>button.title=button.getAttribute('aria-label'));
