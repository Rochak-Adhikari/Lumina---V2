import { AdditiveBlending, BufferAttribute, BufferGeometry, DoubleSide, ShaderMaterial, Vector2, Vector4, Color } from 'three';

/**
 * Screen-space ribbons: every thread in the world is a polyline expanded to a
 * constant pixel width in the vertex shader, with a soft core + halo in the
 * fragment shader. One geometry can hold many threads (one draw call).
 */

export interface ThreadSpec {
  /** xyz triples */
  points: Float32Array;
  color: [number, number, number];
  /** Free per-thread metadata: x = thread id, y = group, z = row, w = stagger 0…1 */
  meta?: [number, number, number, number];
  closed?: boolean;
}

export function buildRibbonGeometry(threads: ThreadSpec[]): BufferGeometry {
  let vCount = 0;
  let iCount = 0;
  for (const th of threads) {
    const n = th.points.length / 3;
    vCount += n * 2;
    iCount += (n - 1) * 6;
  }
  const position = new Float32Array(vCount * 3);
  const prev = new Float32Array(vCount * 3);
  const next = new Float32Array(vCount * 3);
  const side = new Float32Array(vCount);
  const tt = new Float32Array(vCount);
  const meta = new Float32Array(vCount * 4);
  const color = new Float32Array(vCount * 3);
  const index = vCount > 65535 ? new Uint32Array(iCount) : new Uint16Array(iCount);

  let v = 0;
  let ii = 0;
  for (const th of threads) {
    const p = th.points;
    const n = p.length / 3;
    const m = th.meta ?? [0, 0, 0, 0];
    const base = v;
    for (let i = 0; i < n; i++) {
      let pi: number;
      let ni: number;
      if (th.closed) {
        pi = ((i - 1 + n - 1) % (n - 1)) * 3; // last point duplicates the first
        ni = ((i + 1) % (n - 1)) * 3;
      } else {
        pi = Math.max(0, i - 1) * 3;
        ni = Math.min(n - 1, i + 1) * 3;
      }
      for (let s = 0; s < 2; s++) {
        const o = v * 3;
        position[o] = p[i * 3];
        position[o + 1] = p[i * 3 + 1];
        position[o + 2] = p[i * 3 + 2];
        if (!th.closed && i === 0) {
          // extrapolate so the end segment keeps a defined direction
          prev[o] = 2 * p[0] - p[3];
          prev[o + 1] = 2 * p[1] - p[4];
          prev[o + 2] = 2 * p[2] - p[5];
        } else {
          prev[o] = p[pi];
          prev[o + 1] = p[pi + 1];
          prev[o + 2] = p[pi + 2];
        }
        if (!th.closed && i === n - 1) {
          const l = (n - 1) * 3;
          const l2 = (n - 2) * 3;
          next[o] = 2 * p[l] - p[l2];
          next[o + 1] = 2 * p[l + 1] - p[l2 + 1];
          next[o + 2] = 2 * p[l + 2] - p[l2 + 2];
        } else {
          next[o] = p[ni];
          next[o + 1] = p[ni + 1];
          next[o + 2] = p[ni + 2];
        }
        side[v] = s === 0 ? -1 : 1;
        tt[v] = n > 1 ? i / (n - 1) : 0;
        meta[v * 4] = m[0];
        meta[v * 4 + 1] = m[1];
        meta[v * 4 + 2] = m[2];
        meta[v * 4 + 3] = m[3];
        color[o] = th.color[0];
        color[o + 1] = th.color[1];
        color[o + 2] = th.color[2];
        v++;
      }
    }
    for (let i = 0; i < n - 1; i++) {
      const a = base + i * 2;
      index[ii++] = a;
      index[ii++] = a + 1;
      index[ii++] = a + 2;
      index[ii++] = a + 1;
      index[ii++] = a + 3;
      index[ii++] = a + 2;
    }
  }

  const g = new BufferGeometry();
  g.setAttribute('position', new BufferAttribute(position, 3));
  g.setAttribute('aPrev', new BufferAttribute(prev, 3));
  g.setAttribute('aNext', new BufferAttribute(next, 3));
  g.setAttribute('aSide', new BufferAttribute(side, 1));
  g.setAttribute('aT', new BufferAttribute(tt, 1));
  g.setAttribute('aMeta', new BufferAttribute(meta, 4));
  g.setAttribute('aColor', new BufferAttribute(color, 3));
  g.setIndex(new BufferAttribute(index, 1));
  return g;
}

