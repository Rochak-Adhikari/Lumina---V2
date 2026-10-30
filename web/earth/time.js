/**
 * web/earth/time.js
 * 
 * Lumina Earth — Local Time Intelligence Module (P1.6).
 * Formats and maintains live local wall-clock time and calendar date for geographic
 * locations across global IANA timezones, half-hour/quarter-hour offsets, and DST transitions.
 * Pure standard library (Intl.DateTimeFormat), zero external dependencies, zero paid APIs.
 */

/**
 * Normalizes raw offset strings from Intl.DateTimeFormat (e.g. "GMT+5:45", "GMT-4", "GMT")
 * into standard UTC offset notation (e.g. "UTC+05:45", "UTC-04:00", "UTC+00:00").
 * 
 * @param {string|null} raw - Raw shortOffset from Intl
 * @returns {string} Normalized UTC offset
 */
export function normalizeOffset(raw) {
  if (!raw || raw === 'GMT' || raw === 'UTC') return 'UTC+00:00';
  const m = raw.match(/(?:GMT|UTC)?([+-])(\d{1,2})(?::(\d{2}))?/);
  if (!m) return raw;
  const sign = m[1];
  const h = m[2].padStart(2, '0');
  const min = m[3] || '00';
  return `UTC${sign}${h}:${min}`;
}

/**
 * Formats a given Date instant according to an authoritative IANA timezone.
 * Handles fractional hour offsets (e.g. Kathmandu UTC+05:45) and DST transitions.
 * 
 * @param {Date|number|string} dateInput - Instant to format
 * @param {string|null} timezone - IANA timezone identifier (e.g. "Asia/Kathmandu")
 * @returns {{
 *   valid: boolean,
 *   timeString?: string,
 *   period?: string,
 *   dateString?: string,
 *   timezone?: string,
 *   offsetString?: string,
 *   formattedSummary?: string,
 *   error?: string
 * }} Formatted local time components or error object
 */
export function formatLocalTime(dateInput, timezone) {
  if (!timezone || typeof timezone !== 'string' || !timezone.trim()) {
    return { valid: false, error: 'Timezone unavailable' };
  }

  const cleanTz = timezone.trim();
  const date = dateInput instanceof Date ? dateInput : new Date(dateInput);
  if (isNaN(date.getTime())) {
    return { valid: false, error: 'Invalid date instant' };
  }

  try {
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: cleanTz,
      timeZoneName: 'shortOffset',
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    });

    const parts = formatter.formatToParts(date);
    const getPart = (type) => parts.find(p => p.type === type)?.value || '';

    const hour = getPart('hour');
    const minute = getPart('minute');
    const second = getPart('second');
    const period = getPart('dayPeriod') || '';
    const weekday = getPart('weekday');
    const month = getPart('month');
    const day = getPart('day');
    const year = getPart('year');
    const rawTzName = getPart('timeZoneName');

    const timeString = `${hour}:${minute}:${second}`;
    const dateString = `${weekday}, ${month} ${day}, ${year}`;
    const offsetString = normalizeOffset(rawTzName);

    return {
      valid: true,
      timeString,
      period,
      dateString,
      timezone: cleanTz,
      offsetString,
      formattedSummary: `${timeString} ${period} · ${dateString} · ${cleanTz} (${offsetString})`
    };
  } catch (err) {
    return { valid: false, error: 'Invalid timezone' };
  }
}

/**
 * Creates a managed controller for displaying and synchronizing the local time of
 * the currently explored location. Uses a single managed timer, halts updates
 * when Earth is hidden, and seamlessly resumes when visible.
 */
export function createLocalTimeController({
  container,
  clockEl,
  periodEl,
  dateEl,
  tzEl,
  dividerEl,
  getTimeFn = () => new Date(),
  onTick = () => {}
} = {}) {
  let activeTimezone = null;
  let activeLocationName = null;
  let timerId = null;
  let isPaused = false;
  let disposed = false;

  const clock = clockEl || container?.querySelector?.('#earth-local-time-clock');
  const period = periodEl || container?.querySelector?.('#earth-local-time-period');
  const dateDisplay = dateEl || container?.querySelector?.('#earth-local-time-date');
  const tzDisplay = tzEl || container?.querySelector?.('#earth-local-time-tz');
  const divider = dividerEl || container?.querySelector?.('.earth-local-time-divider');

  function render() {
    if (!container) return;

    if (!activeTimezone) {
      if (clock) clock.textContent = '--:--:--';
      if (period) period.textContent = '';
      if (dateDisplay) dateDisplay.textContent = 'Timezone unavailable';
      if (tzDisplay) tzDisplay.textContent = '';
      if (divider) divider.hidden = true;
      container.hidden = false;
      return;
    }

    const now = getTimeFn();
    const formatted = formatLocalTime(now, activeTimezone);

    if (!formatted.valid) {
      if (clock) clock.textContent = '--:--:--';
      if (period) period.textContent = '';
      if (dateDisplay) dateDisplay.textContent = formatted.error || 'Timezone unavailable';
      if (tzDisplay) tzDisplay.textContent = activeTimezone;
      if (divider) divider.hidden = false;
      container.hidden = false;
      return;
    }

    if (clock) clock.textContent = formatted.timeString;
    if (period) period.textContent = formatted.period;
    if (dateDisplay) dateDisplay.textContent = formatted.dateString;
    if (tzDisplay) tzDisplay.textContent = `${formatted.timezone} (${formatted.offsetString})`;
    if (divider) divider.hidden = false;
    container.hidden = false;

    onTick(formatted);
  }

  function startTimer() {
    stopTimer();
    if (disposed || isPaused || !activeTimezone) return;
    timerId = setInterval(() => {
      render();
    }, 1000);
  }

  function stopTimer() {
    if (timerId) {
      clearInterval(timerId);
      timerId = null;
    }
  }

  return {
    setTimezone(timezone, locationName = '') {
      activeTimezone = timezone ? String(timezone).trim() : null;
      activeLocationName = locationName;
      render();
      if (!isPaused && activeTimezone) {
        startTimer();
      } else {
        stopTimer();
      }
    },
    getTimezone: () => activeTimezone,
    getLocationName: () => activeLocationName,
    update: () => render(),
    pause() {
      if (isPaused) return;
      isPaused = true;
      stopTimer();
    },
    resume() {
      if (!isPaused && timerId) return;
      isPaused = false;
      render();
      if (activeTimezone) {
        startTimer();
      }
    },
    clear() {
      stopTimer();
      activeTimezone = null;
      activeLocationName = null;
      if (container) container.hidden = true;
      if (clock) clock.textContent = '--:--:--';
      if (period) period.textContent = '';
      if (dateDisplay) dateDisplay.textContent = '';
      if (tzDisplay) tzDisplay.textContent = '';
    },
    isPaused: () => isPaused,
    dispose() {
      if (disposed) return;
      disposed = true;
      stopTimer();
      activeTimezone = null;
      activeLocationName = null;
      if (container) container.hidden = true;
    }
  };
}
