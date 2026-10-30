import {
  Color,
  Mesh,
  PerspectiveCamera,
  Plane,
  Raycaster,
  Scene,
  ShaderMaterial,
  Vector2,
  Vector3,
  WebGLRenderer,
  BufferGeometry,
  BufferAttribute,
  type Vector4,
} from 'three';
import { store, events, type SiteState } from '../core/store';
import { clamp, lerp, loopProgress, loopView, smooth, APPROVE_STEP } from '../core/sequence';
import { readGpu, pickTier, TIERS, type Quality } from '../core/quality';
import { buildLoom, disposeLoom, intentY, MEMORY_KNOTS, type LoomParts } from './loom';
import { syncFrameUniforms } from './ribbon';
import { KEYS, makePose, poseAt } from './keyframes';
import { DESTINATIONS } from '../content/content';

export interface WorldStats {
  tier: string;
  gpu: string;
  dpr: number;
  framesRendered: number;
  activeFrameMs: number[];
  downgrades: number;
  drawCalls: number;
  triangles: number;
  firstFrameAt: number;
}

const MEMORY_ROWS = MEMORY_KNOTS.map(([, r]) => r);

/** Exponential approach that is independent of frame rate. */
const approach = (cur: number, target: number, rate: number, dt: number): number =>
  cur + (target - cur) * (1 - Math.exp(-rate * dt));

export class World {
  private renderer: WebGLRenderer;
  private scene = new Scene();
  private camera = new PerspectiveCamera(38, 1, 0.1, 80);
  private loom: LoomParts;
  private backdrop: Mesh;
  private backdropMat: ShaderMaterial;
  private quality: Quality;
  private dprScale = 1;
  private raf = 0;
  private lastFrame = 0;
  private lastRender = 0;
  private dirty = true;
  private startTime = 0;
  private settling = 0;
  private disposed = false;
  private unsub: (() => void)[] = [];

  // Smoothed state
  private pose = makePose();
  private camPos = new Vector3();
  private camLook = new Vector3();
  private camInit = false;
  private groupGlow = new Array(16).fill(0);
  private pluck = new Array(16).fill(0);
  private hot = [0, 0, 0, 0];
  private gone = [0, 0, 0, 0];
  private regionAmt = 0;
  private regionRect: [number, number, number, number] = [0, 0, 0, 0];
  private regionColor = new Color(1, 1, 1);
  private ringState = new Array(6).fill(0);
  private orbit = { yaw: 0, pitch: 0, vy: 0, vp: 0 };
  private focusPos = new Vector3();
  private focusLook = new Vector3();
  private focusAmt = 0;
  private demoPulse = 0;
  private struggled = false;

  // Explore interaction
  private stage: HTMLElement | null;
  private drag: { id: number; x: number; y: number; moved: number; startYaw: number; startPitch: number } | null = null;
  private raycaster = new Raycaster();
  private plane = new Plane(new Vector3(0, 0, 1), 0);

  readonly stats: WorldStats;
  /** Called once if the device stays slow at the lowest render resolution. */
  onStruggle: (() => void) | null = null;

