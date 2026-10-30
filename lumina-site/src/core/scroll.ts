import { CHAPTER_COUNT, store } from './store';
import { clamp } from './sequence';

/**
 * The only scroll listener on the page. It maps document scroll position to
 * (a) a continuous camera timeline `t` in keyframe space and
 * (b) per-chapter local progress, then writes both to the store.
 *
 * The mapping is a pure function of scroll position, so reversing direction
 * or jumping via navigation always lands on the same state.
 */

/** Camera keyframe anchors, expressed as (chapter, local progress at which the keyframe is fully reached). */
export const ANCHORS: { chapter: number; at: number }[] = [
  { chapter: 0, at: 0 },
  { chapter: 1, at: 0.5 },
  { chapter: 2, at: 0.5 },
  { chapter: 3, at: 0.12 },
  { chapter: 3, at: 0.5 },
  { chapter: 3, at: 0.88 },
  { chapter: 4, at: 0.5 },
  { chapter: 5, at: 0.5 },
  { chapter: 6, at: 1 },
];

interface SectionGeom {
  top: number;
  height: number;
  sticky: boolean;
}

let sections: HTMLElement[] = [];
let geoms: SectionGeom[] = [];
let anchorY: number[] = [];
let maxScroll = 0;
let frame = 0;

function measure(): void {
  const vh = window.innerHeight;
  // Pinning only works if the content fits; otherwise let the chapter scroll normally.
  const headerH = document.getElementById('site-header')?.offsetHeight ?? 64;
  for (const el of sections) {
    if (!el.classList.contains('chapter--sticky')) continue;
    const inner = el.querySelector<HTMLElement>('.chapter__inner');
    if (!inner) continue;
    const tooTall = inner.offsetHeight > vh - headerH - 48;
    if (el.classList.contains('is-unpinned') !== tooTall) el.classList.toggle('is-unpinned', tooTall);
  }
  const scrollY = window.scrollY;
  maxScroll = Math.max(0, document.documentElement.scrollHeight - vh);
  geoms = sections.map((el) => {
    const r = el.getBoundingClientRect();
    const sticky = el.classList.contains('chapter--sticky') && getComputedStyle(el.querySelector('.sticky') as Element).position === 'sticky';
    return { top: r.top + scrollY, height: r.height, sticky };
  });
  anchorY = ANCHORS.map(({ chapter, at }) => {
    const g = geoms[chapter];
    if (!g) return 0;
    if (chapter === CHAPTER_COUNT - 1 && at >= 1) return Math.min(g.top, maxScroll);
    return clamp(localToScroll(g, at, vh), 0, maxScroll);
  });
  // Keep anchors strictly increasing so the timeline stays monotonic on any layout.
  for (let i = 1; i < anchorY.length; i++) {
    if (anchorY[i] <= anchorY[i - 1]) anchorY[i] = anchorY[i - 1] + 1;
  }
  store.set({ vw: window.innerWidth, vh, compact: window.innerWidth <= 900 });
}

/** Local progress of a section: pinned progress for sticky sections, pass-through progress otherwise. */
function localProgress(g: SectionGeom, scrollY: number, vh: number): number {
  if (g.sticky && g.height > vh) return clamp((scrollY - g.top) / (g.height - vh));
  // 0 when the section's top meets the viewport bottom, 1 when its bottom meets the viewport top.
  return clamp((scrollY - (g.top - vh)) / (g.height + vh));
}

function localToScroll(g: SectionGeom, p: number, vh: number): number {
  if (g.sticky && g.height > vh) return g.top + p * (g.height - vh);
  return g.top - vh + p * (g.height + vh);
}

function update(): void {
  frame = 0;
  const vh = window.innerHeight;
  const y = clamp(window.scrollY, 0, maxScroll);

  // Timeline: piecewise-linear over anchor positions.
  let t = 0;
  if (y <= anchorY[0]) t = 0;
  else if (y >= anchorY[anchorY.length - 1]) t = anchorY.length - 1;
  else {
    for (let i = 1; i < anchorY.length; i++) {
      if (y <= anchorY[i]) {
        t = i - 1 + (y - anchorY[i - 1]) / (anchorY[i] - anchorY[i - 1]);
        break;
      }
    }
  }

  const local = geoms.map((g) => localProgress(g, y, vh));
  const mid = y + vh * 0.5;
  let chapter = 0;
  for (let i = 0; i < geoms.length; i++) if (mid >= geoms[i].top) chapter = i;

  store.set({ t, local, chapter });
}

function schedule(): void {
  if (!frame) frame = requestAnimationFrame(update);
}

export function initScroll(): () => void {
  sections = Array.from(document.querySelectorAll<HTMLElement>('[data-chapter]')).sort(
    (a, b) => Number(a.dataset.chapter) - Number(b.dataset.chapter),
  );
  const onResize = () => {
    measure();
    schedule();
  };
  measure();
  update();
  window.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('resize', onResize);
  // Layout can change after fonts load or content re-renders (demo, capabilities).
  const ro = new ResizeObserver(onResize);
  ro.observe(document.body);
  // Pinned chapters have fixed heights, so watch their content directly (fonts, expanded records).
  sections.forEach((s) => {
    const inner = s.querySelector('.chapter__inner');
    if (inner) ro.observe(inner);
  });
  void document.fonts?.ready.then(onResize);
  return () => {
    window.removeEventListener('scroll', schedule);
    window.removeEventListener('resize', onResize);
    ro.disconnect();
    if (frame) cancelAnimationFrame(frame);
  };
}

/** Scroll position at which the Action chapter is fully settled on a given local progress (used by tests/tools). */
export function scrollForChapter(chapter: number, p: number): number {
  const g = geoms[chapter];
  if (!g) return 0;
  return clamp(localToScroll(g, p, window.innerHeight), 0, maxScroll);
}