const VERT = /* glsl */ `
attribute vec3 aPrev;
attribute vec3 aNext;
attribute float aSide;
attribute float aT;
attribute vec4 aMeta;
attribute vec3 aColor;

uniform vec2 uResolution;
uniform float uPixelRatio;
uniform float uWidth;
uniform float uTime;
uniform float uSegT;
uniform float uDim;

varying float vSide;
varying float vScreenX;
varying float vT;
varying vec3 vColor;
varying float vAlpha;
varying float vBoost;
varying float vWidthPx;

#ifdef WARP
uniform float uGroupGlow[16];
uniform float uPluck[16];
uniform float uStatus[16];
uniform float uShimmer;
uniform float uWarpGlow;
uniform float uFocusAny;
varying float vStatus;
#endif

#ifdef FABRIC
uniform float uRows;
uniform vec3 uForget[4];
varying float vRowReveal;
varying float vRowT;
#endif

#ifdef WAVE
uniform float uWaveAmp;
uniform float uWaveEnd;
#endif

#ifdef RINGS
uniform float uRingState[6];
uniform float uRingPulse;
#endif

#ifdef REGION
uniform vec4 uRegion;
uniform float uRegionAmt;
uniform vec3 uRegionColor;
#endif

#ifdef STAGGER
uniform float uStagger;
varying float vStaggerShift;
#endif

vec3 displace(vec3 p, float t) {
  vec3 q = p;
#ifdef WARP
  int gi = int(aMeta.y + 0.5);
  float env = sin(3.14159265 * clamp(t, 0.0, 1.0));
  q.x += env * (uPluck[gi] * 0.075 * sin(uTime * 41.0 + aMeta.x * 1.7)
              + uShimmer * 0.014 * sin(uTime * 1.1 + aMeta.x * 0.83 + t * 5.0));
  q.z += env * uShimmer * 0.02 * sin(uTime * 0.7 + aMeta.x * 1.31);
#endif
#ifdef WAVE
  float w = 1.0 - smoothstep(uWaveEnd - 3.0, uWaveEnd, p.x);
  float s = sin(p.x * 2.6 - uTime * 3.4) * 0.5
          + sin(p.x * 6.1 - uTime * 5.3) * 0.28
          + sin(p.x * 1.2 + uTime * 1.3) * 0.22;
  float far = smoothstep(-17.0, -10.0, p.x);
  q.y += uWaveAmp * w * far * s * 0.62;
#endif
#ifdef FABRIC
  for (int i = 0; i < 4; i++) {
    vec3 f = uForget[i];
    float on = (1.0 - step(0.5, abs(aMeta.z - f.y))) * f.z;
    float d = p.x - f.x;
    float k = exp(-d * d * 1.4) * on;
    q.y -= k * 0.34;
    q.z += k * 0.36;
  }
#endif
  return q;
}

void main() {
  vec3 pC = displace(position, aT);
  vec3 pP = displace(aPrev, aT - uSegT);
  vec3 pN = displace(aNext, aT + uSegT);

  mat4 mvp = projectionMatrix * modelViewMatrix;
  vec4 cC = mvp * vec4(pC, 1.0);
  vec4 cP = mvp * vec4(pP, 1.0);
  vec4 cN = mvp * vec4(pN, 1.0);

  float aspect = uResolution.x / uResolution.y;
  vec2 sP = cP.xy / max(cP.w, 1e-4);
  vec2 sN = cN.xy / max(cN.w, 1e-4);
  sP.x *= aspect;
  sN.x *= aspect;
  vec2 dir = sN - sP;
  float len = length(dir);
  dir = len > 1e-6 ? dir / len : vec2(1.0, 0.0);
  vec2 nrm = vec2(-dir.y, dir.x);
  nrm.x /= aspect;

  float widthScale = 1.0;
  float alpha = 1.0;
  float boost = 0.0;
  vec3 col = aColor;

#ifdef WARP
  int g = int(aMeta.y + 0.5);
  float glow = uGroupGlow[g];
  widthScale += glow * 1.8 + uPluck[g] * 0.6;
  boost += glow * 2.2 + uPluck[g] * 0.8 + uWarpGlow * 0.25;
  // When one capability is in focus, the other strings step back.
  alpha *= mix(1.0, 0.28, uFocusAny * (1.0 - clamp(glow * 1.4, 0.0, 1.0)));
  vStatus = uStatus[g];
  alpha *= mix(1.0, 0.55, step(1.5, vStatus));
#endif

#ifdef RINGS
  int r = int(aMeta.y + 0.5);
  float st = uRingState[r];
  // 0 = idle, 1 = reached, 2 = waiting (pulse), 3 = approved
  float lit = clamp(st, 0.0, 1.0);
  float waiting = step(1.5, st) * (1.0 - step(2.5, st));
  alpha *= mix(0.28, 1.0, lit);
  boost += lit * 0.35 + waiting * (0.25 + 0.3 * sin(uTime * 5.0)) * uRingPulse;
  widthScale += waiting * 0.6 + step(2.5, st) * 0.4;
  col = mix(col, vec3(0.56, 0.84, 0.69), step(2.5, st) * step(0.5, aMeta.z));
#endif

#ifdef FABRIC
  vRowReveal = uRows - aMeta.z;
  vRowT = mod(aMeta.z, 2.0) < 0.5 ? aT : 1.0 - aT;
  for (int i = 0; i < 4; i++) {
    vec3 f = uForget[i];
    float on = (1.0 - step(0.5, abs(aMeta.z - f.y))) * f.z;
    float d = pC.x - f.x;
    alpha *= 1.0 - 0.75 * exp(-d * d * 1.4) * on;
  }
#endif

#ifdef REGION
  vec2 lo = smoothstep(uRegion.xy - 0.25, uRegion.xy + 0.05, pC.xy);
  vec2 hi = 1.0 - smoothstep(uRegion.zw - 0.05, uRegion.zw + 0.25, pC.xy);
  float inside = lo.x * lo.y * hi.x * hi.y;
  boost += inside * uRegionAmt * 1.1;
  alpha *= mix(1.0, mix(0.35, 1.0, inside), uRegionAmt);
  col = mix(col, uRegionColor, inside * uRegionAmt * 0.65);
#endif

#ifdef STAGGER
  vStaggerShift = aMeta.w * uStagger;
#endif

  float wpx = uWidth * uPixelRatio * widthScale;
  cC.xy += nrm * aSide * wpx / uResolution.y * cC.w;
  gl_Position = cC;
  vScreenX = cC.x / cC.w * 0.5 + 0.5;

  vSide = aSide;
  vT = aT;
  vColor = col;
  vAlpha = alpha * uDim;
  vBoost = boost;
  vWidthPx = wpx;
}
`;

