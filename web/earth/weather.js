// Lumina Earth P0.4 — Weather Controller & UI Presentation Logic
// Decoupled, testable in Node and modern browsers.
// Integrates Open-Meteo weather adapter contract with zero-budget attribution.

/**
 * Maps WMO 4677 weather code to human-readable condition description and emoji icon.
 *
 * @param {number|null} code - WMO weather code
 * @returns {{ description: string, icon: string }}
 */
export function getWmoWeatherInfo(code) {
  if (code === null || code === undefined || typeof code !== 'number') {
    return { description: 'Unknown condition', icon: '☁' };
  }
  switch (code) {
    case 0: return { description: 'Clear sky', icon: '☀' };
    case 1: return { description: 'Mainly clear', icon: '🌤' };
    case 2: return { description: 'Partly cloudy', icon: '⛅' };
    case 3: return { description: 'Overcast', icon: '☁' };
    case 45: return { description: 'Foggy', icon: '🌫' };
    case 48: return { description: 'Depositing rime fog', icon: '🌫' };
    case 51: return { description: 'Light drizzle', icon: '🌦' };
    case 53: return { description: 'Moderate drizzle', icon: '🌦' };
    case 55: return { description: 'Dense drizzle', icon: '🌧' };
    case 56: return { description: 'Light freezing drizzle', icon: '🌧' };
    case 57: return { description: 'Dense freezing drizzle', icon: '🌧' };
    case 61: return { description: 'Slight rain', icon: '🌧' };
    case 63: return { description: 'Moderate rain', icon: '🌧' };
    case 65: return { description: 'Heavy rain', icon: '🌧' };
    case 66: return { description: 'Light freezing rain', icon: '🌧' };
    case 67: return { description: 'Heavy freezing rain', icon: '🌧' };
    case 71: return { description: 'Slight snow fall', icon: '🌨' };
    case 73: return { description: 'Moderate snow fall', icon: '🌨' };
    case 75: return { description: 'Heavy snow fall', icon: '🌨' };
    case 77: return { description: 'Snow grains', icon: '🌨' };
    case 80: return { description: 'Slight rain showers', icon: '🌦' };
    case 81: return { description: 'Moderate rain showers', icon: '🌧' };
    case 82: return { description: 'Violent rain showers', icon: '⛈' };
    case 85: return { description: 'Slight snow showers', icon: '🌨' };
    case 86: return { description: 'Heavy snow showers', icon: '🌨' };
    case 95: return { description: 'Thunderstorm', icon: '⛈' };
    case 96: return { description: 'Thunderstorm with slight hail', icon: '⛈' };
    case 99: return { description: 'Thunderstorm with heavy hail', icon: '⛈' };
    default: return { description: `Weather code ${code}`, icon: '☁' };
  }
}

/**
 * Converts wind direction in degrees (0-360) to 8-point compass cardinal direction.
 *
 * @param {number|null} degrees - Direction in degrees
 * @returns {string} Cardinal direction (e.g. "N", "NE", "E")
 */
export function degreesToCardinal(degrees) {
  if (typeof degrees !== 'number' || !Number.isFinite(degrees)) return '';
  const cardinals = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  const normalized = ((degrees % 360) + 360) % 360;
  const idx = Math.round(normalized / 45) % 8;
  return cardinals[idx];
}

/**
 * Formats temperature value with units.
 *
 * @param {number|null} temp - Temperature number
 * @param {string} [unit='°C'] - Temperature unit
 * @returns {string} Formatted string, e.g. "21.5°C" or "N/A"
 */
export function formatTemperature(temp, unit = '°C') {
  if (temp === null || temp === undefined || !Number.isFinite(temp)) return 'N/A';
  return `${Math.round(temp * 10) / 10}${unit}`;
}

/**
 * Formats wind speed and direction into a compact string.
 *
 * @param {number|null} speed - Wind speed
 * @param {number|null} direction - Wind direction in degrees
 * @param {string} [unit='km/h'] - Speed unit
 * @returns {string} e.g. "8.5 km/h S" or "N/A"
 */
export function formatWind(speed, direction, unit = 'km/h') {
  if (speed === null || speed === undefined || !Number.isFinite(speed)) return 'N/A';
  const card = degreesToCardinal(direction);
  return `${Math.round(speed * 10) / 10} ${unit}${card ? ` ${card}` : ''}`;
}

/**
 * Formats a forecast date string (YYYY-MM-DD) into weekday name.
 *
 * @param {string} dateStr - Date string "YYYY-MM-DD"
 * @param {number} [dayIndex=0] - Index in forecast (0 = today)
 * @returns {string} e.g. "Today" or "Fri"
 */
