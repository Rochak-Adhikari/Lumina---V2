import { Vector3 } from 'three';
import { clamp, lerp, smooth } from '../core/sequence';

/**
 * One table drives the whole journey: camera pose and every world parameter
 * are interpolated from the same timeline `t`, so scrolling backwards simply
 * plays the table in reverse. Keyframe order matches ANCHORS in core/scroll.ts.
 */

export interface Key {
  pos: [number, number, number];
  look: [number, number, number];
  /** Where the subject sits — used to re-centre the shot on narrow screens. */
  subject: [number, number, number];
  rows: number;
  dim: number;
  intent: number;
  intentAlpha: number;
  wave: number;
  exec: number;
  knots: number;
  warpGlow: number;
  warm: number;
  shimmer: number;
  /** Legibility mask behind the text column: left / right. */
  maskL: number;
  maskR: number;
  /** Fabric visibility (fades where the cloth would sit behind dense text). */
  cloth: number;
}

const BASE: Omit<Key, 'pos' | 'look' | 'subject'> = {
  rows: 5,
  dim: 1,
  intent: 0.6,
  intentAlpha: 1,
  wave: 1,
  exec: 0,
  knots: 0.2,
  warpGlow: 0,
  warm: 0.35,
  shimmer: 1,
  maskL: 0,
  maskR: 0,
  cloth: 1,
};

export const KEYS: Key[] = [
  // 0 · Arrival — the loom on the right, the amber voice thread crossing beneath the headline.
  { ...BASE, pos: [4.6, 0.9, 11.6], look: [-3.0, -0.4, 0], subject: [1.2, 0, 0] },
  // 1 · Intent — three-quarter view so the weave has depth; the thread reaches through.
  {
    ...BASE,
    pos: [5.0, 0.9, 7.9],
    look: [-2.9, 0.1, 0],
    subject: [-1.2, 0.2, 0],
    rows: 8,
    intent: 1,
    wave: 0.7,
    knots: 0.35,
    warm: 0.55,
    maskL: 0.55,
  },
  // 2 · Memory — low angle across the fabric; knots catch the light. Text sits on the right.
  {
    ...BASE,
    pos: [-4.4, -4.4, 6.4],
    look: [-0.2, -1.6, 0],
    subject: [-0.6, -1.6, 0],
    rows: 20,
    intent: 1,
    intentAlpha: 0.4,
    wave: 0.25,
    knots: 1,
    warm: 0.8,
    maskR: 0.7,
  },
  // 3a · Action begins — the first heddles.
  {
    ...BASE,
    pos: [-5.2, 1.9, 8.6],
    look: [-6.7, 0.9, 2.2],
    subject: [-4.6, 0.9, 2.4],
    rows: 21,
    dim: 0.7,
    intent: 1,
    intentAlpha: 0.12,
    wave: 0,
    exec: 1,
    knots: 0.45,
    warm: 0.5,
    maskL: 0.75,
  },
  // 3b · Approval — the amber heddle.
  {
    ...BASE,
    pos: [1.0, 1.8, 8.6],
    look: [-1.1, 0.7, 2.6],
    subject: [1.1, 0.7, 2.9],
    rows: 21,
    dim: 0.7,
    intent: 1,
    intentAlpha: 0.12,
    wave: 0,
    exec: 1,
    knots: 0.45,
    warm: 0.6,
    maskL: 0.75,
  },
  // 3c · Verify — the thread leaves the last heddle.
  {
    ...BASE,
    pos: [7.0, 1.6, 8.4],
    look: [3.9, 0.5, 2.2],
    subject: [5.4, 0.5, 2.3],
    rows: 21,
    dim: 0.7,
    intent: 1,
    intentAlpha: 0.12,
    wave: 0,
    exec: 1,
    knots: 0.45,
    warm: 0.4,
    maskL: 0.75,
  },
  // 4 · Capabilities — the strings, frontal, like an instrument.
  {
    ...BASE,
    pos: [0, 0.3, 13.2],
    look: [0, 0.3, 0],
    subject: [0, 0.3, 0],
    rows: 22,
    intent: 1,
    intentAlpha: 0.15,
    wave: 0,
    exec: 0,
    knots: 0.2,
    warpGlow: 1,
    warm: 0.2,
    cloth: 0.22,
  },
  // 5 · Demo — the world steps back and dims so the console can lead.
  {
    ...BASE,
    pos: [0.6, -8.0, 9.0],
    look: [0, -1.4, -1.0],
    subject: [0, -1.4, -1.0],
    rows: 24,
    dim: 0.32,
    intent: 1,
    intentAlpha: 0.2,
    wave: 0,
    exec: 0,
    knots: 0.4,
    warm: 0.3,
    shimmer: 0.6,
  },
  // 6 · Explore — the finished tapestry, framed right of the controls.
  {
    ...BASE,
    pos: [-1.6, -0.1, 11.6],
    look: [-2.9, -0.2, 0],
    subject: [0, -0.2, 0],
    rows: 26,
    intent: 1,
    intentAlpha: 0.7,
    wave: 0.18,
    knots: 1,
    warm: 0.5,
    maskL: 0.5,
  },
];