const FRAG = /* glsl */ `
uniform float uOpacity;
uniform float uCore;
uniform float uHalo;
// Legibility mask: dims threads behind the text column (x: left amount, y: right amount).
uniform vec2 uMask;
varying float vScreenX;

varying float vSide;
varying float vT;
varying vec3 vColor;
varying float vAlpha;
varying float vBoost;
varying float vWidthPx;

#ifdef REVEAL
uniform float uReveal;
uniform float uHead;
#endif

#ifdef STAGGER
varying float vStaggerShift;
#endif

#ifdef WARP
varying float vStatus;
#endif

#ifdef FABRIC
varying float vRowReveal;
varying float vRowT;
#endif

void main() {
  float d = abs(vSide);
  // Core width in pixels stays ~1.4px regardless of halo width.
  float coreFrac = clamp(uCore / max(vWidthPx, 1.0), 0.04, 0.9);
  float core = 1.0 - smoothstep(coreFrac * 0.5, coreFrac, d);
  float halo = exp(-d * d * 5.5) * uHalo;
  float a = core + halo;
  vec3 col = vColor * (1.0 + vBoost);

#ifdef REVEAL
  float rev = uReveal;
  #ifdef STAGGER
  rev = uReveal * (1.0 + 0.6) - vStaggerShift;
  #endif
  float vis = 1.0 - smoothstep(rev - 0.006, rev, vT);
  float head = exp(-pow((vT - rev) / 0.01, 2.0)) * uHead * step(0.002, rev) * step(rev, 0.999);
  a = a * vis + head * (halo + core) * 2.5;
  col += vec3(head * 0.6);
#endif

#ifdef FABRIC
  float vis2 = 1.0 - smoothstep(vRowReveal - 0.015, vRowReveal, vRowT);
  float head2 = exp(-pow((vRowT - vRowReveal) / 0.012, 2.0)) * step(0.0, vRowReveal) * step(vRowReveal, 1.0);
  a = a * vis2 + head2 * (core + halo) * 2.0;
#endif

#ifdef WARP
  // Light pools in the middle of the strings and falls off toward the beams.
  a *= 0.45 + 0.75 * exp(-pow((vT - 0.42) / 0.38, 2.0));
  if (vStatus > 0.5) {
    float period = vStatus > 1.5 ? 90.0 : 46.0;
    float duty = vStatus > 1.5 ? 0.22 : 0.58;
    float m = step(fract(vT * period), duty);
    a *= m;
  }
#endif

  float maskL = (1.0 - smoothstep(0.36, 0.5, vScreenX)) * uMask.x;
  float maskR = smoothstep(0.5, 0.62, vScreenX) * uMask.y;
  a *= 1.0 - 0.8 * max(maskL, maskR);

  if (a * vAlpha < 0.002) discard;
  gl_FragColor = vec4(col, a * vAlpha * uOpacity);
}
`;

