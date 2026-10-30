/**
 * Deterministic demo engine. Pure functions over plain data — no timers, no DOM, no randomness.
 * The UI advances simulated time with tick(); tests do the same.
 */
import { SCENARIOS, defaults, type Approval, type Params, type Result, type Scenario, type StepDef, type Understanding } from './scenarios';

export type StepStatus = 'pending' | 'running' | 'waiting' | 'done' | 'failed' | 'skipped';
export type RuntimeState = 'IDLE' | 'THINKING' | 'WAITING_FOR_USER' | 'EXECUTING' | 'ERROR';
export type Phase = 'ready' | 'running' | 'waiting' | 'failed' | 'done' | 'denied' | 'cancelled';

export interface RunStep extends StepDef {
  status: StepStatus;
  elapsed: number;
  note?: string;
}

export interface LogEntry {
  at: number;
  text: string;
  tone: 'info' | 'ok' | 'warn' | 'user';
}

export interface Run {
  scenarioId: string;
  params: Params;
  understanding: Understanding;
  approval: Approval | null;
  steps: RunStep[];
  cursor: number;
  phase: Phase;
  runtime: RuntimeState;
  clock: number;
  log: LogEntry[];
  /** Step id that will fail on its first attempt, if the visitor asked to simulate a problem. */
  failAt: string | null;
  failedOnce: boolean;
  result: Result | null;
}

export const MAX_REQUEST = 280;

export type Interpretation =
  | { ok: true; scenario: Scenario; params: Params; matched: string[] }
  | { ok: false; reason: 'empty' | 'too-long' | 'unrecognized'; message: string };

export function getScenario(id: string): Scenario {
  const s = SCENARIOS.find((x) => x.id === id);
  if (!s) throw new Error(`Unknown scenario: ${id}`);
  return s;
}

/** Keyword interpretation. The real Lumina uses a model for this; the simulation only knows four examples. */
export function interpret(raw: string): Interpretation {
  const text = raw.trim();
  if (!text) return { ok: false, reason: 'empty', message: 'Type a request, or pick one of the examples.' };
  if (text.length > MAX_REQUEST)
    return { ok: false, reason: 'too-long', message: `Keep it under ${MAX_REQUEST} characters — this simulation reads short requests.` };
  let best: { s: Scenario; score: number; matched: string[] } | null = null;
  for (const s of SCENARIOS) {
    const matched = s.keywords.filter((k) => k.test(text)).map((k) => k.source);
    const score = matched.length;
    if (score > 0 && (!best || score > best.score)) best = { s, score, matched };
  }
  if (!best)
    return {
      ok: false,
      reason: 'unrecognized',
      message:
        'This simulation only understands requests like the four examples (briefs, quotes, reminders, tidying Downloads). In Lumina, a language model does this interpretation.',
    };
  return { ok: true, scenario: best.s, params: { ...defaults(best.s), ...(best.s.extract(text) as Params) }, matched: best.matched };
}

function runtimeFor(step: RunStep | undefined): RuntimeState {
  if (!step) return 'IDLE';
  if (step.status === 'waiting') return 'WAITING_FOR_USER';
  return step.kind === 'understand' || step.kind === 'recall' || step.kind === 'plan' ? 'THINKING' : 'EXECUTING';
}

function log(run: Run, text: string, tone: LogEntry['tone'] = 'info'): void {
  run.log.push({ at: run.clock, text, tone });
}

export function createRun(scenarioId: string, params: Params, opts: { simulateProblem?: boolean } = {}): Run {
  const s = getScenario(scenarioId);
  const p = { ...defaults(s), ...params };
  const steps = s.steps(p).map<RunStep>((d) => ({ ...d, status: 'pending', elapsed: 0 }));
  const hasApproval = steps.some((x) => x.kind === 'approve');
  return {
    scenarioId,
    params: p,
    understanding: s.understand(p),
    approval: hasApproval && s.approval ? s.approval(p) : null,
    steps,
    cursor: -1,
    phase: 'ready',
    runtime: 'IDLE',
    clock: 0,
    log: [],
    failAt: opts.simulateProblem ? s.failStep(p) : null,
    failedOnce: false,
    result: null,
  };
}

const clone = (r: Run): Run => ({
  ...r,
  params: { ...r.params },
  steps: r.steps.map((s) => ({ ...s })),
  log: r.log.slice(),
});

function enter(run: Run, i: number): void {
  run.cursor = i;
  const step = run.steps[i];
  if (!step) {
    run.phase = 'done';
    run.runtime = 'IDLE';
    run.result = getScenario(run.scenarioId).result(run.params);
    log(run, 'Done. Result verified.', 'ok');
    return;
  }
  if (step.kind === 'approve') {
    step.status = 'waiting';
    run.phase = 'waiting';
    log(run, `Waiting for your approval: ${run.approval?.summary ?? step.title}`, 'warn');
  } else {
    step.status = 'running';
    run.phase = 'running';
    log(run, `${step.title}…`);
  }
  run.runtime = runtimeFor(step);
}