const NUM_KEYS: (keyof Omit<Key, 'pos' | 'look' | 'subject'>)[] = [
  'rows',
  'dim',
  'intent',
  'intentAlpha',
  'wave',
  'exec',
  'knots',
  'warpGlow',
  'warm',
  'shimmer',
  'maskL',
  'maskR',
  'cloth',
];

export interface Pose {
  pos: Vector3;
  look: Vector3;
  params: Omit<Key, 'pos' | 'look' | 'subject'>;
}

function catmull(p0: number, p1: number, p2: number, p3: number, t: number): number {
  const t2 = t * t;
  const t3 = t2 * t;
  return 0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3);
}

/**
 * On narrow or portrait screens the text stacks on top of the world, so the shot is
 * re-centred on the subject and pulled back to keep the loom in frame.
 */
function frame(k: Key, aspect: number, compact: boolean): { pos: number[]; look: number[] } {
  if (!compact && aspect >= 1.15) return { pos: k.pos, look: k.look };
  const off = [k.pos[0] - k.look[0], k.pos[1] - k.look[1], k.pos[2] - k.look[2]];
  const look = k.subject;
  // Let the loom crop at the sides on phones: closer and more frontal reads better than a tiny object.
  const pull = clamp(0.62 / Math.max(aspect, 0.4), 1.0, 1.4);
  return { pos: [look[0] + off[0] * 0.45, look[1] + off[1] * pull, look[2] + off[2] * pull], look };
}

export function poseAt(t: number, aspect: number, compact: boolean, out: Pose): Pose {
  const n = KEYS.length;
  const tc = clamp(t, 0, n - 1);
  const i = Math.min(n - 2, Math.floor(tc));
  const f = tc - i;
  const e = lerp(f, smooth(f), 0.75);
  const k0 = frame(KEYS[Math.max(0, i - 1)], aspect, compact);
  const k1 = frame(KEYS[i], aspect, compact);
  const k2 = frame(KEYS[i + 1], aspect, compact);
  const k3 = frame(KEYS[Math.min(n - 1, i + 2)], aspect, compact);
  out.pos.set(
    catmull(k0.pos[0], k1.pos[0], k2.pos[0], k3.pos[0], e),
    catmull(k0.pos[1], k1.pos[1], k2.pos[1], k3.pos[1], e),
    catmull(k0.pos[2], k1.pos[2], k2.pos[2], k3.pos[2], e),
  );
  out.look.set(
    catmull(k0.look[0], k1.look[0], k2.look[0], k3.look[0], e),
    catmull(k0.look[1], k1.look[1], k2.look[1], k3.look[1], e),
    catmull(k0.look[2], k1.look[2], k2.look[2], k3.look[2], e),
  );
  for (const key of NUM_KEYS) out.params[key] = lerp(KEYS[i][key], KEYS[i + 1][key], e);
  return out;
}

export function makePose(): Pose {
  return { pos: new Vector3(), look: new Vector3(), params: { ...BASE } };
}
