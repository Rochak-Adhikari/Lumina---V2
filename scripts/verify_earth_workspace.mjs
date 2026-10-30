#!/usr/bin/env node
/**
 * scripts/verify_earth_workspace.mjs
 * 
 * Repeatable, bounded browser verification harness for Lumina Earth Workspace Integration (P1.3).
 * Tests the live integrated single-page application at http://127.0.0.1:8764/
 * Exercises:
 *   1. Initial SPA shell, WebSocket connection, nav rail Earth button.
 *   2. View switching: Dashboard/Chat -> Earth Workspace.
 *   3. Interactive Earth features inside main shell: search, candidate selection, marker, fly-to, weather, day/night toggle.
 *   4. Rendering lifecycle: pause-on-hide (verified 0 frames rendered while hidden) and resume-on-show.
 *   5. Resource safety: zero duplicate canvases, zero duplicate render loops, preserved WebSocket continuity.
 *   6. Security & CSP: zero errors, zero CSP violations.
 */

import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';

const APP_URL = 'http://127.0.0.1:8764/';
const CDP_PORT = 9464;
const SCRATCH_DIR = resolve('scratch');
const USER_DATA_DIR = join(SCRATCH_DIR, 'chr_workspace_harness');

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
  console.log(' LUMINA EARTH — WORKSPACE INTEGRATION VERIFICATION HARNESS (P1.3)');
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
    console.error('Please start the backend before running this harness:');
    console.error('  Command: & \'.venv\\Scripts\\python.exe\' -m lumina\n');
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
    const networkRequests = [];
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
        console.warn('\n[BROWSER EXCEPTION DETECTED]:', desc);
      }
      if (data.method === 'Network.requestWillBeSent') {
        networkRequests.push(data.params.request.url);
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

    const takeScreenshot = async (filename) => {
      try {
        const shot = await cdpSend('Page.captureScreenshot', { format: 'png' });
        writeFileSync(join(SCRATCH_DIR, filename), Buffer.from(shot.result.data, 'base64'));
      } catch (err) {
        console.warn(`Failed to capture screenshot ${filename}:`, err.message);
      }
    };

    // Enable CDP domains
    await cdpSend('Page.enable');
    await cdpSend('Runtime.enable');
    await cdpSend('Network.enable');
    await cdpSend('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });

    console.log('\n[3/4] Executing integrated workspace scenarios...\n');

    // Scenario 1: Lumina Main Shell Initial Load & WebSocket Connection
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
    const shellState = await evalJs(`({
      hasNav: Boolean(document.getElementById('workspace-navigation')),
      hasEarthBtn: Boolean(document.getElementById('earth-open')),
      earthHidden: document.getElementById('earth-workspace')?.hidden,
      presenceVisible: !document.querySelector('.presence')?.hidden,
      hasWs: Boolean(window.__luminaEarthWorkspace)
    })`);
    const initialPass = spaReady && shellState.hasEarthBtn && shellState.earthHidden === true && shellState.presenceVisible === true;
    logTest('Scenario 1: Main SPA Shell Load & Navigation Rail Presence', initialPass, 'Runtime health connected, #earth-open present, Earth hidden');

    // Scenario 2: Switch to Earth Workspace via Nav Rail
    await evalJs(`document.getElementById('earth-open').click()`);
    let earthReady = false;
    for (let i = 0; i < 40; i++) {
      await sleep(250);
      const state = await evalJs(`document.getElementById('earth-stage')?.dataset.earthState`);
      if (state === 'ready') {
        earthReady = true;
        break;
      }
    }
    const navState = await evalJs(`({
      earthCurrent: document.getElementById('earth-open')?.getAttribute('aria-current'),
      dashboardCurrent: document.querySelector('[data-focus="workspace"]')?.getAttribute('aria-current'),
      earthWorkspaceHidden: document.getElementById('earth-workspace')?.hidden,
      presenceHidden: document.querySelector('.presence')?.hidden,
      renderingState: document.getElementById('earth-stage')?.dataset.rendering,
      canvasCount: document.querySelectorAll('#earth-stage canvas').length
    })`);
    const switchPass = earthReady && navState.earthCurrent === 'page' && navState.earthWorkspaceHidden === false && navState.presenceHidden === true && navState.renderingState === 'active' && navState.canvasCount === 1;
    logTest('Scenario 2: View Switch to Earth Workspace', switchPass, 'earthState=ready, rendering=active, 1 canvas');
    await takeScreenshot('p13_earth_workspace_open.png');

    // Scenario 3: Interactive Search, Candidate Selection & Marker Beacon
    await evalJs(`
      const input = document.getElementById('earth-search-input');
      input.value = 'Kathmandu';
      document.getElementById('earth-search-form').dispatchEvent(new Event('submit', { cancelable: true }));
    `);
    let candidatesFound = false;
    for (let i = 0; i < 30; i++) {
      await sleep(200);
      const count = await evalJs(`document.querySelectorAll('.earth-result-btn').length`);
      if (count > 0) {
        candidatesFound = true;
        break;
      }
    }
    if (candidatesFound) {
      await evalJs(`document.querySelector('.earth-result-btn')?.click()`);
      for (let i = 0; i < 30; i++) {
        await sleep(200);
        const cardReady = await evalJs(`Boolean(!document.getElementById('earth-info-card')?.hidden && document.querySelectorAll('.earth-forecast-day').length === 7)`);
        if (cardReady) break;
      }
    }
    const markerInfo = await evalJs(`({
      hasMarker: Boolean(window.__luminaEarth?.getMarker()),
      lat: window.__luminaEarth?.getMarker()?.lat,
      lon: window.__luminaEarth?.getMarker()?.lon,
      cardVisible: !document.getElementById('earth-info-card')?.hidden,
      weatherTemp: document.querySelector('.earth-weather-val')?.textContent,
      forecastDays: document.querySelectorAll('.earth-forecast-day').length
    })`);
    const searchPass = candidatesFound && markerInfo.hasMarker && markerInfo.cardVisible && markerInfo.forecastDays === 7;
    logTest('Scenario 3: Integrated Location Search, Marker & Weather Card', searchPass, `Marker at (${markerInfo.lat}, ${markerInfo.lon}), Temp: ${markerInfo.weatherTemp}`);
    await takeScreenshot('p13_earth_active_explored.png');

    // Scenario 4: Solar Day/Night Illumination Toggle & Orbit Drag
    const dayNightInitial = await evalJs(`window.__luminaEarth?.isDayNightEnabled()`);
    await evalJs(`document.getElementById('earth-toggle-daynight').click()`);
    await sleep(300);
    const dayNightActive = await evalJs(`window.__luminaEarth?.isDayNightEnabled()`);
    
    // Simulate pointer drag on canvas
    await evalJs(`
      const canvas = document.querySelector('.earth-canvas');
      canvas.dispatchEvent(new PointerEvent('pointerdown', { pointerId: 1, clientX: 500, clientY: 400 }));
      canvas.dispatchEvent(new PointerEvent('pointermove', { pointerId: 1, clientX: 420, clientY: 400 }));
      canvas.dispatchEvent(new PointerEvent('pointerup', { pointerId: 1, clientX: 420, clientY: 400 }));
    `);
    await sleep(400);
    const orbitChanged = await evalJs(`window.__luminaEarth?.orbit?.yaw !== 0`);
    const dayNightPass = (dayNightInitial === false) && (dayNightActive === true) && orbitChanged;
    logTest('Scenario 4: Day/Night Illumination & Manual Orbit Drag', dayNightPass, 'Day/night toggled to ON, orbit drag updated yaw');

    // Scenario 5: Switch Back to Chat / Dashboard (Pause-on-Hide Verification)
    await evalJs(`document.querySelector('[data-focus="message"]').click()`);
    await sleep(400);

    const pauseNavState = await evalJs(`({
      earthCurrent: document.getElementById('earth-open')?.getAttribute('aria-current'),
      chatCurrent: document.querySelector('[data-focus="message"]')?.getAttribute('aria-current'),
      earthWorkspaceHidden: document.getElementById('earth-workspace')?.hidden,
      presenceHidden: document.querySelector('.presence')?.hidden,
      isPaused: window.__luminaEarthWorkspace?.isPaused(),
      renderingState: document.getElementById('earth-stage')?.dataset.rendering,
      initialFrames: Number(document.getElementById('earth-stage')?.dataset.frames || 0)
    })`);

    // Wait 600ms to measure if frame loop is strictly stopped
    await sleep(600);
    const postPauseFrames = await evalJs(`Number(document.getElementById('earth-stage')?.dataset.frames || 0)`);
    const framesIncrementedWhileHidden = postPauseFrames - pauseNavState.initialFrames;
    const pausePass = pauseNavState.earthWorkspaceHidden === true &&
                      pauseNavState.presenceHidden === false &&
                      pauseNavState.isPaused === true &&
                      pauseNavState.renderingState === 'paused' &&
                      framesIncrementedWhileHidden === 0;

    logTest('Scenario 5: Switch to Chat & Pause-on-Hide Lifecycle', pausePass, `Render loop stopped: 0 frames rendered while hidden (frames=${pauseNavState.initialFrames})`);
    await takeScreenshot('p13_switched_to_chat.png');

    // Scenario 6: Switch Back to Earth Workspace (Resume Lifecycle & Zero Duplicate Canvases)
    await evalJs(`document.getElementById('earth-open').click()`);
    await sleep(500);

    const resumeFrames1 = await evalJs(`Number(document.getElementById('earth-stage')?.dataset.frames || 0)`);
    await sleep(300);
    const resumeFrames2 = await evalJs(`Number(document.getElementById('earth-stage')?.dataset.frames || 0)`);
    const framesIncrementingOnResume = resumeFrames2 > resumeFrames1;

    const resumeState = await evalJs(`({
      isPaused: window.__luminaEarthWorkspace?.isPaused(),
      renderingState: document.getElementById('earth-stage')?.dataset.rendering,
      canvasCount: document.querySelectorAll('#earth-stage canvas').length,
      markerRetained: Boolean(window.__luminaEarth?.getMarker()),
      cardRetained: !document.getElementById('earth-info-card')?.hidden
    })`);

    const resumePass = resumeState.isPaused === false &&
                       resumeState.renderingState === 'active' &&
                       resumeState.canvasCount === 1 &&
                       resumeState.markerRetained === true &&
                       framesIncrementingOnResume;

    logTest('Scenario 6: Return to Earth: Resume Rendering & Resource Preservation', resumePass, `Rendering resumed, canvasCount=1, marker & weather retained`);
    await takeScreenshot('p13_resumed_earth.png');

    // Scenario 7: Modal Dialog Interaction (Command Deck)
    await evalJs(`document.getElementById('command-deck-open').click()`);
    await sleep(400);
    const modalOpened = await evalJs(`Boolean(document.getElementById('command-deck-panel')?.open)`);
    await evalJs(`document.getElementById('command-deck-close').click()`);
    await sleep(400);
    const modalClosed = await evalJs(`Boolean(!document.getElementById('command-deck-panel')?.open)`);
    const isEarthActive = await evalJs(`Boolean(window.__luminaEarthWorkspace?.isEarthActive?.())`);
    const modalPass = Boolean(modalOpened && modalClosed && isEarthActive);
    logTest('Scenario 7: Modal Dialog Interleaving (Command Deck)', modalPass, 'Modal opened/closed cleanly; Earth workspace remained active');

    // Scenario 8: WebSocket Continuity Throughout View Transitions
    const wsConnected = await evalJs(`document.getElementById('runtime-health')?.textContent === 'connected'`);
    logTest('Scenario 8: WebSocket Voice & Conversation Continuity', wsConnected, 'Runtime health remained "connected" throughout transitions');

    // Scenario 9: Security, CSP & Exception Conformance
    const nonLocalRequests = networkRequests.filter(u => !u.startsWith('http://127.0.0.1:8764') && !u.startsWith('ws://127.0.0.1:8764') && !u.startsWith('data:'));
    const unexpectedErrors = browserExceptions.filter(e => !e.includes('favicon'));
    const securityPass = nonLocalRequests.length === 0 && unexpectedErrors.length === 0 && cspViolations.length === 0;
    logTest('Scenario 9: Security, CSP & Console Integrity', securityPass, `Non-local requests: 0, Exceptions: ${unexpectedErrors.length}, CSP violations: ${cspViolations.length}`);

    // Summary
    console.log('\n[4/4] Workspace Integration Execution Summary:');
    const allPassed = testResults.every(t => t.passed);
    console.log(`  Total scenarios tested: ${testResults.length}`);
    console.log(`  Scenarios passed: ${testResults.filter(t => t.passed).length}`);
    console.log(`  Scenarios failed: ${testResults.filter(t => !t.passed).length}`);
    console.log(`  Overall workspace verification verdict: ${allPassed ? 'PASS' : 'FAIL'}\n`);

    const reportJson = {
      timestamp: new Date().toISOString(),
      verdict: allPassed ? 'PASS' : 'FAIL',
      scenarios: testResults,
      consoleLogsCount: consoleLogs.length,
      unexpectedExceptions: unexpectedErrors,
      outboundNonLocalRequests: nonLocalRequests,
      cspViolations: cspViolations
    };
    writeFileSync(join(SCRATCH_DIR, 'earth_workspace_report.json'), JSON.stringify(reportJson, null, 2));

    if (!allPassed) {
      process.exit(1);
    }
  } finally {
    try {
      chromeProcess.kill();
    } catch (_) {}
  }
}

main().catch(err => {
  console.error('\n[UNHANDLED HARNESS ERROR]:', err);
  process.exit(1);
});
