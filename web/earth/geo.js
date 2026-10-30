// Lumina Earth P0.2 — Pure geographic coordinate engine
// Renderer-independent mathematical module: converts between WGS84 geographic coordinates
// (latitude, longitude, altitude) and Three.js 3D Cartesian coordinates (x, y, z).
// Matches Three.js SphereGeometry and standard equirectangular Earth texture conventions.

/**
 * Fundamental geographic constants.
 */
export const GEO_CONSTANTS = Object.freeze({
  EARTH_RADIUS_METERS: 6371008.8, // IUGG mean Earth radius
  PROTOTYPE_GLOBE_RADIUS: 1.0,     // Lumina Earth P0.1 Three.js sphere radius
  EPSILON: 1e-12,                 // Floating-point comparison tolerance
  MIN_LATITUDE: -90,
  MAX_LATITUDE: 90,
  MIN_LONGITUDE: -180,
  MAX_LONGITUDE: 180,
  SURFACE_MARKER_ALTITUDE_DEFAULT: 0.003 // Subtle radial offset preventing z-fighting with sphere mesh
});

/**
 * Validates and clamps floating-point boundary errors on latitude.
 * Rejects non-finite values and latitudes outside [-90, 90].
 *
 * @param {number} lat - Latitude in degrees (-90 to +90)
 * @returns {number} Validated latitude
 * @throws {TypeError} If lat is not a finite number
 * @throws {RangeError} If lat is outside [-90, 90]
 */
export function validateLatitude(lat) {
  if (typeof lat !== 'number' || !Number.isFinite(lat)) {
    throw new TypeError(`Latitude must be a finite number, received: ${typeof lat === 'string' ? JSON.stringify(lat) : lat}`);
  }
  // Tolerant clamp for double-precision epsilon around poles
  if (lat > 90 && lat <= 90 + GEO_CONSTANTS.EPSILON) return 90;
  if (lat < -90 && lat >= -90 - GEO_CONSTANTS.EPSILON) return -90;
  if (lat < -90 || lat > 90) {
    throw new RangeError(`Latitude must be between -90 and +90 degrees, received: ${lat}`);
  }
  return lat;
}

/**
 * Normalizes any longitude into the canonical [-180, +180] degree range.
 * 
 * Convention:
 * - Antimeridian: -180° and +180° represent the exact same geographic meridian.
 *   Positive 180 is preserved if input was positive 180.
 * - Values outside [-180, 180] are wrapped modulo 360°.
 *
 * @param {number} lon - Longitude in degrees
 * @returns {number} Normalized longitude in [-180, 180]
 * @throws {TypeError} If lon is not a finite number
 */
export function normalizeLongitude(lon) {
  if (typeof lon !== 'number' || !Number.isFinite(lon)) {
    throw new TypeError(`Longitude must be a finite number, received: ${typeof lon === 'string' ? JSON.stringify(lon) : lon}`);
  }
  // Fast path for canonical values around boundaries
  if (Math.abs(lon - 180) < GEO_CONSTANTS.EPSILON) return 180;
  if (Math.abs(lon + 180) < GEO_CONSTANTS.EPSILON) return -180;

  let n = (lon + 180) % 360;
  if (n < 0) n += 360;
  let normalized = n - 180;

  // Preserve +180 sign if the input had positive orientation
  if (normalized === -180 && lon > 0) normalized = 180;

  // Eliminate negative zero (-0 -> 0)
  return Object.is(normalized, -0) ? 0 : normalized;
}

/**
 * Validates longitude input without normalization, ensuring it is within [-180, 180].
 *
 * @param {number} lon - Longitude in degrees
 * @returns {number} Validated longitude
 * @throws {TypeError} If lon is not a finite number
 * @throws {RangeError} If lon is outside [-180, 180]
 */
export function validateLongitude(lon) {
  if (typeof lon !== 'number' || !Number.isFinite(lon)) {
    throw new TypeError(`Longitude must be a finite number, received: ${typeof lon === 'string' ? JSON.stringify(lon) : lon}`);
  }
  if (lon > 180 && lon <= 180 + GEO_CONSTANTS.EPSILON) return 180;
  if (lon < -180 && lon >= -180 - GEO_CONSTANTS.EPSILON) return -180;
  if (lon < -180 || lon > 180) {
    throw new RangeError(`Longitude must be between -180 and +180 degrees, received: ${lon}`);
  }
  return lon;
}

/**
 * Converts geographic coordinates (latitude, longitude) to 3D Cartesian coordinates (x, y, z)
 * matching Three.js SphereGeometry and equirectangular texture orientation.
 *
 * Orientation Convention:
 * - Y axis: North pole is +Y (lat = +90° -> (0, R, 0)), South pole is -Y (lat = -90° -> (0, -R, 0)).
 * - X axis: Prime meridian (lon = 0°) at Equator (lat = 0°) is +X ((R, 0, 0)).
 * - Z axis: 90°W (lon = -90°) at Equator is +Z ((0, 0, R)). 90°E (lon = +90°) at Equator is -Z ((0, 0, -R)).
 * - Antimeridian: 180° lon at Equator is -X ((-R, 0, 0)).
 *
 * Equations:
 *   latRad = lat * (π / 180)
 *   lonRad = lon * (π / 180)
 *   r = radius + altitude
 *   x = r * cos(latRad) * cos(lonRad)
 *   y = r * sin(latRad)
 *   z = - r * cos(latRad) * sin(lonRad)
 *
 * @param {number} lat - Latitude in degrees (-90 to +90)
 * @param {number} lon - Longitude in degrees (automatically normalized if valid finite number)
 * @param {Object} [options]
 * @param {number} [options.radius=1.0] - Sphere radius (must be > 0)
 * @param {number} [options.altitude=0.0] - Altitude offset above sphere surface (>= 0)
 * @returns {{ x: number, y: number, z: number }} 3D Cartesian coordinates
 */
