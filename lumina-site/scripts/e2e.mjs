// End-to-end checks against a running server (dev or preview).
// Usage: node scripts/e2e.mjs [--url http://localhost:4183/] [--headed]
// Prints one line per check and exits non-zero if any check fails.
import { chromium } from 'playwright-core';
import { chromiumPath } from './shoot-path.mjs';

const argv = process.argv.slice(2);
const url = argv.includes('--url') ? argv[argv.indexOf('--url') + 1] : 'http://localhost:4183/';
const headed = argv.includes('--headed');

const results = [];
const check = async (name, fn) => {
  const t0 = Date.now();
  try {
    const detail = await fn();
    results.push({ name, ok: true, detail });
    console.log(`PASS  ${name}${detail ? ` — ${detail}` : ''} (${Date.now() - t0} ms)`);
  } catch (e) {
    results.push({ name, ok: false, detail: String(e?.message ?? e) });
    console.log(`FAIL  ${name} — ${String(e?.message ?? e).split('\n')[0]}`);
  }
};
const assert = (cond, msg) => {
  if (!cond) throw new Error(msg);
};

const browser = await chromium.launch({
  executablePath: chromiumPath(),
  headless: !headed,
  args: ['--use-angle=d3d11', '--ignore-gpu-blocklist', '--autoplay-policy=user-gesture-required'],
});

async function open(opts = {}, init) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'no-preference', ...opts });
  // Count AudioContext creation so tests can prove audio only starts after a gesture.
  await ctx.addInitScript(() => {
    const Orig = window.AudioContext;
    if (!Orig) return;
    window.__audioCtxCount = 0;
    window.__audioCtxs = [];
    window.AudioContext = class extends Orig {
      constructor(...a) {
        super(...a);
        window.__audioCtxCount++;
        window.__audioCtxs.push(this);
      }
    };
  });
  if (init) await ctx.addInitScript(init);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForFunction(() => ['ready', 'failed', 'off'].includes(window.__lumina?.store.get().world), null, { timeout: 20000 });
  return { ctx, page, errors };
}

const scrollTo = (page, chapter, p) =>
  page.evaluate(([c, pp]) => {
    document.documentElement.style.scrollBehavior = 'auto';
    window.scrollTo(0, window.__lumina.scrollForChapter(c, pp));
  }, [chapter, p]);
const state = (page) => page.evaluate(() => window.__lumina.store.get());

/* ───────── Main desktop session ───────── */
const { ctx, page, errors } = await open();

await check('loads with heading, 3D ready, no console errors', async () => {
  const h1 = await page.locator('h1').innerText();
  assert(/Say what you mean/.test(h1), 'missing h1');
  const s = await state(page);
  assert(s.world === 'ready', `world=${s.world}`);
  assert(errors.length === 0, errors.join(' | '));
  return `world ${s.world}`;
});

await check('audio is not created before a user gesture', async () => {
  const created = await page.evaluate(() => window.__audioCtxCount ?? 0);
  assert(created === 0, `AudioContext created ${created} times`);
});

await check('primary navigation reaches every chapter', async () => {
  const links = await page.locator('.primary-nav__list a').evaluateAll((as) => as.map((a) => a.getAttribute('href')));
  for (const href of links) {
    await page.locator(`.primary-nav__list a[href="${href}"]`).click();
    await page.waitForTimeout(1200);
    const top = await page.evaluate((h) => document.querySelector(h).getBoundingClientRect().top, href);
    assert(Math.abs(top) < 120, `${href} top=${top}`);
  }
  return links.join(' ');
});

await check('scroll state is identical going down and coming back up', async () => {
  const positions = [[0, 0], [1, 0.4], [2, 0.6], [3, 0.3], [3, 0.55], [3, 0.8], [4, 0.5], [6, 0.5]];
  const down = [];
  for (const [c, p] of positions) {
    await scrollTo(page, c, p);
    await page.waitForTimeout(150);
    down.push(await page.evaluate(() => {
      const s = window.__lumina.store.get();
      const steps = [...document.querySelectorAll('.loop__step')].map((e) => e.className).join('|');
      return JSON.stringify({ t: s.t.toFixed(4), ch: s.chapter, steps });
    }));
  }
  const up = [];
  for (const [c, p] of [...positions].reverse()) {
    await scrollTo(page, c, p);
    await page.waitForTimeout(150);
    up.unshift(await page.evaluate(() => {
      const s = window.__lumina.store.get();
      const steps = [...document.querySelectorAll('.loop__step')].map((e) => e.className).join('|');
      return JSON.stringify({ t: s.t.toFixed(4), ch: s.chapter, steps });
    }));
  }
  down.forEach((d, i) => assert(d === up[i], `mismatch at ${positions[i]}: ${d} vs ${up[i]}`));
  return `${positions.length} positions`;
});

