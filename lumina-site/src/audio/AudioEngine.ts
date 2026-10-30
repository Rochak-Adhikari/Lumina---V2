/**
 * Procedural sound for Lumina. No audio files: a slow drone pad whose harmony follows
 * the chapter, plus Karplus–Strong plucked strings for the loom. Created only after an
 * explicit user gesture; suspended when muted or when the tab is hidden.
 */

type CueKind = 'chapter' | 'approve' | 'success' | 'fail' | 'tick' | 'forget' | 'focus';

const NOTE = (midi: number) => 440 * Math.pow(2, (midi - 69) / 12);

// Chapter harmonies (MIDI notes), all rooted around D.
const CHORDS: number[][] = [
  [38, 45, 52, 54], // arrival: D A E F#
  [38, 45, 54, 59], // intent: D A F# B
  [35, 42, 50, 57], // memory: B F# D A
  [31, 38, 45, 47], // action: G D A B
  [38, 45, 52, 57], // capabilities: D A E A
  [38, 45, 50, 57], // demo: quiet D A D A
  [38, 45, 54, 61], // explore: D A F# C#
];

// Harp strings for the fifteen capability threads: D major pentatonic, ascending.
const HARP = [62, 64, 66, 69, 71, 74, 76, 78, 81, 83, 86, 88, 90, 93, 95];

interface Voice {
  oscA: OscillatorNode;
  oscB: OscillatorNode;
  gain: GainNode;
}

export class AudioEngine {
  private ctx: AudioContext;
  private master: GainNode;
  private pad: GainNode;
  private padFilter: BiquadFilterNode;
  private air: GainNode;
  private voices: Voice[] = [];
  private lfo: OscillatorNode;
  private noiseSrc: AudioBufferSourceNode;
  private harp = new Map<number, AudioBuffer>();
  private active: { src: AudioBufferSourceNode; gain: GainNode }[] = [];
  private lastPluck = 0;
  private lastCue: Record<string, number> = {};
  private chapter = -1;
  private volume = 0.6;
  private enabled = false;
  private onVisibility = () => {
    if (document.hidden) void this.ctx.suspend();
    else if (this.enabled) void this.ctx.resume();
  };

  constructor() {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.ctx = new Ctx({ latencyHint: 'interactive' });
    const ctx = this.ctx;

    this.master = ctx.createGain();
    this.master.gain.value = 0;
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -18;
    comp.ratio.value = 3;
    this.master.connect(comp).connect(ctx.destination);

    // Pad
    this.padFilter = ctx.createBiquadFilter();
    this.padFilter.type = 'lowpass';
    this.padFilter.frequency.value = 820;
    this.padFilter.Q.value = 0.6;
    this.pad = ctx.createGain();
    this.pad.gain.value = 0.16;
    this.padFilter.connect(this.pad).connect(this.master);

    this.lfo = ctx.createOscillator();
    this.lfo.frequency.value = 0.045;
    const lfoGain = ctx.createGain();
    lfoGain.gain.value = 260;
    this.lfo.connect(lfoGain).connect(this.padFilter.frequency);
    this.lfo.start();

    for (let i = 0; i < 4; i++) {
      const oscA = ctx.createOscillator();
      const oscB = ctx.createOscillator();
      oscA.type = 'sine';
      oscB.type = 'triangle';
      oscB.detune.value = 6 + i * 2;
      const gain = ctx.createGain();
      gain.gain.value = i === 0 ? 0.32 : 0.2 - i * 0.025;
      oscA.connect(gain);
      oscB.connect(gain);
      gain.connect(this.padFilter);
      oscA.start();
      oscB.start();
      this.voices.push({ oscA, oscB, gain });
    }

    // Air: band-passed noise, very quiet, breathing slowly.
    const len = ctx.sampleRate * 3;
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    let b0 = 0;
    for (let i = 0; i < len; i++) {
      const w = Math.random() * 2 - 1;
      b0 = 0.97 * b0 + 0.03 * w;
      d[i] = b0 * 3;
    }
    this.noiseSrc = ctx.createBufferSource();
    this.noiseSrc.buffer = buf;
    this.noiseSrc.loop = true;
    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.frequency.value = 1400;
    bp.Q.value = 0.7;
    this.air = ctx.createGain();
    this.air.gain.value = 0.035;
    this.noiseSrc.connect(bp).connect(this.air).connect(this.master);
    this.noiseSrc.start();

    this.setChapter(0, true);
    document.addEventListener('visibilitychange', this.onVisibility);
  }

  async enable(volume: number): Promise<void> {
    this.volume = volume;
    this.enabled = true;
    await this.ctx.resume();
    const now = this.ctx.currentTime;
    this.master.gain.cancelScheduledValues(now);
    this.master.gain.setValueAtTime(this.master.gain.value, now);
    this.master.gain.linearRampToValueAtTime(this.level(), now + 1.6);
  }

  disable(): void {
    this.enabled = false;
    const now = this.ctx.currentTime;
    this.master.gain.cancelScheduledValues(now);
    this.master.gain.setValueAtTime(this.master.gain.value, now);
    this.master.gain.linearRampToValueAtTime(0, now + 0.4);
    window.setTimeout(() => {
      if (!this.enabled) void this.ctx.suspend();
    }, 500);
  }

  setVolume(v: number): void {
    this.volume = v;
    if (!this.enabled) return;
    this.master.gain.setTargetAtTime(this.level(), this.ctx.currentTime, 0.08);
  }

