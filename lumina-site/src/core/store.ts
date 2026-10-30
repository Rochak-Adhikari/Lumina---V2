/**
 * Single authoritative source of shared site state.
 * Scroll, UI controls and the demo write here; the 3D world and DOM views read from here.
 * Nothing else keeps its own copy of scroll progress or interaction state.
 */

export type Motion = 'full' | 'reduced';
export type Visuals = 'cinematic' | 'lite';
export type WorldStatus = 'idle' | 'loading' | 'ready' | 'failed' | 'off';
export type DemoPhase = 'idle' | 'running' | 'waiting' | 'done' | 'failed' | 'denied';

export const CHAPTER_COUNT = 7;

export interface SiteState {
  /** Continuous camera timeline in keyframe space (0 … keyframes-1). */
  t: number;
  /** Chapter under the viewport centre. */
  chapter: number;
  /** Per-chapter local progress, 0…1. Pinned chapters report pinned progress. */
  local: number[];
  vw: number;
  vh: number;
  /** Narrow layout (phones, small tablets). */
  compact: boolean;
  motion: Motion;
  visuals: Visuals;
  world: WorldStatus;
  sound: boolean;
  volume: number;
  capHover: number;
  capSelected: number;
  memoryHover: number;
  forgotten: boolean[];
  exploreFocus: string | null;
  /** Bumped when the user asks to reset the exploration camera. */
  exploreReset: number;
  demoPhase: DemoPhase;
  /** 0…1 progress of the current demo run. */
  demoProgress: number;
}

type Listener = (state: Readonly<SiteState>, changed: ReadonlySet<keyof SiteState>) => void;

const initial: SiteState = {
  t: 0,
  chapter: 0,
  local: new Array(CHAPTER_COUNT).fill(0),
  vw: typeof window !== 'undefined' ? window.innerWidth : 1280,
  vh: typeof window !== 'undefined' ? window.innerHeight : 800,
  compact: false,
  motion: 'full',
  visuals: 'cinematic',
  world: 'idle',
  sound: false,
  volume: 0.6,
  capHover: -1,
  capSelected: -1,
  memoryHover: -1,
  forgotten: [false, false, false, false],
  exploreFocus: null,
  exploreReset: 0,
  demoPhase: 'idle',
  demoProgress: 0,
};

let state: SiteState = { ...initial };
const listeners = new Set<Listener>();

export const store = {
  get(): Readonly<SiteState> {
    return state;
  },

  set(patch: Partial<SiteState>): void {
    const changed = new Set<keyof SiteState>();
    for (const key of Object.keys(patch) as (keyof SiteState)[]) {
      const next = patch[key];
      const prev = state[key];
      if (Array.isArray(next) && Array.isArray(prev)) {
        if (next.length !== prev.length || next.some((v, i) => v !== prev[i])) changed.add(key);
      } else if (next !== prev) {
        changed.add(key);
      }
    }
    if (changed.size === 0) return;
    state = { ...state, ...patch };
    for (const fn of listeners) fn(state, changed);
  },

  subscribe(fn: Listener): () => void {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
};

/* ───────── Transient events (not state): plucks, cues ───────── */

export interface SiteEvents {
  pluck: { group: number; strength: number };
  cue: { kind: 'chapter' | 'approve' | 'success' | 'fail' | 'tick' | 'forget' | 'focus' };
}

type EventHandler<K extends keyof SiteEvents> = (payload: SiteEvents[K]) => void;
const handlers = new Map<keyof SiteEvents, Set<(payload: never) => void>>();

export const events = {
  on<K extends keyof SiteEvents>(name: K, fn: EventHandler<K>): () => void {
    let set = handlers.get(name);
    if (!set) handlers.set(name, (set = new Set()));
    const h = fn as (payload: never) => void;
    set.add(h);
    return () => set.delete(h);
  },
  emit<K extends keyof SiteEvents>(name: K, payload: SiteEvents[K]): void {
    handlers.get(name)?.forEach((fn) => (fn as EventHandler<K>)(payload));
  },
};
