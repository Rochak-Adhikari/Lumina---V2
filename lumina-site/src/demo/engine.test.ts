import { describe, expect, it } from 'vitest';
import { approve, cancel, createRun, deny, interpret, isFinished, progress, retry, start, tick, type Run } from './engine';
import { SCENARIOS, defaults } from './scenarios';
import { loopProgress, loopView } from '../core/sequence';

const runToEnd = (r: Run, guard = 200): Run => {
  let run = r;
  for (let i = 0; i < guard && run.phase === 'running'; i++) run = tick(run, 250);
  return run;
};

describe('interpret', () => {
  it('rejects empty and overlong input', () => {
    expect(interpret('   ')).toMatchObject({ ok: false, reason: 'empty' });
    expect(interpret('x'.repeat(281))).toMatchObject({ ok: false, reason: 'too-long' });
  });

  it('is honest about requests outside the simulation', () => {
    const r = interpret('Book me a flight to Tokyo');
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe('unrecognized');
  });

  it('maps every example request to its own scenario', () => {
    for (const s of SCENARIOS) {
      const r = interpret(s.request);
      expect(r.ok, s.id).toBe(true);
      if (r.ok) expect(r.scenario.id).toBe(s.id);
    }
  });

  it('extracts parameters deterministically', () => {
    const r = interpret('Remind me to call the bank on Tuesday at 3pm');
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.params).toMatchObject({ day: 'Tuesday', time: '15:00' });
    const b = interpret("Summarise the meeting notes as a half page of paragraphs, don't save it");
    expect(b.ok && b.params).toMatchObject({ length: 'half', style: 'prose', save: false });
    const t = interpret('Preview moving installers older than 90 days out of downloads');
    expect(t.ok && t.params).toMatchObject({ age: '90', preview: true });
  });
});

describe('run lifecycle', () => {
  it('completes a read-only scenario without asking for approval', () => {
    let run = start(createRun('quotes', {}));
    run = runToEnd(run);
    expect(run.phase).toBe('done');
    expect(run.approval).toBeNull();
    expect(run.steps.every((s) => s.status === 'done')).toBe(true);
    expect(run.result?.headline).toContain('Kettle'); // lowest incl. shipping in the example data
    expect(progress(run)).toBe(1);
  });

  it('changes its answer when parameters change', () => {
    const noShip = runToEnd(start(createRun('quotes', { shipping: false })));
    expect(noShip.result?.headline).toContain('Aster');
    const fast = runToEnd(start(createRun('quotes', { criterion: 'speed' })));
    expect(fast.result?.headline).toContain('3 days');
  });

  it('waits for approval before any change and continues only when approved', () => {
    let run = runToEnd(start(createRun('tidy', {})));
    expect(run.phase).toBe('waiting');
    expect(run.runtime).toBe('WAITING_FOR_USER');
    const act = run.steps.find((s) => s.id === 'act');
    expect(act?.status).toBe('pending');
    // ticking while waiting does nothing
    expect(tick(run, 10_000)).toBe(run);
    run = runToEnd(approve(run));
    expect(run.phase).toBe('done');
    expect(run.result?.headline).toBe('Moved 6 files into Downloads\\Archive');
  });

  it('declining skips every remaining step and changes nothing', () => {
    let run = runToEnd(start(createRun('brief', { save: true })));
    run = deny(run);
    expect(run.phase).toBe('denied');
    expect(isFinished(run)).toBe(true);
    const after = run.steps.slice(run.cursor);
    expect(after.every((s) => s.status === 'skipped')).toBe(true);
    expect(run.result?.headline).toMatch(/declined/);
  });

  it('skips approval for preview-only and unsaved runs', () => {
    expect(createRun('tidy', { preview: true }).approval).toBeNull();
    expect(createRun('brief', { save: false }).approval).toBeNull();
    expect(createRun('reminder', { confirm: false }).approval).toBeNull();
    expect(createRun('reminder', { confirm: true }).approval).not.toBeNull();
  });

  it('reports a simulated problem, never retries on its own, and recovers when asked', () => {
    let run = runToEnd(start(createRun('quotes', {}, { simulateProblem: true })));
    expect(run.phase).toBe('failed');
    expect(run.runtime).toBe('ERROR');
    const failed = run.steps[run.cursor];
    expect(failed.id).toBe('extract');
    // further ticks do not retry
    expect(tick(run, 60_000)).toBe(run);
    run = runToEnd(retry(run));
    expect(run.phase).toBe('done');
    expect(run.steps.find((s) => s.id === 'extract')?.note).toMatch(/Retried/);
  });

  it('can be cancelled mid-run', () => {
    let run = start(createRun('brief', {}));
    run = tick(run, 900);
    run = cancel(run);
    expect(run.phase).toBe('cancelled');
    expect(run.steps.filter((s) => s.status === 'running')).toHaveLength(0);
    expect(run.result?.headline).toBe('Stopped by you');
  });

  it('is deterministic: identical inputs give identical runs', () => {
    for (const s of SCENARIOS) {
      const a = runToEnd(start(createRun(s.id, defaults(s))));
      const b = runToEnd(start(createRun(s.id, defaults(s))));
      expect(JSON.stringify(a)).toBe(JSON.stringify(b));
    }
  });

  it('does not mutate previous run states', () => {
    const r0 = start(createRun('reminder', {}));
    const snapshot = JSON.stringify(r0);
    tick(r0, 5000);
    expect(JSON.stringify(r0)).toBe(snapshot);
  });
});

describe('action loop sequence (shared by HTML steps and 3D heddles)', () => {
  it('is monotonic and pauses at the approval step', () => {
    let last = -1;
    for (let p = 0; p <= 1.0001; p += 0.01) {
      const v = loopProgress(p);
      expect(v).toBeGreaterThanOrEqual(last - 1e-9);
      last = v;
    }
    expect(loopProgress(0.5)).toBeCloseTo(4, 5);
    expect(loopProgress(0.58)).toBeCloseTo(4, 5);
    expect(loopView(0.55)).toMatchObject({ active: 3, approved: false });
    expect(loopView(0.65)).toMatchObject({ approved: true });
    expect(loopView(1)).toMatchObject({ active: 5, reached: 6 });
    expect(loopView(0)).toMatchObject({ active: -1, reached: 0 });
  });
});
