import {selectMicrophone} from './devices.js';
export class BrowserAudio {
  constructor(send){this.send=send;this.sources=new Set();this.next=0;this.speechId=-1;this.turnDone=false;this.capturing=false;this.monitoring=false;this.generation=0;this.playbackTimer=null;}
  async initialize(){
    if(!this.context){this.context=new AudioContext({sampleRate:16000});await this.context.audioWorklet.addModule('/assets/pcm-worklet.js');}
    await this.context.resume();
    if(this.context.state!=='running')throw new Error('Audio playback is blocked by the browser.');
    const sink=localStorage.getItem('lumina.speaker');
    if(this.context.setSinkId)await this.context.setSinkId(!sink||sink==='default'?'':sink);
  }
  async prepareMicrophone(){
    if(this.media)return;
    const acquisition=this.captureGeneration||0;
    await this.initialize();
    const device=selectMicrophone(await navigator.mediaDevices.enumerateDevices(),localStorage.getItem('lumina.microphone'));
    this.media=await navigator.mediaDevices.getUserMedia({audio:{deviceId:{exact:device},channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
    if(acquisition!==(this.captureGeneration||0)){this.media.getTracks().forEach(t=>t.stop());this.media=null;return;}
    this.input=this.context.createMediaStreamSource(this.media);this.worklet=new AudioWorkletNode(this.context,'lumina-pcm');
    this.preRoll=[];
    this.worklet.port.onmessage=event=>{if(event.data==='flushed'){this.flushDone?.();return;}if(!this.media)return;const samples=new Int16Array(event.data);let sum=0;for(const sample of samples)sum+=(sample/32768)**2;this.onLevel?.(samples.length?Math.sqrt(sum/samples.length):0);if(this.capturing)this.send(event.data);else {this.preRoll.push(event.data);if(this.preRoll.length>30)this.preRoll.shift();}this.onPCM?.(event.data);};
    this.silence=this.context.createGain();this.silence.gain.value=0;
    this.input.connect(this.worklet).connect(this.silence).connect(this.context.destination);
  }
  startCapture(){if(this.monitoring){for(const chunk of this.preRoll||[])this.send(chunk);this.preRoll=[];}else this.worklet?.port.postMessage('reset');this.capturing=true;}
  async finishCapture(){if(this.worklet&&this.capturing){await new Promise(resolve=>{this.flushDone=resolve;this.worklet.port.postMessage('flush');setTimeout(resolve,200);});}this.capturing=false;if(!this.monitoring)this.stopCapture();}
  stopCapture(){this.captureGeneration=(this.captureGeneration||0)+1;this.capturing=false;this.media?.getTracks().forEach(t=>t.stop());this.input?.disconnect();this.worklet?.disconnect();this.silence?.disconnect();this.media=null;this.onLevel?.(null);}
  interrupt(){this.generation++;clearTimeout(this.playbackTimer);for(const source of this.sources){source.onended=null;try{source.stop();}catch{}}this.sources.clear();this.next=0;this.turnDone=false;this.speechId=-1;}
  async play(event){
    if(!this.context||this.context.state!=='running')throw new Error('Click Speak or Send to enable audio.');
    clearTimeout(this.playbackTimer);
    if(this.speechId!==event.speech_id){this.interrupt();this.speechId=event.speech_id;}
    this.turnDone=false;
    const bytes=Uint8Array.from(atob(event.data),c=>c.charCodeAt(0));const pcm=new DataView(bytes.buffer);
    const buffer=this.context.createBuffer(1,bytes.length/2,event.sample_rate);const data=buffer.getChannelData(0);
    for(let i=0;i<data.length;i++)data[i]=pcm.getInt16(i*2,true)/32768;
    const source=this.context.createBufferSource();source.buffer=buffer;source.connect(this.context.destination);
    this.next=Math.max(this.context.currentTime+.025,this.next);
    if(this.next-this.context.currentTime>30)throw new Error('Audio output fell behind. The session was stopped.');
    const generation=this.generation;source.onended=()=>{this.sources.delete(source);if(generation===this.generation)this.maybeDone();};
    const wasEmpty=this.sources.size===0;this.sources.add(source);source.start(this.next);this.next+=buffer.duration;
    if(wasEmpty){this.onPlaybackStart?.();this.send({type:'playback_start',speech_id:this.speechId});}
  }
  complete(id){if(id===this.speechId){this.turnDone=true;this.maybeDone();}}
  maybeDone(){if(this.turnDone&&this.sources.size===0){const id=this.speechId;this.playbackTimer=setTimeout(()=>{this.onPlaybackEnd?.();this.send({type:'playback_end',speech_id:id});},300);}}
}
