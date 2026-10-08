class PCMCapture extends AudioWorkletProcessor {
  constructor(){super();this.buffer=new Int16Array(1600);this.index=0;this.phase=0;this.sum=0;this.samples=0;
    this.port.onmessage=event=>{if(event.data==='reset'){this.index=0;this.phase=0;this.sum=0;this.samples=0;}
      if(event.data==='flush'){if(this.index){const tail=this.buffer.slice(0,this.index);this.port.postMessage(tail.buffer,[tail.buffer]);this.index=0;}this.port.postMessage('flushed');}};
  }
  process(inputs){
    const input=inputs[0]?.[0];if(!input)return true;
    for(const value of input){
      this.sum+=value;this.samples++;this.phase+=16000;
      if(this.phase>=sampleRate){
        this.phase-=sampleRate;const value=Math.max(-1,Math.min(1,this.sum/this.samples));
        this.buffer[this.index++]=value<0?value*32768:value*32767;this.sum=0;this.samples=0;
        if(this.index===this.buffer.length){this.port.postMessage(this.buffer.buffer,[this.buffer.buffer]);this.buffer=new Int16Array(1600);this.index=0;}
      }
    }
    return true;
  }
}
registerProcessor('lumina-pcm',PCMCapture);
