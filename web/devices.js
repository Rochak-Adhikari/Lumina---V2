export function selectMicrophone(devices,saved){
 const inputs=devices.filter(d=>d.kind==='audioinput'&&d.deviceId&&!['default','communications'].includes(d.deviceId));
 if(saved&&!['default','communications'].includes(saved)){if(inputs.some(d=>d.deviceId===saved))return saved;throw Error('The selected microphone is unavailable. Choose another device in Settings.');}
 const internal=inputs.filter(d=>!/bluetooth|airpods|headset|hands.free/i.test(d.label)&&/internal|built.in|microphone array/i.test(d.label));
 if(internal.length===1)return internal[0].deviceId;
 throw Error('Select an explicit microphone in Settings; no unique built-in microphone was identified.');
}
const $=id=>document.getElementById(id);
export function microphoneError(error){
  return ({NotSupportedError:'This browser runtime does not support microphone capture. Use a full current browser or the desktop WebView; this is not evidence of Windows denying permission.',NotAllowedError:'Microphone access was not granted. Press Enable device access and approve the LUMINA microphone prompt. If no prompt appears, check Allow microphone requests in the LUMINA menu and Windows privacy settings.',NotFoundError:'No microphone was found. Connect one and refresh the device list.',OverconstrainedError:'The selected microphone is unavailable. Open Microphone settings and choose another device.',NotReadableError:'The microphone could not be opened. Check Windows microphone access and whether another app is using it.'})[error.name]||error.message;
}
export function setupDevices(notice, endTurn){
  let stream,context,frame,generation=0,testing=false,discovering=false,discoveryGeneration=0;
  const grantedOutputs=new Map();
  function stopTest(){
    generation++;testing=false;cancelAnimationFrame(frame);stream?.getTracks().forEach(t=>t.stop());stream=null;
    context?.close();context=null;$('mic-level').value=0;$('mic-test').textContent='Test microphone';
    $('mic-test-status').textContent='Test stopped. Microphone released.';
  }
  async function listDevices(){
    if(!navigator.mediaDevices?.enumerateDevices)throw Error('Audio devices require localhost or HTTPS in this browser.');
    const devices=await navigator.mediaDevices.enumerateDevices();
    for(const [id,kind] of [['microphone','audioinput'],['speaker','audiooutput']]){
      const selected=localStorage.getItem('lumina.'+id)||'default';
      $(id).replaceChildren(new Option(id==='microphone'?'Auto-select built-in microphone':'Windows default output','default'));
      for(const [i,device] of devices.filter(d=>d.kind===kind&&d.deviceId&&d.deviceId!=='default').entries())$(id).add(new Option(device.label||`${id} ${i+1} (allow access for names)`,device.deviceId));
      if(id==='speaker')for(const [key,label] of grantedOutputs)if(![...$(id).options].some(o=>o.value===key))$(id).add(new Option(label,key));
      if(![...$(id).options].some(o=>o.value===selected))$(id).add(new Option('Saved device unavailable — choose another',selected));
      $(id).value=selected;
    }
    const labelled=devices.some(d=>d.kind==='audioinput'&&d.label);
    const inputCount=devices.filter(d=>d.kind==='audioinput'&&d.deviceId&&!['default','communications'].includes(d.deviceId)).length;
    const outputCount=devices.filter(d=>d.kind==='audiooutput'&&d.deviceId&&!['default','communications'].includes(d.deviceId)).length;
    $('device-status').textContent=labelled?`${inputCount} microphone(s) and ${outputCount} output(s) exposed by this browser. Choose and test below.`:'Your browser is hiding device names. Enable device access to reveal them.';
    const outputSupported=typeof AudioContext!=='undefined'&&typeof AudioContext.prototype.setSinkId==='function';
    $('speaker').disabled=!outputSupported;
    $('speaker-status').textContent=outputSupported?(outputCount?'Choose where LUMINA plays audio.':'The browser has not exposed individual outputs. Use Choose audio output if available, or allow device access; Windows default remains available.'):'This browser cannot select an output device. LUMINA uses Windows default output.';
    $('speaker-choose').hidden=!outputSupported||!navigator.mediaDevices.selectAudioOutput;
    return labelled;
  }
  async function open(){endTurn();$('settings').showModal();try{
    if(!await listDevices())await discover();
  }catch(e){$('device-status').textContent=microphoneError(e);}}
  $('settings-open').onclick=open;$('mic-settings').onclick=open;
  $('settings-close').onclick=()=>$('settings').close();
  $('settings').addEventListener('close',()=>{discoveryGeneration++;stopTest();});
  async function discover(){
    if(discovering)return;
    discovering=true;const token=discoveryGeneration;$('devices').disabled=true;let permissionStream;
    try{
      if(!navigator.mediaDevices?.getUserMedia)throw Error('Use localhost or HTTPS to enable audio devices.');
      // Explicit permission gesture. This brief probe may open the Windows default
      // microphone; the UI tells the user before they choose it. Never send audio.
      $('device-status').textContent='Allow microphone access in the browser prompt to discover your audio devices. No audio is sent.';
      const devices=await navigator.mediaDevices.enumerateDevices();
      let device;try{device=selectMicrophone(devices,localStorage.getItem('lumina.microphone'));}catch{}
      permissionStream=await navigator.mediaDevices.getUserMedia({audio:device?{deviceId:{exact:device}}:true,video:false});
      if(token===discoveryGeneration&&$('settings').open){
        await listDevices();
        // Retain an explicit selected endpoint, never an opaque "default" alias.
        const available=await navigator.mediaDevices.enumerateDevices();
        try{const chosen=selectMicrophone(available,localStorage.getItem('lumina.microphone'));localStorage.setItem('lumina.microphone',chosen);$('microphone').value=chosen;}catch{}
      }
    }catch(e){$('device-status').textContent=microphoneError(e);}
    finally{permissionStream?.getTracks().forEach(track=>track.stop());$('devices').disabled=false;discovering=false;}
  }
  $('devices').onclick=discover;
  $('speaker-choose').onclick=async()=>{try{
    const device=await navigator.mediaDevices.selectAudioOutput();
    grantedOutputs.set(device.deviceId,device.label||'Authorized audio output');
    localStorage.setItem('lumina.speaker',device.deviceId);await listDevices();
  }catch(e){$('speaker-status').textContent=e.message||'Output selection was cancelled.';}};
  $('speaker-test').onclick=async()=>{
    let output;
    try{stopTest();output=new AudioContext();await output.resume();
      const sink=$('speaker').value;
      if(output.setSinkId)await output.setSinkId(sink==='default'?'':sink);
      else if(sink!=='default')throw Error('Output selection is unavailable in this browser.');
      const tone=output.createOscillator(),gain=output.createGain();gain.gain.value=.06;
      tone.frequency.value=440;tone.connect(gain).connect(output.destination);
      tone.start();tone.stop(output.currentTime+.35);
      await new Promise(resolve=>{tone.onended=resolve;});
      $('speaker-status').textContent='Test tone played through the selected output.';
    }catch(e){$('speaker-status').textContent=e.message||'Speaker test failed.';}
    finally{await output?.close();}
  };
  for(const id of ['microphone','speaker'])$(id).onchange=()=>{
    stopTest();localStorage.setItem('lumina.'+id,$(id).value);
    notice(id==='speaker'&&!AudioContext.prototype.setSinkId?'This browser uses the Windows default output device.':'Device saved for the next speaking turn.');
  };
  $('mic-test').onclick=async()=>{
    if(testing){stopTest();return;}
    testing=true;const token=++generation;$('mic-test').textContent='Stop test';$('mic-test-status').textContent='Opening microphone…';
    try{
      const device=selectMicrophone(await navigator.mediaDevices.enumerateDevices(),$('microphone').value);
      const media=await navigator.mediaDevices.getUserMedia({audio:{deviceId:{exact:device},channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
      if(token!==generation){media.getTracks().forEach(t=>t.stop());return;}
      stream=media;context=new AudioContext();await context.resume();
      if(token!==generation)return;
      const analyser=context.createAnalyser();analyser.fftSize=1024;context.createMediaStreamSource(stream).connect(analyser);
      const samples=new Float32Array(analyser.fftSize);
      $('mic-test-status').textContent=`Testing: ${stream.getAudioTracks()[0].label||'selected microphone'}. Speak and watch the level. Audio stays on this device.`;
      function update(){analyser.getFloatTimeDomainData(samples);const rms=Math.sqrt(samples.reduce((sum,x)=>sum+x*x,0)/samples.length);$('mic-level').value=Math.min(100,rms*500);frame=requestAnimationFrame(update);}
      update();await listDevices();
    }catch(e){if(token===generation){stopTest();$('mic-test-status').textContent=microphoneError(e);}}
  };
  navigator.mediaDevices?.addEventListener('devicechange',()=>{if($('settings').open)listDevices().catch(()=>{});});
  window.addEventListener('lumina-microphone-policy',event=>{if(!event.detail?.enabled){discoveryGeneration++;stopTest();$('device-status').textContent='Microphone requests are disabled in the LUMINA menu.';}});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stopTest();});
  window.addEventListener('pagehide',stopTest);
}