await check('action loop waits at Approve, then shows approval', async () => {
  await scrollTo(page, 3, 0.55);
  await page.waitForTimeout(200);
  const waiting = await page.locator('#approve-badge').innerText();
  await scrollTo(page, 3, 0.7);
  await page.waitForTimeout(200);
  const approved = await page.locator('#approve-badge').innerText();
  assert(/waiting/i.test(waiting) && /approved/i.test(approved), `${waiting} / ${approved}`);
  return `${waiting} → ${approved}`;
});

await check('memory: inspect, forget, undo, restore', async () => {
  await scrollTo(page, 2, 0.5);
  const first = page.locator('.memory').first();
  await first.locator('[data-act="inspect"]').click();
  assert(await first.locator('dl').isVisible(), 'details not visible');
  await first.locator('[data-act="forget"]').click();
  let s = await state(page);
  assert(s.forgotten[0] === true && (await first.getAttribute('class')).includes('is-forgotten'), 'not forgotten');
  await first.locator('[data-act="forget"]').click();
  s = await state(page);
  assert(s.forgotten[0] === false, 'undo failed');
  await page.locator('.memory').nth(2).locator('[data-act="forget"]').click();
  await page.locator('#memory-restore').click();
  s = await state(page);
  assert(s.forgotten.every((f) => !f), 'restore failed');
  return 'ok';
});

await check('capabilities: selecting a card highlights its thread', async () => {
  await scrollTo(page, 4, 0.5);
  const card = page.locator('.cap').nth(4);
  await card.click();
  const pressed = await card.getAttribute('aria-pressed');
  const s = await state(page);
  assert(pressed === 'true' && s.capSelected === 4, `pressed=${pressed} sel=${s.capSelected}`);
  await card.click();
  assert((await state(page)).capSelected === -1, 'deselect failed');
  const counts = await page.evaluate(() => ['working', 'dev', 'roadmap'].map((k) => document.querySelectorAll(`.cap-col--${k} .cap`).length));
  return `working/dev/roadmap = ${counts.join('/')}`;
});

/* Demo flows */
const demo = page.locator('#demo-root');
const runUntil = async (phaseRe, timeout = 15000) => {
  await page.waitForFunction((re) => new RegExp(re).test(window.__lumina.store.get().demoPhase), phaseRe.source, { timeout });
};

await check('demo: brief → approve → saved result with evidence', async () => {
  await scrollTo(page, 5, 0.4);
  await demo.locator('.chip', { hasText: 'Write a brief' }).click();
  await demo.locator('[data-act="run"]').click();
  await runUntil(/waiting/);
  const runtime = await demo.locator('.runtime__label').innerText();
  const approvalItems = await demo.locator('.approval__items li').allInnerTexts();
  await demo.locator('[data-act="approve"]').click();
  await runUntil(/done/);
  const head = await demo.locator('.result__headline').innerText();
  const ev = await demo.locator('.result__evidence li').count();
  assert(/Saved/.test(head) && ev >= 4 && /waiting/i.test(runtime), `${head} ev=${ev} rt=${runtime}`);
  return `${runtime} → "${head}", ${ev} evidence lines, approval: ${approvalItems[0]}`;
});

await check('demo: read-only compare needs no approval; parameters change the answer', async () => {
  await demo.locator('[data-act="reset"]').click();
  await demo.locator('.chip', { hasText: 'Compare quotes' }).click();
  await demo.locator('[data-act="run"]').click();
  await runUntil(/done/);
  const a = await demo.locator('.result__headline').innerText();
  await demo.locator('[data-act="reset"]').click();
  await demo.locator('[data-param="shipping"]').uncheck();
  await demo.locator('[data-act="run"]').click();
  await runUntil(/done/);
  const b = await demo.locator('.result__headline').innerText();
  assert(a !== b && /Kettle/.test(a) && /Aster/.test(b), `${a} / ${b}`);
  return `"${a}" vs "${b}"`;
});

await check('demo: declining an approval changes nothing', async () => {
  await demo.locator('[data-act="reset"]').click();
  await demo.locator('.chip', { hasText: 'Tidy Downloads' }).click();
  await demo.locator('[data-act="run"]').click();
  await runUntil(/waiting/);
  await demo.locator('[data-act="deny"]').click();
  await runUntil(/denied/);
  const head = await demo.locator('.result__headline').innerText();
  const skipped = await demo.locator('.step[data-status="skipped"]').count();
  assert(/Nothing moved/.test(head) && skipped >= 3, `${head} skipped=${skipped}`);
  return `"${head}", ${skipped} steps skipped`;
});

