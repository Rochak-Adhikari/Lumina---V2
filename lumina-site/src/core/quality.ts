/**
 * Picks a starting quality tier from what the device tells us. The world then
 * adapts downward at runtime if frame times stay high.
 */

export type Tier = 'high' | 'medium' | 'low';

export interface Quality {
  tier: Tier;
  /** Maximum device pixel ratio to render at. */
  maxDpr: number;
  /** Warp threads per capability group. */
  warpPerGroup: number;
  motes: number;
  /** Points along each fabric row. */
  rowPoints: number;
  /** Idle shimmer frame interval in ms (0 = no idle rendering). */
  idleInterval: number;
}

export const TIERS: Record<Tier, Quality> = {
  high: { tier: 'high', maxDpr: 1.75, warpPerGroup: 3, motes: 420, rowPoints: 200, idleInterval: 1000 / 45 },
  medium: { tier: 'medium', maxDpr: 1.25, warpPerGroup: 3, motes: 240, rowPoints: 150, idleInterval: 1000 / 30 },
  low: { tier: 'low', maxDpr: 1, warpPerGroup: 2, motes: 110, rowPoints: 96, idleInterval: 1000 / 20 },
};

export interface GpuInfo {
  renderer: string;
  software: boolean;
}

export function readGpu(gl: WebGLRenderingContext | WebGL2RenderingContext): GpuInfo {
  let renderer = '';
  try {
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    renderer = ext ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : String(gl.getParameter(gl.RENDERER));
  } catch {
    renderer = '';
  }
  const software = /swiftshader|llvmpipe|software|basic render/i.test(renderer);
  return { renderer, software };
}

export function pickTier(gpu: GpuInfo): Tier {
  const nav = navigator as Navigator & { deviceMemory?: number };
  const mem = nav.deviceMemory ?? 8;
  const cores = nav.hardwareConcurrency ?? 4;
  const coarse = window.matchMedia('(pointer: coarse)').matches;
  const small = Math.min(window.innerWidth, window.innerHeight) < 600;
  if (gpu.software || mem <= 2 || (coarse && small)) return 'low';
  if (/intel|uhd|iris|hd graphics|mali|adreno|powervr|videocore/i.test(gpu.renderer) || mem <= 4 || cores <= 4 || coarse)
    return 'medium';
  return 'high';
}

export function lower(t: Tier): Tier {
  return t === 'high' ? 'medium' : 'low';
}
