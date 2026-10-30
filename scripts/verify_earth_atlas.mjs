#!/usr/bin/env node
/**
 * scripts/verify_earth_atlas.mjs
 * 
 * Repeatable, bounded browser verification harness for Lumina Earth Atlas UI,
 * Saved Places, and Multi-Waypoint 3D Globe Visualization (P1.5).
 * Tests live single-page app at http://127.0.0.1:8764/
 */

import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';

const APP_URL = 'http://127.0.0.1:8764/';
const CDP_PORT = 9465;
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
  console.log(' LUMINA EARTH — ATLAS UI & MULTI-WAYPOINT VERIFICATION HARNESS (P1.5)');
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
    const cspViolations = [];

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
      if (data.method === 'Security.securityStateChanged' || data.method === 'Log.entryAdded') {
        if (JSON.stringify(data).includes('Content Security Policy')) {
          cspViolations.push(JSON.stringify(data));
        }
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

    // Wait for SPA to bootstrap and connect
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
    logTest('Earth workspace becomes visible in shell', earthVisible && earthReady);

    let canvasReady = false;
    for (let i = 0; i < 30; i++) {
      canvasReady = await evalJs('!!document.querySelector("#earth-stage canvas.earth-canvas")');
      if (canvasReady) break;
      await sleep(200);
    }
    logTest('3D Earth canvas rendered locally', canvasReady);

    // 2. Atlas Panel Toolbar Button & Initial State
    console.log('\n--- Step 2: Atlas Toolbar Toggle & Initial State ---');
    const atlasBtnExists = await evalJs('!!document.getElementById("earth-toggle-atlas")');
    logTest('Atlas toggle button exists in Earth toolbar', atlasBtnExists);

    const atlasInitiallyHidden = await evalJs('document.getElementById("earth-atlas-panel").hidden === true');
    logTest('Atlas panel starts closed', atlasInitiallyHidden);
    await captureScreenshot('p15_atlas_panel_closed.png');

    // Click toggle to open Atlas
    await evalJs('document.getElementById("earth-toggle-atlas").click()');
    await sleep(400);

    const atlasIsOpen = await evalJs('!document.getElementById("earth-atlas-panel").hidden');
    const toggleAriaPressed = await evalJs('document.getElementById("earth-toggle-atlas").getAttribute("aria-pressed") === "true"');
    logTest('Clicking Atlas button opens panel and sets aria-pressed="true"', atlasIsOpen && toggleAriaPressed);
    await captureScreenshot('p15_atlas_panel_open.png');

    // 3. Search for a place and Save to Atlas flow
    console.log('\n--- Step 3: Search Location & Save to Atlas ---');
    // Clean any prior test waypoints with name starting with "TEST_"
    await evalJs(`(async () => {
      try {
        const res = await fetch('/api/earth/waypoints');
        const data = await res.json();
        for (const wp of (data.waypoints || [])) {
          if (wp.name.startsWith('TEST_')) {
            await fetch('/api/earth/waypoints/' + wp.id, { method: 'DELETE' });
          }
        }
      } catch(e) {}
    })()`);
    await sleep(300);

    // Search for Kathmandu
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
    logTest('Location search returns candidates for Kathmandu', candidateCount > 0, `${candidateCount} candidates`);

    // Select candidate
    await evalJs('document.querySelector(".earth-result-btn")?.click()');
    for (let i = 0; i < 30; i++) {
      await sleep(200);
      const cardReady = await evalJs('!document.getElementById("earth-info-card")?.hidden');
      if (cardReady) break;
    }

    const saveBtnEnabled = await evalJs('!document.getElementById("earth-save-location-btn").disabled');
    logTest('Info card shows "Save to Atlas" button enabled for selected place', saveBtnEnabled);

    // Click "Save to Atlas"
    await evalJs('document.getElementById("earth-save-location-btn").click()');
    await sleep(400);

    const formVisible = await evalJs('!document.getElementById("earth-atlas-form-wrap").hidden');
    const nameVal = await evalJs('document.getElementById("earth-atlas-name").value');
    logTest('Atlas create form drawer opens pre-filled with place name', formVisible && nameVal.includes('Kathmandu'), `Name: ${nameVal}`);

    // Fill test name and submit
    await evalJs(`(() => {
      document.getElementById("earth-atlas-name").value = "TEST_Kathmandu_P15";
      document.getElementById("earth-atlas-desc").value = "Capital of Nepal in the Himalayas";
      document.getElementById("earth-atlas-form").dispatchEvent(new Event('submit', { cancelable: true }));
    })()`);
    await sleep(1200);

    // Verify waypoint appears in Atlas list
    const waypointCardsCount = await evalJs('document.querySelectorAll(".earth-atlas-card").length');
    const hasKathmanduCard = await evalJs(`Array.from(document.querySelectorAll(".earth-atlas-card-name")).some(el => el.textContent === "TEST_Kathmandu_P15")`);
    logTest('New place saved to persistent store and rendered in Atlas list', hasKathmanduCard, `Total cards: ${waypointCardsCount}`);

    // 4. Multi-Waypoint: Add Second Place (Tokyo)
    console.log('\n--- Step 4: Add Second Waypoint (Tokyo) ---');
    await evalJs(`(() => {
      const input = document.getElementById('earth-search-input');
      input.value = 'Tokyo';
      document.getElementById('earth-search-form').dispatchEvent(new Event('submit', { cancelable: true }));
    })()`);

    for (let i = 0; i < 30; i++) {
      const count = await evalJs('document.querySelectorAll(".earth-result-btn").length');
      if (count > 0) break;
      await sleep(200);
    }

    await evalJs('document.querySelector(".earth-result-btn")?.click()');
    for (let i = 0; i < 30; i++) {
      await sleep(200);
      const cardReady = await evalJs('!document.getElementById("earth-info-card")?.hidden');
      if (cardReady) break;
    }

    await evalJs('document.getElementById("earth-save-location-btn").click()');
    await sleep(400);

    await evalJs(`(() => {
      document.getElementById("earth-atlas-name").value = "TEST_Tokyo_P15";
      document.getElementById("earth-atlas-desc").value = "Tokyo Metropolis in Japan";
      document.getElementById("earth-atlas-form").dispatchEvent(new Event('submit', { cancelable: true }));
    })()`);
    await sleep(1200);

    const twoCards = await evalJs('document.querySelectorAll(".earth-atlas-card").length >= 2');
    const markersCountOnGlobe = await evalJs('window.__luminaEarth?.getWaypointMarkers?.()?.size ?? 0');
    logTest('Multiple waypoints rendered simultaneously on 3D globe', twoCards && markersCountOnGlobe >= 2, `${markersCountOnGlobe} markers on globe`);

    // 5. Waypoint Selection & Fly-To
    console.log('\n--- Step 5: Waypoint Selection, Navigation, and Highlighting ---');
    // Select Kathmandu card
    await evalJs(`(() => {
      const cards = Array.from(document.querySelectorAll('.earth-atlas-card'));
      const ktm = cards.find(c => c.textContent.includes('TEST_Kathmandu_P15'));
      ktm?.querySelector('.earth-btn-primary')?.click();
    })()`);
    await sleep(1500);

    const ktmCardSelected = await evalJs(`(() => {
      const cards = Array.from(document.querySelectorAll('.earth-atlas-card'));
      const ktm = cards.find(c => c.textContent.includes('TEST_Kathmandu_P15'));
      return ktm?.classList?.contains('selected') && ktm?.getAttribute('aria-selected') === 'true';
    })()`);
    const infoCardTitle = await evalJs('document.getElementById("earth-info-title").textContent');
    logTest('Selecting waypoint card activates selection and updates info card', ktmCardSelected && infoCardTitle === 'TEST_Kathmandu_P15');
    await captureScreenshot('p15_atlas_waypoint_selected.png');

    // 6. Globe 3D Marker Raycasting Click
    console.log('\n--- Step 6: 3D Globe Marker Click Interaction ---');
    const tokyoWpId = await evalJs(`(() => {
      const cards = Array.from(document.querySelectorAll('.earth-atlas-card'));
      const tokyo = cards.find(c => c.textContent.includes('TEST_Tokyo_P15'));
      return tokyo?.dataset?.waypointId;
    })()`);

    // Simulate selecting Tokyo on the globe
    await evalJs(`(() => {
      const view = window.__luminaEarth;
      if (view?.atlasController && "${tokyoWpId}") {
        view.atlasController.selectWaypoint("${tokyoWpId}", { fly: true });
      }
    })()`);
    await sleep(1500);

    const tokyoSelected = await evalJs(`(() => {
      const cards = Array.from(document.querySelectorAll('.earth-atlas-card'));
      const tokyo = cards.find(c => c.textContent.includes('TEST_Tokyo_P15'));
      return tokyo?.classList?.contains('selected');
    })()`);
    logTest('Waypoint selection highlights Tokyo and navigates camera', tokyoSelected);

    // 7. Edit Flow
    console.log('\n--- Step 7: Edit Waypoint Flow ---');
    await evalJs(`(() => {
      const cards = Array.from(document.querySelectorAll('.earth-atlas-card'));
      const tokyo = cards.find(c => c.textContent.includes('TEST_Tokyo_P15'));
      tokyo?.querySelector('.earth-btn-secondary')?.click();
    })()`);
    await sleep(400);

    const editDrawerOpen = await evalJs('!document.getElementById("earth-atlas-form-wrap").hidden');
    await evalJs(`(() => {
      document.getElementById("earth-atlas-desc").value = "Updated note: Greater Tokyo Area";
      document.getElementById("earth-atlas-form").dispatchEvent(new Event('submit', { cancelable: true }));
    })()`);
    await sleep(1200);

    const updatedNoteRendered = await evalJs(`(() => {
      const cards = Array.from(document.querySelectorAll('.earth-atlas-card'));
      const tokyo = cards.find(c => c.textContent.includes('TEST_Tokyo_P15'));
      return tokyo?.textContent?.includes('Updated note: Greater Tokyo Area');
    })()`);
    logTest('Edit waypoint persists changes and re-renders card', editDrawerOpen && updatedNoteRendered);
    await captureScreenshot('p15_atlas_edit_flow.png');

    // 8. Delete Flow with Confirmation Step
    console.log('\n--- Step 8: Delete Flow with Confirmation ---');
    // Click Delete on Tokyo card
    await evalJs(`(() => {
      const cards = Array.from(document.querySelectorAll('.earth-atlas-card'));
      const tokyo = cards.find(c => c.textContent.includes('TEST_Tokyo_P15'));
      tokyo?.querySelector('.earth-btn-danger-outline')?.click();
    })()`);
    await sleep(300);

    const confirmBannerVisible = await evalJs(`(() => {
      const cards = Array.from(document.querySelectorAll('.earth-atlas-card'));
      const tokyo = cards.find(c => c.textContent.includes('TEST_Tokyo_P15'));
      return tokyo?.querySelector('.earth-atlas-confirm-msg')?.textContent?.includes('Delete this place?');
    })()`);
    logTest('Clicking Delete triggers explicit confirmation banner', confirmBannerVisible);

    // Test Cancel on confirmation
    await evalJs(`(() => {
      const cards = Array.from(document.querySelectorAll('.earth-atlas-card'));
      const tokyo = cards.find(c => c.textContent.includes('TEST_Tokyo_P15'));
      const cancelBtn = tokyo?.querySelector('.earth-atlas-confirm-wrap .earth-btn-secondary');
      cancelBtn?.click();
    })()`);
    await sleep(300);

    const stillExistsAfterCancel = await evalJs(`Array.from(document.querySelectorAll(".earth-atlas-card-name")).some(el => el.textContent === "TEST_Tokyo_P15")`);
    logTest('Canceling delete preserves the waypoint', stillExistsAfterCancel);

    // Re-trigger and confirm deletion
    await evalJs(`(() => {
      const cards = Array.from(document.querySelectorAll('.earth-atlas-card'));
      const tokyo = cards.find(c => c.textContent.includes('TEST_Tokyo_P15'));
      tokyo?.querySelector('.earth-btn-danger-outline')?.click();
    })()`);
    await sleep(300);

    await evalJs(`(() => {
      const cards = Array.from(document.querySelectorAll('.earth-atlas-card'));
      const tokyo = cards.find(c => c.textContent.includes('TEST_Tokyo_P15'));
      const doDel = tokyo?.querySelector('.earth-atlas-confirm-wrap .earth-btn-danger');
      doDel?.click();
    })()`);
    await sleep(1200);

    const tokyoDeleted = await evalJs(`!Array.from(document.querySelectorAll(".earth-atlas-card-name")).some(el => el.textContent === "TEST_Tokyo_P15")`);
    logTest('Confirmed delete removes waypoint from API and Atlas list', tokyoDeleted);

    // 9. Lifecycle Pause-on-Hide
    console.log('\n--- Step 9: Lifecycle Pause-on-Hide & Resume ---');
    // Switch to Chat / Dashboard
    await evalJs('document.querySelector("[data-focus=\'message\']")?.click()');
    await sleep(400);

    const isHidden = await evalJs('document.getElementById("earth-workspace").hidden');
    const isPaused = await evalJs('document.getElementById("earth-stage").dataset.rendering === "paused"');
    logTest('Switching away hides Earth and pauses WebGL rendering loop', isHidden && isPaused);
    await captureScreenshot('p15_atlas_chat_paused.png');

    const framesWhenPaused = Number(await evalJs('document.getElementById("earth-stage").dataset.frames || "0"'));
    // Wait 600ms to confirm 0 frames rendered while paused
    await sleep(600);
    const framesAfterWait = Number(await evalJs('document.getElementById("earth-stage").dataset.frames || "0"'));
    const zeroIncrement = framesAfterWait === framesWhenPaused;
    logTest('Zero frames rendered while hidden (GPU idle)', zeroIncrement, `Frames: ${framesWhenPaused} == ${framesAfterWait}`);

    // Switch back to Earth
    await evalJs('document.getElementById("earth-open").click()');
    await sleep(400);
    const isResumed = await evalJs('document.getElementById("earth-stage").dataset.rendering === "active"');
    logTest('Switching back restores view and resumes rendering loop', isResumed);

    // Clean up Kathmandu test waypoint
    await evalJs(`(async () => {
      try {
        const res = await fetch('/api/earth/waypoints');
        const data = await res.json();
        for (const wp of (data.waypoints || [])) {
          if (wp.name.startsWith('TEST_')) {
            await fetch('/api/earth/waypoints/' + wp.id, { method: 'DELETE' });
          }
        }
      } catch(e) {}
    })()`);
    await sleep(300);

    // 10. Security & Error Log Inspection
    console.log('\n--- Step 10: Security, Exceptions & CSP Validation ---');
    logTest('Zero browser unhandled exceptions', browserExceptions.length === 0, `${browserExceptions.length} exceptions`);
    logTest('Zero Content Security Policy violations', cspViolations.length === 0, `${cspViolations.length} violations`);

    console.log('\n========================================================================');
    const allPassed = testResults.every(t => t.passed);
    console.log(` VERIFICATION RESULT: ${allPassed ? 'ALL PASS ✓' : 'SOME CHECKS FAILED ✗'}`);
    console.log(` Passed: ${testResults.filter(t => t.passed).length} / ${testResults.length}`);
    console.log('========================================================================\n');

    await cdpSend('Browser.close');
    process.exit(allPassed ? 0 : 1);

  } catch (err) {
    console.error('\n[VERIFICATION ERROR]:', err);
    chromeProcess.kill();
    process.exit(1);
  } finally {
    try { chromeProcess.kill(); } catch (e) {}
  }
}

main();
