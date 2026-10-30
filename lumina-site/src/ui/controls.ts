import { store, events, type Motion, type Visuals } from '../core/store';
import type { AudioEngine } from '../audio/AudioEngine';

const LS = {
  motion: 'lumina.motion',
  visuals: 'lumina.visuals',
  volume: 'lumina.volume',
};

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage unavailable — preferences last for this visit only */
  }
}

/* ───────── Motion & visuals preferences ───────── */

export function initPreferences(): void {
  const html = document.documentElement;
  const sysQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  const resolve = (pref: string | null): Motion => (pref === 'full' || pref === 'reduced' ? pref : sysQuery.matches ? 'reduced' : 'full');

  let motionPref = read(LS.motion);
  const visualsPref: Visuals = read(LS.visuals) === 'lite' ? 'lite' : 'cinematic';
  const vol = Number(read(LS.volume) ?? '0.6');

  store.set({ motion: resolve(motionPref), visuals: visualsPref, volume: Number.isFinite(vol) ? vol : 0.6 });

  const motionRadios = Array.from(document.querySelectorAll<HTMLInputElement>('input[name="motion"]'));
  const visualRadios = Array.from(document.querySelectorAll<HTMLInputElement>('input[name="visuals"]'));
  motionRadios.forEach((r) => (r.checked = r.value === (motionPref ?? 'system')));
  visualRadios.forEach((r) => (r.checked = r.value === visualsPref));

  motionRadios.forEach((r) =>
    r.addEventListener('change', () => {
      if (!r.checked) return;
      motionPref = r.value === 'system' ? null : r.value;
      write(LS.motion, motionPref);
      store.set({ motion: resolve(motionPref) });
    }),
  );
  visualRadios.forEach((r) =>
    r.addEventListener('change', () => {
      if (!r.checked) return;
      const v = r.value as Visuals;
      write(LS.visuals, v === 'lite' ? 'lite' : null);
      store.set({ visuals: v });
    }),
  );
  sysQuery.addEventListener('change', () => {
    if (!motionPref) store.set({ motion: resolve(null) });
  });

  store.subscribe((s, changed) => {
    if (changed.has('motion')) html.dataset.motion = s.motion;
    if (changed.has('visuals')) html.dataset.visuals = s.visuals;
  });
  html.dataset.motion = store.get().motion;
  html.dataset.visuals = store.get().visuals;

  // Settings popover
  const toggle = document.getElementById('settings-toggle') as HTMLButtonElement | null;
  const panel = document.getElementById('settings-panel');
  const close = document.getElementById('settings-close');
  const setOpen = (open: boolean, returnFocus = false) => {
    if (!toggle || !panel) return;
    toggle.setAttribute('aria-expanded', String(open));
    panel.hidden = !open;
    if (open) panel.querySelector<HTMLInputElement>('input:checked')?.focus();
    else if (returnFocus) toggle.focus();
  };
  toggle?.addEventListener('click', () => setOpen(toggle.getAttribute('aria-expanded') !== 'true'));
  close?.addEventListener('click', () => setOpen(false, true));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && panel && !panel.hidden) setOpen(false, true);
  });
  document.addEventListener('pointerdown', (e) => {
    if (!panel || panel.hidden) return;
    const t = e.target as Node;
    if (!panel.contains(t) && !toggle?.contains(t)) setOpen(false);
  });
}

/* ───────── Sound ───────── */

export function initSound(): void {
  const btn = document.getElementById('sound-toggle') as HTMLButtonElement | null;
  const state = btn?.querySelector('.sound-toggle__state');
  const volume = document.getElementById('volume') as HTMLInputElement | null;
  let engine: AudioEngine | null = null;
  let loading: Promise<AudioEngine | null> | null = null;

  if (volume) volume.value = String(Math.round(store.get().volume * 100));

  const ensure = (): Promise<AudioEngine | null> => {
    if (engine) return Promise.resolve(engine);
    loading ??= import('../audio/AudioEngine')
      .then(({ AudioEngine }) => {
        engine = new AudioEngine();
        engine.setChapter(store.get().chapter, true);
        return engine;
      })
      .catch(() => {
        if (btn) {
          btn.disabled = true;
          btn.title = 'Sound is unavailable in this browser';
        }
        return null;
      });
    return loading;
  };

  btn?.addEventListener('click', async () => {
    const on = !store.get().sound;
    if (on) {
      // Audio starts only from this explicit gesture.
      const e = await ensure();
      if (!e) return;
      await e.enable(store.get().volume);
    } else engine?.disable();
    store.set({ sound: on });
  });

  volume?.addEventListener('input', () => {
    const v = Number(volume.value) / 100;
    store.set({ volume: v });
    write(LS.volume, String(v));
    engine?.setVolume(v);
  });

  store.subscribe((s, changed) => {
    if (changed.has('sound') && btn) {
      btn.setAttribute('aria-pressed', String(s.sound));
      btn.title = s.sound ? 'Sound is on' : 'Sound is off';
      if (state) state.textContent = s.sound ? 'on' : 'off';
    }
    if (changed.has('chapter')) engine?.setChapter(s.chapter);
  });

  events.on('pluck', ({ group, strength }) => engine?.pluck(group, strength));
  events.on('cue', ({ kind }) => engine?.cue(kind));
}
