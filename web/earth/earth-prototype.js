// Lumina Earth P0.4 — 3D Earth Exploration Prototype.
// Vertical slice: location search, geographic markers, camera fly-to, weather card & day/night spike.
// 100% zero-budget: public-domain NASA texture, keyless Open-Meteo geocoding & weather.
import * as THREE from '../vendor/three.module.js';
import {
  createOrbitState,
  applyDrag,
  applyZoom,
  applyInertia,
  cameraPosition,
  renderPixelRatio,
  calculateTargetOrbit,
  shortestAngleDiff,
  interpolateOrbit
} from './orbit.js';
import { latLonToVector } from './geo.js';
import { createSearchController, formatCoordinates } from './search.js';
import { calculateSubsolarVector } from './solar.js';
import { createWeatherController } from './weather.js';
import { createAtlasApiClient, createAtlasController } from './atlas.js';
import { createLocalTimeController } from './time.js';

const TEXTURE_URL = new URL('./assets/land_shallow_topo_2048.jpg', import.meta.url).href;

const ATMOSPHERE_VERTEX = `
varying vec3 vNormal; varying vec3 vView;
void main(){ vec4 mv = modelViewMatrix * vec4(position,1.0); vNormal = normalize(normalMatrix*normal); vView = normalize(-mv.xyz); gl_Position = projectionMatrix*mv; }`;
const ATMOSPHERE_FRAGMENT = `
varying vec3 vNormal; varying vec3 vView;
void main(){
  // On BackSide, -dot(vNormal, vView) is 0 at the outer silhouette and increases smoothly inward to Earth limb.
  float d = max(0.0, -dot(vNormal, vView));
  float factor = min(1.0, d / 0.16);
  float a = pow(factor, 2.0) * 0.45;
  gl_FragColor = vec4(0.25, 0.55, 0.95, a);
}`;

