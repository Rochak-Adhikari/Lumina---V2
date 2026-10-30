import { existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import os from 'node:os';

/** Locates the Chromium build that Playwright has already cached on this machine. */
export function chromiumPath() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  const base = join(os.homedir(), 'AppData', 'Local', 'ms-playwright');
  const dirs = existsSync(base) ? readdirSync(base).filter((d) => /^chromium-\d+$/.test(d)).sort().reverse() : [];
  for (const d of dirs) {
    const p = join(base, d, 'chrome-win64', 'chrome.exe');
    if (existsSync(p)) return p;
  }
  throw new Error('No cached Chromium found; set CHROMIUM_PATH.');
}
