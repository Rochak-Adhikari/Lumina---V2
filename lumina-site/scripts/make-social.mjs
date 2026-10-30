// Renders the social preview image (1200×630) from the live hero and the 180×180 touch icon from favicon.svg.
// Usage: node scripts/make-social.mjs [--url http://localhost:4183/]
import { chromium } from 'playwright-core';
import { readFileSync } from 'node:fs';
import { chromiumPath } from './shoot-path.mjs';

const argv = process.argv.slice(2);
const url = argv.includes('--url') ? argv[argv.indexOf('--url') + 1] : 'http://localhost:4183/';
const browser = await chromium.launch({ executablePath: chromiumPath(), headless: true, args: ['--use-angle=d3d11', '--ignore-gpu-blocklist'] });

const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
await page.goto(url, { waitUntil: 'load' });
await page.waitForFunction(() => window.__lumina?.store.get().world === 'ready');
await page.addStyleTag({ content: '.site-header,.chapter-rail,.scroll-cue,.hero__fine,.cta-row{display:none!important}' });
await page.waitForTimeout(4200);
await page.screenshot({ path: 'public/og-image.png' });

const svg = readFileSync('public/favicon.svg', 'utf8');
const icon = await browser.newPage({ viewport: { width: 180, height: 180 } });
await icon.setContent(`<html><body style="margin:0;background:#07080b">${svg.replace('<svg ', '<svg width="180" height="180" ')}</body></html>`);
await icon.screenshot({ path: 'public/apple-touch-icon.png' });
await browser.close();
console.log('wrote public/og-image.png (convert to og-image.jpg with ffmpeg) and public/apple-touch-icon.png');