export function formatForecastDay(dateStr, dayIndex = 0) {
  if (dayIndex === 0) return 'Today';
  if (!dateStr) return `Day ${dayIndex + 1}`;
  try {
    const parts = dateStr.split('-');
    if (parts.length === 3) {
      const d = new Date(Date.UTC(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])));
      return d.toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' });
    }
  } catch (_) {}
  return dateStr;
}

/**
 * Creates an in-memory weather cache with time-to-live (TTL).
 *
 * @param {number} [ttlMs=300000] - Cache lifetime in milliseconds (default: 5 minutes)
 */
export function createWeatherCache(ttlMs = 300000) {
  const store = new Map();

  const makeKey = (lat, lon, units) => {
    return `${Number(lat).toFixed(3)},${Number(lon).toFixed(3)},${units}`;
  };

  return {
    get(lat, lon, units = 'metric') {
      const key = makeKey(lat, lon, units);
      const entry = store.get(key);
      if (!entry) return null;
      if (Date.now() - entry.time > ttlMs) {
        store.delete(key);
        return null;
      }
      return entry.data;
    },
    set(lat, lon, data, units = 'metric') {
      const key = makeKey(lat, lon, units);
      store.set(key, { data, time: Date.now() });
    },
    clear() {
      store.clear();
    },
    size() {
      return store.size;
    }
  };
}

/**
 * Creates and manages weather data retrieval, caching, UI state lifecycle,
 * and stale-response discarding.
 */
