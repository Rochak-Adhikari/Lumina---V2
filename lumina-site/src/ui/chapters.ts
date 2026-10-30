import { store, events } from '../core/store';
import { loopView, APPROVE_STEP } from '../core/sequence';
import { CAPABILITIES, MEMORIES, DESTINATIONS, STATUS_LABEL, type Status } from '../content/content';

/* ───────── Header, menu, chapter rail ───────── */

export function initNav(): void {
  const header = document.getElementById('site-header');
  const toggle = document.querySelector<HTMLButtonElement>('.primary-nav__toggle');
  const list = document.getElementById('primary-nav-list');
  const railLinks = Array.from(document.querySelectorAll<HTMLAnchorElement>('.chapter-rail a'));
  const navLinks = Array.from(document.querySelectorAll<HTMLAnchorElement>('.primary-nav__list a'));

  const closeMenu = () => {
    toggle?.setAttribute('aria-expanded', 'false');
    list?.classList.remove('is-open');
  };
  toggle?.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(open));
    list?.classList.toggle('is-open', open);
  });
  list?.addEventListener('click', (e) => {
    if ((e.target as HTMLElement).closest('a')) closeMenu();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && toggle?.getAttribute('aria-expanded') === 'true') {
      closeMenu();
      toggle.focus();
    }
  });

  let lastChapter = -1;
  let scrolled: boolean | null = null;
  store.subscribe((s, changed) => {
    if (changed.has('t') || changed.has('chapter')) {
      const now = window.scrollY > 24;
      if (now !== scrolled) header?.classList.toggle('is-scrolled', (scrolled = now));
    }
    if (!changed.has('chapter')) return;
    railLinks.forEach((a) => {
      const i = Number(a.dataset.rail);
      if (i === s.chapter) a.setAttribute('aria-current', 'step');
      else a.removeAttribute('aria-current');
      a.classList.toggle('is-past', i < s.chapter);
    });
    const id = document.querySelector<HTMLElement>(`[data-chapter="${s.chapter}"]`)?.id;
    navLinks.forEach((a) => {
      if (a.getAttribute('href') === `#${id}`) a.setAttribute('aria-current', 'true');
      else a.removeAttribute('aria-current');
    });
    if (lastChapter !== -1 && s.chapter !== lastChapter) events.emit('cue', { kind: 'chapter' });
    lastChapter = s.chapter;
  });
  header?.classList.toggle('is-scrolled', window.scrollY > 24);
}

/* ───────── 03 Action: HTML step list mirrors the 3D heddles ───────── */

export function initLoopSteps(): void {
  const list = document.getElementById('loop-steps');
  if (!list) return;
  const steps = Array.from(list.querySelectorAll<HTMLElement>('.loop__step'));
  const badge = document.getElementById('approve-badge');
  list.setAttribute('data-sequenced', '');
  let lastApproved: boolean | null = null;
  let lastKey = '';

  const render = (p: number) => {
    const v = loopView(p);
    // Scroll updates arrive every frame; touch the DOM only when what it shows changes.
    const key = `${v.reached}|${v.active}|${v.approved}|${v.fill.toFixed(3)}`;
    if (key === lastKey) return;
    lastKey = key;
    steps.forEach((el, i) => {
      el.classList.toggle('is-past', i < v.reached && i !== v.active);
      el.classList.toggle('is-active', i === v.active);
      if (i === APPROVE_STEP) el.classList.toggle('is-approved', v.approved);
    });
    list.style.setProperty('--loop-progress', v.fill.toFixed(4));
    if (badge) badge.textContent = v.approved ? 'Approved by you' : 'Waiting for you';
    if (lastApproved === false && v.approved) events.emit('cue', { kind: 'approve' });
    lastApproved = v.approved;
  };
  store.subscribe((s, changed) => {
    if (changed.has('local')) render(s.local[3] ?? 0);
  });
  render(store.get().local[3] ?? 0);
}

/* ───────── 02 Memory inspector ───────── */

