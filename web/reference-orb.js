function sphereMesh(){const t=(1+Math.sqrt(5))/2;let vs=[[-1,t,0],[1,t,0],[-1,-t,0],[1,-t,0],[0,-1,t],[0,1,t],[0,-1,-t],[0,1,-t],[t,0,-1],[t,0,1],[-t,0,-1],[-t,0,1]].map(norm);let faces=[[0,11,5],[0,5,1],[0,1,7],[0,7,10],[0,10,11],[1,5,9],[5,11,4],[11,10,2],[10,7,6],[7,1,8],[3,9,4],[3,4,2],[3,2,6],[3,6,8],[3,8,9],[4,9,5],[2,4,11],[6,2,10],[8,6,7],[9,8,1]];for(let level=0;level<2;level++){const cache=new Map();const mid=(a,b)=>{let k=[a,b].sort((x,y)=>x-y).join(',');if(cache.has(k))return cache.get(k);let p=norm(vs[a].map((v,i)=>(v+vs[b][i])/2)),n=vs.push(p)-1;cache.set(k,n);return n;};faces=faces.flatMap(([a,b,c])=>{let ab=mid(a,b),bc=mid(b,c),ca=mid(c,a);return [[a,ab,ca],[b,bc,ab],[c,ca,bc],[ab,bc,ca]];});}vs=vs.map((v,i)=>norm(v.map((x,j)=>x+Math.sin(i*17.31+j*9.7)*.065)));const es=new Map();faces.forEach(f=>f.forEach((a,i)=>{let b=f[(i+1)%3];es.set([a,b].sort((x,y)=>x-y).join(','),[a,b]);}));return {vs,edges:[...es.values()]};}
function norm(v){let l=Math.hypot(...v);return v.map(x=>x/l);}
function animateOrb(canvas){const ctx=canvas.getContext('2d');if(!ctx)return()=>{};const {vs,edges}=sphereMesh();let raf=0,last=0,phase=0,energy=0,disposed=false;const paused=()=>canvas.parentElement.dataset.orbMotion==='off';
 const draw=(now)=>{if(disposed)return;if(now-last<20&&!paused()){raf=requestAnimationFrame(draw);return;}
 const dt=last?Math.min(.1,(now-last)/1000):0;last=now;
 const speaking=canvas.parentElement.dataset.orbState==='SPEAKING';
 energy=paused()?(speaking?1:0):energy+((speaking?1:0)-energy)*(1-Math.exp(-12*dt));
 if(!paused())phase+=dt*(.65+energy*.30);
 const time=paused()?0:phase,pulse=paused()?0:energy*(.5+.5*Math.sin(now*.008));
 ctx.setTransform(2,0,0,2,330,330);ctx.clearRect(-165,-165,330,330);
 const swell=1+pulse*.025;ctx.scale(swell,swell);
 const line=(x1,y1,x2,y2,c,w=.6)=>{ctx.strokeStyle=c;ctx.lineWidth=w;ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();};const circle=(r,c,w=1,start=0,end=Math.PI*2)=>{ctx.strokeStyle=c;ctx.lineWidth=w;ctx.beginPath();ctx.arc(0,0,r,start,end);ctx.stroke();};
 let bg=ctx.createRadialGradient(0,0,40,0,0,158);bg.addColorStop(0,'#61000b33');bg.addColorStop(.6,'#ee001b16');bg.addColorStop(1,'#00000000');ctx.fillStyle=bg;ctx.fillRect(-165,-165,330,330);
 for(let j=0;j<3;j++){let r=141+j*5;circle(r,`rgba(255,20,45,${j===0?.24:.10})`,.5);for(let k=0;k<6;k++){let a=k*Math.PI/3+time*(j%2?1:-1)+j;circle(r,'rgba(255,29,57,.35)',.8,a,a+.12);}}
 for(let i=0;i<120;i++){let a=i*Math.PI/60+time*.6,r=i%5===0?144:147;line(Math.cos(a)*r,Math.sin(a)*r,Math.cos(a)*151,Math.sin(a)*151,i%5===0?'#ef244b':'#771123',i%5===0?1:.5);}
 ctx.save();ctx.rotate(-time*.5);for(let i=0;i<8;i++){let a=i*Math.PI/4;ctx.save();ctx.rotate(a);ctx.fillStyle='#e31b3a';ctx.fillRect(132,-2,9,3);ctx.font='4px monospace';ctx.fillText('0'+i+' / LUMINA',118,8);ctx.restore();}ctx.restore();
 // Circular paths in three differently tilted planes, projected through a camera.
 const orbitPoint=(a,plane=0)=>{const radius=plane===2?130:124,x=radius*Math.cos(a),y=radius*Math.sin(a),inclination=[1.06,.92,1.22][plane]+Math.sin(time*.7+plane)*.18,tilt=[-.48,.95,2.1][plane]+time*[.85,-.65,.5][plane];
 const yy=y*Math.cos(inclination),z=y*Math.sin(inclination),scale=600/(600-z);
 return [(x*Math.cos(tilt)-yy*Math.sin(tilt))*scale,(x*Math.sin(tilt)+yy*Math.cos(tilt))*scale,z,scale];};
 const orbit=(front)=>{for(let j=0;j<3;j++){ctx.beginPath();let pen=false;for(let i=0;i<=180;i++){const p=orbitPoint(i/180*Math.PI*2,j);if((p[2]>=0)===front){if(!pen)ctx.moveTo(p[0],p[1]);else ctx.lineTo(p[0],p[1]);pen=true;}else pen=false;}
 ctx.strokeStyle=front?['#ff9aaf','#ff456c','#bd2449'][j]:'#64112b';ctx.lineWidth=front?(j===0?1.3:.8)+energy*.55:.6;ctx.shadowColor='#ff174b';ctx.shadowBlur=front?5+energy*6:0;ctx.stroke();ctx.shadowBlur=0;
 const angle=time*[2.5,-1.8,1.4][j]+j*2.1,p=orbitPoint(angle,j);
 if((p[2]>=0)===front){for(let k=1;k<=12;k++){const trail=orbitPoint(angle-k*.035*(j===1?-1:1),j);if((trail[2]>=0)!==front)continue;ctx.fillStyle=`rgba(255,65,105,${(1-k/13)*.45})`;ctx.beginPath();ctx.arc(trail[0],trail[1],1.3*trail[3],0,Math.PI*2);ctx.fill();}
 ctx.shadowColor='#ff3868';ctx.shadowBlur=front?12:2;ctx.fillStyle=front?'#fff4f8':'#9c2445';ctx.beginPath();ctx.arc(p[0],p[1],(front?2.7:1.7)*p[3],0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;}
 }};
 orbit(false);
 let fill=ctx.createRadialGradient(-32,-38,3,0,0,100);fill.addColorStop(0,'#ff617e');fill.addColorStop(.12,'#b92247');fill.addColorStop(.38,'#600e27');fill.addColorStop(.72,'#210813');fill.addColorStop(.93,'#09060c');fill.addColorStop(1,'#921136');ctx.fillStyle=fill;ctx.beginPath();ctx.arc(0,0,97,0,Math.PI*2);ctx.fill();
 let points=vs.map(([x,y,z])=>{let a=time*1.4+.3;let xx=x*Math.cos(a)+z*Math.sin(a),zz=-x*Math.sin(a)+z*Math.cos(a);let b=.3+Math.sin(time*.45)*.2;return [xx*96,(y*Math.cos(b)-zz*Math.sin(b))*96,y*Math.sin(b)+zz*Math.cos(b)];});
 ctx.shadowColor='#ff1035';ctx.shadowBlur=1;edges.slice().sort((a,b)=>(points[a[0]][2]+points[a[1]][2])-(points[b[0]][2]+points[b[1]][2])).forEach(([a,b])=>{let p=points[a],q=points[b],z=(p[2]+q[2])/2;line(p[0],p[1],q[0],q[1],`rgba(255,${35+Math.round((z+1)*35)},${60+Math.round((z+1)*28)},${z<0?.045:.18+z*.65})`,z>0?.8:.35);});
 ctx.shadowBlur=0;points.forEach((p,i)=>{if(p[2]>.05){ctx.fillStyle=i%9===0?'#fff3ee':'#ff5c70';ctx.beginPath();ctx.arc(p[0],p[1],i%9===0?1.4:.7,0,Math.PI*2);ctx.fill();}});
 ctx.shadowColor='#ff002a';ctx.shadowBlur=10+energy*10;circle(97,'#c91b49',1.2);circle(96,'#ff94ac',1,-2.8,-.7);ctx.shadowBlur=0;orbit(true);
 // Speech-state decoration, not a fabricated audio waveform or microphone level.
 if(energy>.01){for(let i=0;i<48;i++){const a=i*Math.PI/24,r=104,extension=paused()?3:3+(Math.sin(now*.007+i*.8)+1)*3*energy;
 line(Math.cos(a)*r,Math.sin(a)*r,Math.cos(a)*(r+extension),Math.sin(a)*(r+extension),`rgba(255,150,179,${energy*.65})`,1);}}
 if(!paused())raf=requestAnimationFrame(draw);
 };raf=requestAnimationFrame(draw);const change=()=>{cancelAnimationFrame(raf);raf=requestAnimationFrame(draw);};const stop=()=>{disposed=true;cancelAnimationFrame(raf);};stop.repaint=()=>{if(!disposed)change();};return stop;}


// Existing runtime contract: constructor(container), setState(state).
// Only the supplied visual renderer is used, never its microphone or sample-data code.
export class ReferenceOrb {
 constructor(container){
  this.container=container;this.canvas=document.createElement('canvas');
  this.canvas.width=660;this.canvas.height=660;this.canvas.className='reference-orb-canvas';
  // Explicit local motion preference: this animation can run even when the
  // browser disables ambient motion. The user can pause just this component.
  let enabled=true;try{enabled=localStorage.getItem('lumina.orbMotion')!=='off';}catch{}
  container.dataset.orbMotion=enabled?'on':'off';
  this.motionButton=document.createElement('button');this.motionButton.type='button';this.motionButton.className='orb-motion-toggle';
  const update=()=>{this.motionButton.textContent=enabled?'Pause orb':'Animate orb';this.motionButton.setAttribute('aria-label',enabled?'Pause orb animation':'Start orb animation');this.motionButton.setAttribute('aria-pressed',String(enabled));};
  this.motionButton.addEventListener('click',()=>{enabled=!enabled;container.dataset.orbMotion=enabled?'on':'off';try{localStorage.setItem('lumina.orbMotion',enabled?'on':'off');}catch{}update();this.stop?.repaint?.();});
  update();container.append(this.canvas,this.motionButton);this.stop=animateOrb(this.canvas);this.setState('IDLE');
  window.addEventListener('pagehide',()=>this.stop(),{once:true});
 }
 setState(state){this.container.dataset.orbState=state;this.stop?.repaint?.();}
}