  constructor(canvas: HTMLCanvasElement, onFail: (reason: string) => void) {
    this.renderer = new WebGLRenderer({
      canvas,
      antialias: false,
      alpha: false,
      powerPreference: 'high-performance',
      failIfMajorPerformanceCaveat: false,
      stencil: false,
    });
    const gl = this.renderer.getContext();
    const gpu = readGpu(gl);
    const tier = pickTier(gpu);
    this.quality = TIERS[tier];
    this.stats = {
      tier,
      gpu: gpu.renderer,
      dpr: 1,
      framesRendered: 0,
      activeFrameMs: [],
      downgrades: 0,
      drawCalls: 0,
      triangles: 0,
      firstFrameAt: 0,
    };
    this.renderer.setClearColor(new Color('#07080b'), 1);
    this.renderer.autoClear = true;

    this.loom = buildLoom(this.quality);
    this.scene.add(this.loom.root);

    // Screen-filling backdrop: a soft pool of light whose warmth follows the story.
    const bgGeo = new BufferGeometry();
    bgGeo.setAttribute('position', new BufferAttribute(new Float32Array([-1, -1, 0, 3, -1, 0, -1, 3, 0]), 3));
    this.backdropMat = new ShaderMaterial({
      depthTest: false,
      depthWrite: false,
      uniforms: { uWarm: { value: 0.3 }, uDim: { value: 1 }, uAspect: { value: 1 }, uCenter: { value: new Vector2(0.66, 0.5) } },
      vertexShader: /* glsl */ `
        varying vec2 vUv;
        void main() { vUv = position.xy * 0.5 + 0.5; gl_Position = vec4(position.xy, 0.0, 1.0); }
      `,
      fragmentShader: /* glsl */ `
        uniform float uWarm;
        uniform float uDim;
        uniform float uAspect;
        uniform vec2 uCenter;
        varying vec2 vUv;
        float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
        void main() {
          vec2 p = vUv - uCenter;
          p.x *= uAspect;
          float r = length(p);
          vec3 ink = vec3(0.027, 0.031, 0.043);
          vec3 cool = vec3(0.075, 0.095, 0.15);
          vec3 warm = vec3(0.15, 0.095, 0.055);
          vec3 pool = mix(cool, warm, uWarm);
          vec3 col = ink + pool * exp(-r * r * 2.2) * (0.35 + 0.65 * uDim);
          col += (hash(gl_FragCoord.xy) - 0.5) / 255.0 * 1.5;
          gl_FragColor = vec4(col, 1.0);
        }
      `,
    });
    this.backdrop = new Mesh(bgGeo, this.backdropMat);
    this.backdrop.frustumCulled = false;
    this.backdrop.renderOrder = -10;
    this.scene.add(this.backdrop);

    this.camera.position.set(0, 0, 12);

    canvas.addEventListener('webglcontextlost', this.onContextLost(onFail), false);

    this.resize();
    const onResize = () => this.resize();
    window.addEventListener('resize', onResize);
    this.unsub.push(() => window.removeEventListener('resize', onResize));

    this.unsub.push(
      store.subscribe((_s, changed) => {
        this.dirty = true;
        if (changed.has('motion')) this.settling = performance.now() + 400;
        if (changed.has('exploreReset')) {
          this.orbit.yaw = this.orbit.pitch = this.orbit.vy = this.orbit.vp = 0;
        }
      }),
    );
    this.unsub.push(
      events.on('pluck', ({ group, strength }) => {
        if (group >= 0 && group < 16) this.pluck[group] = Math.max(this.pluck[group], strength);
        this.settling = performance.now() + 1800;
      }),
    );

    this.stage = document.getElementById('explore-stage');
    this.bindStage();

    // Compile shaders before the first visible frame to avoid a stutter on reveal.
    this.renderer.compile(this.scene, this.camera);
  }

  start(): void {
    this.startTime = performance.now();
    this.lastFrame = this.startTime;
    this.raf = requestAnimationFrame(this.loop);
  }

  /* ───────── Frame loop (demand-driven) ───────── */

  private loop = (now: number): void => {
    if (this.disposed) return;
    this.raf = requestAnimationFrame(this.loop);
    const s = store.get();
    const reduced = s.motion === 'reduced';
    const dt = Math.min(0.1, (now - this.lastFrame) / 1000);
    this.lastFrame = now;

    const introRunning = !reduced && now - this.startTime < 3200;
    const busy = this.dirty || introRunning || now < this.settling || this.drag !== null || Math.abs(this.orbit.vy) > 1e-4;
    const idleEvery = reduced ? Infinity : this.quality.idleInterval * (s.chapter === 5 ? 2 : 1);
    if (!busy && now - this.lastRender < idleEvery) return;

    const moving = this.update(s, dt, now, reduced);
    this.dirty = moving;
    this.renderer.render(this.scene, this.camera);

    if (this.stats.framesRendered === 0) this.stats.firstFrameAt = now;
    this.stats.framesRendered++;
    if (busy && now - this.lastRender < 200) this.recordFrame(now - this.lastRender, now);
    this.lastRender = now;
    const info = this.renderer.info.render;
    this.stats.drawCalls = info.calls;
    this.stats.triangles = info.triangles;
  };