export function initMemoryLedger(): void {
  const list = document.getElementById('memory-list');
  const restore = document.getElementById('memory-restore') as HTMLButtonElement | null;
  if (!list) return;

  list.innerHTML = '';
  MEMORIES.forEach((m, i) => {
    const li = document.createElement('li');
    li.className = 'memory';
    li.dataset.index = String(i);
    const detailsId = `memory-details-${i}`;
    li.innerHTML = `
      <div class="memory__row">
        <span class="memory__knot" aria-hidden="true"></span>
        <div class="memory__body">
          <p class="memory__text"></p>
          <p class="memory__meta"></p>
        </div>
        <div class="memory__actions">
          <button class="mini-btn" type="button" data-act="inspect" aria-expanded="false" aria-controls="${detailsId}">Inspect</button>
          <button class="mini-btn mini-btn--warn" type="button" data-act="forget">Forget</button>
        </div>
      </div>
      <dl class="memory__details" id="${detailsId}" hidden></dl>`;
    (li.querySelector('.memory__text') as HTMLElement).textContent = m.text;
    (li.querySelector('.memory__meta') as HTMLElement).textContent = `${m.source} · ${m.recorded}`;
    const dl = li.querySelector('dl') as HTMLElement;
    const rows: [string, string][] = [
      ['Source', m.source],
      ['Recorded', m.recorded],
      ['Confidence', m.confidence],
      ['Scope', m.scope],
    ];
    if (m.history) rows.push(['History', m.history]);
    for (const [k, v] of rows) {
      const dt = document.createElement('dt');
      dt.textContent = k;
      const dd = document.createElement('dd');
      dd.textContent = v;
      dl.append(dt, dd);
    }
    list.append(li);
  });

  const items = Array.from(list.querySelectorAll<HTMLElement>('.memory'));
  const setHover = (i: number) => store.set({ memoryHover: i });

  list.addEventListener('pointerover', (e) => {
    const li = (e.target as HTMLElement).closest<HTMLElement>('.memory');
    if (li) setHover(Number(li.dataset.index));
  });
  list.addEventListener('pointerleave', () => setHover(-1));
  list.addEventListener('focusin', (e) => {
    const li = (e.target as HTMLElement).closest<HTMLElement>('.memory');
    if (li) setHover(Number(li.dataset.index));
  });
  list.addEventListener('focusout', (e) => {
    if (!list.contains(e.relatedTarget as Node)) setHover(-1);
  });

  list.addEventListener('click', (e) => {
    const btn = (e.target as HTMLElement).closest<HTMLButtonElement>('button[data-act]');
    if (!btn) return;
    const li = btn.closest<HTMLElement>('.memory');
    if (!li) return;
    const i = Number(li.dataset.index);
    if (btn.dataset.act === 'inspect') {
      const dl = li.querySelector('dl') as HTMLElement;
      const open = btn.getAttribute('aria-expanded') !== 'true';
      // One record open at a time keeps the pinned chapter within the viewport.
      items.forEach((other) => {
        if (other === li) return;
        other.querySelector('[data-act="inspect"]')?.setAttribute('aria-expanded', 'false');
        (other.querySelector('dl') as HTMLElement).hidden = true;
      });
      btn.setAttribute('aria-expanded', String(open));
      dl.hidden = !open;
      events.emit('pluck', { group: 6, strength: 0.4 });
    } else {
      const forgotten = store.get().forgotten.slice();
      forgotten[i] = !forgotten[i];
      store.set({ forgotten });
      if (forgotten[i]) events.emit('cue', { kind: 'forget' });
    }
  });

  store.subscribe((s, changed) => {
    if (changed.has('memoryHover')) items.forEach((li, i) => li.classList.toggle('is-hot', i === s.memoryHover));
    if (changed.has('forgotten')) {
      items.forEach((li, i) => {
        const f = s.forgotten[i];
        li.classList.toggle('is-forgotten', f);
        const btn = li.querySelector<HTMLButtonElement>('[data-act="forget"]');
        if (btn) {
          btn.textContent = f ? 'Undo' : 'Forget';
          btn.setAttribute('aria-label', f ? `Undo forgetting: ${MEMORIES[i].text}` : `Forget: ${MEMORIES[i].text}`);
        }
        const meta = li.querySelector('.memory__meta');
        if (meta) meta.textContent = f ? 'Forgotten — removed from recall in this example' : `${MEMORIES[i].source} · ${MEMORIES[i].recorded}`;
      });
      if (restore) restore.hidden = !s.forgotten.some(Boolean);
    }
  });
  items.forEach((li, i) => {
    li.querySelector<HTMLButtonElement>('[data-act="forget"]')?.setAttribute('aria-label', `Forget: ${MEMORIES[i].text}`);
    li.querySelector<HTMLButtonElement>('[data-act="inspect"]')?.setAttribute('aria-label', `Inspect: ${MEMORIES[i].text}`);
  });
  restore?.addEventListener('click', () => store.set({ forgotten: [false, false, false, false] }));
}

/* ───────── 04 Capabilities ───────── */