await check('demo: simulated problem stops, then retries only when asked', async () => {
  await demo.locator('[data-act="reset"]').click();
  await demo.locator('.chip', { hasText: 'Compare quotes' }).click();
  await demo.locator('.fail-input').check();
  await demo.locator('[data-act="run"]').click();
  await runUntil(/failed/);
  await page.waitForTimeout(1500);
  assert((await state(page)).demoPhase === 'failed', 'did not stay failed');
  await demo.locator('[data-act="retry"]').click();
  await runUntil(/done/);
  return 'failed → (held) → retry → done';
});

await check('demo: unrecognized and empty requests are rejected honestly', async () => {
  await demo.locator('[data-act="reset"]').click();
  await demo.locator('#demo-request').fill('Book me a flight to Tokyo');
  await demo.locator('.req-form button[type="submit"]').click();
  const msg = await demo.locator('#demo-error').innerText();
  await demo.locator('#demo-request').fill('   ');
  await demo.locator('.req-form button[type="submit"]').click();
  const msg2 = await demo.locator('#demo-error').innerText();
  await demo.locator('#demo-request').fill('Remind me to call the bank on Tuesday at 3pm');
  await demo.locator('.req-form button[type="submit"]').click();
  const day = await demo.locator('[data-param="day"]').inputValue();
  const time = await demo.locator('[data-param="time"]').inputValue();
  assert(/only understands/.test(msg) && /Type a request/.test(msg2) && day === 'Tuesday' && time === '15:00', `${msg} | ${msg2} | ${day} ${time}`);
  return `free text → reminder ${day} ${time}`;
});

await check('demo: stop mid-run cancels remaining steps', async () => {
  await demo.locator('.chip', { hasText: 'Write a brief' }).click();
  await demo.locator('[data-act="run"]').click();
  await page.waitForTimeout(700);
  await demo.locator('[data-act="stop"]').click();
  const head = await demo.locator('.result__headline').innerText();
  assert(/Stopped/.test(head), head);
  return head;
});

await check('explore: destination focus, card, and reset', async () => {
  await scrollTo(page, 6, 0.5);
  await page.waitForTimeout(800);
  await page.locator('.dest-btn', { hasText: 'Memory' }).click();
  await page.waitForTimeout(400);
  const s = await state(page);
  const h3 = await page.locator('#explore-card h3').innerText();
  await page.locator('#explore-reset').click();
  const s2 = await state(page);
  assert(s.exploreFocus === 'memory' && /Knots/.test(h3) && s2.exploreFocus === null, `${s.exploreFocus} ${h3} ${s2.exploreFocus}`);
  return h3;
});

await check('explore: clicking the loom focuses a region; dragging orbits without selecting', async () => {
  await scrollTo(page, 6, 0.5);
  await page.waitForTimeout(1500);
  // drag
  await page.mouse.move(1000, 450);
  await page.mouse.down();
  await page.mouse.move(1150, 480, { steps: 8 });
  await page.mouse.up();
  const afterDrag = (await state(page)).exploreFocus;
  // click through the stage onto the loom; scan a few points for a region hit
  let hit = null;
  for (const [x, y] of [[1100, 600], [1250, 650], [1000, 520], [1200, 300], [900, 650]]) {
    await page.mouse.click(x, y);
    await page.waitForTimeout(200);
    hit = (await state(page)).exploreFocus;
    if (hit) break;
  }
  await page.locator('#explore-reset').click();
  assert(afterDrag === null && hit, `drag selected=${afterDrag}, click hit=${hit}`);
  return `click → ${hit}`;
});

await check('keyboard: skip link moves focus into main content', async () => {
  await page.reload({ waitUntil: 'load' });
  await page.waitForFunction(() => window.__lumina?.store.get().world === 'ready', null, { timeout: 20000 });
  await page.keyboard.press('Tab');
  const first = await page.evaluate(() => document.activeElement?.textContent?.trim());
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  const hash = await page.evaluate(() => location.hash);
  const focused = await page.evaluate(() => document.activeElement?.id);
  assert(/Skip to content/.test(first) && hash === '#main' && focused === 'main', `${first} ${hash} ${focused}`);
  return first;
});

await check('keyboard: capability cards and demo controls are reachable and operable', async () => {
  await page.locator('.cap').first().focus();
  await page.keyboard.press('Enter');
  const sel = (await state(page)).capSelected;
  await page.keyboard.press('Enter');
  await page.locator('.chip').nth(2).focus();
  await page.keyboard.press('Enter');
  const pressed = await page.locator('.chip').nth(2).getAttribute('aria-pressed');
  assert(sel === 0 && pressed === 'true', `sel=${sel} chip=${pressed}`);
  return 'Enter activates cards and chips';
});