  private recordFrame(ms: number, now: number): void {
    const arr = this.stats.activeFrameMs;
    arr.push(ms);
    if (arr.length > 240) arr.shift();
    // Adapt downward if the device keeps missing ~30 fps after warm-up.
    if (now - this.startTime > 4000 && arr.length >= 90 && this.stats.framesRendered % 30 === 0) {
      const recent = arr.slice(-90).sort((a, b) => a - b);
      const median = recent[45];
      if (median > 36 && this.dprScale > 0.62) {
        this.dprScale = Math.max(0.6, this.dprScale - 0.15);
        this.stats.downgrades++;
        this.resize();
        arr.length = 0;
      } else if (median > 40 && !this.struggled) {
        // Already at the lowest resolution and still slow: the device is CPU-bound. Offer Lite mode once.
        this.struggled = true;
        this.onStruggle?.();
      }
    }
  }

  private update(s: Readonly<SiteState>, dt: number, now: number, reduced: boolean): boolean {
    const time = reduced ? 12 : (now - this.startTime) / 1000;
    const aspect = s.vw / Math.max(1, s.vh);
    const P = poseAt(s.t, aspect, s.compact, this.pose).params;
    let moving = false;

    /* Intro: strings draw in, then the amber thread arrives. */
    const it = reduced ? 10 : (now - this.startTime) / 1000;
    const warpIntro = smooth(it / 1.8);
    const intentIntro = smooth((it - 0.7) / 2.3);

    /* Camera: scroll pose → explore focus/orbit blend → damped. */
    const exploreW = smooth((s.t - (KEYS.length - 1.5)) / 0.5);
    const dest = DESTINATIONS.find((d) => d.id === s.exploreFocus);
    this.focusAmt = reduced ? (dest ? 1 : 0) : approach(this.focusAmt, dest ? 1 : 0, 3.2, dt);
    if (dest) {
      const [x0, y0, x1, y1] = dest.region;
      const cx = (x0 + x1) / 2;
      const cy = (y0 + y1) / 2;
      const dist = s.compact ? 8.5 : 6.2;
      // keep the focused region right of the controls on wide screens
      const shift = s.compact ? 0 : -1.9;
      this.focusLook.set(cx + shift * 0.6, cy - (s.compact ? 0.9 : 0), 0);
      this.focusPos.set(cx + 0.9 + shift * 0.3, cy + 0.35, dist);
    }
    const fw = this.focusAmt * exploreW;
    const tgtPos = this.pose.pos.clone().lerp(this.focusPos, fw);
    const tgtLook = this.pose.look.clone().lerp(this.focusLook, fw);

    // Orbit around the look target, only in the final chapter.
    if (!this.drag && !reduced) {
      this.orbit.yaw += this.orbit.vy;
      this.orbit.pitch += this.orbit.vp;
      this.orbit.vy *= Math.pow(0.0025, dt);
      this.orbit.vp *= Math.pow(0.0025, dt);
      if (Math.abs(this.orbit.vy) < 1e-5) this.orbit.vy = 0;
      if (Math.abs(this.orbit.vp) < 1e-5) this.orbit.vp = 0;
    }
    this.orbit.yaw = clamp(this.orbit.yaw, -0.6, 0.6);
    this.orbit.pitch = clamp(this.orbit.pitch, -0.28, 0.28);
    if (exploreW > 0.001 && (this.orbit.yaw !== 0 || this.orbit.pitch !== 0)) {
      const off = tgtPos.clone().sub(tgtLook);
      const r = off.length();
      const yaw = Math.atan2(off.x, off.z) + this.orbit.yaw * exploreW;
      const pitch = Math.asin(clamp(off.y / r, -1, 1)) + this.orbit.pitch * exploreW;
      off.set(Math.sin(yaw) * Math.cos(pitch) * r, Math.sin(pitch) * r, Math.cos(yaw) * Math.cos(pitch) * r);
      tgtPos.copy(tgtLook).add(off);
    }

    // Subtle pointer-free drift so the shot breathes (disabled for reduced motion).
    if (!reduced) {
      tgtPos.x += Math.sin(time * 0.13) * 0.12;
      tgtPos.y += Math.sin(time * 0.17 + 1.3) * 0.08;
    }

    if (!this.camInit || reduced) {
      this.camPos.copy(tgtPos);
      this.camLook.copy(tgtLook);
      this.camInit = true;
    } else {
      const before = this.camPos.distanceToSquared(tgtPos) + this.camLook.distanceToSquared(tgtLook);
      const rate = 4.2;
      this.camPos.lerp(tgtPos, 1 - Math.exp(-rate * dt));
      this.camLook.lerp(tgtLook, 1 - Math.exp(-rate * dt));
      // Ambient drift keeps a tiny lag forever; only a real transition counts as movement
      // so idle frames stay on the capped ambient cadence.
      if (before > 2e-4) moving = true;
    }
    this.camera.position.copy(this.camPos);
    this.camera.lookAt(this.camLook);

    /* Story parameters */
    const L = this.loom;
    const dim = P.dim;
    const regionTarget = dest ? exploreW : 0;
    this.regionAmt = reduced ? regionTarget : approach(this.regionAmt, regionTarget, 4, dt);
    if (dest) {
      this.regionRect = dest.region;
      this.regionColor.set(dest.color);
    }
    if (Math.abs(this.regionAmt - regionTarget) > 0.002) moving = true;

    for (const m of L.ribbonMats) {
      m.uniforms.uDim.value = dim;
      (m.uniforms.uRegion.value as Vector4).set(...this.regionRect);
      m.uniforms.uRegionAmt.value = this.regionAmt;
      (m.uniforms.uRegionColor.value as Color).copy(this.regionColor);
      // On narrow layouts text stacks over the world, so the scrim does the work instead.
      (m.uniforms.uMask.value as Vector2).set(s.compact ? 0 : P.maskL, s.compact ? 0 : P.maskR);
    }

    // Warp strings
    const wu = L.warpMat.uniforms;
    wu.uReveal.value = warpIntro;
    wu.uShimmer.value = reduced ? 0 : P.shimmer;
    wu.uWarpGlow.value = P.warpGlow;
    const glow = wu.uGroupGlow.value as number[];
    const pl = wu.uPluck.value as number[];
    const capW = smooth((1 - Math.abs(s.t - 6) / 1.1) * 1.4);
    for (let g = 0; g < 16; g++) {
      const target = (s.capSelected === g ? 1 : s.capHover === g ? 0.7 : 0) * Math.max(capW, 0.25);
      this.groupGlow[g] = reduced ? target : approach(this.groupGlow[g], target, 8, dt);
      glow[g] = this.groupGlow[g];
      if (Math.abs(this.groupGlow[g] - target) > 0.003) moving = true;
      this.pluck[g] = reduced ? 0 : this.pluck[g] * Math.exp(-dt * 2.6);
      if (this.pluck[g] < 0.002) this.pluck[g] = 0;
      pl[g] = this.pluck[g];
    }
    wu.uFocusAny.value = Math.min(1, Math.max(...this.groupGlow) * 1.6);

    // Fabric
    const fu = L.fabricMat.uniforms;
    fu.uRows.value = P.rows * (reduced ? 1 : smooth(it / 1.4)) + this.demoPulse;
    fu.uOpacity.value = 0.7 * P.cloth;
    const forget = fu.uForget.value as Vector3[];
    for (let i = 0; i < 4; i++) {
      const tg = s.forgotten[i] ? 1 : 0;
      this.gone[i] = reduced ? tg : approach(this.gone[i], tg, 2.4, dt);
      if (Math.abs(this.gone[i] - tg) > 0.002) moving = true;
      forget[i].set(L.memoryKnots[i].x, MEMORY_ROWS[i], this.gone[i]);
      const hotT = s.memoryHover === i ? 1 : 0;
      this.hot[i] = reduced ? hotT : approach(this.hot[i], hotT, 9, dt);
      if (Math.abs(this.hot[i] - hotT) > 0.002) moving = true;
    }

    // Knots
    const ku = L.knotsMat.uniforms;
    ku.uRows.value = fu.uRows.value;
    ku.uAlpha.value = P.knots;
    ku.uDim.value = dim;
    ku.uHot.value = this.hot.map((h) => h * (s.chapter === 2 ? 1 : 0.6));
    ku.uGone.value = this.gone.slice();
    ku.uTime.value = time;

    // Intent thread
    const iu = L.intentMat.uniforms;
    iu.uReveal.value = P.intent * intentIntro;
    iu.uWaveAmp.value = P.wave;
    iu.uOpacity.value = P.intentAlpha;
    L.intent.position.y = intentY(Math.max(P.rows, 5));

    // Action thread and heddles — the same function drives the HTML step list.
    const p3 = s.local[3] ?? 0;
    const view = loopView(p3);
    const v = loopProgress(p3);
    const rt = L.ringT;
    let reveal: number;
    if (v >= 6) reveal = lerp(rt[5] + 0.004, 1, smooth((p3 - 0.86) / 0.14));
    else {
      const kk = Math.floor(v);
      const f = v - kk;
      const from = kk === 0 ? rt[0] - 0.1 : rt[kk - 1] + 0.004;
      reveal = lerp(from, rt[kk] + 0.004, f);
    }
    const eu = L.execMat.uniforms;
    eu.uReveal.value = reveal;
    eu.uOpacity.value = P.exec;
    L.exec.visible = P.exec > 0.01;
    L.rings.visible = P.exec > 0.01;
    for (let r = 0; r < 6; r++) {
      let st = view.reached > r ? 1 : 0;
      if (r === APPROVE_STEP && v >= APPROVE_STEP + 1 - 0.02) st = view.approved ? 3 : 2;
      this.ringState[r] = st;
    }
    const ru = L.ringsMat.uniforms;
    ru.uRingState.value = this.ringState.slice();
    ru.uOpacity.value = P.exec;
    ru.uRingPulse.value = reduced ? 0 : 1;

    // Demo heartbeat: while a demo runs, the newest fabric row advances with it.
    const demoTarget = s.demoPhase === 'running' || s.demoPhase === 'waiting' ? s.demoProgress * 0.9 : s.demoPhase === 'done' ? 1 : 0;
    this.demoPulse = reduced ? demoTarget : approach(this.demoPulse, demoTarget, 3, dt);

    // Motes, rods, backdrop
    L.motesMat.uniforms.uTime.value = time;
    L.motesMat.uniforms.uAlpha.value = dim * (reduced ? 0.6 : 1);
    L.motesMat.uniforms.uWarm.value = P.warm * 0.5;
    L.rodMat.uniforms.uDim.value = dim;
    this.backdropMat.uniforms.uWarm.value = P.warm;
    this.backdropMat.uniforms.uDim.value = dim;
    this.backdropMat.uniforms.uAspect.value = aspect;
    (this.backdropMat.uniforms.uCenter.value as Vector2).set(s.compact ? 0.5 : 0.64, s.compact ? 0.42 : 0.5);

    syncFrameUniforms(L.ribbonMats, s.vw, s.vh, this.renderer.getPixelRatio(), time);
    L.knotsMat.uniforms.uPixelRatio.value = this.renderer.getPixelRatio();
    L.motesMat.uniforms.uPixelRatio.value = this.renderer.getPixelRatio();

    return moving;
  }