export function createWeatherController({
  container,
  weatherEndpoint = '/api/earth/weather',
  cacheTtlMs = 300000,
  fetchFn = (typeof window !== 'undefined' ? window.fetch.bind(window) : null),
  units = 'metric'
} = {}) {
  let activeRequestId = 0;
  const cache = createWeatherCache(cacheTtlMs);
  let disposed = false;
  let lastLoadedReport = null;

  const renderLoading = () => {
    if (!container) return;
    container.innerHTML = `
      <div class="earth-weather-loading" role="status" aria-live="polite">
        <span class="earth-weather-spinner"></span>
        <span>Loading current weather & forecast…</span>
      </div>
    `;
    container.hidden = false;
  };

  const renderError = (errorMessage, onRetry = null) => {
    if (!container) return;
    container.innerHTML = `
      <div class="earth-weather-error" role="alert">
        <div class="earth-weather-error-msg">Weather unavailable: ${errorMessage}</div>
        ${onRetry ? '<button type="button" class="earth-weather-retry-btn">Retry</button>' : ''}
      </div>
    `;
    container.hidden = false;
    if (onRetry) {
      const btn = container.querySelector('.earth-weather-retry-btn');
      if (btn) btn.addEventListener('click', onRetry, { once: true });
    }
  };

  const renderWeather = (report) => {
    if (!container) return;
    lastLoadedReport = report;

    const cur = report?.current || {};
    const daily = Array.isArray(report?.daily) ? report.daily : [];
    const reportUnits = report?.units || {};
    const tempUnit = reportUnits.temperature || reportUnits.temperature_2m || '°C';
    const windUnit = reportUnits.wind_speed || reportUnits.wind_speed_10m || 'km/h';
    const precipUnit = reportUnits.precipitation || reportUnits.precipitation_sum || 'mm';

    const curWmo = getWmoWeatherInfo(cur.weather_code);
    const tempText = formatTemperature(cur.temperature, tempUnit);
    const feelsText = cur.apparent_temperature != null ? `Feels like ${formatTemperature(cur.apparent_temperature, tempUnit)}` : '';
    const windText = formatWind(cur.wind_speed, cur.wind_direction, windUnit);
    const humidityText = cur.humidity_relative != null ? `${Math.round(cur.humidity_relative)}%` : 'N/A';
    const precipText = cur.precipitation != null ? `${cur.precipitation} ${precipUnit}` : 'N/A';
    const obsTime = cur.timestamp ? `Observed: ${cur.timestamp.replace('T', ' ')}` : 'Live observation';

    // Daily Forecast Items
    const forecastHtml = daily.slice(0, 7).map((day, idx) => {
      const dayLabel = formatForecastDay(day.date, idx);
      const wmo = getWmoWeatherInfo(day.weather_code);
      const maxT = formatTemperature(day.temperature_max, tempUnit);
      const minT = formatTemperature(day.temperature_min, tempUnit);
      const rain = day.precipitation_sum > 0 ? `<span class="earth-forecast-rain" title="Precipitation">${day.precipitation_sum}mm</span>` : '';

      return `
        <div class="earth-forecast-day" title="${wmo.description}">
          <span class="earth-forecast-label">${dayLabel}</span>
          <span class="earth-forecast-icon" aria-hidden="true">${wmo.icon}</span>
          <span class="earth-forecast-temp"><span class="earth-temp-max">${maxT}</span> <span class="earth-temp-min">${minT}</span></span>
          ${rain}
        </div>
      `;
    }).join('');

    container.innerHTML = `
      <div class="earth-weather-content">
        <!-- Current Weather Overview -->
        <div class="earth-weather-current">
          <div class="earth-weather-hero">
            <span class="earth-weather-icon" aria-hidden="true">${curWmo.icon}</span>
            <div class="earth-weather-temps">
              <span class="earth-weather-val">${tempText}</span>
              ${feelsText ? `<span class="earth-weather-feels">${feelsText}</span>` : ''}
            </div>
          </div>
          <div class="earth-weather-cond-text">${curWmo.description}</div>
        </div>

        <!-- Current Meteorological Metrics -->
        <div class="earth-weather-metrics">
          <div class="earth-metric-item" title="Wind speed & direction">
            <span class="earth-metric-label">Wind</span>
            <span class="earth-metric-val">${windText}</span>
          </div>
          <div class="earth-metric-item" title="Relative humidity">
            <span class="earth-metric-label">Humidity</span>
            <span class="earth-metric-val">${humidityText}</span>
          </div>
          <div class="earth-metric-item" title="Precipitation">
            <span class="earth-metric-label">Precip</span>
            <span class="earth-metric-val">${precipText}</span>
          </div>
        </div>

        <!-- 7-Day Forecast Section -->
        ${forecastHtml ? `
        <div class="earth-weather-forecast-wrap">
          <div class="earth-forecast-title">7-Day Forecast</div>
          <div class="earth-weather-forecast-strip" role="region" aria-label="Seven day forecast">
            ${forecastHtml}
          </div>
        </div>
        ` : ''}

        <div class="earth-weather-stamp">
          <span>${obsTime}</span>
          <span class="earth-weather-credit">Open-Meteo (CC BY 4.0)</span>
        </div>
      </div>
    `;
    container.hidden = false;
  };

  const loadWeather = async (latitude, longitude, customUnits = units) => {
    if (typeof latitude !== 'number' || typeof longitude !== 'number') {
      renderError('Invalid geographic coordinates.');
      return;
    }

    const currentReqId = ++activeRequestId;

    // Check in-memory cache first
    const cached = cache.get(latitude, longitude, customUnits);
    if (cached) {
      renderWeather(cached);
      return cached;
    }

    renderLoading();

    try {
      if (!fetchFn) throw new Error('Fetch API is not available.');
      const url = `${weatherEndpoint}?lat=${encodeURIComponent(latitude)}&lon=${encodeURIComponent(longitude)}&units=${encodeURIComponent(customUnits)}&days=7`;
      const res = await fetchFn(url, { headers: { 'Accept': 'application/json' } });

      if (currentReqId !== activeRequestId) {
        // Discard stale response
        return null;
      }

      if (!res.ok) {
        let errDetail = 'Weather request failed';
        try {
          const errData = await res.json();
          if (errData?.error) errDetail = errData.error;
        } catch (_) {}
        renderError(errDetail, () => loadWeather(latitude, longitude, customUnits));
        return null;
      }

      const json = await res.json();
      if (currentReqId !== activeRequestId) return null;

      const reportData = json?.data;
      if (!reportData || !reportData.current) {
        renderError('Received malformed weather data from provider.');
        return null;
      }

      // Cache successful response
      cache.set(latitude, longitude, reportData, customUnits);
      renderWeather(reportData);
      return reportData;
    } catch (err) {
      if (currentReqId !== activeRequestId) return null;
      renderError(err.message || 'Unable to connect to weather service.', () => loadWeather(latitude, longitude, customUnits));
      return null;
    }
  };

  const clear = () => {
    activeRequestId++;
    if (container) {
      container.innerHTML = '';
      container.hidden = true;
    }
    lastLoadedReport = null;
  };

  return {
    loadWeather,
    clear,
    getLastLoadedReport: () => lastLoadedReport,
    getCacheSize: () => cache.size(),
    clearCache: () => cache.clear(),
    renderWeather,
    renderLoading,
    renderError,
    dispose() {
      if (disposed) return;
      disposed = true;
      clear();
      cache.clear();
    }
  };
}
