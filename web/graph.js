import * as THREE from './vendor/three.module.js';
const palette=['#f0718d','#9b8dc9','#79b5ad','#829bc3','#bda0b4','#bf797b'];
export function branchColor(name){let n=0;for(const c of String(name))n=(n*31+c.charCodeAt(0))>>>0;return palette[n%palette.length];}
export class EnvironmentGraph{
 constructor(element,onSelect){this.element=element;this.nodes=[];this.meshes=new Map();this.main=new Set();this.fitted=false;this.searchQuestion='';
 this.graph=ForceGraph3D()(element).backgroundColor('#08090b').showNavInfo(false).nodeThreeObject(n=>{
 const color=n.hyperedge?'#efc65b':branchColor(n.community);
 const mesh=new THREE.Mesh(new THREE.SphereGeometry(n.radius,12,8),new THREE.MeshBasicMaterial({color,transparent:true,opacity:1}));
 // Shared sphere geometry remains the picking target; child visuals do not change layout.
 const core=new THREE.Mesh(new THREE.SphereGeometry(n.radius*.45,8,6),new THREE.MeshBasicMaterial({color:'#ffffff',transparent:true,depthTest:false,opacity:.85}));core.userData.baseOpacity=.85;mesh.add(core);
 this.meshes.set(n.id,mesh);this.search(this.searchQuestion);return mesh;})
 .nodeLabel(n=>{const el=document.createElement('span');el.textContent=n.label;return el;}).linkColor(e=>e.hyperedge?'#efc65b':branchColor(e.relation)).linkOpacity(.45).linkWidth(.45)
 .onNodeClick(n=>onSelect({...n,filename:n.label,path:n.source_file||'',type:'concept'})).cooldownTicks(110)
 .onEngineStop(()=>{if(!this.fitted){this.fit();this.fitted=true;}element.dataset.settled='true';});
 const grid=new THREE.GridHelper(600,30,0x39121d,0x191a20);grid.position.y=-70;grid.material.transparent=true;grid.material.opacity=.22;this.graph.scene().add(grid);
 this.graph.d3Force('charge').strength(-45);element.dataset.renderer='webgl';new ResizeObserver(()=>{this.graph.width(element.clientWidth).height(element.clientHeight);}).observe(element);
 this.labelLayer=document.createElement('div');this.labelLayer.className='graph-hud-labels';this.labelLayer.setAttribute('aria-hidden','true');element.append(this.labelLayer);this.labels=[];
 let last=0;const renderLabels=now=>{if(now-last>80){last=now;this.positionLabels();}this.labelFrame=requestAnimationFrame(renderLabels);};this.labelFrame=requestAnimationFrame(renderLabels);
 window.addEventListener('pagehide',()=>cancelAnimationFrame(this.labelFrame),{once:true});
 }
 update(data){
 const nodes=data.nodes.map(n=>({...n,id:String(n.id),label:n.label||n.id,degree:0})),byId=new Map(nodes.map(n=>[n.id,n]));
 const links=(data.edges||data.links||[]).map(e=>({...e,source:String(e.source),target:String(e.target),relation:e.relation||e.type||'related_to'})).filter(e=>byId.has(e.source)&&byId.has(e.target));
 for(const h of data.hyperedges||[]){const members=[...new Set((h.members||h.nodes||[]).map(String))].filter(i=>byId.has(i));if(members.length<3)continue;const hub={id:'hyperedge:'+h.id,label:h.label||'Shared concept',hyperedge:true,degree:members.length};nodes.push(hub);byId.set(hub.id,hub);for(const member of members)links.push({source:hub.id,target:member,relation:'member_of',hyperedge:true});}
 for(const e of links){byId.get(e.source).degree++;byId.get(e.target).degree++;}
 nodes.sort((a,b)=>b.degree-a.degree||a.id.localeCompare(b.id));const keep=new Set(nodes.slice(0,420).map(n=>n.id));
 this.nodes=nodes.filter(n=>keep.has(n.id));this.links=links.filter(e=>keep.has(e.source)&&keep.has(e.target));
 for(const n of this.nodes)n.radius=1.6+Math.sqrt(n.degree)*.45;
 const adj=new Map(this.nodes.map(n=>[n.id,[]]));for(const e of this.links){adj.get(e.source).push(e.target);adj.get(e.target).push(e.source);}
 const seen=new Set();this.main=new Set();for(const n of this.nodes){if(seen.has(n.id))continue;const component=new Set(),queue=[n.id];while(queue.length){const i=queue.pop();if(seen.has(i))continue;seen.add(i);component.add(i);queue.push(...adj.get(i));}if(component.size>this.main.size)this.main=component;}
 this.meshes.clear();this.fitted=false;this.graph.graphData({nodes:this.nodes,links:this.links});
 this.labelLayer.replaceChildren();this.labels=this.nodes.slice(0,4).map(node=>{const card=document.createElement('div');card.className='graph-hud-label';card.style.setProperty('--node-color',node.hyperedge?'#efc65b':branchColor(node.community));const title=document.createElement('strong'),detail=document.createElement('small');title.textContent=node.label;detail.textContent=node.hyperedge?'Shared concept':`${node.degree} connections`;card.append(title,detail);this.labelLayer.append(card);return {node,card};});
 this.element.dataset.nodeCount=String(this.nodes.length);
 return {total:nodes.length,drawn:this.nodes.length,trimmed:nodes.length-this.nodes.length};
 }
 search(question){this.searchQuestion=String(question||'');const stop=new Set(['the','a','an','is','of','in','to','and','how','what','does','my','about','with','for']);const tokens=(this.searchQuestion.toLowerCase().match(/[a-z0-9]+/g)||[]).filter(t=>!stop.has(t));let hits=0;
 for(const n of this.nodes){const words=new Set([n.label,n.aliases,n.source_file,n.source_files,n.source_location].flat().filter(Boolean).join(' ').toLowerCase().match(/[a-z0-9]+/g)||[]);const hit=tokens.some(t=>words.has(t));if(hit)hits++;const mesh=this.meshes.get(n.id);if(mesh){mesh.scale.setScalar(hit?3.2:1);mesh.material.opacity=tokens.length&&!hit?.30:1;for(const child of mesh.children)child.material.opacity=mesh.material.opacity*(child.userData.baseOpacity||1);}}
 return hits;
 }
 positionLabels(){
 const w=this.element.clientWidth,h=this.element.clientHeight,placed=[];
 for(const {node,card} of this.labels){if(![node.x,node.y,node.z].every(Number.isFinite)){card.hidden=true;continue;}const p=this.graph.graph2ScreenCoords(node.x,node.y,node.z);card.hidden=p.x<0||p.x>w||p.y<0||p.y>h;if(card.hidden)continue;
 const index=this.labels.findIndex(item=>item.node===node),left=index%2===0;let x=Math.max(12,Math.min(w-164,p.x+(left?-166:22))),y=Math.max(12,Math.min(h-92,p.y+(index<2?-64:20)));
 for(const prev of placed)if(Math.abs(x-prev.x)<160&&Math.abs(y-prev.y)<52)y=Math.min(h-92,prev.y+56);
 placed.push({x,y});card.style.transform=`translate(${x}px,${y}px)`;card.style.opacity=this.meshes.get(node.id)?.material.opacity??1;
 }
 }
 fit(){
 // Frame the same main component, excluding HUD labels from the scene bounds.
 // Decorative label cards must not push the actual graph away from the user.
 const nodes=this.nodes.filter(n=>this.main.has(n.id)&&[n.x,n.y,n.z].every(Number.isFinite));if(!nodes.length)return;
 const bounds=['x','y','z'].map(axis=>[Math.min(...nodes.map(n=>n[axis]-n.radius)),Math.max(...nodes.map(n=>n[axis]+n.radius))]);
 const center=Object.fromEntries(['x','y','z'].map((axis,i)=>[axis,(bounds[i][0]+bounds[i][1])/2]));
 const camera=this.graph.camera(),v=camera.fov*Math.PI/360,h=Math.atan(Math.tan(v)*camera.aspect);
 const distance=Math.max((bounds[0][1]-bounds[0][0])/2/Math.tan(h),(bounds[1][1]-bounds[1][0])/2/Math.tan(v))*1.65+(bounds[2][1]-bounds[2][0])/2;
 this.graph.cameraPosition({x:center.x,y:center.y,z:center.z+Math.max(70,distance)},center,600);
 }
}