  /* ───────── Explore stage: drag to orbit, click to focus ───────── */

  private bindStage(): void {
    const el = this.stage;
    if (!el) return;
    const down = (e: PointerEvent) => {
      if (store.get().motion === 'reduced' && e.pointerType !== 'mouse') return;
      this.drag = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: 0, startYaw: this.orbit.yaw, startPitch: this.orbit.pitch };
      if (e.pointerType === 'mouse') el.setPointerCapture(e.pointerId);
      el.classList.add('is-dragging');
    };
    const move = (e: PointerEvent) => {
      if (!this.drag || e.pointerId !== this.drag.id) {
        this.hover(e);
        return;
      }
      const dx = e.clientX - this.drag.x;
      const dy = e.clientY - this.drag.y;
      this.drag.moved = Math.max(this.drag.moved, Math.hypot(dx, dy));
      // On touch, vertical drags belong to page scrolling (touch-action: pan-y).
      const reduced = store.get().motion === 'reduced';
      const prevYaw = this.orbit.yaw;
      this.orbit.yaw = clamp(this.drag.startYaw - (dx / window.innerWidth) * 1.6, -0.6, 0.6);
      if (e.pointerType === 'mouse') this.orbit.pitch = clamp(this.drag.startPitch + (dy / window.innerHeight) * 0.8, -0.28, 0.28);
      this.orbit.vy = reduced ? 0 : (this.orbit.yaw - prevYaw) * 0.6;
      this.dirty = true;
    };
    const up = (e: PointerEvent) => {
      if (!this.drag || e.pointerId !== this.drag.id) return;
      const wasClick = this.drag.moved < 6;
      this.drag = null;
      el.classList.remove('is-dragging');
      if (wasClick) this.pick(e);
    };
    const cancel = () => {
      this.drag = null;
      el.classList.remove('is-dragging');
    };
    el.addEventListener('pointerdown', down);
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', cancel);
    el.addEventListener('pointerleave', () => (el.style.cursor = ''));
    this.unsub.push(() => {
      el.removeEventListener('pointerdown', down);
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', cancel);
    });
  }

  private regionAt(e: PointerEvent): string | null {
    const ndc = new Vector2((e.clientX / window.innerWidth) * 2 - 1, -(e.clientY / window.innerHeight) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const hit = new Vector3();
    if (!this.raycaster.ray.intersectPlane(this.plane, hit)) return null;
    const d = DESTINATIONS.find(({ region: [x0, y0, x1, y1] }) => hit.x >= x0 && hit.x <= x1 && hit.y >= y0 && hit.y <= y1);
    return d ? d.id : null;
  }

  private hover(e: PointerEvent): void {
    if (!this.stage || e.pointerType !== 'mouse') return;
    this.stage.style.cursor = this.regionAt(e) ? 'pointer' : '';
  }

  private pick(e: PointerEvent): void {
    const id = this.regionAt(e);
    const cur = store.get().exploreFocus;
    if (id) {
      store.set({ exploreFocus: cur === id ? null : id });
      events.emit('cue', { kind: 'focus' });
    }
  }

  /* ───────── Lifecycle ───────── */

  private onContextLost(onFail: (reason: string) => void) {
    return (e: Event) => {
      // dispose() deliberately loses the context; only unexpected losses are failures.
      if (this.disposed) return;
      e.preventDefault();
      cancelAnimationFrame(this.raf);
      onFail('The 3D view lost its graphics context.');
    };
  }

  resize(): void {
    const w = window.innerWidth;
    const h = window.innerHeight;
    const dpr = Math.min(window.devicePixelRatio || 1, this.quality.maxDpr) * this.dprScale;
    this.renderer.setPixelRatio(dpr);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.fov = w / h < 0.8 ? 52 : w / h < 1.2 ? 44 : 38;
    this.camera.updateProjectionMatrix();
    this.stats.dpr = dpr;
    this.dirty = true;
  }

  dispose(): void {
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    this.unsub.forEach((fn) => fn());
    this.unsub = [];
    disposeLoom(this.loom);
    this.backdrop.geometry.dispose();
    this.backdropMat.dispose();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
  }
}