  private level(): number {
    return Math.pow(this.volume, 2) * 0.9;
  }

  setChapter(i: number, immediate = false): void {
    if (i === this.chapter || !CHORDS[i]) return;
    this.chapter = i;
    const now = this.ctx.currentTime;
    const tc = immediate ? 0.01 : 1.1;
    CHORDS[i].forEach((m, k) => {
      const f = NOTE(m);
      this.voices[k].oscA.frequency.setTargetAtTime(f, now, tc);
      this.voices[k].oscB.frequency.setTargetAtTime(f * 1.0015, now, tc);
    });
    this.pad.gain.setTargetAtTime(i === 5 ? 0.08 : 0.16, now, 1.2);
    this.padFilter.Q.setTargetAtTime(i === 3 ? 1.1 : 0.6, now, 1.0);
  }

  /** Karplus–Strong string, rendered once per pitch and cached. */
  private string(midi: number): AudioBuffer {
    const hit = this.harp.get(midi);
    if (hit) return hit;
    const sr = this.ctx.sampleRate;
    const f = NOTE(midi);
    const n = Math.max(2, Math.round(sr / f));
    const len = Math.floor(sr * 1.8);
    const buf = this.ctx.createBuffer(1, len, sr);
    const out = buf.getChannelData(0);
    const ring = new Float32Array(n);
    let seed = midi * 9301 + 49297;
    let prev = 0;
    for (let i = 0; i < n; i++) {
      seed = (seed * 9301 + 49297) % 233280;
      const w = (seed / 233280) * 2 - 1;
      prev = prev * 0.5 + w * 0.5; // soften the excitation
      ring[i] = prev;
    }
    const decay = 0.9965 - (midi - 60) * 0.00008;
    let idx = 0;
    for (let i = 0; i < len; i++) {
      const a = ring[idx];
      const b = ring[(idx + 1) % n];
      const v = decay * 0.5 * (a + b);
      ring[idx] = v;
      out[i] = a;
      idx = (idx + 1) % n;
    }
    // gentle fade-out tail
    const tail = Math.floor(sr * 0.25);
    for (let i = 0; i < tail; i++) out[len - 1 - i] *= i / tail;
    this.harp.set(midi, buf);
    return buf;
  }

  private play(midi: number, gain: number, pan = 0, delay = 0, filter?: number): void {
    const ctx = this.ctx;
    const src = ctx.createBufferSource();
    src.buffer = this.string(midi);
    const g = ctx.createGain();
    g.gain.value = gain;
    let node: AudioNode = src;
    if (filter) {
      const lp = ctx.createBiquadFilter();
      lp.type = 'lowpass';
      lp.frequency.value = filter;
      node.connect(lp);
      node = lp;
    }
    const p = ctx.createStereoPanner();
    p.pan.value = pan;
    node.connect(g).connect(p).connect(this.master);
    // Cap simultaneous strings so rapid input never piles up.
    if (this.active.length >= 6) {
      const old = this.active.shift();
      if (old) {
        old.gain.gain.setTargetAtTime(0, ctx.currentTime, 0.03);
        old.src.stop(ctx.currentTime + 0.12);
      }
    }
    const entry = { src, gain: g };
    this.active.push(entry);
    src.onended = () => {
      this.active = this.active.filter((e) => e !== entry);
      src.disconnect();
      g.disconnect();
      p.disconnect();
    };
    src.start(ctx.currentTime + delay);
  }

  pluck(group: number, strength: number): void {
    if (!this.enabled) return;
    const now = performance.now();
    if (now - this.lastPluck < 45) return;
    this.lastPluck = now;
    const midi = HARP[Math.max(0, Math.min(HARP.length - 1, group))];
    this.play(midi, 0.18 + 0.32 * strength, (group / 14 - 0.5) * 1.2);
  }

  cue(kind: CueKind): void {
    if (!this.enabled) return;
    const now = performance.now();
    const gap = kind === 'tick' ? 90 : kind === 'chapter' ? 1400 : 250;
    if (now - (this.lastCue[kind] ?? 0) < gap) return;
    this.lastCue[kind] = now;
    switch (kind) {
      case 'chapter':
        this.play(74, 0.12, -0.2, 0, 2400);
        this.play(81, 0.08, 0.2, 0.09, 2400);
        break;
      case 'approve':
        this.play(69, 0.3, -0.1);
        this.play(74, 0.26, 0.1, 0.11);
        break;
      case 'success':
        this.play(74, 0.24, -0.2);
        this.play(78, 0.22, 0, 0.1);
        this.play(81, 0.22, 0.2, 0.2);
        break;
      case 'fail':
        this.play(50, 0.34, 0, 0, 700);
        this.play(49, 0.22, 0, 0.12, 600);
        break;
      case 'tick':
        this.play(86, 0.07, 0.3, 0, 3000);
        break;
      case 'forget':
        this.play(78, 0.2, 0.2);
        this.play(73, 0.18, 0, 0.09, 1800);
        this.play(66, 0.14, -0.2, 0.18, 1200);
        break;
      case 'focus':
        this.play(76, 0.18, 0);
        break;
    }
  }

  dispose(): void {
    document.removeEventListener('visibilitychange', this.onVisibility);
    this.active.forEach((a) => {
      try {
        a.src.stop();
      } catch {
        /* already stopped */
      }
    });
    this.voices.forEach((v) => {
      v.oscA.stop();
      v.oscB.stop();
    });
    this.lfo.stop();
    this.noiseSrc.stop();
    void this.ctx.close();
  }
}
