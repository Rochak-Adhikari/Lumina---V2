// Gemini supplies provisional words; no local recognition or synthesis.
export class VoiceActivity {
  constructor(start,end,threshold=()=>.012){this.start=start;this.end=end;this.threshold=threshold;this.reset();}
  reset(){this.active=false;this.loud=0;this.quiet=0;this.duration=0;this.text='';this.finished=false;}
  setTranscript(text){this.text=text.trim().toLowerCase();if(/^(stop|hang up)[.!?]*$/.test(this.text))this.finish();}
  finish(){if(!this.finished){this.finished=true;this.end();}}
  feed(buffer){
    if(this.finished)return;
    const samples=new Int16Array(buffer);let sum=0;for(const sample of samples)sum+=(sample/32768)**2;
    const ms=samples.length/16,loud=Math.sqrt(sum/Math.max(1,samples.length))>this.threshold();
    this.duration+=ms;
    if(loud){this.loud+=ms;this.quiet=0;if(!this.active&&this.loud>=300){this.active=true;this.start();}}
    else this.quiet+=ms;
    const incomplete=/\b(and|but|so|because|which|to)[.!?,…]*$/.test(this.text);
    if(this.active&&this.quiet>=(incomplete?2000:1100))this.finish();
    if(this.duration>=60000||(!this.active&&this.duration>=10000))this.finish();
  }
}