export function createEarth(container, { onStatus = () => {} } = {}) {
  let disposed = false, frame = 0, dragging = null, last = performance.now();
  let flyToAnimation = null;
  let activeMarker = null;
  let idleSpin = true;
  const waypointMarkers = new Map();
  let selectedWaypointId = null;
  const waypointClickListeners = new Set();
  const raycaster = new THREE.Raycaster();

  const status = (state, message) => {
    container.dataset.earthState = state;
    onStatus(state, message);
  };
  status('loading', 'Loading Earth texture…');

  const probe = document.createElement('canvas');
  if (!(probe.getContext('webgl2') || probe.getContext('webgl'))) {
    status('error', 'WebGL is unavailable in this view, so the globe cannot render.');
    return { dispose() {} };
  }

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setClearColor(0x08090b, 1);
  renderer.domElement.className = 'earth-canvas';
  renderer.domElement.setAttribute('aria-label', 'Interactive 3D Earth. Drag to rotate, scroll to zoom.');
  renderer.domElement.tabIndex = 0;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 100);
  const orbit = createOrbitState();

  const earthGeometry = new THREE.SphereGeometry(1, 128, 64);
  const earthMaterial = new THREE.MeshStandardMaterial({ color: 0x1b2a3a, roughness: 0.95, metalness: 0 });
  const earth = new THREE.Mesh(earthGeometry, earthMaterial);
  scene.add(earth);

  const atmosphereGeometry = new THREE.SphereGeometry(1.02, 96, 48);
  const atmosphereMaterial = new THREE.ShaderMaterial({
    vertexShader: ATMOSPHERE_VERTEX,
    fragmentShader: ATMOSPHERE_FRAGMENT,
    transparent: true,
    blending: THREE.AdditiveBlending,
    side: THREE.BackSide,
    depthWrite: false
  });
  const halo = new THREE.Mesh(atmosphereGeometry, atmosphereMaterial);
  scene.add(halo);

  const BASELINE_AMBIENT = 0.55;
  const DAYNIGHT_AMBIENT = 0.08;
  const BASELINE_SUN_POS = new THREE.Vector3(5, 2, 4);
  let dayNightEnabled = false;

  const ambient = new THREE.AmbientLight(0xffffff, BASELINE_AMBIENT);
  const sun = new THREE.DirectionalLight(0xffffff, 2.2);
  sun.position.copy(BASELINE_SUN_POS);
  scene.add(ambient, sun);

  function updateDayNightSun() {
    const sLocal = calculateSubsolarVector(new Date(), 5.0);
    const sVec = new THREE.Vector3(sLocal.x, sLocal.y, sLocal.z);
    sVec.applyQuaternion(earth.quaternion);
    sun.position.copy(sVec);
  }

  function setDayNight(enabled) {
    dayNightEnabled = Boolean(enabled);
    if (!dayNightEnabled) {
      ambient.intensity = BASELINE_AMBIENT;
      sun.position.copy(BASELINE_SUN_POS);
    } else {
      ambient.intensity = DAYNIGHT_AMBIENT;
      updateDayNightSun();
    }
    container.dataset.dayNight = String(dayNightEnabled);
    return dayNightEnabled;
  }

  let texture = null;
  let textureLoaded = false;
  const textureTimeout = setTimeout(() => {
    if (!textureLoaded && !disposed) {
      status('error', 'Earth texture loading timed out. Rendering globe with baseline material.');
    }
  }, 5000);

  new THREE.TextureLoader().load(TEXTURE_URL, (t) => {
    clearTimeout(textureTimeout);
    textureLoaded = true;
    if (disposed) { t.dispose(); return; }
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
    texture = t;
    earthMaterial.map = t;
    earthMaterial.color.set(0xffffff);
    earthMaterial.needsUpdate = true;
    status('ready', 'Earth ready');
  }, undefined, (err) => {
    clearTimeout(textureTimeout);
    console.error('Texture load failure:', err);
    status('error', 'Failed to load local Earth texture; rendering fallback sphere.');
  });

  const resize = () => {
    const w = container.clientWidth || 800;
    const h = container.clientHeight || 600;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    const dpr = renderPixelRatio(window.devicePixelRatio);
    renderer.setPixelRatio(dpr);
    renderer.setSize(w, h, false);
  };
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(container);

  let dprQuery = null;
  const watchDpr = () => {
    dprQuery?.removeEventListener('change', onDpr);
    dprQuery = matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
    dprQuery.addEventListener('change', onDpr);
  };
  function onDpr() { resize(); watchDpr(); }
  watchDpr();
  resize();

  const cancelFlyTo = () => {
    if (flyToAnimation) {
      flyToAnimation = null;
    }
  };

  const el = renderer.domElement;
  let downPoint = null;

  const onDown = (e) => {
    cancelFlyTo();
    idleSpin = true;
    downPoint = { x: e.clientX, y: e.clientY, time: performance.now() };
    dragging = { id: e.pointerId, x: e.clientX, y: e.clientY };
    el.setPointerCapture(e.pointerId);
    el.classList.add('dragging');
  };
  const onMove = (e) => {
    if (!dragging || e.pointerId !== dragging.id) return;
    applyDrag(orbit, e.clientX - dragging.x, e.clientY - dragging.y, el.clientHeight);
    dragging.x = e.clientX;
    dragging.y = e.clientY;
  };
  const onUp = (e) => {
    if (dragging && e.pointerId === dragging.id) {
      if (downPoint) {
        const dist = Math.hypot(e.clientX - downPoint.x, e.clientY - downPoint.y);
        const dt = performance.now() - downPoint.time;
        if (dist < 6 && dt < 500) {
          checkMarkerClick(e);
        }
      }
      dragging = null;
      downPoint = null;
      el.classList.remove('dragging');
    }
  };
  const onWheel = (e) => {
    e.preventDefault();
    cancelFlyTo();
    applyZoom(orbit, e.deltaY);
  };
  const onKey = (e) => {
    cancelFlyTo();
    const step = { ArrowLeft: [-40, 0], ArrowRight: [40, 0], ArrowUp: [0, -40], ArrowDown: [0, 40] }[e.key];
    if (step) { applyDrag(orbit, step[0], step[1], el.clientHeight); e.preventDefault(); }
    else if (e.key === '+' || e.key === '=') applyZoom(orbit, -120);
    else if (e.key === '-') applyZoom(orbit, 120);
  };

  el.addEventListener('pointerdown', onDown);
  el.addEventListener('pointermove', onMove);
  el.addEventListener('pointerup', onUp);
  el.addEventListener('pointercancel', onUp);
  el.addEventListener('wheel', onWheel, { passive: false });
  el.addEventListener('keydown', onKey);

  const onLost = (e) => {
    e.preventDefault();
    status('error', 'The graphics context was lost. Reload this view to retry.');
  };
  el.addEventListener('webglcontextlost', onLost);

  // Geographic Marker Management
  function setMarker(lat, lon, details = {}) {
    clearMarker();
    const local = latLonToVector(lat, lon, { radius: 1.0, altitude: 0 });
    const normal = new THREE.Vector3(local.x, local.y, local.z).normalize();

    const group = new THREE.Group();
    group.name = 'geographic-marker';

    // Surface disc halo ring
    const ringGeo = new THREE.RingGeometry(0.012, 0.024, 32);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.85,
      depthTest: true
    });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.position.set(0, 0, 0.003);
    group.add(ring);

    // Vertical pin stem
    const stemGeo = new THREE.CylinderGeometry(0.002, 0.002, 0.038, 8);
    const stemMat = new THREE.MeshBasicMaterial({ color: 0x93c5fd });
    const stem = new THREE.Mesh(stemGeo, stemMat);
    stem.rotation.x = Math.PI / 2;
    stem.position.set(0, 0, 0.02);
    group.add(stem);

    // Beacon head sphere
    const headGeo = new THREE.SphereGeometry(0.016, 16, 16);
    const headMat = new THREE.MeshStandardMaterial({
      color: 0x38bdf8,
      emissive: 0x0284c7,
      emissiveIntensity: 0.9,
      roughness: 0.2
    });
    const head = new THREE.Mesh(headGeo, headMat);
    head.position.set(0, 0, 0.04);
    group.add(head);

    // Orient along surface normal vector
    const defaultNormal = new THREE.Vector3(0, 0, 1);
    group.quaternion.setFromUnitVectors(defaultNormal, normal);
    group.position.set(local.x, local.y, local.z);

    // Attached as child of earth so it rotates with surface
    earth.add(group);

    activeMarker = {
      group,
      lat,
      lon,
      details,
      geometries: [ringGeo, stemGeo, headGeo],
      materials: [ringMat, stemMat, headMat]
    };

    container.dataset.markerLocation = `${lat.toFixed(4)},${lon.toFixed(4)}`;
    return activeMarker;
  }

  function clearMarker() {
    if (!activeMarker) return;
    earth.remove(activeMarker.group);
    activeMarker.geometries.forEach(g => g.dispose());
    activeMarker.materials.forEach(m => m.dispose());
    activeMarker = null;
    delete container.dataset.markerLocation;
  }

  // Multi-waypoint Marker Management (P1.5 Atlas)
  function createWaypointMarkerObject(waypoint, isSelected = false) {
    const lat = waypoint.latitude;
    const lon = waypoint.longitude;
    const local = latLonToVector(lat, lon, { radius: 1.0, altitude: 0 });
    const normal = new THREE.Vector3(local.x, local.y, local.z).normalize();

    const group = new THREE.Group();
    group.name = `waypoint-marker-${waypoint.id}`;
    group.userData = { type: 'waypoint', id: waypoint.id, waypoint };

    // Amber/Gold styling for saved places (distinguishable from cyan search beacon)
    const baseColor = isSelected ? 0x38bdf8 : 0xf59e0b;
    const emissiveColor = isSelected ? 0x0284c7 : 0xb45309;
    const emissiveIntensity = isSelected ? 1.4 : 0.8;

    // Disc halo ring
    const ringGeo = new THREE.RingGeometry(0.010, 0.020, 32);
    const ringMat = new THREE.MeshBasicMaterial({
      color: baseColor,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.85,
      depthTest: true
    });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.position.set(0, 0, 0.003);
    ring.userData = { type: 'waypoint', id: waypoint.id };
    group.add(ring);

    // Pin stem
    const stemGeo = new THREE.CylinderGeometry(0.002, 0.002, 0.030, 8);
    const stemMat = new THREE.MeshBasicMaterial({ color: isSelected ? 0x93c5fd : 0xfde68a });
    const stem = new THREE.Mesh(stemGeo, stemMat);
    stem.rotation.x = Math.PI / 2;
    stem.position.set(0, 0, 0.015);
    stem.userData = { type: 'waypoint', id: waypoint.id };
    group.add(stem);

    // Head sphere
    const headGeo = new THREE.SphereGeometry(0.014, 16, 16);
    const headMat = new THREE.MeshStandardMaterial({
      color: baseColor,
      emissive: emissiveColor,
      emissiveIntensity: emissiveIntensity,
      roughness: 0.25
    });
    const head = new THREE.Mesh(headGeo, headMat);
    head.position.set(0, 0, 0.030);
    head.userData = { type: 'waypoint', id: waypoint.id };
    group.add(head);

    if (isSelected) {
      group.scale.set(1.35, 1.35, 1.35);
    }

    const defaultNormal = new THREE.Vector3(0, 0, 1);
    group.quaternion.setFromUnitVectors(defaultNormal, normal);
    group.position.set(local.x, local.y, local.z);

    earth.add(group);

    return {
      group,
      waypoint,
      meshes: [ring, stem, head],
      geometries: [ringGeo, stemGeo, headGeo],
      materials: [ringMat, stemMat, headMat],
      isSelected
    };
  }

  function setWaypoints(list = []) {
    const incomingIds = new Set(list.map(w => w.id));

    // Remove obsolete markers
    for (const [id, markerObj] of waypointMarkers.entries()) {
      if (!incomingIds.has(id)) {
        earth.remove(markerObj.group);
        markerObj.geometries.forEach(g => g.dispose());
        markerObj.materials.forEach(m => m.dispose());
        waypointMarkers.delete(id);
      }
    }

    // Add or update markers
    for (const wp of list) {
      const existing = waypointMarkers.get(wp.id);
      const isSelected = wp.id === selectedWaypointId;

      if (existing) {
        if (existing.waypoint.latitude !== wp.latitude || existing.waypoint.longitude !== wp.longitude) {
          earth.remove(existing.group);
          existing.geometries.forEach(g => g.dispose());
          existing.materials.forEach(m => m.dispose());
          const newObj = createWaypointMarkerObject(wp, isSelected);
          waypointMarkers.set(wp.id, newObj);
        } else {
          existing.waypoint = wp;
        }
      } else {
        const newObj = createWaypointMarkerObject(wp, isSelected);
        waypointMarkers.set(wp.id, newObj);
      }
    }
  }

  function highlightWaypointMarker(id) {
    selectedWaypointId = id;
    for (const [wpId, markerObj] of waypointMarkers.entries()) {
      const shouldBeSelected = wpId === id;
      if (markerObj.isSelected !== shouldBeSelected) {
        earth.remove(markerObj.group);
        markerObj.geometries.forEach(g => g.dispose());
        markerObj.materials.forEach(m => m.dispose());
        const updated = createWaypointMarkerObject(markerObj.waypoint, shouldBeSelected);
        waypointMarkers.set(wpId, updated);
      }
    }
  }

  function clearWaypoints() {
    for (const markerObj of waypointMarkers.values()) {
      earth.remove(markerObj.group);
      markerObj.geometries.forEach(g => g.dispose());
      markerObj.materials.forEach(m => m.dispose());
    }
    waypointMarkers.clear();
    selectedWaypointId = null;
  }

  function checkMarkerClick(e) {
    if (!waypointMarkers.size || !waypointClickListeners.size) return false;
    const rect = el.getBoundingClientRect();
    const mouse = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1
    );

    raycaster.setFromCamera(mouse, camera);

    const candidates = [];
    for (const markerObj of waypointMarkers.values()) {
      candidates.push(...markerObj.meshes);
    }

    const intersects = raycaster.intersectObjects(candidates, false);
    if (intersects.length > 0) {
      const hit = intersects[0];
      const wpId = hit.object.userData?.id;
      if (wpId) {
        waypointClickListeners.forEach(listener => {
          try { listener(wpId); } catch (err) { console.error(err); }
        });
        return true;
      }
    }
    return false;
  }

  function onWaypointClick(callback) {
    if (typeof callback === 'function') {
      waypointClickListeners.add(callback);
      return () => waypointClickListeners.delete(callback);
    }
    return () => {};
  }

  // Camera Fly-To Interpolation
  function flyTo(lat, lon, { duration = 1400, targetDistance = 1.85, onComplete = () => {} } = {}) {
    const prefersReducedMotion = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
    const effectiveDuration = prefersReducedMotion ? 0 : duration;

    const target = calculateTargetOrbit(lat, lon, earth.rotation.y, { targetDistance });
    idleSpin = false; // Pause automatic rotation while focused on a location

    if (effectiveDuration <= 0) {
      orbit.yaw = target.yaw;
      orbit.pitch = target.pitch;
      orbit.distance = target.distance;
      orbit.velocityYaw = 0;
      orbit.velocityPitch = 0;
      onComplete();
      return;
    }

    flyToAnimation = {
      startTime: performance.now(),
      duration: effectiveDuration,
      startOrbit: { ...orbit },
      targetOrbit: target,
      onComplete
    };
  }

  let running = true;
  container.dataset.rendering = 'active';

  function tick(now) {
    if (disposed || !running) return;
    const dt = Math.min(0.1, last ? (now - last) / 1000 : 0.016);
    last = now;

    if (flyToAnimation) {
      const elapsed = (now - flyToAnimation.startTime) / flyToAnimation.duration;
      if (elapsed >= 1) {
        const target = flyToAnimation.targetOrbit;
        const start = flyToAnimation.startOrbit;
        orbit.yaw = start.yaw + shortestAngleDiff(target.yaw, start.yaw);
        orbit.pitch = target.pitch;
        orbit.distance = target.distance;
        orbit.velocityYaw = 0;
        orbit.velocityPitch = 0;
        const cb = flyToAnimation.onComplete;
        flyToAnimation = null;
        cb();
      } else {
        const cur = interpolateOrbit(flyToAnimation.startOrbit, flyToAnimation.targetOrbit, elapsed);
        orbit.yaw = cur.yaw;
        orbit.pitch = cur.pitch;
        orbit.distance = cur.distance;
        orbit.velocityYaw = 0;
        orbit.velocityPitch = 0;
      }
    } else {
      if (!dragging) applyInertia(orbit, dt);
      if (idleSpin && !activeMarker) {
        earth.rotation.y += dt * 0.02; // slow idle spin
      }
    }

    if (dayNightEnabled) {
      updateDayNightSun();
    }

    const p = cameraPosition(orbit);
    camera.position.set(p.x, p.y, p.z);
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
    container.dataset.frames = String((Number(container.dataset.frames) || 0) + 1);
    frame = requestAnimationFrame(tick);
  }
  frame = requestAnimationFrame(tick);

  return {
    orbit,
    earth,
    scene,
    camera,
    flyTo,
    setMarker,
    clearMarker,
    getMarker: () => activeMarker,
    setWaypoints,
    highlightWaypointMarker,
    clearWaypoints,
    onWaypointClick,
    getWaypointMarkers: () => waypointMarkers,
    getSelectedWaypointId: () => selectedWaypointId,
    isAnimating: () => !!flyToAnimation,
    setDayNight,
    isDayNightEnabled: () => dayNightEnabled,
    pause() {
      if (!running || disposed) return;
      running = false;
      if (frame) {
        cancelAnimationFrame(frame);
        frame = null;
      }
      container.dataset.rendering = 'paused';
      if (this.localTimeController) this.localTimeController.pause();
    },
    resume() {
      if (running || disposed) return;
      running = true;
      last = 0;
      frame = requestAnimationFrame(tick);
      container.dataset.rendering = 'active';
      resize();
      if (this.localTimeController) this.localTimeController.resume();
    },
    isPaused: () => !running,
    dispose() {
      if (disposed) return;
      disposed = true;
      running = false;
      container.dataset.rendering = 'disposed';
      if (this.localTimeController) this.localTimeController.dispose();
      cancelFlyTo();
      clearMarker();
      clearWaypoints();
      waypointClickListeners.clear();
      clearTimeout(textureTimeout);
      if (frame) {
        cancelAnimationFrame(frame);
        frame = null;
      }
      resizeObserver.disconnect();
      dprQuery?.removeEventListener('change', onDpr);
      el.removeEventListener('pointerdown', onDown);
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerup', onUp);
      el.removeEventListener('pointercancel', onUp);
      el.removeEventListener('wheel', onWheel);
      el.removeEventListener('keydown', onKey);
      el.removeEventListener('webglcontextlost', onLost);
      earthGeometry.dispose();
      earthMaterial.dispose();
      atmosphereGeometry.dispose();
      atmosphereMaterial.dispose();
      sun.dispose?.();
      texture?.dispose();
      renderer.dispose();
      el.remove();
      host.__earthInstance = null;
      if (window.__luminaEarth) window.__luminaEarth = null;
      status('disposed', 'Earth view closed');
    },
  };
}

