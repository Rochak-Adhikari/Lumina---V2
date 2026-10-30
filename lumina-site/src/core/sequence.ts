/**
 * Pure math shared by the HTML step list and the 3D heddles, so both always agree.
 */

export const clamp = (v: number, lo = 0, hi = 1): number => (v < lo ? lo : v > hi ? hi : v);
export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;
export const smooth = (t: number): number => {
  const x = clamp(t);
  return x * x * (3 - 2 * x);
};
export const smoother = (t: number): number => {
  const x = clamp(t);
  return x * x * x * (x * (x * 6 - 15) + 10);
};

/** Index of the approval heddle in the six-step loop. */
export const APPROVE_STEP = 3;
export const STEP_COUNT = 6;

/**
 * Pinned progress (0…1) of the Action chapter → thread progress through the six steps (0…6).
 * The thread pauses at the approval step before continuing.
 */
const STOPS: [number, number][] = [
  [0.0, 0.0],
  [0.06, 0.0],
  [0.16, 1.0],
  [0.27, 2.0],
  [0.38, 3.0],
  [0.48, 4.0], // arrives at Approve (step index 3 → value 4 means step 3 reached fully)
  [0.6, 4.0], // waits for the person
  [0.72, 5.0],
  [0.86, 6.0],
  [1.0, 6.0],
];

export function loopProgress(p: number): number {
  const x = clamp(p);
  for (let i = 1; i < STOPS.length; i++) {
    const [p1, v1] = STOPS[i];
    const [p0, v0] = STOPS[i - 1];
    if (x <= p1) {
      const f = p1 === p0 ? 1 : (x - p0) / (p1 - p0);
      return lerp(v0, v1, smooth(f));
    }
  }
  return STOPS[STOPS.length - 1][1];
}

export interface LoopView {
  /** Steps whose heddle the thread has passed through. */
  reached: number;
  /** Step that is currently active (−1 before start). */
  active: number;
  /** Whether the approval step has been granted in this scroll position. */
  approved: boolean;
  /** 0…1 fill for the progress line. */
  fill: number;
}

export function loopView(p: number): LoopView {
  const v = loopProgress(p);
  const reached = Math.floor(v + 1e-3);
  const active = v <= 0.02 ? -1 : Math.min(STEP_COUNT - 1, Math.max(0, Math.ceil(v - 1e-3) - 1));
  return {
    reached,
    active,
    approved: clamp(p) >= 0.6,
    fill: v / STEP_COUNT,
  };
}
