import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  CatmullRomCurve3,
  CylinderGeometry,
  Mesh,
  Points,
  ShaderMaterial,
  Vector3,
  Group,
} from 'three';
import { buildRibbonGeometry, createRibbonMaterial, type ThreadSpec } from './ribbon';
import type { Quality } from '../core/quality';
import { CAPABILITIES } from '../content/content';

/* World units. The loom is centred on the origin, facing +z. */
export const LOOM_W = 9.6;
export const LOOM_H = 6.0;
export const GROUPS = 15;
export const FABRIC_ROWS = 26;
export const ROW_BASE = -2.82;
export const ROW_STEP = 0.112;
/** The amber thread always sits on the line currently being woven. */
export const intentY = (rows: number): number => ROW_BASE + rows * ROW_STEP + 0.16;
export const WAVE_END_X = -LOOM_W / 2 - 0.2;
/** [warp group, fabric row] for each of the four example memories. */
export const MEMORY_KNOTS: [number, number][] = [
  [4, 17],
  [2, 13],
  [5, 9],
  [1, 6],
];

const LUMEN: [number, number, number] = [0.6, 0.72, 1.0];
const LUMEN_DIM: [number, number, number] = [0.42, 0.5, 0.72];
const EMBER: [number, number, number] = [1.0, 0.56, 0.22];
const KNOT_GOLD: [number, number, number] = [1.0, 0.82, 0.45];

/** Small deterministic PRNG so the world looks the same on every visit. */
function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function groupCenterX(g: number): number {
  const gx = LOOM_W / GROUPS;
  return -LOOM_W / 2 + gx * (g + 0.5);
}

/** Over/under offset shared by weft rows so everything weaves consistently. */
function weaveZ(x: number, row: number): number {
  return 0.05 * Math.sin((x / (LOOM_W / GROUPS / 3)) * Math.PI + row * Math.PI);
}

export interface LoomParts {
  root: Group;
  warp: Mesh;
  warpMat: ShaderMaterial;
  fabric: Mesh;
  fabricMat: ShaderMaterial;
  intent: Mesh;
  intentMat: ShaderMaterial;
  exec: Mesh;
  execMat: ShaderMaterial;
  rings: Mesh;
  ringsMat: ShaderMaterial;
  knots: Points;
  knotsMat: ShaderMaterial;
  motes: Points;
  motesMat: ShaderMaterial;
  rods: Mesh[];
  rodMat: ShaderMaterial;
  /** Arc-length positions (0…1) of each heddle along the action thread. */
  ringT: number[];
  ringCenters: Vector3[];
  /** World positions of the four memory knots. */
  memoryKnots: Vector3[];
  ribbonMats: ShaderMaterial[];
}

