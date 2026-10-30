// Performance measurement against a running production preview.
// Usage: node scripts/perf.mjs [--url http://localhost:4183/] [--w 1440] [--h 900] [--mobile] [--cpu 4]
// Reports load milestones, transfer sizes, frame times during a scripted scroll
// through the whole journey (both directions), and JS heap growth across repeated passes.
import { chromium } from 'playwright-core';
import { chromiumPath } from './shoot-path.mjs';

const argv = process.argv.slice(2);
const arg = (k, d) => (argv.includes(`--${k}`) ? argv[argv.indexOf(`--${k}`) + 1] : d);
const url = arg('url', 'http://localhost:4183/');
const w = Number(arg('w', 1440));
const h = Number(arg('h', 900));
const mobile = argv.includes('--mobile');
const cpu = Number(arg('cpu', 1));

const browser = await chromium.launch({
  executablePath: chromiumPath(),
  headless: true,
  args: ['--use-angle=d3d11', '--ignore-gpu-blocklist', '--enable-precise-memory-info', '--js-flags=--expose-gc'],
});
const ctx = await browser.newContext({
  viewport: { width: w, height: h },
  deviceScaleFactor: mobile ? 2 : 1,
  isMobile: mobile,
  hasTouch: mobile,
  reducedMotion: 'no-preference',
});
const page = await ctx.newPage();
const cdp = await ctx.newCDPSession(page);
await cdp.send('Network.enable');
await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
if (cpu > 1) await cdp.send('Emulation.setCPUThrottlingRate', { rate: cpu });

await page.addInitScript(() => {
  window.__lcp = 0;
  new PerformanceObserver((l) => {
    for (const e of l.getEntries()) window.__lcp = e.startTime;
  }).observe({ type: 'largest-contentful-paint', buffered: true });
});

const t0 = Date.now();
await page.goto(url, { waitUntil: 'load' });
await page.waitForFunction(() => window.__lumina?.store.get().world === 'ready', null, { timeout: 30000 });
const loadWall = Date.now() - t0;
await page.waitForTimeout(3500);

const load = await page.evaluate(() => {
  const nav = performance.getEntriesByType('navigation')[0];
  const paint = Object.fromEntries(performance.getEntriesByType('paint').map((p) => [p.name, Math.round(p.startTime)]));
  const res = performance.getEntriesByType('resource');
  const by = (re) => res.filter((r) => re.test(r.name)).reduce((a, r) => a + (r.transferSize || r.encodedBodySize || 0), 0);
  const largest = [...res].sort((a, b) => (b.transferSize || b.encodedBodySize) - (a.transferSize || a.encodedBodySize)).slice(0, 5)
    .map((r) => `${r.name.split('/').pop()} ${Math.round((r.transferSize || r.encodedBodySize) / 1024)} KB`);
  return {
    ttfb: Math.round(nav.responseStart),
    domContentLoaded: Math.round(nav.domContentLoadedEventEnd),
    load: Math.round(nav.loadEventEnd),
    ...paint,
    lcp: Math.round(window.__lcp),
    worldFirstFrame: Math.round(window.__lumina.world.firstFrameAt),
    worldReady: window.__lumina.perf.worldReadyMs,
    tier: window.__lumina.world.tier,
    dpr: window.__lumina.world.dpr,
    gpu: window.__lumina.world.gpu,
    transferKB: {
      html: Math.round((nav.transferSize || 0) / 1024),
      js: Math.round(by(/\.js(\?|$)/) / 1024),
      css: Math.round(by(/\.css(\?|$)/) / 1024),
      fonts: Math.round(by(/\.woff2?(\?|$)/) / 1024),
      total: Math.round((by(/./) + (nav.transferSize || 0)) / 1024),
    },
    requests: res.length + 1,
    failed: res.filter((r) => r.responseStatus >= 400).map((r) => r.name),
    largest,
  };
});

// Frame timing during a continuous scripted scroll down and back up.
const heap = async () => {
  await page.evaluate(() => window.gc?.());
  return page.evaluate(() => Math.round((performance.memory?.usedJSHeapSize ?? 0) / 1048576 * 10) / 10);
};
const heap0 = await heap();
const passes = [];
for (let pass = 0; pass < 3; pass++) {
  const r = await page.evaluate(async () => {
    document.documentElement.style.scrollBehavior = 'auto';
    const max = document.documentElement.scrollHeight - innerHeight;
    const frames = [];
    let last = performance.now();
    let y = 0;
    let dir = 1;
    const step = max / 420; // ~7 s down, ~7 s up at 60 Hz
    await new Promise((resolve) => {
      const tick = (now) => {
        frames.push(now - last);
        last = now;
        y += step * dir;
        if (y >= max) dir = -1;
        window.scrollTo(0, Math.max(0, Math.min(max, y)));
        if (dir === -1 && y <= 0) return resolve();
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    frames.shift();
    const s = [...frames].sort((a, b) => a - b);
    const q = (p) => Math.round(s[Math.min(s.length - 1, Math.floor(p * s.length))] * 10) / 10;
    return {
      frames: frames.length,
      avgMs: Math.round((frames.reduce((a, b) => a + b, 0) / frames.length) * 10) / 10,
      p50: q(0.5),
      p95: q(0.95),
      p99: q(0.99),
      over33: frames.filter((f) => f > 33.4).length,
      over50: frames.filter((f) => f > 50).length,
      downgrades: window.__lumina.world.downgrades,
      dprAfter: window.__lumina.world.dpr,
    };
  });
  passes.push(r);
}
const heap1 = await heap();

// Idle cost: frames rendered per second when nothing changes (motion on → ambient shimmer cap).
const idle = await page.evaluate(async () => {
  window.scrollTo(0, 0);
  await new Promise((r) => setTimeout(r, 1500));
  const a = window.__lumina.world.framesRendered;
  await new Promise((r) => setTimeout(r, 3000));
  return Math.round(((window.__lumina.world.framesRendered - a) / 3) * 10) / 10;
});

console.log(JSON.stringify({ viewport: `${w}x${h}${mobile ? ' mobile' : ''}`, cpuThrottle: cpu, loadWallMs: loadWall, load, scrollPasses: passes, heapMB: { before: heap0, after3Passes: heap1 }, idleRenderFps: idle }, null, 1));
await browser.close();
