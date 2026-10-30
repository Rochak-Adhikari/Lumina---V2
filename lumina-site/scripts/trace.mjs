// Chrome trace of a throttled scripted scroll; aggregates renderer main-thread event time by name.
// Usage: node scripts/trace.mjs [--url http://localhost:4183/] [--cpu 4]
import { chromium } from 'playwright-core';
import { chromiumPath } from './shoot-path.mjs';

const argv = process.argv.slice(2);
const arg = (k, d) => (argv.includes(`--${k}`) ? argv[argv.indexOf(`--${k}`) + 1] : d);
const url = arg('url', 'http://localhost:4183/');
const cpu = Number(arg('cpu', 4));
const browser = await chromium.launch({ executablePath: chromiumPath(), headless: true, args: ['--use-angle=d3d11', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(url, { waitUntil: 'load' });
await page.waitForFunction(() => window.__lumina?.store.get().world === 'ready');
await page.waitForTimeout(3000);
const cdp = await page.context().newCDPSession(page);
await cdp.send('Emulation.setCPUThrottlingRate', { rate: cpu });
await browser.startTracing(page, { categories: ['devtools.timeline', 'disabled-by-default-devtools.timeline'] });
await page.evaluate(async () => {
  document.documentElement.style.scrollBehavior = 'auto';
  const max = document.documentElement.scrollHeight - innerHeight;
  let y = 0;
  await new Promise((res) => {
    const tick = () => {
      y += max / 300;
      window.scrollTo(0, y);
      if (y >= max) return res();
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
});
const buf = await browser.stopTracing();
await browser.close();
const { traceEvents } = JSON.parse(buf.toString());
const main = traceEvents.find((e) => e.name === 'thread_name' && e.args?.name === 'CrRendererMain');
const totals = new Map();
for (const e of traceEvents) {
  if (e.ph !== 'X' || !e.dur || (main && (e.pid !== main.pid || e.tid !== main.tid))) continue;
  totals.set(e.name, (totals.get(e.name) ?? 0) + e.dur / 1000);
}
for (const [k, v] of [...totals.entries()].sort((a, b) => b[1] - a[1]).slice(0, 16)) console.log(`${v.toFixed(0).padStart(7)} ms  ${k}`);
