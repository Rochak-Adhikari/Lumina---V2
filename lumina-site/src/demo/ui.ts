import { approve, cancel, createRun, deny, interpret, isFinished, MAX_REQUEST, progress, retry, start, tick, type Run, type RunStep } from './engine';
import { PERMISSION_LABEL, SCENARIOS, defaults, type Params, type ResultBlock, type Scenario } from './scenarios';
import { store, events } from '../core/store';

const TICK_MS = 60;

const RUNTIME_LABEL: Record<Run['runtime'], string> = {
  IDLE: 'Idle',
  THINKING: 'Thinking',
  WAITING_FOR_USER: 'Waiting for you',
  EXECUTING: 'Executing',
  ERROR: 'Needs attention',
};

const STATUS_LABEL: Record<RunStep['status'], string> = {
  pending: 'Pending',
  running: 'Running',
  waiting: 'Waiting for you',
  done: 'Done',
  failed: 'Problem',
  skipped: 'Skipped',
};

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export function initDemo(root: HTMLElement): () => void {
  root.innerHTML = `
  <div class="console" role="region" aria-label="Lumina concept console — simulation">
    <div class="console__bar">
      <span class="console__dots" aria-hidden="true"><i></i><i></i><i></i></span>
      <span class="console__title">Lumina · concept console</span>
      <span class="tag tag--sim">Simulation · example data</span>
      <span class="runtime" data-state="IDLE"><span class="runtime__dot" aria-hidden="true"></span><span class="visually-hidden">Runtime state: </span><span class="runtime__label">Idle</span></span>
    </div>
    <p class="console__notice">Runs entirely in your browser. Nothing on your computer is read or changed.</p>
    <div class="console__body">
      <section class="pane pane--request" aria-labelledby="demo-h-req">
        <h3 class="pane__title" id="demo-h-req"><span class="pane__num">1</span> Request</h3>
        <div class="chips" role="group" aria-label="Example requests"></div>
        <form class="req-form" novalidate>
          <label class="field-label" for="demo-request">What should Lumina do?</label>
          <textarea id="demo-request" class="req-input" rows="3" maxlength="${MAX_REQUEST + 40}" aria-describedby="demo-count demo-error"></textarea>
          <div class="req-row">
            <span class="req-count" id="demo-count" aria-live="off"></span>
            <button class="btn btn--small btn--ghost" type="submit">Interpret</button>
          </div>
          <p class="req-error" id="demo-error" role="alert"></p>
        </form>
        <div class="understood" hidden>
          <h4 class="sub-title">Understood</h4>
          <dl class="understood__list"></dl>
          <div class="params" role="group" aria-label="Adjust the request"></div>
          <label class="check fail-toggle"><input type="checkbox" class="fail-input" /> <span>Simulate a problem</span></label>
        </div>
      </section>

      <section class="pane pane--plan" aria-labelledby="demo-h-plan">
        <h3 class="pane__title" id="demo-h-plan"><span class="pane__num">2</span> Plan &amp; execution</h3>
        <p class="plan-empty">Interpret a request to see Lumina's plan.</p>
        <ol class="steps" aria-live="polite" aria-relevant="text"></ol>
        <div class="approval" hidden tabindex="-1" role="group" aria-labelledby="demo-approval-title">
          <p class="approval__eyebrow">Approval needed</p>
          <p class="approval__title" id="demo-approval-title"></p>
          <ul class="approval__items"></ul>
          <p class="approval__note"></p>
          <div class="approval__actions">
            <button class="btn btn--primary btn--small" type="button" data-act="approve">Approve</button>
            <button class="btn btn--ghost btn--small" type="button" data-act="deny">Decline</button>
          </div>
        </div>
        <div class="problem" hidden tabindex="-1" role="group" aria-labelledby="demo-problem-title">
          <p class="problem__title" id="demo-problem-title">Lumina stopped and is asking you</p>
          <p class="problem__text"></p>
          <div class="approval__actions">
            <button class="btn btn--primary btn--small" type="button" data-act="retry">Retry this step</button>
            <button class="btn btn--ghost btn--small" type="button" data-act="cancel">Stop here</button>
          </div>
        </div>
        <div class="run-controls">
          <button class="btn btn--primary btn--small" type="button" data-act="run" disabled>Run plan</button>
          <button class="btn btn--ghost btn--small" type="button" data-act="stop" hidden>Stop</button>
          <button class="btn btn--ghost btn--small" type="button" data-act="reset" hidden>Run again</button>
          <div class="meter" role="progressbar" aria-label="Task progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><span class="meter__fill"></span></div>
        </div>
      </section>

      <section class="pane pane--result" aria-labelledby="demo-h-res">
        <h3 class="pane__title" id="demo-h-res"><span class="pane__num">3</span> Result &amp; evidence</h3>
        <div class="result" aria-live="polite"><p class="result__empty">The result appears here, with the evidence it was checked against.</p></div>
        <details class="log">
          <summary>Event log <span class="log__count">(0)</span></summary>
          <ol class="log__list"></ol>
        </details>
      </section>
    </div>
  </div>`;

  const q = <T extends Element>(sel: string) => root.querySelector(sel) as T;
  const chips = q<HTMLElement>('.chips');
  const form = q<HTMLFormElement>('.req-form');
  const input = q<HTMLTextAreaElement>('#demo-request');
  const count = q<HTMLElement>('.req-count');
  const error = q<HTMLElement>('.req-error');
  const understood = q<HTMLElement>('.understood');
  const uList = q<HTMLElement>('.understood__list');
  const paramsEl = q<HTMLElement>('.params');
  const failInput = q<HTMLInputElement>('.fail-input');
  const failToggle = q<HTMLElement>('.fail-toggle');
  const planEmpty = q<HTMLElement>('.plan-empty');
  const stepsEl = q<HTMLOListElement>('.steps');
  const approvalEl = q<HTMLElement>('.approval');
  const problemEl = q<HTMLElement>('.problem');
  const runBtn = q<HTMLButtonElement>('[data-act="run"]');
  const stopBtn = q<HTMLButtonElement>('[data-act="stop"]');
  const resetBtn = q<HTMLButtonElement>('[data-act="reset"]');
  const meter = q<HTMLElement>('.meter');
  const meterFill = q<HTMLElement>('.meter__fill');
  const resultEl = q<HTMLElement>('.result');
  const logList = q<HTMLOListElement>('.log__list');
  const logCount = q<HTMLElement>('.log__count');
  const runtimeEl = q<HTMLElement>('.runtime');
  const runtimeLabel = q<HTMLElement>('.runtime__label');

  let scenario: Scenario | null = null;
  let params: Params = {};
  let run: Run | null = null;
  let stale = false;
  let timer = 0;
  let lastPhase: Run['phase'] | null = null;
  let lastDone = 0;

  /* ── Scenario chips ── */
  SCENARIOS.forEach((s) => {
    const b = el('button', 'chip', s.label);
    b.type = 'button';
    b.dataset.id = s.id;
    b.setAttribute('aria-pressed', 'false');
    chips.append(b);
  });
  chips.addEventListener('click', (e) => {
    const b = (e.target as HTMLElement).closest<HTMLButtonElement>('.chip');
    if (!b) return;
    const s = SCENARIOS.find((x) => x.id === b.dataset.id);
    if (!s) return;
    input.value = s.request;
    doInterpret();
  });

  /* ── Request ── */
  const updateCount = () => {
    const n = input.value.trim().length;
    count.textContent = `${n}/${MAX_REQUEST}`;
    count.classList.toggle('is-over', n > MAX_REQUEST);
  };
  input.addEventListener('input', () => {
    updateCount();
    if (scenario && !stale && (!run || run.phase === 'ready' || isFinished(run))) {
      stale = true;
      error.textContent = '';
      renderAll();
    }
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    doInterpret();
  });

  function doInterpret(): void {
    if (run && (run.phase === 'running' || run.phase === 'waiting' || run.phase === 'failed')) return;
    const r = interpret(input.value);
    if (!r.ok) {
      error.textContent = r.message;
      input.setAttribute('aria-invalid', 'true');
      return;
    }
    error.textContent = '';
    input.removeAttribute('aria-invalid');
    scenario = r.scenario;
    params = r.params;
    stale = false;
    failInput.checked = false;
    rebuild();
    renderParams();
    events.emit('cue', { kind: 'tick' });
  }

  function rebuild(): void {
    if (!scenario) return;
    stopTimer();
    run = createRun(scenario.id, params, { simulateProblem: failInput.checked });
    lastDone = 0;
    publish();
    renderAll();
  }

  /* ── Parameters ── */
  function renderParams(): void {
    paramsEl.innerHTML = '';
    if (!scenario) return;
    for (const d of scenario.params) {
      const id = `demo-p-${scenario.id}-${d.id}`;
      const wrap = el('div', 'param');
      if (d.type === 'select') {
        const label = el('label', 'field-label', d.label);
        label.htmlFor = id;
        const sel = el('select', 'select');
        sel.id = id;
        sel.dataset.param = d.id;
        for (const o of d.options ?? []) {
          const opt = el('option', undefined, o.label);
          opt.value = o.value;
          sel.append(opt);
        }
        sel.value = String(params[d.id] ?? d.default);
        wrap.append(label, sel);
      } else {
        const label = el('label', 'check');
        const cb = el('input');
        cb.type = 'checkbox';
        cb.id = id;
        cb.dataset.param = d.id;
        cb.checked = Boolean(params[d.id] ?? d.default);
        label.append(cb, el('span', undefined, d.label));
        wrap.append(label);
      }
      if (d.hint) wrap.append(el('p', 'param__hint', d.hint));
      paramsEl.append(wrap);
    }
  }
  paramsEl.addEventListener('change', (e) => {
    const t = e.target as HTMLInputElement | HTMLSelectElement;
    const key = t.dataset.param;
    if (!key || !scenario) return;
    params = { ...params, [key]: t instanceof HTMLInputElement && t.type === 'checkbox' ? t.checked : t.value };
    rebuild();
  });
  failInput.addEventListener('change', rebuild);

  /* ── Run controls ── */
  root.addEventListener('click', (e) => {
    const b = (e.target as HTMLElement).closest<HTMLButtonElement>('button[data-act]');
    if (!b || !run) return;
    switch (b.dataset.act) {
      case 'run':
        if (run.phase !== 'ready' || stale) return;
        run = start(run);
        startTimer();
        break;
      case 'approve':
        run = approve(run);
        events.emit('cue', { kind: 'approve' });
        startTimer();
        break;
      case 'deny':
        run = deny(run);
        break;
      case 'retry':
        run = retry(run);
        startTimer();
        break;
      case 'stop':
      case 'cancel':
        run = cancel(run);
        stopTimer();
        break;
      case 'reset':
        rebuild();
        runBtn.focus();
        return;
    }
    publish();
    renderAll();
  });

  function startTimer(): void {
    if (timer) return;
    timer = window.setInterval(() => {
      if (!run) return stopTimer();
      const next = tick(run, TICK_MS);
      if (next === run) return stopTimer();
      run = next;
      publish();
      renderAll();
      if (run.phase !== 'running') stopTimer();
    }, TICK_MS);
  }

  function stopTimer(): void {
    if (timer) window.clearInterval(timer);
    timer = 0;
  }

  /* ── Publishing to the shared store (the 3D world listens) ── */
  function publish(): void {
    if (!run) {
      store.set({ demoPhase: 'idle', demoProgress: 0 });
      return;
    }
    const phase =
      run.phase === 'running' ? 'running' : run.phase === 'waiting' ? 'waiting' : run.phase === 'failed' ? 'failed' : run.phase === 'done' ? 'done' : run.phase === 'denied' || run.phase === 'cancelled' ? 'denied' : 'idle';
    store.set({ demoPhase: phase, demoProgress: progress(run) });
    const done = run.steps.filter((s) => s.status === 'done').length;
    if (done > lastDone && run.phase === 'running') events.emit('cue', { kind: 'tick' });
    lastDone = done;
    if (run.phase !== lastPhase) {
      if (run.phase === 'done') events.emit('cue', { kind: 'success' });
      if (run.phase === 'failed') events.emit('cue', { kind: 'fail' });
    }
  }

  /* ── Rendering ── */
  function renderAll(): void {
    const phaseChanged = run?.phase !== lastPhase;
    // chips
    chips.querySelectorAll<HTMLButtonElement>('.chip').forEach((c) => c.setAttribute('aria-pressed', String(!stale && c.dataset.id === scenario?.id)));
    const busy = !!run && (run.phase === 'running' || run.phase === 'waiting' || run.phase === 'failed');
    chips.querySelectorAll<HTMLButtonElement>('.chip').forEach((c) => (c.disabled = busy));
    input.disabled = busy;
    form.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled = busy;

    // understanding + params
    understood.hidden = !run;
    understood.classList.toggle('is-stale', stale);
    if (run) {
      uList.innerHTML = '';
      const u = run.understanding;
      const rows: [string, string][] = [
        ['Goal', u.goal],
        ['Constraints', u.constraints.join(' · ')],
        ['Done when', u.done],
      ];
      for (const [k, v] of rows) uList.append(el('dt', undefined, k), el('dd', undefined, v));
      paramsEl.querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-param]').forEach((c) => (c.disabled = run!.phase !== 'ready' && !isFinished(run!)));
      const failStep = scenario?.failStep(run.params);
      failToggle.hidden = !failStep;
      failInput.disabled = run.phase !== 'ready' && !isFinished(run);
      const failLabel = failToggle.querySelector('span');
      if (failLabel && failStep) {
        const st = run.steps.find((s) => s.id === failStep);
        failLabel.textContent = `Simulate a problem at “${st?.title ?? failStep}”`;
      }
    }

    // plan
    planEmpty.hidden = !!run;
    if (stale && run) {
      planEmpty.hidden = false;
      planEmpty.textContent = 'The request changed — interpret it again to update the plan.';
    } else planEmpty.textContent = "Interpret a request to see Lumina's plan.";
    stepsEl.hidden = !run || stale;
    if (run && !stale) renderSteps(run);

    // approval
    const waiting = run?.phase === 'waiting';
    approvalEl.hidden = !waiting;
    if (waiting && run?.approval) {
      q<HTMLElement>('.approval__title').textContent = run.approval.summary;
      const ul = q<HTMLElement>('.approval__items');
      ul.innerHTML = '';
      run.approval.items.forEach((it) => ul.append(el('li', undefined, it)));
      q<HTMLElement>('.approval__note').textContent = run.approval.note;
      if (phaseChanged) approvalEl.focus({ preventScroll: false });
    }
    // problem
    const failed = run?.phase === 'failed';
    problemEl.hidden = !failed;
    if (failed && run) {
      q<HTMLElement>('.problem__text').textContent = run.steps[run.cursor]?.note ?? '';
      if (phaseChanged) problemEl.focus({ preventScroll: false });
    }

    // controls
    runBtn.hidden = !!run && run.phase !== 'ready';
    runBtn.disabled = !run || run.phase !== 'ready' || stale;
    stopBtn.hidden = !run || !(run.phase === 'running' || run.phase === 'waiting');
    resetBtn.hidden = !run || !isFinished(run);
    const pct = run ? Math.round(progress(run) * 100) : 0;
    meter.setAttribute('aria-valuenow', String(pct));
    meterFill.style.transform = `scaleX(${pct / 100})`;
    meter.dataset.phase = run?.phase ?? 'ready';

    // runtime chip
    const rt = run?.runtime ?? 'IDLE';
    runtimeEl.dataset.state = rt;
    runtimeLabel.textContent = RUNTIME_LABEL[rt];

    // result
    if (phaseChanged || !run) renderResult(run);
    renderLog(run);
    if (phaseChanged && run && isFinished(run)) resetBtn.focus({ preventScroll: true });
    lastPhase = run?.phase ?? null;
  }

  function renderSteps(r: Run): void {
    if (stepsEl.children.length !== r.steps.length || stepsEl.dataset.key !== `${r.scenarioId}:${r.steps.map((s) => s.id).join(',')}`) {
      stepsEl.innerHTML = '';
      stepsEl.dataset.key = `${r.scenarioId}:${r.steps.map((s) => s.id).join(',')}`;
      r.steps.forEach((s) => {
        const li = el('li', 'step');
        li.innerHTML = `<span class="step__icon" aria-hidden="true"></span>
          <div class="step__main">
            <div class="step__head"><span class="step__title"></span><span class="step__perm"></span></div>
            <p class="step__detail"></p>
            <p class="step__note"></p>
          </div>
          <span class="step__status"></span>`;
        (li.querySelector('.step__title') as HTMLElement).textContent = s.title;
        const perm = li.querySelector('.step__perm') as HTMLElement;
        perm.textContent = PERMISSION_LABEL[s.permission];
        perm.dataset.perm = s.permission;
        (li.querySelector('.step__detail') as HTMLElement).textContent = s.detail;
        stepsEl.append(li);
      });
    }
    r.steps.forEach((s, i) => {
      const li = stepsEl.children[i] as HTMLElement;
      li.dataset.status = s.status;
      (li.querySelector('.step__status') as HTMLElement).textContent = STATUS_LABEL[s.status];
      const note = li.querySelector('.step__note') as HTMLElement;
      note.textContent = s.note ?? '';
      note.hidden = !s.note;
      const pct = s.status === 'running' && s.duration ? s.elapsed / s.duration : s.status === 'done' ? 1 : 0;
      li.style.setProperty('--step-p', pct.toFixed(3));
    });
  }

  function renderBlocks(blocks: ResultBlock[], into: HTMLElement): void {
    for (const b of blocks) {
      if (b.type === 'text') into.append(el('p', 'result__text', b.text));
      else if (b.type === 'list') {
        const ul = el('ul', 'result__list');
        b.items.forEach((it) => ul.append(el('li', undefined, it)));
        into.append(ul);
      } else {
        const table = el('table', 'result__table');
        const thead = el('thead');
        const tr = el('tr');
        b.head.forEach((h) => {
          const th = el('th', undefined, h);
          th.scope = 'col';
          tr.append(th);
        });
        thead.append(tr);
        const tbody = el('tbody');
        b.rows.forEach((row) => {
          const r = el('tr');
          row.forEach((c, i) => {
            if (i === 0) {
              const th = el('th', undefined, c);
              th.scope = 'row';
              r.append(th);
            } else r.append(el('td', undefined, c));
          });
          tbody.append(r);
        });
        table.append(thead, tbody);
        into.append(table);
      }
    }
  }

  function renderResult(r: Run | null): void {
    resultEl.innerHTML = '';
    if (!r || !r.result) {
      const msg =
        r?.phase === 'waiting'
          ? 'Paused at the approval step. Nothing has changed yet.'
          : r?.phase === 'failed'
            ? 'Stopped at a problem. Nothing after this step has run.'
            : r?.phase === 'running'
              ? 'Working…'
              : 'The result appears here, with the evidence it was checked against.';
      resultEl.append(el('p', 'result__empty', msg));
      return;
    }
    const tone = r.phase === 'done' ? 'ok' : 'neutral';
    const head = el('p', `result__headline result__headline--${tone}`, r.result.headline);
    resultEl.append(head);
    renderBlocks(r.result.blocks, resultEl);
    const ev = r.steps.filter((s) => s.status === 'done' && s.note).map((s) => s.note as string);
    if (ev.length) {
      const h = el('p', 'result__ev-title', 'Evidence');
      const ul = el('ul', 'result__evidence');
      ev.forEach((x) => ul.append(el('li', undefined, x)));
      resultEl.append(h, ul);
    }
    resultEl.append(el('p', 'result__disclaimer', 'Example output from the simulation — no real files, folders or reminders were involved.'));
  }

  function renderLog(r: Run | null): void {
    const entries = r?.log ?? [];
    if (logList.children.length === entries.length && entries.length) return;
    logList.innerHTML = '';
    entries.forEach((e) => {
      const li = el('li', `log__item log__item--${e.tone}`);
      li.append(el('span', 'log__time', `+${(e.at / 1000).toFixed(1)}s`), el('span', 'log__text', e.text));
      logList.append(li);
    });
    logCount.textContent = `(${entries.length})`;
  }

  // Initial state: first example selected and interpreted, ready to run.
  input.value = SCENARIOS[0].request;
  updateCount();
  scenario = SCENARIOS[0];
  params = defaults(scenario);
  rebuild();
  renderParams();

  return () => stopTimer();
}
