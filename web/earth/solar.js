// Lumina Earth P0.4 — Solar Position & Subsolar Calculations
// Astronomical solar position approximation based on NOAA / Spencer formulas.
// Computes subsolar geographic coordinates (latitude, longitude) and 3D Cartesian
// unit vectors matching Lumina Earth's coordinate conventions in web/earth/geo.js.

import { latLonToVector, normalizeLongitude } from './geo.js';

/**
 * Calculates day of year (1 to 366) and fractional UTC hours from a Date.
 *
 * @param {Date} date - UTC Date
 * @returns {{ dayOfYear: number, utcHours: number }}
 */
export function getUtcTimeComponents(date) {
  const d = date instanceof Date ? date : new Date(date);
  const startOfYear = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const diffMs = d.getTime() - startOfYear.getTime();
  const dayOfYear = Math.floor(diffMs / 86400000) + 1;
  const utcHours = d.getUTCHours() + d.getUTCMinutes() / 60 + d.getUTCSeconds() / 3600 + d.getUTCMilliseconds() / 3600000;
  return { dayOfYear, utcHours };
}

/**
 * Calculates solar declination (subsolar latitude) and Equation of Time (EoT)
 * using the standard Spencer (1971) Fourier series approximation.
 *
 * Accuracy: ~0.1° declination, ~0.5 min EoT (sufficient for planetary day/night visualization).
 *
 * @param {number} dayOfYear - Day of year (1-366)
 * @param {number} utcHours - Fractional UTC hours (0-24)
 * @returns {{ declinationDeg: number, eotMinutes: number }}
 */
export function calculateSolarDeclinationAndEoT(dayOfYear, utcHours = 12) {
  // Fractional year in radians
  const gamma = (2 * Math.PI / 365.25) * (dayOfYear - 1 + (utcHours - 12) / 24);

  // Solar declination in radians
  const declinationRad =
    0.006918 -
    0.399912 * Math.cos(gamma) +
    0.070257 * Math.sin(gamma) -
    0.006758 * Math.cos(2 * gamma) +
    0.000907 * Math.sin(2 * gamma) -
    0.002697 * Math.cos(3 * gamma) +
    0.00148 * Math.sin(3 * gamma);

  // Equation of Time in minutes
  const eotMinutes =
    229.18 *
    (0.000075 +
      0.001868 * Math.cos(gamma) -
      0.032077 * Math.sin(gamma) -
      0.014615 * Math.cos(2 * gamma) -
      0.040849 * Math.sin(2 * gamma));

  return {
    declinationDeg: declinationRad * (180 / Math.PI),
    eotMinutes
  };
}

/**
 * Calculates the subsolar point (latitude, longitude) on Earth for a given UTC Date.
 *
 * @param {Date} [date=new Date()] - UTC Date
 * @returns {{
 *   latitude: number,
 *   longitude: number,
 *   declination: number,
 *   eotMinutes: number,
 *   utcHours: number
 * }}
 */
export function calculateSubsolarPoint(date = new Date()) {
  const { dayOfYear, utcHours } = getUtcTimeComponents(date);
  const { declinationDeg, eotMinutes } = calculateSolarDeclinationAndEoT(dayOfYear, utcHours);

  // Subsolar longitude:
  // At solar noon at Greenwich (12:00 UTC - EoT), Sun is at 0° longitude.
  // Earth rotates 15° per hour (Westward from Sun perspective -> positive East longitude).
  // lon = (12.0 - utcHours) * 15° - (eotMinutes / 4)
  const lonRaw = (12.0 - utcHours) * 15.0 - (eotMinutes / 4.0);
  const longitude = normalizeLongitude(lonRaw);

  return {
    latitude: declinationDeg,
    longitude,
    declination: declinationDeg,
    eotMinutes,
    utcHours
  };
}

/**
 * Calculates the 3D Cartesian unit vector pointing toward the Sun in Earth's local coordinate system.
 * Directly compatible with latLonToVector from web/earth/geo.js.
 *
 * @param {Date} [date=new Date()] - UTC Date
 * @param {number} [distance=1.0] - Radial distance multiplier
 * @returns {{ x: number, y: number, z: number }}
 */
export function calculateSubsolarVector(date = new Date(), distance = 1.0) {
  const subsolar = calculateSubsolarPoint(date);
  return latLonToVector(subsolar.latitude, subsolar.longitude, { radius: distance, altitude: 0 });
}