export function latLonToVector(lat, lon, { radius = 1.0, altitude = 0.0 } = {}) {
  const validLat = validateLatitude(lat);
  const normLon = normalizeLongitude(lon);

  if (typeof radius !== 'number' || !Number.isFinite(radius)) {
    throw new TypeError(`Sphere radius must be a finite number, received: ${radius}`);
  }
  if (radius <= 0) {
    throw new RangeError(`Sphere radius must be strictly positive, received: ${radius}`);
  }

  if (typeof altitude !== 'number' || !Number.isFinite(altitude)) {
    throw new TypeError(`Altitude must be a finite number, received: ${altitude}`);
  }
  if (altitude < 0) {
    throw new RangeError(`Altitude must be non-negative, received: ${altitude}`);
  }

  const r = radius + altitude;
  const latRad = validLat * (Math.PI / 180);
  const lonRad = normLon * (Math.PI / 180);

  const cosLat = Math.cos(latRad);
  const sinLat = Math.sin(latRad);
  const cosLon = Math.cos(lonRad);
  const sinLon = Math.sin(lonRad);

  const x = r * cosLat * cosLon;
  const y = r * sinLat;
  const z = -r * cosLat * sinLon;

  return {
    x: Object.is(x, -0) ? 0 : x,
    y: Object.is(y, -0) ? 0 : y,
    z: Object.is(z, -0) ? 0 : z
  };
}

/**
 * Converts a non-zero 3D Cartesian position vector (x, y, z) back to geographic
 * latitude, longitude, and radius.
 *
 * Inverse Equations:
 *   r = sqrt(x^2 + y^2 + z^2)
 *   latRad = asin(clamp(y / r, -1, 1))
 *   lonRad = atan2(-z, x)
 *   lat = latRad * (180 / π)
 *   lon = lonRad * (180 / π)
 *
 * At the poles (lat = ±90°), longitude is degenerate and is set to 0.0.
 *
 * @param {number} x - Cartesian X coordinate
 * @param {number} y - Cartesian Y coordinate
 * @param {number} z - Cartesian Z coordinate
 * @returns {{ lat: number, lon: number, radius: number }}
 * @throws {TypeError} If any coordinate is not a finite number
 * @throws {RangeError} If the vector has zero length (origin)
 */
export function vectorToLatLon(x, y, z) {
  if (typeof x !== 'number' || !Number.isFinite(x) ||
      typeof y !== 'number' || !Number.isFinite(y) ||
      typeof z !== 'number' || !Number.isFinite(z)) {
    throw new TypeError(`Cartesian coordinates (x, y, z) must be finite numbers, received: (${x}, ${y}, ${z})`);
  }

  const r = Math.hypot(x, y, z);
  if (r < GEO_CONSTANTS.EPSILON) {
    throw new RangeError('Cannot convert zero-length Cartesian position vector to geographic coordinates');
  }

  const normalizedY = Math.min(1, Math.max(-1, y / r));
  const latRad = Math.asin(normalizedY);
  let lat = latRad * (180 / Math.PI);

  // Guard pole singularity: at exact poles, longitude is degenerate
  let lon = 0;
  if (Math.abs(Math.abs(normalizedY) - 1.0) > GEO_CONSTANTS.EPSILON) {
    const lonRad = Math.atan2(-z, x);
    lon = lonRad * (180 / Math.PI);
  } else {
    lat = normalizedY > 0 ? 90 : -90;
  }

  const normLon = normalizeLongitude(lon);

  return {
    lat: Object.is(lat, -0) ? 0 : lat,
    lon: Object.is(normLon, -0) ? 0 : normLon,
    radius: r
  };
}

/**
 * Computes great-circle surface distance between two points on a spherical Earth (Haversine formula).
 *
 * @param {number} lat1 - Latitude of first point in degrees
 * @param {number} lon1 - Longitude of first point in degrees
 * @param {number} lat2 - Latitude of second point in degrees
 * @param {number} lon2 - Longitude of second point in degrees
 * @param {number} [radius=GEO_CONSTANTS.EARTH_RADIUS_METERS] - Sphere radius
 * @returns {number} Distance in the units of radius
 */
export function surfaceDistance(lat1, lon1, lat2, lon2, radius = GEO_CONSTANTS.EARTH_RADIUS_METERS) {
  const phi1 = validateLatitude(lat1) * (Math.PI / 180);
  const phi2 = validateLatitude(lat2) * (Math.PI / 180);
  const deltaPhi = (validateLatitude(lat2) - validateLatitude(lat1)) * (Math.PI / 180);
  const deltaLambda = (normalizeLongitude(lon2) - normalizeLongitude(lon1)) * (Math.PI / 180);

  const a = Math.sin(deltaPhi / 2) ** 2 +
            Math.cos(phi1) * Math.cos(phi2) * (Math.sin(deltaLambda / 2) ** 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(Math.max(0, 1 - a)));

  return radius * c;
}
