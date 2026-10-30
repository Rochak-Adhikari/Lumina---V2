import '@fontsource/instrument-serif/latin-400.css';
import '@fontsource/instrument-serif/latin-400-italic.css';
import '@fontsource-variable/geist/wght.css';
import '@fontsource-variable/geist-mono/wght.css';
import './styles/tokens.css';
import './styles/base.css';
import './styles/layout.css';
import './styles/sections.css';
import './styles/demo.css';

import { store } from './core/store';
import { initScroll, scrollForChapter } from './core/scroll';
import { initPreferences, initSound } from './ui/controls';
import { initCapabilities, initExplore, initLoopSteps, initMemoryLedger, initNav } from './ui/chapters';
import { initDemo } from './demo/ui';
import type { World } from './world/World';

/*
 * Boot order (progressive):
 *  1. HTML + CSS shell is already on screen.
 *  2. Wire state, scroll and every DOM interaction — the site is fully usable now.
 *  3. After first paint, load the 3D engine if the device can run it.
 *  4. Sound loads only when the visitor turns it on.
 */

initPreferences();
initNav();
initLoopSteps();
initMemoryLedger();
initCapabilities();
initExplore();
const demoRoot = document.getElementById('demo-root');
if (demoRoot) initDemo(demoRoot);
initSound();
initScroll();

/* ───────── 3D world lifecycle ───────── */

const worldEl = document.querySelector<HTMLElement>('.world');
let canvas = document.getElementById('world-canvas') as HTMLCanvasElement | null;
const statusEl = document.getElementById('world-status');
let world: World | null = null;
let booting = false;

function setStatus(text: string): void {
  if (statusEl) statusEl.textContent = text;
}

function webglAvailable(): boolean {
  try {
    const c = document.createElement('canvas');
    const gl = c.getContext('webgl2') ?? c.getContext('webgl');
    const ok = !!gl;
    (gl as WebGLRenderingContext | null)?.getExtension('WEBGL_lose_context')?.loseContext();
    return ok;
  } catch {
    return false;
  }
}

function fail(reason: string): void {
  const had = !!world;
  world?.dispose();
  world = null;
  if (had) freshCanvas();
  worldEl?.classList.remove('is-ready');
  worldEl?.classList.add('is-failed');
  document.documentElement.classList.add('world-failed');
  store.set({ world: 'failed' });
  setStatus(`${reason} Showing the lite version — every section still works.`);
}

async function bootWorld(): Promise<void> {
  if (world || booting || !canvas || store.get().visuals !== 'cinematic') return;
  if (!webglAvailable()) {
    fail('This browser or device cannot run WebGL.');
    return;
  }
  booting = true;
  store.set({ world: 'loading' });
  setStatus('Loading the 3D view…');
  const t0 = performance.now();
  try {
    const { World } = await import('./world/World');
    if (store.get().visuals !== 'cinematic') return;
    setStatus('Building the loom…');
    world = new World(canvas, fail);
    world.onStruggle = offerLite;
    world.start();
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        if (!world) return;
        worldEl?.classList.add('is-ready');
        store.set({ world: 'ready' });
        const ms = Math.round(performance.now() - t0);
        setStatus(`3D view ready (${world.stats.tier} quality, ${ms} ms).`);
        perf.worldReadyMs = Math.round(performance.now());
      }),
    );
  } catch (err) {
    console.error(err);
    fail('The 3D view could not start.');
  } finally {
    booting = false;
  }
}

/** A disposed renderer force-loses its context, which cannot be reacquired; swap in a fresh canvas. */
function freshCanvas(): void {
  if (!canvas) return;
  const next = canvas.cloneNode(false) as HTMLCanvasElement;
  canvas.replaceWith(next);
  canvas = next;
}

function stopWorld(): void {
  const had = !!world;
  world?.dispose();
  world = null;
  if (had) freshCanvas();
  worldEl?.classList.remove('is-ready', 'is-failed');
  store.set({ world: 'off' });
  setStatus('3D view is off (lite mode).');
}

store.subscribe((s, changed) => {
  if (!changed.has('visuals')) return;
  if (s.visuals === 'lite') stopWorld();
  else {
    document.documentElement.classList.remove('world-failed');
    worldEl?.classList.remove('is-failed');
    void bootWorld();
  }
});

// Load the world after the first paint so text and navigation never wait on WebGL.
const perf: Record<string, number> = {};
if (store.get().visuals === 'cinematic') {
  const kick = () => void bootWorld();
  if (document.readyState === 'complete') requestAnimationFrame(() => setTimeout(kick, 0));
  else window.addEventListener('load', () => requestAnimationFrame(() => setTimeout(kick, 0)), { once: true });
} else {
  store.set({ world: 'off' });
  setStatus('3D view is off (lite mode).');
}

/** Shown at most once per visit, never forced. */
function offerLite(): void {
  const el = document.getElementById('perf-notice');
  if (!el || sessionStorage.getItem('lumina.perfNoticeShown')) return;
  sessionStorage.setItem('lumina.perfNoticeShown', '1');
  el.hidden = false;
  el.querySelector<HTMLButtonElement>('[data-act="lite"]')?.addEventListener('click', () => {
    el.hidden = true;
    try {
      localStorage.setItem('lumina.visuals', 'lite');
    } catch {
      /* preference lasts for this visit only */
    }
    document.querySelectorAll<HTMLInputElement>('input[name="visuals"]').forEach((r) => (r.checked = r.value === 'lite'));
    store.set({ visuals: 'lite' });
  });
  el.querySelector<HTMLButtonElement>('[data-act="dismiss"]')?.addEventListener('click', () => (el.hidden = true));
}

/* ───────── Fallback art (also used in lite mode) ───────── */

const warpGroup = document.querySelector('.weave-fallback__warp');
if (warpGroup) {
  const ns = 'http://www.w3.org/2000/svg';
  for (let i = 0; i < 40; i++) {
    const x = 560 + i * 15 + (i % 3) * 2;
    const line = document.createElementNS(ns, 'line');
    line.setAttribute('x1', String(x));
    line.setAttribute('x2', String(x));
    line.setAttribute('y1', '90');
    line.setAttribute('y2', '710');
    line.setAttribute('opacity', String(0.4 + ((i * 37) % 10) / 20));
    warpGroup.append(line);
  }
}

/* ───────── Diagnostics for testing (read-only) ───────── */

declare global {
  interface Window {
    __lumina?: unknown;
  }
}
window.__lumina = {
  store,
  scrollForChapter,
  perf,
  get world() {
    return world?.stats ?? null;
  },
};
if (import.meta.env.DEV) Object.defineProperty(window.__lumina, 'worldInstance', { get: () => world });