export interface RibbonOptions {
  width: number;
  core?: number;
  halo?: number;
  opacity?: number;
  segT: number;
  defines?: Record<string, string | number | boolean>;
  extraUniforms?: Record<string, { value: unknown }>;
}

export function createRibbonMaterial(opts: RibbonOptions): ShaderMaterial {
  const defines: Record<string, string | number | boolean> = {};
  for (const [k, v] of Object.entries(opts.defines ?? {})) if (v) defines[k] = v === true ? '' : v;
  return new ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    defines,
    transparent: true,
    depthWrite: false,
    depthTest: true,
    // Ribbon winding flips with screen-space direction, so both faces must draw.
    side: DoubleSide,
    blending: AdditiveBlending,
    uniforms: {
      uResolution: { value: new Vector2(1, 1) },
      uPixelRatio: { value: 1 },
      uWidth: { value: opts.width },
      uCore: { value: opts.core ?? 1.5 },
      uHalo: { value: opts.halo ?? 0.35 },
      uOpacity: { value: opts.opacity ?? 1 },
      uTime: { value: 0 },
      uSegT: { value: opts.segT },
      uDim: { value: 1 },
      uReveal: { value: 1 },
      uHead: { value: 0 },
      uStagger: { value: 0 },
      uRegion: { value: new Vector4(0, 0, 0, 0) },
      uRegionAmt: { value: 0 },
      uMask: { value: new Vector2(0, 0) },
      uRegionColor: { value: new Color(1, 1, 1) },
      ...(opts.extraUniforms ?? {}),
    },
  });
}

/** Shared uniforms updated once per frame for every ribbon material. */
export function syncFrameUniforms(mats: ShaderMaterial[], w: number, h: number, dpr: number, time: number): void {
  for (const m of mats) {
    (m.uniforms.uResolution.value as Vector2).set(w * dpr, h * dpr);
    m.uniforms.uPixelRatio.value = dpr;
    m.uniforms.uTime.value = time;
  }
}
