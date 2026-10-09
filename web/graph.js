import * as THREE from './vendor/three.module.js';
const palette=['#ff5d8e','#a783ff','#39efcf','#40cfff','#ee78ef','#ff925e','#72de85','#8296ff'];
export function branchColor(name){let n=0;for(const c of String(name))n=(n*31+c.charCodeAt(0))>>>0;return palette[n%palette.length];}
function identityHash(name){let hash=2166136261;for(const char of String(name)){hash^=char.charCodeAt(0);hash=Math.imul(hash,16777619);}return hash>>>0;}
export function nodeColor(node){const hash=identityHash(node.id);return node.hyperedge?'#ffd36c':'#'+new THREE.Color().setHSL((hash%360000)/360000,.85+((hash>>>9)%140)/1000,.42+((hash>>>17)%160)/1000).getHexString();}
function nodeMaterial(node,hash){
 // A faceted luminous junction, not a shaded sphere or separate planet.
 return new THREE.ShaderMaterial({transparent:true,depthWrite:false,side:THREE.DoubleSide,blending:THREE.AdditiveBlending,
  uniforms:{tint:{value:new THREE.Color(nodeColor(node))},fade:{value:1},emphasis:{value:0},phase:{value:(hash%6283)/1000}},
  vertexShader:'varying vec2 orbitUV; void main(){orbitUV=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',
  fragmentShader:`varying vec2 orbitUV;uniform vec3 tint;uniform float fade;uniform float emphasis;uniform float phase;
    void main(){
      vec2 q=orbitUV*2.0-1.0;float r=length(q);float angle=atan(q.y,q.x)+phase;
      float aa=max(fwidth(r),.008);
      float rim=exp(-pow((r-.39)/max(.012,aa),2.0));
      float spokes=exp(-pow(abs(sin(angle*3.0))*r/max(.009,aa*.7),2.0))*(1.0-smoothstep(.37,.4,r));
      float facet=cos(mod(angle+1.0472,2.0944)-1.0472)*r;
      float triangle=exp(-pow((facet-.18)/max(.009,aa*.7),2.0))*(1.0-smoothstep(.36,.4,r));
      float core=exp(-r*22.0),body=(1.0-smoothstep(.2,.41,r))*.19;
      float halo=exp(-r*r*7.0)*.3;
      float selected=emphasis*exp(-pow((r-.55)/max(.009,aa),2.0))*.75;
      float wire=clamp(rim*.85+spokes*.52+triangle*.4+core,0.0,1.0);
      float light=clamp(wire+body+halo+selected,0.0,1.0);
      if(light*fade<.005)discard;
      gl_FragColor=vec4(mix(tint,vec3(1.0),clamp(wire*.65,0.0,.85)),light*fade);
    }`});
}
function connectionMaterial(){
 // One batch for all real edges: screen-space glow ribbons stay legible when
 // zooming without adding another render pass or particles for every edge.
 return new THREE.ShaderMaterial({transparent:true,depthWrite:false,side:THREE.DoubleSide,blending:THREE.AdditiveBlending,
  uniforms:{viewport:{value:new THREE.Vector2(1,1)},time:{value:0}},
  vertexShader:`attribute vec3 target;attribute vec3 tint;attribute float strength;attribute float phase;
    uniform vec2 viewport;varying vec2 edgeUV;varying vec3 edgeTint;varying float edgeStrength;varying float edgePhase;
    void main(){
      vec4 a=projectionMatrix*modelViewMatrix*vec4(position,1.0);
      vec4 b=projectionMatrix*modelViewMatrix*vec4(target,1.0);
      vec2 delta=(b.xy/max(b.w,.001)-a.xy/max(a.w,.001))*viewport;
      vec2 normal=vec2(-delta.y,delta.x)/max(length(delta),.001);
      vec4 point=mix(a,b,uv.x);point.xy+=normal*(uv.y*2.0-1.0)*7.0/viewport*point.w;
      gl_Position=point;edgeUV=uv;edgeTint=tint;edgeStrength=(a.w>0.0&&b.w>0.0)?strength:0.0;edgePhase=phase;
    }`,
  fragmentShader:`uniform float time;varying vec2 edgeUV;varying vec3 edgeTint;varying float edgeStrength;varying float edgePhase;
    void main(){
      float crossLine=abs(edgeUV.y*2.0-1.0);
      float core=1.0-smoothstep(.055,.055+max(fwidth(crossLine),.05),crossLine);
      float glow=exp(-crossLine*crossLine*7.0)*.24;
      float travel=fract(edgeUV.x-time*.045+edgePhase);
      float pulse=exp(-pow((travel-.5)/.035,2.0))*.25;
      float alpha=(core*.8+glow)*(1.0+pulse)*edgeStrength;
      gl_FragColor=vec4(mix(edgeTint,vec3(1.0),core*.32),alpha);
    }`});
}
export class EnvironmentGraph{
 constructor(element,onSelect){this.element=element;this.nodes=[];this.meshes=new Map();this.main=new Set();this.fitted=false;this.searchQuestion='';
 this.reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');
 this.graph=ForceGraph3D()(element).backgroundColor('#05070c').showNavInfo(false).nodeThreeObject(n=>{
 const hash=identityHash(n.id);
 const material=nodeMaterial(n,hash);material.color=material.uniforms.tint.value;
 const mesh=new THREE.Mesh(new THREE.PlaneGeometry(n.radius*7.2,n.radius*7.2),material);
 this.meshes.set(n.id,mesh);this.search(this.searchQuestion);return mesh;})
 .nodeLabel(n=>{const el=document.createElement('span');el.textContent=n.label;return el;}).linkVisibility(false)
 .onNodeHover(n=>{this.hovered=n?.id;this.updateActive();})
 .onNodeClick(n=>{this.selected=n.id;this.updateActive();onSelect({...n,filename:n.label,path:n.source_file||'',type:'concept'});}).cooldownTicks(110)
 .onEngineTick(()=>{if(!this.fitted&&!this.initialFramed&&++this.layoutTicks>=25){this.fit();this.initialFramed=true;}})
 .onEngineStop(()=>{if(!this.fitted){this.fit();this.fitted=true;}element.dataset.settled='true';});
 const grid=new THREE.GridHelper(1000,50,0x422032,0x26303b);grid.position.y=-70;grid.material.transparent=true;grid.material.opacity=.35;this.graph.scene().add(grid);
 this.graph.d3Force('charge').strength(-45);element.dataset.renderer='webgl';new ResizeObserver(()=>{this.graph.width(element.clientWidth).height(element.clientHeight);}).observe(element);
 this.labelLayer=document.createElement('div');this.labelLayer.className='graph-hud-labels';this.labelLayer.setAttribute('aria-hidden','true');element.append(this.labelLayer);this.labels=[];
 let last=0;const renderLabels=now=>{if(!document.hidden&&now-last>50){last=now;this.positionLabels();this.positionConnections(now);for(const mesh of this.meshes.values())mesh.quaternion.copy(this.graph.camera().quaternion);}this.labelFrame=requestAnimationFrame(renderLabels);};this.labelFrame=requestAnimationFrame(renderLabels);
 window.addEventListener('pagehide',()=>{cancelAnimationFrame(this.labelFrame);this.disposeConnections();for(const mesh of this.meshes.values()){mesh.material.dispose();mesh.geometry.dispose();}},{once:true});
 }
 updateActive(){for(const [id,mesh] of this.meshes)mesh.material.uniforms.emphasis.value=id===this.hovered||id===this.selected?1:0;}
 disposeConnections(){if(this.connectionMesh){this.graph.scene().remove(this.connectionMesh);this.connectionMesh.geometry.dispose();this.connectionMesh.material.dispose();this.connectionMesh=null;}}
 createConnections(){
  this.disposeConnections();const vertices=this.links.length*6,geometry=new THREE.BufferGeometry();
  for(const name of ['position','target','tint'])geometry.setAttribute(name,new THREE.BufferAttribute(new Float32Array(vertices*3),3));
  for(const name of ['strength','phase'])geometry.setAttribute(name,new THREE.BufferAttribute(new Float32Array(vertices),1));
  geometry.setAttribute('uv',new THREE.BufferAttribute(new Float32Array(vertices*2),2));
  const uv=[0,0,1,0,1,1,0,0,1,1,0,1];
  this.links.forEach((edge,index)=>{const color=new THREE.Color(edge.hyperedge?'#ffd36c':branchColor(edge.relation));
   for(let v=0;v<6;v++){const i=index*6+v;geometry.attributes.tint.setXYZ(i,color.r,color.g,color.b);geometry.attributes.uv.setXY(i,uv[v*2],uv[v*2+1]);geometry.attributes.phase.setX(i,(index*.618)%1);}
  });
  this.connectionMesh=new THREE.Mesh(geometry,connectionMaterial());this.connectionMesh.frustumCulled=false;
  this.graph.scene().add(this.connectionMesh);this.positionConnections(0);
 }
 positionConnections(now){
  if(!this.connectionMesh)return;
  const {geometry,material}=this.connectionMesh,byId=new Map(this.nodes.map(node=>[node.id,node]));
  this.links.forEach((edge,index)=>{const source=typeof edge.source==='object'?edge.source:byId.get(edge.source),target=typeof edge.target==='object'?edge.target:byId.get(edge.target);
   const valid=[source?.x,source?.y,source?.z,target?.x,target?.y,target?.z].every(Number.isFinite);
   const hitSource=this.hits?.has(source?.id),hitTarget=this.hits?.has(target?.id);
   const strength=!valid ? 0 : !this.hasFilter ? .72 : hitSource&&hitTarget ? 1 : hitSource||hitTarget ? .55 : .18;
   for(let v=0;v<6;v++){const i=index*6+v;geometry.attributes.position.setXYZ(i,valid?source.x:0,valid?source.y:0,valid?source.z:0);geometry.attributes.target.setXYZ(i,valid?target.x:0,valid?target.y:0,valid?target.z:0);geometry.attributes.strength.setX(i,strength);}
  });
  for(const name of ['position','target','strength'])geometry.attributes[name].needsUpdate=true;
  material.uniforms.viewport.value.set(Math.max(1,this.element.clientWidth),Math.max(1,this.element.clientHeight));
  material.uniforms.time.value=this.reducedMotion.matches?0:now/1000;
 }
 update(data){
 const revision=data.revision||JSON.stringify(data),sameSource=this.source===data.source;
 if(sameSource&&this.revision===revision)return this.counts;
 const previous=new Map(this.nodes.map(n=>[n.id,n]));this.source=data.source;this.revision=revision;
 const nodes=data.nodes.map(n=>({...n,id:String(n.id),label:n.label||n.id,degree:0})),byId=new Map(nodes.map(n=>[n.id,n]));
 const links=(data.edges||data.links||[]).map(e=>({...e,source:String(e.source),target:String(e.target),relation:e.relation||e.type||'related_to'})).filter(e=>byId.has(e.source)&&byId.has(e.target));
 for(const h of data.hyperedges||[]){const members=[...new Set((h.members||h.nodes||[]).map(String))].filter(i=>byId.has(i));if(members.length<3)continue;const hub={id:'hyperedge:'+h.id,label:h.label||'Shared concept',hyperedge:true,degree:0};nodes.push(hub);byId.set(hub.id,hub);for(const member of members)links.push({source:hub.id,target:member,relation:'member_of',hyperedge:true});}
 for(const e of links){byId.get(e.source).degree++;byId.get(e.target).degree++;}
 nodes.sort((a,b)=>b.degree-a.degree||a.id.localeCompare(b.id));const keep=new Set(nodes.slice(0,420).map(n=>n.id));
 this.nodes=nodes.filter(n=>keep.has(n.id));this.links=links.filter(e=>keep.has(e.source)&&keep.has(e.target));
 for(const n of this.nodes){n.radius=3+Math.sqrt(n.degree)*.7;const old=previous.get(n.id);if(sameSource&&old)for(const key of ['x','y','z','vx','vy','vz'])if(Number.isFinite(old[key]))n[key]=old[key];}
 const adj=new Map(this.nodes.map(n=>[n.id,[]]));for(const e of this.links){adj.get(e.source).push(e.target);adj.get(e.target).push(e.source);}
 const seen=new Set();this.main=new Set();for(const n of this.nodes){if(seen.has(n.id))continue;const component=new Set(),queue=[n.id];while(queue.length){const i=queue.pop();if(seen.has(i))continue;seen.add(i);component.add(i);queue.push(...adj.get(i));}if(component.size>this.main.size)this.main=component;}
 for(const mesh of this.meshes.values()){mesh.material.dispose();mesh.geometry.dispose();}this.meshes.clear();if(!sameSource){this.fitted=false;this.initialFramed=false;this.layoutTicks=0;}this.graph.graphData({nodes:this.nodes,links:this.links});
 this.createConnections();this.updateActive();
 this.labelLayer.replaceChildren();this.labels=this.nodes.slice(0,4).map(node=>{const card=document.createElement('div'),leader=document.createElement('div');card.className='graph-hud-label';leader.className='graph-hud-leader';for(const el of [card,leader])el.style.setProperty('--node-color',nodeColor(node));const title=document.createElement('strong'),detail=document.createElement('small');title.textContent=node.label;detail.textContent=node.hyperedge?'Shared concept':`${node.degree} connections`;card.append(title,detail);this.labelLayer.append(leader,card);return {node,card,leader};});
 this.element.dataset.nodeCount=String(this.nodes.length);this.element.dataset.source=data.source||'notes';this.element.dataset.revision=revision;
 const inspector=document.getElementById('graph-inspect');if(inspector){const selected=inspector.value;inspector.replaceChildren(new Option('Inspect concept',''));for(const n of this.nodes)inspector.add(new Option(n.label,n.id));inspector.value=selected;}
 this.search(this.searchQuestion);
 this.counts={total:data.eligible_counts?.nodes||nodes.length,drawn:this.nodes.length,trimmed:(data.eligible_counts?.nodes||nodes.length)-this.nodes.length};return this.counts;
 }
 search(question){this.searchQuestion=String(question||'');this.hits=new Set();const stop=new Set(['the','a','an','is','of','in','to','and','how','what','does','my','about','with','for']);const tokens=(this.searchQuestion.toLowerCase().match(/[a-z0-9]+/g)||[]).filter(t=>!stop.has(t));let hits=0;
 for(const n of this.nodes){const words=new Set([n.label,n.aliases,n.source_file,n.source_files,n.source_location].flat().filter(Boolean).join(' ').toLowerCase().match(/[a-z0-9]+/g)||[]);const hit=tokens.some(t=>words.has(t));if(hit){hits++;this.hits.add(n.id);}const mesh=this.meshes.get(n.id);if(mesh){mesh.scale.setScalar(hit?3.2:1);mesh.material.opacity=tokens.length&&!hit?.30:1;mesh.material.uniforms.fade.value=mesh.material.opacity;}}
 this.hasFilter=tokens.length>0;
 return hits;
 }
 positionLabels(){
 const w=this.element.clientWidth,h=this.element.clientHeight,placed=[];
 for(const {node,card,leader} of this.labels){if(![node.x,node.y,node.z].every(Number.isFinite)||(h<360&&this.labels.findIndex(item=>item.node===node)>1)){card.hidden=leader.hidden=true;continue;}const p=this.graph.graph2ScreenCoords(node.x,node.y,node.z);card.hidden=leader.hidden=p.x<0||p.x>w||p.y<0||p.y>h;if(card.hidden)continue;
 // Dense memory clusters need their centre unobstructed. Dock the handful of
 // labels beside the network and use leaders to identify the actual junctions.
 const left=this.labels.findIndex(item=>item.node===node)%2===0;let x=left?12:Math.max(12,w-150),y=Math.max(10,Math.min(h-88,p.y-36));
 for(const prev of placed)if(Math.abs(x-prev.x)<148&&Math.abs(y-prev.y)<50)y=Math.min(h-88,prev.y+54);
 placed.push({x,y});card.style.transform=`translate(${x}px,${y}px)`;card.style.opacity=this.meshes.get(node.id)?.material.opacity??1;
 const dx=(left?x+138:x)-p.x,dy=y+24-p.y;leader.style.width=`${Math.hypot(dx,dy)}px`;leader.style.transform=`translate(${p.x}px,${p.y}px) rotate(${Math.atan2(dy,dx)}rad)`;leader.style.opacity=card.style.opacity;
 }
 }
 fit(){
 // Frame the same main component, excluding HUD labels from the scene bounds.
 // Decorative label cards must not push the actual graph away from the user.
 const nodes=this.nodes.filter(n=>this.main.has(n.id)&&[n.x,n.y,n.z].every(Number.isFinite));if(!nodes.length)return;
 const bounds=['x','y','z'].map(axis=>[Math.min(...nodes.map(n=>n[axis]-n.radius)),Math.max(...nodes.map(n=>n[axis]+n.radius))]);
 const center=Object.fromEntries(['x','y','z'].map((axis,i)=>[axis,(bounds[i][0]+bounds[i][1])/2]));
 const camera=this.graph.camera(),v=camera.fov*Math.PI/360,h=Math.atan(Math.tan(v)*camera.aspect);
 const distance=Math.max((bounds[0][1]-bounds[0][0])/2/Math.tan(h),(bounds[1][1]-bounds[1][0])/2/Math.tan(v))*1.15+(bounds[2][1]-bounds[2][0])/2;
 this.graph.cameraPosition({x:center.x,y:center.y,z:center.z+Math.max(70,distance)},center,600);
 }
}