// Exported Earth initializer (used by both standalone prototype and Lumina workspace)
export function initEarth(host = document.getElementById('earth-stage'), options = {}) {
  if (!host) return null;
  if (host.__earthInstance) {
    return host.__earthInstance;
  }
  const label = options.statusLabel || document.getElementById('earth-status');
  try {
    const view = createEarth(host, {
      onStatus: (state, message) => {
        if (label) {
          label.textContent = message;
          label.dataset.state = state;
          label.hidden = (state === 'ready');
        }
        if (typeof options.onStatus === 'function') {
          options.onStatus(state, message);
        }
      }
    });

    // Day/Night visualization toggle
    const dayNightBtn = options.dayNightBtn || document.getElementById('earth-toggle-daynight');
    const dayNightLabel = options.dayNightLabel || document.getElementById('earth-toggle-label');
    if (dayNightBtn) {
      dayNightBtn.addEventListener('click', () => {
        const next = !view.isDayNightEnabled();
        view.setDayNight(next);
        dayNightBtn.setAttribute('aria-pressed', String(next));
        if (dayNightLabel) dayNightLabel.textContent = `Day/Night: ${next ? 'ON' : 'OFF'}`;
      });
    }

    // Weather Controller
    const weatherContainer = options.weatherContainer || document.getElementById('earth-weather-container');
    const weatherCtrl = createWeatherController({
      container: weatherContainer,
      weatherEndpoint: options.weatherEndpoint || '/api/earth/weather'
    });
    view.weatherController = weatherCtrl;

    // Local Time Controller (P1.6)
    const localTimeWrap = options.localTimeWrap || document.getElementById('earth-local-time-wrap');
    let localTimeCtrl = null;
    if (localTimeWrap) {
      localTimeCtrl = createLocalTimeController({
        container: localTimeWrap
      });
      view.localTimeController = localTimeCtrl;
    }

    // Atlas Controller (P1.5 Saved Places)
    const atlasPanel = options.atlasPanel || document.getElementById('earth-atlas-panel');
    const atlasToggleBtn = options.atlasToggleBtn || document.getElementById('earth-toggle-atlas');
    const atlasToggleLabel = options.atlasToggleLabel || document.getElementById('earth-atlas-label');
    const saveLocationBtn = options.saveLocationBtn || document.getElementById('earth-save-location-btn');
    const infoCard = options.infoCard || document.getElementById('earth-info-card');

    let atlasCtrl = null;
    if (atlasPanel) {
      const apiClient = options.atlasApiClient || createAtlasApiClient({
        getHeaders: options.getHeaders || (() => ({ 'Content-Type': 'application/json' })),
        baseUrl: options.atlasEndpoint || '/api/earth/waypoints',
        historyBaseUrl: options.historyEndpoint || '/api/earth/history'
      });

      atlasCtrl = createAtlasController({
        panel: atlasPanel,
        toggleBtn: atlasToggleBtn,
        toggleLabel: atlasToggleLabel,
        saveBtn: saveLocationBtn,
        infoCard: infoCard,
        earthView: view,
        apiClient: apiClient,
        notice: options.notice || ((msg) => console.log(msg)),
        onSelectWaypoint: (wp) => {
          if (weatherCtrl && typeof weatherCtrl.loadWeather === 'function') {
            weatherCtrl.loadWeather(wp.latitude, wp.longitude).then(report => {
              if (report?.location?.timezone && localTimeCtrl && !localTimeCtrl.getTimezone()) {
                localTimeCtrl.setTimezone(report.location.timezone, wp.name);
              }
            }).catch(() => {});
          }
          if (localTimeCtrl) {
            localTimeCtrl.setTimezone(wp.timezone || null, wp.name);
          }
        },
        onSelectHistory: (candidate) => {
          view.setMarker(candidate.latitude, candidate.longitude, candidate);
          view.flyTo(candidate.latitude, candidate.longitude);
          if (weatherCtrl && typeof weatherCtrl.loadWeather === 'function') {
            weatherCtrl.loadWeather(candidate.latitude, candidate.longitude).then(report => {
              if (report?.location?.timezone && (!candidate.timezone || candidate.timezone !== report.location.timezone)) {
                if (localTimeCtrl) localTimeCtrl.setTimezone(report.location.timezone, candidate.name);
              }
            }).catch(() => {});
          }
          if (localTimeCtrl) {
            localTimeCtrl.setTimezone(candidate.timezone, candidate.name);
          }
          if (infoCard) {
            const titleEl = infoCard.querySelector('#earth-info-title');
            const subEl = infoCard.querySelector('#earth-info-sub');
            const detailsEl = infoCard.querySelector('#earth-info-details');
            if (titleEl) titleEl.textContent = candidate.name;
            if (subEl) {
              const parts = [candidate.admin1, candidate.country].filter(Boolean);
              subEl.textContent = parts.join(' · ') || 'Geographic Location';
            }
            if (detailsEl) {
              const coords = formatCoordinates(candidate.latitude, candidate.longitude);
              const tz = candidate.timezone ? `<span class="earth-info-badge">${candidate.timezone}</span>` : '';
              detailsEl.innerHTML = `<span class="earth-info-badge">${coords}</span>${tz}`;
            }
            infoCard.hidden = false;
          }
          atlasCtrl.setCurrentCandidate(candidate);
          atlasCtrl.recordHistory(candidate);
        }
      });
      view.atlasController = atlasCtrl;

      view.onWaypointClick((id) => {
        atlasCtrl.selectWaypoint(id, { fly: true });
      });

      atlasCtrl.loadWaypoints().catch(err => {
        console.warn('Initial Atlas waypoints load warning:', err);
      });
    }

    const searchForm = options.searchForm || document.getElementById('earth-search-form');
    const searchInput = options.searchInput || document.getElementById('earth-search-input');
    const searchSubmit = options.searchSubmit || document.getElementById('earth-search-submit');
    const searchClear = options.searchClear || document.getElementById('earth-search-clear');
    const resultsList = options.resultsList || document.getElementById('earth-search-results');
    const feedback = options.feedback || document.getElementById('earth-search-feedback');

    if (searchForm && searchInput) {
      const searchCtrl = createSearchController({
        form: searchForm,
        input: searchInput,
        submitBtn: searchSubmit,
        clearBtn: searchClear,
        resultsList: resultsList,
        feedback: feedback,
        infoCard: infoCard,
        searchEndpoint: options.searchEndpoint || '/api/earth/search',
        onSelect: (candidate) => {
          view.setMarker(candidate.latitude, candidate.longitude, candidate);
          view.flyTo(candidate.latitude, candidate.longitude);
          if (weatherCtrl && typeof weatherCtrl.loadWeather === 'function') {
            weatherCtrl.loadWeather(candidate.latitude, candidate.longitude).then(report => {
              if (report?.location?.timezone && (!candidate.timezone || candidate.timezone !== report.location.timezone)) {
                if (localTimeCtrl) localTimeCtrl.setTimezone(report.location.timezone, candidate.name);
              }
            }).catch(() => {});
          }
          if (atlasCtrl) {
            atlasCtrl.setCurrentCandidate(candidate);
            atlasCtrl.recordHistory(candidate);
          }
          if (localTimeCtrl) {
            localTimeCtrl.setTimezone(candidate.timezone, candidate.name);
          }
        }
      });
      view.searchController = searchCtrl;
    }

    const closeBtn = infoCard?.querySelector('#earth-info-close') || options.infoCloseBtn;
    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        weatherCtrl.clear();
        localTimeCtrl?.clear();
      });
    }

    window.addEventListener('pagehide', () => {
      atlasCtrl?.dispose();
      weatherCtrl.dispose();
      localTimeCtrl?.dispose();
      view.searchController?.dispose();
      view.dispose();
      host.__earthInstance = null;
    }, { once: true });
    host.__earthInstance = view;
    window.__luminaEarth = view;
    return view;
  } catch (error) {
    if (label) {
      label.textContent = 'The Earth prototype failed to start: ' + (error.message || error);
      label.dataset.state = 'error';
      label.hidden = false;
    }
    host.dataset.earthState = 'error';
    console.error(error);
    if (typeof options.onError === 'function') {
      options.onError(error);
    }
    return null;
  }
}

// Standalone Page bootstrap (only when loaded directly by earth-prototype.html).
function autoInitStandalone() {
  const standaloneHost = document.getElementById?.('earth-stage');
  if (standaloneHost && (document.body?.classList?.contains('earth-standalone') || window.__luminaEarthStandalone === true)) {
    initEarth(standaloneHost);
  }
}
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInitStandalone, { once: true });
  } else {
    autoInitStandalone();
  }
}