export function start(prev: Run): Run {
  if (prev.phase !== 'ready') return prev;
  const run = clone(prev);
  log(run, 'Request received.', 'user');
  enter(run, 0);
  return run;
}

/** Advance simulated time. Steps complete when their duration elapses. */
export function tick(prev: Run, ms: number): Run {
  if (prev.phase !== 'running' || ms <= 0) return prev;
  const run = clone(prev);
  let budget = ms;
  while (budget > 0 && run.phase === 'running') {
    const step = run.steps[run.cursor];
    const need = step.duration - step.elapsed;
    const used = Math.min(need, budget);
    step.elapsed += used;
    run.clock += used;
    budget -= used;
    if (step.elapsed >= step.duration) {
      if (run.failAt === step.id && !run.failedOnce) {
        step.status = 'failed';
        step.note = step.failMessage ?? 'This step failed.';
        run.failedOnce = true;
        run.phase = 'failed';
        run.runtime = 'ERROR';
        log(run, `Problem: ${step.note}`, 'warn');
        break;
      }
      step.status = 'done';
      step.note = run.failedOnce && run.failAt === step.id ? step.retryEvidence ?? step.evidence : step.evidence;
      if (step.note) log(run, step.note, 'ok');
      enter(run, run.cursor + 1);
    }
  }
  return run;
}

export function approve(prev: Run): Run {
  if (prev.phase !== 'waiting') return prev;
  const run = clone(prev);
  const step = run.steps[run.cursor];
  step.status = 'done';
  step.note = 'Approved by you for exactly the items listed.';
  log(run, 'You approved.', 'user');
  enter(run, run.cursor + 1);
  return run;
}

export function deny(prev: Run): Run {
  if (prev.phase !== 'waiting') return prev;
  const run = clone(prev);
  const step = run.steps[run.cursor];
  step.status = 'skipped';
  step.note = 'Declined by you.';
  for (let i = run.cursor + 1; i < run.steps.length; i++) {
    run.steps[i].status = 'skipped';
    run.steps[i].note = 'Not run — approval was declined.';
  }
  run.phase = 'denied';
  run.runtime = 'IDLE';
  const s = getScenario(run.scenarioId);
  run.result = s.deniedResult ? s.deniedResult(run.params) : { headline: 'Stopped — nothing changed', blocks: [] };
  log(run, 'You declined. Nothing was changed.', 'user');
  return run;
}

/** Retry only happens when the person asks; the same failed action is never repeated automatically. */
export function retry(prev: Run): Run {
  if (prev.phase !== 'failed') return prev;
  const run = clone(prev);
  const step = run.steps[run.cursor];
  step.status = 'running';
  step.elapsed = 0;
  step.note = undefined;
  run.phase = 'running';
  run.runtime = runtimeFor(step);
  log(run, `You asked to retry: ${step.title}`, 'user');
  return run;
}

export function cancel(prev: Run): Run {
  if (prev.phase !== 'running' && prev.phase !== 'waiting' && prev.phase !== 'failed') return prev;
  const run = clone(prev);
  for (let i = Math.max(0, run.cursor); i < run.steps.length; i++) {
    const st = run.steps[i];
    if (st.status !== 'done') {
      st.status = 'skipped';
      st.note = i === run.cursor ? 'Stopped by you.' : 'Not run.';
    }
  }
  run.phase = 'cancelled';
  run.runtime = 'IDLE';
  const done = run.steps.filter((x) => x.status === 'done').length;
  run.result = {
    headline: 'Stopped by you',
    blocks: [{ type: 'text', text: `${done} of ${run.steps.length} steps had finished; nothing after that ran.` }],
  };
  log(run, 'You stopped the task.', 'user');
  return run;
}

/** 0…1 for progress displays. Waiting and failed states hold their position. */
export function progress(run: Run): number {
  const total = run.steps.reduce((a, s) => a + Math.max(s.duration, 300), 0);
  let done = 0;
  for (const s of run.steps) {
    const w = Math.max(s.duration, 300);
    if (s.status === 'done' || s.status === 'skipped') done += w;
    else if (s.status === 'running') done += w * (s.duration ? s.elapsed / s.duration : 0);
  }
  return total ? Math.min(1, done / total) : 0;
}

export function isFinished(run: Run): boolean {
  return run.phase === 'done' || run.phase === 'denied' || run.phase === 'cancelled';
}