export function initCapabilities(): void {
  const root = document.getElementById('cap-columns');
  if (!root) return;
  const order: Status[] = ['working', 'dev', 'roadmap'];
  root.innerHTML = '';
  for (const status of order) {
    const col = document.createElement('div');
    col.className = `cap-col cap-col--${status}`;
    const h = document.createElement('h3');
    h.className = 'cap-col__title';
    h.innerHTML = `<span class="status-dot status-dot--${status === 'dev' ? 'dev' : status}" aria-hidden="true"></span>`;
    h.append(STATUS_LABEL[status]);
    const ul = document.createElement('ul');
    ul.className = 'cap-list';
    CAPABILITIES.forEach((c, i) => {
      if (c.status !== status) return;
      const li = document.createElement('li');
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'cap';
      b.dataset.index = String(i);
      b.setAttribute('aria-pressed', 'false');
      const name = document.createElement('span');
      name.className = 'cap__name';
      name.textContent = c.name;
      const desc = document.createElement('span');
      desc.className = 'cap__desc';
      desc.textContent = c.desc;
      b.append(name, desc);
      if (c.limit) {
        const lim = document.createElement('span');
        lim.className = 'cap__limit';
        lim.textContent = c.limit;
        b.append(lim);
      }
      const sr = document.createElement('span');
      sr.className = 'visually-hidden';
      sr.textContent = `Status: ${STATUS_LABEL[c.status]}. Highlights its thread on the loom.`;
      b.append(sr);
      li.append(b);
      ul.append(li);
    });
    col.append(h, ul);
    root.append(col);
  }

  const buttons = Array.from(root.querySelectorAll<HTMLButtonElement>('.cap'));
  let lastPluck = -1;
  const pluck = (i: number, strength: number) => {
    if (i === lastPluck && strength < 1) return;
    lastPluck = i;
    events.emit('pluck', { group: i, strength });
  };
  root.addEventListener('pointerover', (e) => {
    const b = (e.target as HTMLElement).closest<HTMLButtonElement>('.cap');
    if (!b) return;
    const i = Number(b.dataset.index);
    if (store.get().capHover !== i) {
      store.set({ capHover: i });
      pluck(i, 0.55);
    }
  });
  root.addEventListener('pointerleave', () => {
    store.set({ capHover: -1 });
    lastPluck = -1;
  });
  root.addEventListener('focusin', (e) => {
    const b = (e.target as HTMLElement).closest<HTMLButtonElement>('.cap');
    if (b) store.set({ capHover: Number(b.dataset.index) });
  });
  root.addEventListener('focusout', (e) => {
    if (!root.contains(e.relatedTarget as Node)) store.set({ capHover: -1 });
  });
  root.addEventListener('click', (e) => {
    const b = (e.target as HTMLElement).closest<HTMLButtonElement>('.cap');
    if (!b) return;
    const i = Number(b.dataset.index);
    const sel = store.get().capSelected === i ? -1 : i;
    store.set({ capSelected: sel });
    if (sel >= 0) events.emit('pluck', { group: i, strength: 1 });
  });
  store.subscribe((s, changed) => {
    if (changed.has('capSelected')) buttons.forEach((b) => b.setAttribute('aria-pressed', String(Number(b.dataset.index) === s.capSelected)));
  });
}

/* ───────── 06 Explore ───────── */

export function initExplore(): void {
  const wrap = document.getElementById('explore-dest');
  const card = document.getElementById('explore-card');
  const reset = document.getElementById('explore-reset');
  if (!wrap || !card) return;

  wrap.innerHTML = '';
  for (const d of DESTINATIONS) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'dest-btn';
    b.dataset.id = d.id;
    b.style.setProperty('--dest-c', d.color);
    b.setAttribute('aria-pressed', 'false');
    b.textContent = d.label;
    wrap.append(b);
  }
  const buttons = Array.from(wrap.querySelectorAll<HTMLButtonElement>('.dest-btn'));

  wrap.addEventListener('click', (e) => {
    const b = (e.target as HTMLElement).closest<HTMLButtonElement>('.dest-btn');
    if (!b) return;
    const id = b.dataset.id ?? null;
    store.set({ exploreFocus: store.get().exploreFocus === id ? null : id });
    events.emit('cue', { kind: 'focus' });
  });
  reset?.addEventListener('click', () => {
    store.set({ exploreFocus: null, exploreReset: store.get().exploreReset + 1 });
  });

  const renderCard = (id: string | null) => {
    const d = DESTINATIONS.find((x) => x.id === id);
    card.innerHTML = '';
    if (!d) {
      const p = document.createElement('p');
      p.textContent = 'Choose a thread above to see what it stands for — each one leads back to the part of the story where it was introduced.';
      card.append(p);
      return;
    }
    const h = document.createElement('h3');
    h.textContent = d.title;
    const p = document.createElement('p');
    p.textContent = d.body;
    const st = document.createElement('span');
    st.className = 'explore__status';
    st.innerHTML = `<span class="status-dot status-dot--${d.status}" aria-hidden="true"></span>`;
    st.append(STATUS_LABEL[d.status]);
    const a = document.createElement('a');
    a.href = d.href;
    a.textContent = d.linkText;
    card.append(h, p, st, a);
  };

  store.subscribe((s, changed) => {
    if (!changed.has('exploreFocus')) return;
    buttons.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.id === s.exploreFocus)));
    renderCard(s.exploreFocus);
  });
  renderCard(null);
}
