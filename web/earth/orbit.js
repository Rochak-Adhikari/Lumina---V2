// Lumina Earth P0.1 — renderer-independent orbit math (testable in Node).
export const ORBIT_LIMITS = Object.freeze({ minDistance: 1.35, maxDistance: 6, minPitch: -1.45, maxPitch: 1.45 });

export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

export function createOrbitState(init = {}) {
  return { yaw: init.yaw ?? 0, pitch: init.pitch ?? 0.35, distance: init.distance ?? 3.2, velocityYaw: 0, velocityPitch: 0 };
}

/** Apply a pointer drag in CSS pixels; rotation speed scales with zoom so the surface tracks the cursor. */
export function applyDrag(state, dx, dy, viewportHeight, limits = ORBIT_LIMITS) {
  const scale = (Math.PI / Math.max(1, viewportHeight)) * ((state.distance - 1) / 2.2);
  state.velocityYaw = -dx * scale;
  state.velocityPitch = dy * scale;
  state.yaw += state.velocityYaw;
  state.pitch = clamp(state.pitch + state.velocityPitch, limits.minPitch, limits.maxPitch);
  return state;
}

/** Wheel zoom: exponential, clamped to limits. */
export function applyZoom(state, deltaY, limits = ORBIT_LIMITS) {
  const factor = Math.exp(clamp(deltaY, -500, 500) * 0.0012);
  state.distance = clamp(state.distance * factor, limits.minDistance, limits.maxDistance);
  return state;
}

/** Inertia decay per frame; returns true while still moving. */
export function applyInertia(state, dtSeconds, limits = ORBIT_LIMITS) {
  const decay = Math.pow(0.04, dtSeconds);
  state.velocityYaw *= decay;
  state.velocityPitch *= decay;
  state.yaw += state.velocityYaw;
  state.pitch = clamp(state.pitch + state.velocityPitch, limits.minPitch, limits.maxPitch);
  return Math.abs(state.velocityYaw) + Math.abs(state.velocityPitch) > 1e-5;
}

/** Camera position on a sphere around the origin (Y up). */
export function cameraPosition(state) {
  const c = Math.cos(state.pitch);
  return { x: state.distance * c * Math.sin(state.yaw), y: state.distance * Math.sin(state.pitch), z: state.distance * c * Math.cos(state.yaw) };
}

/** Calculate shortest angular distance on a circle (in radians, range [-π, +π]). */
export function shortestAngleDiff(targetAngle, startAngle) {
  let diff = (targetAngle - startAngle) % (2 * Math.PI);
  if (diff > Math.PI) diff -= 2 * Math.PI;
  if (diff < -Math.PI) diff += 2 * Math.PI;
  return diff;
}

/** Smooth cubic ease in-out curve for natural camera acceleration and deceleration. */
export function easeInOutCubic(t) {
  const clamped = clamp(t, 0, 1);
  return clamped < 0.5 ? 4 * clamped * clamped * clamped : 1 - Math.pow(-2 * clamped + 2, 3) / 2;
}

/**
 * Calculates target camera orbit (yaw, pitch, distance) needed to center a geographic
 * coordinate (latitude, longitude) in the viewport given current globe rotation.
 */
export function calculateTargetOrbit(lat, lon, earthRotationY = 0, { targetDistance = 1.85, limits = ORBIT_LIMITS } = {}) {
  const latRad = lat * (Math.PI / 180);
  const lonRad = lon * (Math.PI / 180);

  // Local Cartesian coordinate from geo convention
  const localX = Math.cos(latRad) * Math.cos(lonRad);
  const localY = Math.sin(latRad);
  const localZ = -Math.cos(latRad) * Math.sin(lonRad);

  // Transform to world space using current Earth Y-rotation
  const cosRot = Math.cos(earthRotationY);
  const sinRot = Math.sin(earthRotationY);
  const worldX = localX * cosRot + localZ * sinRot;
  const worldY = localY;
  const worldZ = -localX * sinRot + localZ * cosRot;

  const r = Math.hypot(worldX, worldY, worldZ);
  const targetPitch = clamp(Math.asin(Math.min(1, Math.max(-1, worldY / Math.max(1e-9, r)))), limits.minPitch, limits.maxPitch);
  const targetYaw = Math.atan2(worldX, worldZ);

  return {
    yaw: targetYaw,
    pitch: targetPitch,
    distance: clamp(targetDistance, limits.minDistance, limits.maxDistance)
  };
}

/**
 * Smoothly interpolates an orbit state toward target orbit using cubic easing and shortest angular path.
 */
export function interpolateOrbit(startOrbit, targetOrbit, progress) {
  const ease = easeInOutCubic(progress);
  const diffYaw = shortestAngleDiff(targetOrbit.yaw, startOrbit.yaw);

  return {
    yaw: startOrbit.yaw + diffYaw * ease,
    pitch: startOrbit.pitch + (targetOrbit.pitch - startOrbit.pitch) * ease,
    distance: startOrbit.distance + (targetOrbit.distance - startOrbit.distance) * ease,
    velocityYaw: 0,
    velocityPitch: 0
  };
}

/** Pixel ratio capped for GPU cost; always >= 1. */
export function renderPixelRatio(devicePixelRatio, cap = 2) {
  const r = Number(devicePixelRatio);
  return clamp(Number.isFinite(r) && r > 0 ? r : 1, 1, cap);
}
