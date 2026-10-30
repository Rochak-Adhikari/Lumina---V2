#!/usr/bin/env node
/**
 * scripts/verify_earth_history.mjs
 * 
 * Repeatable, bounded browser verification harness for Lumina Earth Local Time Intelligence
 * and Persistent Search History (P1.6).
 * Tests live single-page app at http://127.0.0.1:8764/ using Headless Chrome & CDP.
 */

import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';

const APP_URL = 'http://127.0.0.1:8764/';
const CDP_PORT = 9466;
const SCRATCH_DIR = resolve('scratch');

const CHROME_CANDIDATE_PATHS = [
  'C:\\Users\\Administrator\\AppData\\Local\\ms-playwright\\chromium-1248\\chrome-win64\\chrome.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
];

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

function findChromePath() {
  for (const p of CHROME_CANDIDATE_PATHS) {
    if (existsSync(p)) return p;
  }
  return null;
}

async function main() {
  console.log('========================================================================');
  console.log(' LUMINA EARTH — LOCAL TIME & SEARCH HISTORY VERIFICATION HARNESS (P1.6)');
  console.log('========================================================================\n');

  // 1. Check prerequisites
  console.log('[1/4] Checking environment prerequisites...');
  try {
    const res = await fetch(APP_URL, { signal: AbortSignal.timeout(3000) });
    if (!res.ok && res.status !== 200) {
      throw new Error(`Server returned status ${res.status}`);
    }
  } catch (err) {
    console.error('\n[PREREQUISITE ERROR] Lumina backend is not running at http://127.0.0.1:8764');
    process.exit(1);
  }
  console.log('  ✓ Backend server is active at http://127.0.0.1:8764');

  const chromePath = findChromePath();
  if (!chromePath) {
    console.error('\n[PREREQUISITE ERROR] No suitable Chromium executable found.');
    process.exit(1);
  }
  console.log(`  ✓ Browser engine located: ${chromePath}`);

  if (!existsSync(SCRATCH_DIR)) {
    mkdirSync(SCRATCH_DIR, { recursive: true });
  }

  // 2. Launch browser with CDP
  console.log('\n[2/4] Launching headless browser on CDP port', CDP_PORT);
  const chromeProcess = spawn(chromePath, [
    `--remote-debugging-port=${CDP_PORT}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--headless=new',
    'about:blank'
  ], { stdio: 'ignore' });

  const testResults = [];
  const logTest = (name, passed, details = '') => {
    testResults.push({ name, passed, details });
    const mark = passed ? '✓ PASS' : '✗ FAIL';
    console.log(`  ${mark}: ${name} ${details ? `(${details})` : ''}`);
  };

  try {
    let targets = null;
    for (let i = 0; i < 30; i++) {
      try {
        const res = await fetch(`http://127.0.0.1:${CDP_PORT}/json`);
        if (res.ok) {
          targets = await res.json();
          if (Array.isArray(targets) && targets.length > 0) break;
        }
      } catch (e) {}
      await sleep(200);
    }

    if (!targets || targets.length === 0) {
      throw new Error(`Failed to establish CDP connection on port ${CDP_PORT}`);
    }

    const pageTarget = targets.find(t => t.type === 'page') || targets[0];
    const ws = new WebSocket(pageTarget.webSocketDebuggerUrl);
    await new Promise((res, rej) => {
      ws.onopen = res;
      ws.onerror = rej;
    });

    let messageId = 0;
    const pendingRequests = new Map();
    const consoleLogs = [];
    const browserExceptions = [];

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.id && pendingRequests.has(data.id)) {
        pendingRequests.get(data.id)(data);
        pendingRequests.delete(data.id);
      }
      if (data.method === 'Runtime.consoleAPICalled') {
        const text = `console.${data.params.type}: ${data.params.args.map(a => a.value ?? a.description).join(' ')}`;
        consoleLogs.push(text);
      }
      if (data.method === 'Runtime.exceptionThrown') {
        const details = data.params.exceptionDetails;
        const desc = details?.exception?.description || details?.text || 'Uncaught exception';
        browserExceptions.push(desc);
      }
    };

    const cdpSend = (method, params = {}) => new Promise((res, rej) => {
      const id = ++messageId;
      pendingRequests.set(id, (response) => {
        if (response.error) rej(new Error(JSON.stringify(response.error)));
        else res(response);
      });
      ws.send(JSON.stringify({ id, method, params }));
    });

    const evalJs = async (expr) => {
      const res = await cdpSend('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
      if (res.result?.exceptionDetails) {
        console.warn('evalJs Exception:', expr, res.result.exceptionDetails.text);
      }
      return res.result?.result?.value;
    };

    const captureScreenshot = async (filename) => {
      const { result } = await cdpSend('Page.captureScreenshot', { format: 'png' });
      const outPath = join(SCRATCH_DIR, filename);
      writeFileSync(outPath, Buffer.from(result.data, 'base64'));
      console.log(`    ↳ Screenshot saved: ${outPath}`);
    };

    await cdpSend('Page.enable');
    await cdpSend('Runtime.enable');
    await cdpSend('Network.enable');

    console.log('\n[3/4] Navigating to Lumina SPA Shell...');
    await cdpSend('Page.navigate', { url: APP_URL });

    let spaReady = false;
    for (let i = 0; i < 40; i++) {
      await sleep(250);
      const health = await evalJs(`document.getElementById('runtime-health')?.textContent`);
      if (health === 'connected') {
        spaReady = true;
        break;
      }
    }
    logTest('Lumina shell DOM loaded with active WebSocket connection', spaReady);

    // 1. Open Earth Workspace
    console.log('\n--- Step 1: Open Earth Workspace ---');
    await evalJs('document.getElementById("earth-open").click()');
    let earthReady = false;
    for (let i = 0; i < 40; i++) {
      await sleep(250);
      const state = await evalJs(`document.getElementById('earth-stage')?.dataset.earthState`);
      if (state === 'ready') {
        earthReady = true;
        break;
      }
    }

    const earthVisible = await evalJs('!document.getElementById("earth-workspace").hidden');
    logTest('Earth workspace active and ready', earthVisible && earthReady);

    // Clean prior search history in backend before testing
    await evalJs(`(async () => {
      const token = window.__luminaConfig?.token;
      const headers = token ? { 'X-Lumina-Token': token } : {};
      await fetch('/api/earth/history', { method: 'DELETE', headers });
    })()`);
    await sleep(300);

    // 2. Search Kathmandu & Validate Local Time (UTC+05:45)
    console.log('\n--- Step 2: Search Kathmandu & Validate Local Time (UTC+05:45) ---');
    await evalJs(`(() => {
      const input = document.getElementById('earth-search-input');
      input.value = 'Kathmandu';
      document.getElementById('earth-search-form').dispatchEvent(new Event('submit', { cancelable: true }));
    })()`);

    let candidateCount = 0;
    for (let i = 0; i < 30; i++) {
      candidateCount = await evalJs('document.querySelectorAll(".earth-result-btn").length');
      if (candidateCount > 0) break;
      await sleep(200);
    }
    logTest('Search returns candidates for Kathmandu', candidateCount > 0);

    // Select candidate
    await evalJs('document.querySelector(".earth-result-btn")?.click()');
    await sleep(600);

    // Verify Local Time widget
    const timeWrapVisible = await evalJs('!document.getElementById("earth-local-time-wrap")?.hidden');
    logTest('Local time widget becomes visible in location card', timeWrapVisible);

    const clockText = await evalJs('document.getElementById("earth-local-time-clock")?.textContent');
    const clockValid = /^\d{2}:\d{2}:\d{2}$/.test(clockText);
    logTest('Live digital clock ticks with tabular format', clockValid, clockText);

    const dateText = await evalJs('document.getElementById("earth-local-time-date")?.textContent');
    const dateValid = dateText && dateText.length > 5;
    logTest('Calendar date formatted accurately', dateValid, dateText);

    const tzBadge = await evalJs('document.getElementById("earth-local-time-tz")?.textContent');
    const tzKathmandu = tzBadge && tzBadge.includes('Asia/Kathmandu') && tzBadge.includes('UTC+05:45');
    logTest('Timezone badge displays Asia/Kathmandu with UTC+05:45 offset', tzKathmandu, tzBadge);

    await captureScreenshot('p16_local_time_kathmandu.png');

    // 3. Search Tokyo & Validate Timezone Transition (UTC+09:00)
    console.log('\n--- Step 3: Search Tokyo & Validate Timezone Transition (UTC+09:00) ---');
    await evalJs(`(() => {
      const input = document.getElementById('earth-search-input');
      input.value = 'Tokyo';
      document.getElementById('earth-search-form').dispatchEvent(new Event('submit', { cancelable: true }));
    })()`);

    candidateCount = 0;
    for (let i = 0; i < 30; i++) {
      candidateCount = await evalJs('document.querySelectorAll(".earth-result-btn").length');
      if (candidateCount > 0) break;
      await sleep(200);
    }
    logTest('Search returns candidates for Tokyo', candidateCount > 0);

    await evalJs('document.querySelector(".earth-result-btn")?.click()');
    await sleep(600);

    const tzTokyo = await evalJs('document.getElementById("earth-local-time-tz")?.textContent');
    const isTokyo = tzTokyo && tzTokyo.includes('Asia/Tokyo') && tzTokyo.includes('UTC+09:00');
    logTest('Timezone updates seamlessly to Asia/Tokyo (UTC+09:00)', isTokyo, tzTokyo);

    await captureScreenshot('p16_local_time_tokyo.png');

    // 4. Open Atlas & Inspect Search History Tab
    console.log('\n--- Step 4: Atlas Panel & Recent Searches Tab ---');
    // Open Atlas panel if not already open
    const isAtlasOpen = await evalJs('!document.getElementById("earth-atlas-panel")?.hidden');
    if (!isAtlasOpen) {
      await evalJs('document.getElementById("earth-toggle-atlas").click()');
      await sleep(400);
    }

    // Switch to Recent Searches tab
    await evalJs('document.getElementById("earth-atlas-tab-history").click()');
    await sleep(500);

    const tabHistoryActive = await evalJs('document.getElementById("earth-atlas-tab-history").classList.contains("active")');
    const historySectionVisible = await evalJs('!document.getElementById("earth-atlas-history-section").hidden');
    logTest('Switching to Recent Searches tab displays history section', tabHistoryActive && historySectionVisible);

    let historyItemCount = 0;
    for (let i = 0; i < 20; i++) {
      historyItemCount = await evalJs('document.querySelectorAll("#earth-history-list .earth-history-card").length');
      if (historyItemCount >= 2) break;
      await sleep(200);
    }
    logTest('Persistent search history displays recorded places', historyItemCount >= 2, `${historyItemCount} entries`);

    await captureScreenshot('p16_history_tab_populated.png');

    // 5. Revisit Kathmandu from History
    console.log('\n--- Step 5: Revisit Location from History ---');
    // Click on Kathmandu in history list
    const revisitTriggered = await evalJs(`(() => {
      const cards = Array.from(document.querySelectorAll("#earth-history-list .earth-history-card"));
      const ktmCard = cards.find(c => c.querySelector(".earth-history-card-title")?.textContent?.includes("Kathmandu"));
      if (!ktmCard) return false;
      const btn = ktmCard.querySelector(".earth-btn-primary");
      btn ? btn.click() : ktmCard.click();
      return true;
    })()`);
    logTest('Clicking Revisit on Kathmandu in history triggers navigation', revisitTriggered);
    await sleep(700);

    const revisitedTz = await evalJs('document.getElementById("earth-local-time-tz")?.textContent');
    const revertedToKtm = revisitedTz && revisitedTz.includes('Asia/Kathmandu');
    logTest('Revisiting from history accurately restores local time clock and timezone', revertedToKtm, revisitedTz);

    await captureScreenshot('p16_history_revisit.png');

    // 6. Delete Individual History Item
    console.log('\n--- Step 6: Delete Individual History Item ---');
    const deleteTriggered = await evalJs(`(() => {
      const cards = Array.from(document.querySelectorAll("#earth-history-list .earth-history-card"));
      const ktmCard = cards.find(c => c.querySelector(".earth-history-card-title")?.textContent?.includes("Kathmandu"));
      if (!ktmCard) return false;
      const delBtn = ktmCard.querySelector(".earth-btn-danger-outline");
      if (!delBtn) return false;
      delBtn.click();
      return true;
    })()`);
    logTest('Delete button on history card triggers deletion', deleteTriggered);
    await sleep(500);

    const postDeleteCount = await evalJs('document.querySelectorAll("#earth-history-list .earth-history-card").length');
    logTest('History card removed immediately from list', postDeleteCount === historyItemCount - 1, `Now ${postDeleteCount} entries`);

    // 7. Clear All History with Confirmation
    console.log('\n--- Step 7: Clear All History Flow ---');
    await evalJs('document.getElementById("earth-history-clear-btn").click()');
    await sleep(200);

    const confirmVisible = await evalJs('!document.getElementById("earth-history-confirm").hidden');
    logTest('Clear All button displays confirmation banner', confirmVisible);
    await captureScreenshot('p16_history_clear_confirm.png');

    // Confirm deletion
    await evalJs('document.getElementById("earth-history-confirm-btn").click()');
    await sleep(500);

    const finalHistoryCount = await evalJs('document.querySelectorAll("#earth-history-list .earth-history-card").length');
    const emptyStateVisible = await evalJs('!document.getElementById("earth-history-empty").hidden');
    logTest('Confirming clear removes all search history and reveals empty state', finalHistoryCount === 0 && emptyStateVisible);
    await captureScreenshot('p16_history_empty.png');

    // 8. Error and exception checks
    console.log('\n--- Step 8: Diagnostics & Integrity Verification ---');
    logTest('No unhandled browser exceptions occurred', browserExceptions.length === 0, `${browserExceptions.length} exceptions`);
    if (browserExceptions.length > 0) {
      console.warn('  Browser exceptions:', browserExceptions);
    }

  } finally {
    console.log('\n[4/4] Cleaning up headless browser instance...');
    chromeProcess.kill('SIGTERM');
  }

  // Summary
  const passedCount = testResults.filter(t => t.passed).length;
  const totalCount = testResults.length;
  console.log('\n========================================================================');
  console.log(` VERIFICATION SUMMARY: ${passedCount}/${totalCount} tests passed`);
  console.log('========================================================================\n');

  if (passedCount < totalCount) {
    process.exit(1);
  }
}

main().catch(err => {
  console.error('\nHarness failure:', err);
  process.exit(1);
});
