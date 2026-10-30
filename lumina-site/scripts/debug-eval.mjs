// Dev-only: run an expression in the page (dev server) and screenshot.
// Usage: node scripts/debug-eval.mjs "<js expression returning JSON-able>" [shot.png]
import { chromium } from 'playwright-core';
import { chromiumPath } from './shoot-path.mjs';

const expr = process.argv[2] ?? '1';
const shot = process.argv[3];
const browser = await chromium.launch({ executablePath: chromiumPath(), headless: true, args: ['--use-angle=d3d11', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const logs = [];
page.on('console', (m) => logs.push(`${m.type()}: ${m.text()}`));
page.on('pageerror', (e) => logs.push(`pageerror: ${e}`));
await page.goto(process.env.URL ?? 'http://localhost:5183/');
await page.waitForFunction(() => window.__lumina?.store.get().world === 'ready', null, { timeout: 20000 });
await page.waitForTimeout(2500);
const res = await page.evaluate(`(async () => { ${expr} })()`);
await page.waitForTimeout(500);
if (shot) await page.screenshot({ path: shot });
console.log(JSON.stringify(res, null, 1));
console.log(logs.filter((l) => !l.includes('[vite]')).join('\n'));
await browser.close();