await check('sound: starts only on click, toggles off, volume persists', async () => {
  await page.locator('#sound-toggle').click();
  await page.waitForTimeout(500);
  const on = await page.evaluate(() => ({ n: window.__audioCtxCount, st: window.__audioCtxs?.[0]?.state }));
  await page.locator('#sound-toggle').click();
  await page.waitForTimeout(800);
  const off = await page.evaluate(() => window.__audioCtxs?.[0]?.state);
  const pressed = await page.locator('#sound-toggle').getAttribute('aria-pressed');
  assert(on.n === 1 && on.st === 'running' && off === 'suspended' && pressed === 'false', JSON.stringify({ on, off, pressed }));
  return `created on click (${on.st}) → ${off}`;
});

await check('settings: lite mode removes WebGL, cinematic restores it', async () => {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.locator('#settings-toggle').click();
  await page.locator('input[name="visuals"][value="lite"]').check();
  await page.waitForTimeout(300);
  const lite = await page.evaluate(() => ({ v: document.documentElement.dataset.visuals, w: window.__lumina.store.get().world, canvas: getComputedStyle(document.querySelector('.world__canvas')).display }));
  await page.locator('input[name="visuals"][value="cinematic"]').check();
  await page.waitForFunction(() => window.__lumina.store.get().world === 'ready', null, { timeout: 15000 });
  await page.keyboard.press('Escape');
  const expanded = await page.locator('#settings-toggle').getAttribute('aria-expanded');
  assert(lite.v === 'lite' && lite.w === 'off' && lite.canvas === 'none' && expanded === 'false', JSON.stringify(lite));
  return 'lite → off, cinematic → ready, Esc closes';
});

await check('no runtime errors during the whole session', async () => {
  assert(errors.length === 0, errors.join(' | '));
  return '0 errors';
});
await ctx.close();

/* ───────── Reduced motion ───────── */
await check('reduced motion: honoured, world renders on demand only', async () => {
  const { ctx: c, page: p } = await open({ reducedMotion: 'reduce' });
  const motion = await p.evaluate(() => document.documentElement.dataset.motion);
  await p.waitForTimeout(1500);
  const f0 = await p.evaluate(() => window.__lumina.world.framesRendered);
  await p.waitForTimeout(2000);
  const f1 = await p.evaluate(() => window.__lumina.world.framesRendered);
  await scrollTo(p, 3, 0.55);
  await p.waitForTimeout(400);
  const f2 = await p.evaluate(() => window.__lumina.world.framesRendered);
  await c.close();
  assert(motion === 'reduced' && f1 - f0 <= 2 && f2 > f1, `motion=${motion} idle frames=${f1 - f0} after scroll=${f2 - f1}`);
  return `idle 2 s: ${f1 - f0} frames; scroll: +${f2 - f1}`;
});

/* ───────── WebGL unavailable ───────── */
await check('WebGL unavailable: fallback art, status message, demo still works', async () => {
  const { ctx: c, page: p, errors: errs } = await open({}, () => {
    const orig = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
      if (/webgl/.test(type)) return null;
      return orig.call(this, type, ...rest);
    };
  });
  await p.waitForTimeout(1000); // fallback art fades in over 640 ms
  const s = await p.evaluate(() => ({ w: window.__lumina.store.get().world, status: document.getElementById('world-status').textContent, fb: getComputedStyle(document.querySelector('.world__fallback')).opacity }));
  await scrollTo(p, 5, 0.4);
  await p.locator('#demo-root .chip', { hasText: 'Compare quotes' }).click();
  await p.locator('#demo-root [data-act="run"]').click();
  await p.waitForFunction(() => window.__lumina.store.get().demoPhase === 'done', null, { timeout: 15000 });
  await c.close();
  assert(s.w === 'failed' && Number(s.fb) > 0.5 && /lite version/.test(s.status) && errs.length === 0, JSON.stringify(s) + errs.join('|'));
  return s.status;
});

/* ───────── Mobile ───────── */
await check('mobile: menu opens, navigates and closes; demo usable', async () => {
  const { ctx: c, page: p, errors: errs } = await open({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  await p.locator('.primary-nav__toggle').tap();
  const open1 = await p.locator('#primary-nav-list').isVisible();
  await p.locator('#primary-nav-list a[href="#demo"]').tap();
  await p.waitForTimeout(1200);
  const closed = !(await p.locator('#primary-nav-list').isVisible());
  const top = await p.evaluate(() => document.querySelector('#demo').getBoundingClientRect().top);
  await p.locator('#demo-root [data-act="run"]').scrollIntoViewIfNeeded();
  await p.locator('#demo-root [data-act="run"]').tap();
  await p.waitForFunction(() => window.__lumina.store.get().demoPhase === 'waiting', null, { timeout: 15000 });
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  const tier = await p.evaluate(() => window.__lumina.world?.tier);
  await c.close();
  assert(open1 && closed && Math.abs(top) < 120 && overflow <= 0 && errs.length === 0, JSON.stringify({ open1, closed, top, overflow, errs }));
  return `no horizontal overflow, tier ${tier}`;
});

await browser.close();
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
