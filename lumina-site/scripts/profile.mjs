// CPU profile of a scripted scroll under CPU throttling; prints the hottest functions by self time.
// Usage: node scripts/profile.mjs [--url http://localhost:4183/] [--cpu 4]
import { chromium } from 'playwright-core';
import { chromiumPath } from './shoot-path.mjs';

const argv = process.argv.slice(2);
const arg = (k, d) => (argv.includes(`--${k}`) ? argv[argv.indexOf(`--${k}`) + 1] : d);
const url = arg('url', 'http://localhost:4183/');
const cpu = Number(arg('cpu', 4));

const browser = await chromium.launch({ executablePath: chromiumPath(), headless: true, args: ['--use-angle=d3d11', '--ignore-gpu-blocklist'] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const cdp = await ctx.newCDPSession(page);
await page.goto(url, { waitUntil: 'load' });
await page.waitForFunction(() => window.__lumina?.store.get().world === 'ready');
await page.waitForTimeout(3000);
await cdp.send('Emulation.setCPUThrottlingRate', { rate: cpu });
await cdp.send('Profiler.enable');
await cdp.send('Profiler.setSamplingInterval', { interval: 200 });
await cdp.send('Profiler.start');
const frames = await page.evaluate(async () => {
  document.documentElement.style.scrollBehavior = 'auto';
  const max = document.documentElement.scrollHeight - innerHeight;
  const out = [];
  let last = performance.now();
  let y = 0;
  await new Promise((res) => {
    const tick = (now) => {
      out.push(now - last);
      last = now;
      y += max / 300;
      window.scrollTo(0, y);
      if (y >= max) return res();
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
  out.shift();
  return out;
});
const { profile } = await cdp.send('Profiler.stop');
await browser.close();

const byId = new Map(profile.nodes.map((n) => [n.id, n]));
const self = new Map();
const dt = profile.timeDeltas;
profile.samples.forEach((id, i) => {
  const n = byId.get(id);
  const key = `${n.callFrame.functionName || '(anonymous)'} ${n.callFrame.url.split('/').pop()}:${n.callFrame.lineNumber}`;
  self.set(key, (self.get(key) ?? 0) + (dt[i] ?? 0));
});
const total = [...self.values()].reduce((a, b) => a + b, 0);
const top = [...self.entries()].sort((a, b) => b[1] - a[1]).slice(0, 18);
const s = [...frames].sort((a, b) => a - b);
console.log(`frames ${frames.length}, p50 ${s[Math.floor(s.length * 0.5)].toFixed(1)} ms, p95 ${s[Math.floor(s.length * 0.95)].toFixed(1)} ms`);
for (const [k, v] of top) console.log(`${((v / total) * 100).toFixed(1).padStart(5)}%  ${(v / 1000).toFixed(0).padStart(6)} ms  ${k}`);
