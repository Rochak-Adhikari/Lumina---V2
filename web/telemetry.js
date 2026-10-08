// Values represent observed samples only. No oscillator, random or state-derived load.
export function setupTelemetry(audio){
  const host=document.getElementById('orb');
  const panels=document.createElement('div');panels.className='orb-telemetry';
  function panel(label,max){
    const node=document.createElement('div');node.className='orb-readout';node.hidden=true;
    const title=document.createElement('span');title.textContent=label;
    const value=document.createElement('output');
    const meter=max?document.createElement('meter'):null;
    if(meter){meter.min=0;meter.max=max;meter.setAttribute('aria-label',label);}
    node.append(title,value);if(meter)node.append(meter);panels.append(node);
    const header=max===100&&label.includes('microphone')?null:node.cloneNode(true);
    if(header){header.className='header-readout';document.querySelector('.top-status').after(header);}
    return {node,hide(){node.hidden=true;if(header)header.hidden=true;},set(number,text){node.hidden=false;value.textContent=text;if(meter)meter.value=number;if(header){header.hidden=false;header.querySelector('output').textContent=text;}}};
  }
  const cpu=panel('Machine CPU',100),agents=panel('Running agents'),mic=panel('Live microphone RMS',100);
  host.append(panels);
  let stopped=false,micAt=0,timer;
  audio.onLevel=level=>{micAt=performance.now();if(level===null){mic.node.hidden=true;return;}mic.set(level*100,`${(level*100).toFixed(1)}%`);};
  async function update(){
    try{
      const response=await fetch('/api/telemetry',{cache:'no-store',signal:AbortSignal.timeout(2500)});
      if(!response.ok)throw Error();const data=await response.json();
      if(stopped)return;
      if(Number.isFinite(data.cpu_percent))cpu.set(data.cpu_percent,`${data.cpu_percent.toFixed(1)}%`);else cpu.hide();
      if(Number.isInteger(data.running_agents)&&data.running_agents>=0)agents.set(data.running_agents,String(data.running_agents));else agents.hide();
    }catch{cpu.hide();agents.hide();}
    if(!stopped)timer=setTimeout(update,1000);
  }
  const stale=setInterval(()=>{if(performance.now()-micAt>500)mic.node.hidden=true;},250);
  window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(timer);clearInterval(stale);cpu.hide();agents.hide();mic.hide();},{once:true});
  update();
}
