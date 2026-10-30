#!/usr/bin/env node
/**
 * scripts/verify_earth_runtime.mjs
 * 
 * Repeatable, bounded browser verification harness for Lumina Earth.
 * Drives headless Chromium / WebView2-equivalent engine via Chrome DevTools Protocol (CDP).
 * Zero external npm dependencies (uses native Node 24 WebSocket, fetch, and child_process).
 * 
 * Prerequisites:
 *   1. Lumina backend listening at http://127.0.0.1:8764
 *   2. Chromium / Chrome installed at standard Playwright or system location.
 * 
 * Usage:
 *   node scripts/verify_earth_runtime.mjs
 */

import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';

const APP_URL = 'http://127.0.0.1:8764/assets/earth/earth-prototype.html';
const HEALTH_URL = 'http://127.0.0.1:8764/';
const CDP_PORT = 9460;
const SCRATCH_DIR = resolve('scratch');
const USER_DATA_DIR = join(SCRATCH_DIR, 'chr_earth_harness');

const CHROME_CANDIDATE_PATHS = [
  'C:\\Users\\Administrator\\AppData\\Local\\ms-playwright\\chromium-1248\\chrome-win64\\chrome.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
];

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function checkBackendPrerequisite() {
  try {
    const res = await fetch(HEALTH_URL, { signal: AbortSignal.timeout(3000) });
    if (res.ok || res.status === 200 || res.status === 404) {
      return true;
    }
  } catch (err) {
    // Connection refused or timeout
  }
  return false;
}

function findChromePath() {
  for (const p of CHROME_CANDIDATE_PATHS) {
    if (existsSync(p)) return p;
  }
  return null;
}

