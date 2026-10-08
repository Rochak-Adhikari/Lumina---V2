// User-opened conversation: silence ends an utterance, not the call.
export class ConversationLease {
 constructor(close,now=()=>performance.now()){this.close=close;this.now=now;this.opened=now();this.lastSpeech=null;this.answerEnded=null;this.awaiting=false;this.closed=false;}
 speech(){this.lastSpeech=this.now();this.answerEnded=null;this.awaiting=true;}
 answered(startedAt){if(this.lastSpeech!==null&&startedAt>=this.lastSpeech){this.answerEnded=this.now();this.awaiting=false;}}
 tick(){/* Explicit Stop/device disconnect owns call lifetime. */}
}