export function buildLoom(q: Quality): LoomParts {
  const root = new Group();
  const rand = rng(7);

  /* ── Warp: vertical strings, grouped by capability ── */
  const warpThreads: ThreadSpec[] = [];
  const warpPoints = 44;
  const perGroup = q.warpPerGroup;
  const total = GROUPS * perGroup;
  let id = 0;
  for (let g = 0; g < GROUPS; g++) {
    const cx = groupCenterX(g);
    for (let k = 0; k < perGroup; k++) {
      const x = cx + (k - (perGroup - 1) / 2) * 0.1;
      const pts = new Float32Array(warpPoints * 3);
      for (let i = 0; i < warpPoints; i++) {
        const s = i / (warpPoints - 1);
        pts[i * 3] = x;
        pts[i * 3 + 1] = LOOM_H / 2 + 0.1 - s * (LOOM_H + 0.2);
        pts[i * 3 + 2] = -0.04 * Math.sin(Math.PI * s);
      }
      const status = CAPABILITIES[g]?.status ?? 'working';
      const col = status === 'working' ? LUMEN : LUMEN_DIM;
      warpThreads.push({ points: pts, color: col, meta: [id, g, 0, (id / total) * 0.9 + rand() * 0.1] });
      id++;
    }
  }
  const warpGeo = buildRibbonGeometry(warpThreads);
  const statusArr = new Array(16).fill(0);
  CAPABILITIES.forEach((c, i) => (statusArr[i] = c.status === 'working' ? 0 : c.status === 'dev' ? 1 : 2));
  const warpMat = createRibbonMaterial({
    width: 5,
    core: 1.3,
    halo: 0.22,
    opacity: 0.62,
    segT: 1 / (warpPoints - 1),
    defines: { WARP: true, REVEAL: true, STAGGER: true, REGION: true },
    extraUniforms: {
      uGroupGlow: { value: new Array(16).fill(0) },
      uPluck: { value: new Array(16).fill(0) },
      uStatus: { value: statusArr },
      uShimmer: { value: 1 },
      uWarpGlow: { value: 0 },
      uFocusAny: { value: 0 },
    },
  });
  warpMat.uniforms.uStagger.value = 0.6;
  const warp = new Mesh(warpGeo, warpMat);
  warp.frustumCulled = false;
  warp.renderOrder = 2;
  root.add(warp);

  /* ── Fabric: woven weft rows, growing from the bottom beam upward ── */
  const rowThreads: ThreadSpec[] = [];
  const rp = q.rowPoints;
  for (let r = 0; r < FABRIC_ROWS; r++) {
    const y = ROW_BASE + r * ROW_STEP;
    const pts = new Float32Array(rp * 3);
    const x0 = -LOOM_W / 2 - 0.15;
    const x1 = LOOM_W / 2 + 0.15;
    for (let i = 0; i < rp; i++) {
      const s = i / (rp - 1);
      const x = x0 + (x1 - x0) * s;
      pts[i * 3] = x;
      pts[i * 3 + 1] = y + 0.012 * Math.sin(x * 1.7 + r);
      pts[i * 3 + 2] = weaveZ(x, r);
    }
    // Mostly silver rows; every fourth row carries the person's amber; a few gold rows mark remembered things.
    const isEmber = r % 4 === 1;
    const isGold = r === 9 || r === 17 || r === 22;
    const c = isEmber ? EMBER : isGold ? KNOT_GOLD : LUMEN_DIM;
    const tint = 0.75 + rand() * 0.25;
    rowThreads.push({ points: pts, color: [c[0] * tint, c[1] * tint, c[2] * tint], meta: [r, 0, r, 0] });
  }
  const fabricGeo = buildRibbonGeometry(rowThreads);
  const fabricMat = createRibbonMaterial({
    width: 4.2,
    core: 1.2,
    halo: 0.2,
    opacity: 0.7,
    segT: 1 / (rp - 1),
    defines: { FABRIC: true, REGION: true },
    extraUniforms: {
      uRows: { value: 0 },
      uForget: { value: [new Vector3(), new Vector3(), new Vector3(), new Vector3()] },
    },
  });
  const fabric = new Mesh(fabricGeo, fabricMat);
  fabric.frustumCulled = false;
  fabric.renderOrder = 3;
  root.add(fabric);

  /* ── Intent: the amber thread — a voice waveform that straightens as it enters the weave ── */
  const ip = q.tier === 'low' ? 260 : 420;
  const intentPts = new Float32Array(ip * 3);
  const ix0 = -17;
  const ix1 = LOOM_W / 2 + 0.6;
  for (let i = 0; i < ip; i++) {
    const s = i / (ip - 1);
    const x = ix0 + (ix1 - ix0) * s;
    // Outside the loom the thread sweeps up from below and toward the viewer, so it
    // arrives under the headline rather than through it.
    const out = Math.min(1, Math.max(0, (WAVE_END_X - x) / (WAVE_END_X - ix0)));
    intentPts[i * 3] = x;
    const k = Math.min(1, out / 0.2);
    const low = k * k * (3 - 2 * k);
    intentPts[i * 3 + 1] = -5.2 * low;
    intentPts[i * 3 + 2] = x > -LOOM_W / 2 - 0.3 ? weaveZ(x, FABRIC_ROWS) * 1.4 : 2.4 * low;
  }
  const intentGeo = buildRibbonGeometry([{ points: intentPts, color: EMBER, meta: [0, 0, 0, 0] }]);
  const intentMat = createRibbonMaterial({
    width: 9,
    core: 2.0,
    halo: 0.5,
    opacity: 1,
    segT: 1 / (ip - 1),
    defines: { WAVE: true, REVEAL: true, REGION: true },
    extraUniforms: { uWaveAmp: { value: 1 }, uWaveEnd: { value: WAVE_END_X } },
  });
  intentMat.uniforms.uHead.value = 1;
  const intent = new Mesh(intentGeo, intentMat);
  intent.frustumCulled = false;
  intent.renderOrder = 5;
  root.add(intent);

  /* ── Action: six heddles in front of the loom and the thread that passes through them ── */
  const ringCenters: Vector3[] = [];
  for (let k = 0; k < 6; k++) {
    const x = -5.6 + k * 2.24;
    const z = 2.3 + 0.7 * Math.sin((k / 5) * Math.PI);
    const y = 0.95 - k * 0.12 + 0.18 * Math.sin(k * 1.3);
    ringCenters.push(new Vector3(x, y, z));
  }
  const ctrl = [
    new Vector3(-14, 1.7, 1.2),
    new Vector3(-9.5, 1.35, 1.8),
    ...ringCenters,
    new Vector3(8.8, 0.35, 2.0),
    new Vector3(13, 0.1, 1.2),
  ];
  const curve = new CatmullRomCurve3(ctrl, false, 'centripetal');
  const ep = q.tier === 'low' ? 260 : 420;
  const spaced = curve.getSpacedPoints(ep - 1);
  const execPts = new Float32Array(ep * 3);
  spaced.forEach((p, i) => {
    execPts[i * 3] = p.x;
    execPts[i * 3 + 1] = p.y;
    execPts[i * 3 + 2] = p.z;
  });
  const ringT = ringCenters.map((c) => {
    let best = 0;
    let bd = Infinity;
    spaced.forEach((p, i) => {
      const d = p.distanceToSquared(c);
      if (d < bd) {
        bd = d;
        best = i;
      }
    });
    return best / (ep - 1);
  });
  const execGeo = buildRibbonGeometry([{ points: execPts, color: [1.0, 0.68, 0.36], meta: [0, 0, 0, 0] }]);
  const execMat = createRibbonMaterial({
    width: 8,
    core: 1.9,
    halo: 0.45,
    opacity: 1,
    segT: 1 / (ep - 1),
    defines: { REVEAL: true },
  });
  execMat.uniforms.uHead.value = 1;
  const exec = new Mesh(execGeo, execMat);
  exec.frustumCulled = false;
  exec.renderOrder = 6;
  root.add(exec);

  // Heddle rings: closed loops perpendicular to the thread.
  const ringThreads: ThreadSpec[] = [];
  const ringN = 72;
  ringCenters.forEach((c, k) => {
    const tangent = curve.getTangentAt(ringT[k]).normalize().add(new Vector3(0, 0, 1.25)).normalize();
    const up = Math.abs(tangent.y) > 0.9 ? new Vector3(1, 0, 0) : new Vector3(0, 1, 0);
    const u = new Vector3().crossVectors(tangent, up).normalize();
    const v = new Vector3().crossVectors(tangent, u).normalize();
    const approve = k === 3;
    const radius = approve ? 0.78 : 0.58;
    for (let layer = 0; layer < (approve ? 2 : 1); layer++) {
      const rr = radius + layer * 0.16;
      const pts = new Float32Array(ringN * 3);
      for (let i = 0; i < ringN; i++) {
        const a = (i / (ringN - 1)) * Math.PI * 2;
        const p = c.clone().addScaledVector(u, Math.cos(a) * rr).addScaledVector(v, Math.sin(a) * rr);
        pts[i * 3] = p.x;
        pts[i * 3 + 1] = p.y;
        pts[i * 3 + 2] = p.z;
      }
      ringThreads.push({
        points: pts,
        color: approve ? EMBER : LUMEN,
        meta: [k, k, approve ? 1 : 0, 0],
        closed: true,
      });
    }
  });
  const ringsGeo = buildRibbonGeometry(ringThreads);
  const ringsMat = createRibbonMaterial({
    width: 6,
    core: 1.6,
    halo: 0.4,
    opacity: 0.95,
    segT: 1 / (ringN - 1),
    defines: { RINGS: true },
    extraUniforms: { uRingState: { value: new Array(6).fill(0) }, uRingPulse: { value: 1 } },
  });
  const rings = new Mesh(ringsGeo, ringsMat);
  rings.frustumCulled = false;
  rings.renderOrder = 6;
  root.add(rings);

  /* ── Knots: remembered things, set into the fabric ── */
  // Memory knots sit on the left of the cloth so they stay visible beside the inspector panel.
  const memoryKnots = MEMORY_KNOTS.map(([g, r]) => new Vector3(groupCenterX(g), ROW_BASE + r * ROW_STEP, weaveZ(groupCenterX(g), r) + 0.04));
  const ambient = 22;
  const kCount = memoryKnots.length + ambient;
  const kPos = new Float32Array(kCount * 3);
  const kKind = new Float32Array(kCount);
  const kSeed = new Float32Array(kCount);
  memoryKnots.forEach((p, i) => {
    kPos.set([p.x, p.y, p.z], i * 3);
    kKind[i] = i + 1;
    kSeed[i] = rand();
  });
  for (let i = memoryKnots.length; i < kCount; i++) {
    const r = Math.floor(rand() * 22);
    const g = Math.floor(rand() * GROUPS);
    const x = groupCenterX(g) + (rand() - 0.5) * 0.2;
    const y = ROW_BASE + r * ROW_STEP;
    kPos.set([x, y, weaveZ(x, r) + 0.03], i * 3);
    kKind[i] = 0;
    kSeed[i] = rand();
  }
  const knotGeo = new BufferGeometry();
  knotGeo.setAttribute('position', new BufferAttribute(kPos, 3));
  knotGeo.setAttribute('aKind', new BufferAttribute(kKind, 1));
  knotGeo.setAttribute('aSeed', new BufferAttribute(kSeed, 1));
  const knotsMat = new ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: AdditiveBlending,
    uniforms: {
      uPixelRatio: { value: 1 },
      uTime: { value: 0 },
      uAlpha: { value: 1 },
      uRows: { value: 0 },
      uHot: { value: [0, 0, 0, 0] },
      uGone: { value: [0, 0, 0, 0] },
      uDim: { value: 1 },
      uScale: { value: 1 },
    },
    vertexShader: /* glsl */ `
      attribute float aKind;
      attribute float aSeed;
      uniform float uPixelRatio;
      uniform float uTime;
      uniform float uRows;
      uniform float uHot[4];
      uniform float uGone[4];
      uniform float uScale;
      varying float vA;
      varying float vHot;
      varying float vKind;
      void main() {
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        float row = (position.y - ${ROW_BASE.toFixed(4)}) / ${ROW_STEP.toFixed(4)};
        float woven = smoothstep(row + 0.2, row + 1.2, uRows);
        float hot = 0.0;
        float gone = 0.0;
        int k = int(aKind + 0.5) - 1;
        if (k >= 0) { hot = uHot[k]; gone = uGone[k]; }
        float tw = 0.75 + 0.25 * sin(uTime * 1.4 + aSeed * 40.0);
        float base = aKind > 0.5 ? 1.0 : 0.5;
        vA = woven * base * tw * (1.0 - gone);
        vHot = hot;
        vKind = aKind;
        float size = (aKind > 0.5 ? 36.0 : 15.0) * (1.0 + hot * 0.9) * (1.0 - gone * 0.6);
        gl_PointSize = size * uPixelRatio * uScale / max(-mv.z, 0.5) * 3.2;
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uAlpha;
      uniform float uDim;
      varying float vA;
      varying float vHot;
      varying float vKind;
      void main() {
        vec2 c = gl_PointCoord - 0.5;
        float d = length(c) * 2.0;
        float disc = 1.0 - smoothstep(0.18, 0.32, d);
        float glow = exp(-d * d * 6.0) * 0.6;
        float ring = (1.0 - smoothstep(0.05, 0.1, abs(d - 0.72))) * vHot;
        float a = (disc + glow + ring) * vA * uAlpha * uDim;
        if (a < 0.003) discard;
        vec3 col = mix(vec3(1.0, 0.84, 0.5), vec3(1.0, 0.95, 0.8), vHot);
        gl_FragColor = vec4(col * (1.0 + vHot * 0.8), a);
      }
    `,
  });
  const knots = new Points(knotGeo, knotsMat);
  knots.frustumCulled = false;
  knots.renderOrder = 7;
  root.add(knots);

  /* ── Motes: slow dust in the light ── */
  const mCount = q.motes;
  const mPos = new Float32Array(mCount * 3);
  const mSeed = new Float32Array(mCount);
  for (let i = 0; i < mCount; i++) {
    mPos.set([(rand() - 0.5) * 26, (rand() - 0.5) * 13, (rand() - 0.5) * 12 - 1], i * 3);
    mSeed[i] = rand();
  }
  const motesGeo = new BufferGeometry();
  motesGeo.setAttribute('position', new BufferAttribute(mPos, 3));
  motesGeo.setAttribute('aSeed', new BufferAttribute(mSeed, 1));
  const motesMat = new ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: AdditiveBlending,
    uniforms: { uTime: { value: 0 }, uPixelRatio: { value: 1 }, uAlpha: { value: 1 }, uWarm: { value: 0.3 } },
    vertexShader: /* glsl */ `
      attribute float aSeed;
      uniform float uTime;
      uniform float uPixelRatio;
      varying float vA;
      varying float vSeed;
      void main() {
        vec3 p = position;
        p.y = mod(p.y + 6.5 + uTime * (0.04 + aSeed * 0.06), 13.0) - 6.5;
        p.x += sin(uTime * 0.2 + aSeed * 30.0) * 0.3;
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        float edge = smoothstep(6.5, 5.0, abs(p.y));
        vA = edge * (0.35 + 0.65 * fract(aSeed * 7.13)) * (0.6 + 0.4 * sin(uTime * (0.6 + aSeed) + aSeed * 20.0));
        vSeed = aSeed;
        gl_PointSize = (1.4 + aSeed * 2.4) * uPixelRatio * 7.0 / max(-mv.z, 0.6);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uAlpha;
      uniform float uWarm;
      varying float vA;
      varying float vSeed;
      void main() {
        float d = length(gl_PointCoord - 0.5) * 2.0;
        float a = exp(-d * d * 4.0) * vA * uAlpha * 0.55;
        if (a < 0.003) discard;
        vec3 cool = vec3(0.62, 0.74, 1.0);
        vec3 warm = vec3(1.0, 0.72, 0.45);
        gl_FragColor = vec4(mix(cool, warm, step(1.0 - uWarm, vSeed)), a);
      }
    `,
  });
  const motes = new Points(motesGeo, motesMat);
  motes.frustumCulled = false;
  motes.renderOrder = 1;
  root.add(motes);

  /* ── Beams: the loom's top and bottom rods ── */
  const rodMat = new ShaderMaterial({
    uniforms: { uDim: { value: 1 }, uRim: { value: 0.5 } },
    vertexShader: /* glsl */ `
      varying vec3 vN;
      varying vec3 vV;
      void main() {
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vN = normalize(normalMatrix * normal);
        vV = normalize(-mv.xyz);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uDim;
      uniform float uRim;
      varying vec3 vN;
      varying vec3 vV;
      void main() {
        float f = pow(1.0 - max(dot(normalize(vN), normalize(vV)), 0.0), 2.4);
        float top = max(normalize(vN).y, 0.0);
        vec3 base = vec3(0.035, 0.04, 0.055);
        vec3 col = base + vec3(0.55, 0.66, 0.9) * f * uRim + vec3(0.12, 0.1, 0.08) * top * 0.4;
        gl_FragColor = vec4(col * uDim + base * (1.0 - uDim), 1.0);
      }
    `,
  });
  const rodGeo = new CylinderGeometry(0.075, 0.075, LOOM_W + 1.4, 20, 1, false);
  rodGeo.rotateZ(Math.PI / 2);
  const rods = [LOOM_H / 2 + 0.16, -LOOM_H / 2 - 0.16].map((y) => {
    const m = new Mesh(rodGeo, rodMat);
    m.position.set(0, y, -0.02);
    m.renderOrder = 0;
    root.add(m);
    return m;
  });

  return {
    root,
    warp,
    warpMat,
    fabric,
    fabricMat,
    intent,
    intentMat,
    exec,
    execMat,
    rings,
    ringsMat,
    knots,
    knotsMat,
    motes,
    motesMat,
    rods,
    rodMat,
    ringT,
    ringCenters,
    memoryKnots,
    ribbonMats: [warpMat, fabricMat, intentMat, execMat, ringsMat],
  };
}

export function disposeLoom(parts: LoomParts): void {
  const geos = new Set<BufferGeometry>();
  parts.root.traverse((o) => {
    const m = o as Mesh;
    if (m.geometry) geos.add(m.geometry as BufferGeometry);
  });
  geos.forEach((g) => g.dispose());
  [...parts.ribbonMats, parts.knotsMat, parts.motesMat, parts.rodMat].forEach((m) => m.dispose());
}
