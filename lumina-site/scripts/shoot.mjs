// Visual inspection helper: opens the site in the locally cached Playwright Chromium,
// scrolls to chapter positions and saves screenshots + world stats.
// Usage: node scripts/shoot.mjs [--url http://localhost:5183/] [--w 1440] [--h 900]
//        [--motion full|reduced] [--headed] [--shots "0:0,1:0.5,3:0.5"] [--out test-artifacts/shots]
import { chromium } from 'playwright-core';
import { mkdirSync } from "node:fs";
import { chromiumPath } from "./shoot-path.mjs";
import { join } from 'node:path';


const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => {
    if (a.startsWith('--')) acc.push([a.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : true]);
    return acc;
  }, []),
);

const url = args.url ?? 'http://localhost:5183/';
const w = Number(args.w ?? 1440);
const h = Number(args.h ?? 900);
const out = args.out ?? 'test-artifacts/shots';
const shots = String(args.shots ?? '0:0').split(',').map((s) => s.split(':').map(Number));
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({
  executablePath: chromiumPath(),
  headless: !args.headed,
  args: ['--use-angle=d3d11', '--enable-gpu-rasterization', '--ignore-gpu-blocklist'],
});
const ctx = await browser.newContext({
  viewport: { width: w, height: h },
  deviceScaleFactor: Number(args.dpr ?? 1),
  reducedMotion: args.motion === 'reduced' ? 'reduce' : 'no-preference',
  isMobile: Boolean(args.mobile),
  hasTouch: Boolean(args.mobile),
});
if (args.lite) await ctx.addInitScript(() => localStorage.setItem('lumina.visuals', 'lite'));
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
await page.goto(url, { waitUntil: 'load' });
await page.waitForFunction(() => ['ready', 'failed', 'off'].includes(window.__lumina?.store.get().world), null, { timeout: 20000 });
await page.waitForTimeout(Number(args.settle ?? 3500));

for (const [chapter, p] of shots) {
  await page.evaluate(([c, pp]) => {
    document.documentElement.style.scrollBehavior = 'auto';
    window.scrollTo(0, window.__lumina.scrollForChapter(c, pp));
  }, [chapter, p]);
  await page.waitForTimeout(Number(args.wait ?? 1600));
  const file = join(out, `${w}x${h}-${args.motion ?? 'full'}${args.lite ? '-lite' : ''}-c${chapter}-${String(p).replace('.', '_')}.png`);
  await page.screenshot({ path: file });
  console.log('shot', file);
}
const stats = await page.evaluate(() => {
  const s = window.__lumina.world;
  return s && { tier: s.tier, gpu: s.gpu, dpr: s.dpr, frames: s.framesRendered, drawCalls: s.drawCalls, tris: s.triangles, downgrades: s.downgrades };
});
console.log(JSON.stringify({ stats, errors }, null, 1));
await browser.close();