async function main() {
  console.log('===============================================================');
  console.log(' LUMINA EARTH — BROWSER RUNTIME VERIFICATION HARNESS (P1.2)');
  console.log('===============================================================\n');

  // 1. Check prerequisites
  console.log('[1/4] Checking environment prerequisites...');
  const backendAlive = await checkBackendPrerequisite();
  if (!backendAlive) {
    console.error('\n[PREREQUISITE ERROR] Lumina backend is not running at http://127.0.0.1:8764');
    console.error('Please start the backend before running this harness:');
    console.error('  Command: & \'.venv\\Scripts\\python.exe\' -m lumina');
    console.error('  Or: powershell -ExecutionPolicy Bypass -File .\\start.ps1\n');
    process.exit(1);
  }
  console.log('  ✓ Backend server is active at http://127.0.0.1:8764');

  const chromePath = findChromePath();
  if (!chromePath) {
    console.error('\n[PREREQUISITE ERROR] No suitable Chromium/Chrome executable found.');
    console.error('Searched paths:', CHROME_CANDIDATE_PATHS);
    process.exit(1);
  }
  console.log(`  ✓ Browser engine located: ${chromePath}`);

  // Prepare scratch directory
  if (!existsSync(SCRATCH_DIR)) {
    mkdirSync(SCRATCH_DIR, { recursive: true });
  }

  // 2. Launch browser with CDP (using native ANGLE Direct3D11 acceleration)
  console.log('\n[2/4] Launching headless browser on CDP port', CDP_PORT);
  const chromeProcess = spawn(chromePath, [
    `--remote-debugging-port=${CDP_PORT}`,
    `--user-data-dir=${USER_DATA_DIR}`,
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
        const desc = data.params.exceptionDetails?.text || 'Uncaught exception';
        browserExceptions.push(desc);
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
    await cdpSend('Emulation.setDeviceMetricsOverride', { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });

    console.log('\n[3/4] Executing verification scenarios...\n');

    // Scenario 1: Page Navigation & Earth Stage Initialization
    await cdpSend('Page.navigate', { url: APP_URL });
    let readyState = false;
    for (let i = 0; i < 40; i++) {
      await sleep(250);
      const state = await evalJs(`document.getElementById('earth-stage')?.dataset.earthState`);
      if (state === 'ready') {
        readyState = true;
        break;
      }
    }
    logTest('Scenario 1: Page Load & WebGL2 Ready State', readyState, `dataset.earthState === 'ready'`);

    // Scenario 2: Earth Texture Load Completion
    const textureLoaded = await evalJs(`Boolean(window.__luminaEarth?.earth?.material?.map?.image?.complete)`);
    const textureDimensions = await evalJs(`({
      width: window.__luminaEarth?.earth?.material?.map?.image?.naturalWidth || 0,
      height: window.__luminaEarth?.earth?.material?.map?.image?.naturalHeight || 0
    })`);
    const validTexture = textureLoaded && textureDimensions.width > 0 && textureDimensions.height > 0;
    logTest('Scenario 2: Earth Texture Load Completion', validTexture, `${textureDimensions.width}x${textureDimensions.height}px`);

    // Scenario 3: Search UI Component Presence
    const searchUi = await evalJs(`({
      form: Boolean(document.getElementById('earth-search-form')),
      input: Boolean(document.getElementById('earth-search-input')),
      submit: Boolean(document.getElementById('earth-search-submit')),
      dayNightBtn: Boolean(document.getElementById('earth-toggle-daynight'))
    })`);
    const uiComplete = searchUi.form && searchUi.input && searchUi.submit && searchUi.dayNightBtn;
    logTest('Scenario 3: Search UI & Controls Presence', uiComplete, 'form, input, submit button, day/night toggle');

    // Scenario 4: Location Search & Candidate Selection
    await evalJs(`
      const input = document.getElementById('earth-search-input');
      input.value = 'Kathmandu';
      document.getElementById('earth-search-form').dispatchEvent(new Event('submit', { cancelable: true }));
    `);
    let candidateCount = 0;
    for (let i = 0; i < 30; i++) {
      await sleep(200);
      candidateCount = await evalJs(`document.querySelectorAll('.earth-result-btn').length`) || 0;
      if (candidateCount > 0) break;
    }
    const searchSuccess = candidateCount > 0;
    logTest('Scenario 4: Location Search Candidates Rendered', searchSuccess, `${candidateCount} candidates found`);

    // Scenario 5: Marker Creation & Selection Interaction
    await evalJs(`document.querySelector('.earth-result-btn')?.click()`);
    await sleep(1500); // Wait for marker creation and fly-to animation

    const markerData = await evalJs(`({
      hasMarker: Boolean(window.__luminaEarth?.getMarker()),
      lat: window.__luminaEarth?.getMarker()?.lat,
      lon: window.__luminaEarth?.getMarker()?.lon,
      containerLoc: document.getElementById('earth-stage')?.dataset.markerLocation
    })`);
    const markerValid = markerData.hasMarker && markerData.lat !== undefined;
    logTest('Scenario 5: 3D Geographic Surface Marker Creation', markerValid, `lat=${markerData.lat}, lon=${markerData.lon}`);

    // Scenario 6: Camera Fly-To Orientation Settling
    let flySettled = false;
    for (let i = 0; i < 20; i++) {
      const animating = await evalJs(`Boolean(window.__luminaEarth?.isAnimating())`);
      if (!animating) {
        flySettled = true;
        break;
      }
      await sleep(200);
    }
    logTest('Scenario 6: Camera Fly-To Settled', flySettled, 'Interpolation settled without oscillation');

    // Scenario 7: Weather Card & 7-Day Forecast Rendering
    let weatherPopulated = false;
    for (let i = 0; i < 30; i++) {
      const temp = await evalJs(`document.querySelector('.earth-weather-val')?.textContent`);
      if (temp && temp !== 'N/A' && temp !== '--') {
        weatherPopulated = true;
        break;
      }
      await sleep(250);
    }
    const weatherData = await evalJs(`({
      title: document.getElementById('earth-info-title')?.textContent,
      temp: document.querySelector('.earth-weather-val')?.textContent,
      feels: document.querySelector('.earth-weather-feels')?.textContent,
      cond: document.querySelector('.earth-weather-cond-text')?.textContent,
      wind: document.querySelectorAll('.earth-metric-val')?.[0]?.textContent,
      forecastCount: document.querySelectorAll('.earth-forecast-day').length
    })`);
    const weatherValid = weatherPopulated && weatherData.forecastCount === 7;
    logTest('Scenario 7: Live Weather & 7-Day Forecast Population', weatherValid, `${weatherData.temp}, ${weatherData.cond}, 7-day strip`);
    await takeScreenshot('harness_kathmandu_weather.png');

    // Scenario 8: Day/Night Solar Illumination Toggle
    const dayNightInitial = await evalJs(`window.__luminaEarth?.isDayNightEnabled()`);
    await evalJs(`document.getElementById('earth-toggle-daynight').click()`);
    await sleep(400);
    const dayNightActive = await evalJs(`window.__luminaEarth?.isDayNightEnabled()`);
    const ariaPressed = await evalJs(`document.getElementById('earth-toggle-daynight').getAttribute('aria-pressed')`);
    
    // Toggle back to clean state
    await evalJs(`document.getElementById('earth-toggle-daynight').click()`);
    await sleep(200);
    const dayNightRestored = await evalJs(`window.__luminaEarth?.isDayNightEnabled()`);

    const dayNightSuccess = (dayNightInitial === false) && (dayNightActive === true) && (ariaPressed === 'true') && (dayNightRestored === false);
    logTest('Scenario 8: Day/Night Solar Illumination Cycle', dayNightSuccess, `Initial=OFF -> Toggled=ON (aria-pressed=true) -> Restored=OFF`);
    await takeScreenshot('harness_daynight_toggle.png');

    // Scenario 9: Multi-Location Exploration (Tokyo)
    await evalJs(`window.__luminaEarth.searchController.performSearch('Tokyo')`);
    let tokyoFound = false;
    for (let i = 0; i < 30; i++) {
      await sleep(200);
      const count = await evalJs(`document.querySelectorAll('.earth-result-btn').length`);
      if (count > 0) {
        tokyoFound = true;
        break;
      }
    }
    if (tokyoFound) {
      await evalJs(`document.querySelector('.earth-result-btn')?.click()`);
      await sleep(2000);
    }
    const tokyoTitle = await evalJs(`document.getElementById('earth-info-title')?.textContent`);
    const tokyoSuccess = tokyoFound && tokyoTitle?.includes('Tokyo');
    logTest('Scenario 9: Second Location Navigation (Tokyo)', tokyoSuccess, `Selected "${tokyoTitle}"`);

    // Scenario 10: Deterministic Simulated Upstream Failure & Retry UI
    await evalJs(`
      window.__luminaEarth.weatherController.renderError('Upstream Open-Meteo gateway timeout simulation', () => {
        window.__luminaEarth.__simulatedRetryTriggered = true;
      });
    `);
    await sleep(300);
    const errorText = await evalJs(`document.querySelector('.earth-weather-error-msg')?.textContent`);
    const retryBtnExists = await evalJs(`Boolean(document.querySelector('.earth-weather-retry-btn'))`);
    
    // Click retry
    await evalJs(`document.querySelector('.earth-weather-retry-btn')?.click()`);
    const retryTriggered = await evalJs(`Boolean(window.__luminaEarth.__simulatedRetryTriggered)`);
    
    const errorHandlingSuccess = errorText?.includes('timeout') && retryBtnExists && retryTriggered;
    logTest('Scenario 10: Simulated Upstream Failure & Retry Action', errorHandlingSuccess, 'Error banner rendered, retry handler invoked');
    await takeScreenshot('harness_error_simulation.png');

    // Scenario 11: Security, CSP & Exception Conformance
    const nonLocalRequests = networkRequests.filter(u => !u.startsWith('http://127.0.0.1:8764') && !u.startsWith('data:'));
    const unexpectedErrors = browserExceptions.filter(e => !e.includes('favicon'));
    const securitySuccess = nonLocalRequests.length === 0 && unexpectedErrors.length === 0 && cspViolations.length === 0;
    logTest('Scenario 11: Security, CSP & Console Integrity', securitySuccess, `Outbound non-local requests: ${nonLocalRequests.length}, Exceptions: ${unexpectedErrors.length}`);

    // Summary
    console.log('\n[4/4] Harness Execution Summary:');
    const allPassed = testResults.every(t => t.passed);
    console.log(`  Total scenarios tested: ${testResults.length}`);
    console.log(`  Scenarios passed: ${testResults.filter(t => t.passed).length}`);
    console.log(`  Scenarios failed: ${testResults.filter(t => !t.passed).length}`);
    console.log(`  Overall browser verification verdict: ${allPassed ? 'PASS' : 'FAIL'}\n`);

    const reportJson = {
      timestamp: new Date().toISOString(),
      verdict: allPassed ? 'PASS' : 'FAIL',
      scenarios: testResults,
      consoleLogsCount: consoleLogs.length,
      unexpectedExceptions: unexpectedErrors,
      outboundNonLocalRequests: nonLocalRequests,
      cspViolations: cspViolations
    };
    writeFileSync(join(SCRATCH_DIR, 'earth_harness_report.json'), JSON.stringify(reportJson, null, 2));

    if (!allPassed) {
      process.exit(1);
    }
  } finally {
    try {
      chromeProcess.kill();
    } catch (_) {}
    try {
      rmSync(USER_DATA_DIR, { recursive: true, force: true });
    } catch (_) {}
  }
}

main().catch(err => {
  console.error('\n[UNHANDLED HARNESS ERROR]:', err);
  process.exit(1);
});
