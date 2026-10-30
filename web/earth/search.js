// Lumina Earth P0.3 — Search Controller & UI Presentation Logic
// Decoupled, accessible, testable in Node and modern browsers.

/**
 * Validates place query against bounding rules.
 *
 * @param {any} query - Input search string
 * @returns {{ valid: boolean, error?: string, cleanQuery?: string }}
 */
export function validateQuery(query) {
  if (typeof query !== 'string') {
    return { valid: false, error: 'Place query must be text.' };
  }
  const clean = query.trim();
  if (!clean) {
    return { valid: false, error: 'Please enter a place or city name.' };
  }
  if (clean.length > 200) {
    return { valid: false, error: 'Search query exceeds maximum length of 200 characters.' };
  }
  for (let i = 0; i < clean.length; i++) {
    const code = clean.charCodeAt(i);
    if (code < 32 && code !== 9) {
      return { valid: false, error: 'Search query contains invalid control characters.' };
    }
  }
  return { valid: true, cleanQuery: clean };
}

/**
 * Formats decimal latitude and longitude into human-readable geographic string.
 * e.g. 27.7017, 85.3206 -> "27.70° N, 85.32° E"
 *
 * @param {number} lat - Latitude in degrees
 * @param {number} lon - Longitude in degrees
 * @returns {string} Formatted coordinates
 */
export function formatCoordinates(lat, lon) {
  if (typeof lat !== 'number' || typeof lon !== 'number') return '';
  const latDir = lat >= 0 ? 'N' : 'S';
  const lonDir = lon >= 0 ? 'E' : 'W';
  return `${Math.abs(lat).toFixed(2)}° ${latDir}, ${Math.abs(lon).toFixed(2)}° ${lonDir}`;
}

/**
 * Creates and manages place-search interactions, keyboard accessibility,
 * stale-response discarding, and candidate selection.
 */
export function createSearchController({
  form,
  input,
  submitBtn,
  clearBtn,
  resultsList,
  feedback,
  infoCard,
  onSelect = () => {},
  searchEndpoint = '/api/earth/search',
  fetchFn = (typeof window !== 'undefined' ? window.fetch.bind(window) : null)
} = {}) {
  let searchCounter = 0;
  let activeCandidates = [];
  let disposed = false;

  const setFeedback = (message, state = 'idle') => {
    if (!feedback) return;
    if (!message) {
      feedback.hidden = true;
      feedback.textContent = '';
      feedback.dataset.state = 'idle';
    } else {
      feedback.hidden = false;
      feedback.textContent = message;
      feedback.dataset.state = state;
    }
  };

  const closeResults = () => {
    if (resultsList) {
      resultsList.hidden = true;
      resultsList.innerHTML = '';
    }
    activeCandidates = [];
  };

  const setLoading = (loading) => {
    if (input) input.disabled = loading;
    if (submitBtn) {
      submitBtn.disabled = loading;
      submitBtn.setAttribute('aria-busy', String(loading));
    }
    if (loading) {
      setFeedback('Searching places…', 'loading');
    }
  };

  const renderCandidates = (candidates, query) => {
    if (!resultsList) return;
    const doc = resultsList.ownerDocument || (typeof document !== 'undefined' ? document : null);
    if (!doc || !doc.createElement) return;

    resultsList.innerHTML = '';
    activeCandidates = candidates;

    if (!candidates || candidates.length === 0) {
      resultsList.hidden = true;
      setFeedback(`No places found for "${query}".`, 'empty');
      return;
    }

    setFeedback(candidates.length > 1 ? `Found ${candidates.length} locations. Select one:` : '', 'ready');
    resultsList.hidden = false;

    candidates.forEach((c, idx) => {
      const li = doc.createElement('li');
      li.className = 'earth-result-item';
      li.setAttribute('role', 'option');
      li.setAttribute('id', `earth-result-opt-${idx}`);

      const btn = doc.createElement('button');
      btn.type = 'button';
      btn.className = 'earth-result-btn';
      btn.setAttribute('tabindex', '0');

      const title = doc.createElement('span');
      title.className = 'earth-result-title';
      title.textContent = c.name;

      const subParts = [c.admin1, c.country].filter(Boolean);
      const sub = doc.createElement('span');
      sub.className = 'earth-result-sub';
      sub.textContent = subParts.length > 0 ? subParts.join(', ') : formatCoordinates(c.latitude, c.longitude);

      btn.appendChild(title);
      btn.appendChild(sub);

      btn.addEventListener('click', (e) => {
        if (e && e.preventDefault) e.preventDefault();
        selectCandidate(c);
      });

      li.appendChild(btn);
      resultsList.appendChild(li);
    });
  };

  const selectCandidate = (candidate) => {
    closeResults();
    setFeedback('');
    if (input) input.value = candidate.name;
    showInfoCard(candidate);
    onSelect(candidate);
  };

  const showInfoCard = (candidate) => {
    if (!infoCard) return;
    const titleEl = infoCard.querySelector('#earth-info-title');
    const subEl = infoCard.querySelector('#earth-info-sub');
    const detailsEl = infoCard.querySelector('#earth-info-details');

    if (titleEl) titleEl.textContent = candidate.name;
    if (subEl) {
      const parts = [candidate.admin1, candidate.admin2, candidate.country].filter(Boolean);
      subEl.textContent = parts.join(' · ') || 'Geographic Location';
    }
    if (detailsEl) {
      const coords = formatCoordinates(candidate.latitude, candidate.longitude);
      const elev = candidate.elevation_m != null ? `${Math.round(candidate.elevation_m)} m elevation` : null;
      const tz = candidate.timezone ? `${candidate.timezone}` : null;
      detailsEl.innerHTML = [coords, elev, tz].filter(Boolean).map(t => `<span class="earth-info-badge">${t}</span>`).join('');
    }
    infoCard.hidden = false;
  };

  const hideInfoCard = () => {
    if (infoCard) infoCard.hidden = true;
  };

  const performSearch = async (rawQuery) => {
    const val = validateQuery(rawQuery);
    if (!val.valid) {
      setFeedback(val.error, 'error');
      closeResults();
      return;
    }

    const query = val.cleanQuery;
    const currentSearchId = ++searchCounter;
    closeResults();
    setLoading(true);

    try {
      if (!fetchFn) throw new Error('Fetch API is unavailable.');
      const url = `${searchEndpoint}?query=${encodeURIComponent(query)}&limit=6`;
      const res = await fetchFn(url, { headers: { 'Accept': 'application/json' } });

      if (currentSearchId !== searchCounter) {
        // Discard stale response from superseded search
        return;
      }

      if (!res.ok) {
        let errDetail = 'Place search failed';
        try {
          const errData = await res.json();
          if (errData?.error) errDetail = errData.error;
        } catch (_) {}
        setFeedback(`Search error: ${errDetail}`, 'error');
        return;
      }

      const json = await res.json();
      if (currentSearchId !== searchCounter) return;

      const candidates = json?.data?.candidates || [];
      renderCandidates(candidates, query);
    } catch (err) {
      if (currentSearchId !== searchCounter) return;
      setFeedback(err.message || 'Unable to complete search. Please check network connection.', 'error');
    } finally {
      if (currentSearchId === searchCounter) {
        setLoading(false);
      }
    }
  };

  // Event handlers
  const onSubmit = (e) => {
    e.preventDefault();
    if (input) performSearch(input.value);
  };

  const onInput = () => {
    if (clearBtn && input) {
      clearBtn.hidden = !input.value;
    }
  };

  const onClear = () => {
    if (input) {
      input.value = '';
      input.focus();
    }
    if (clearBtn) clearBtn.hidden = true;
    closeResults();
    setFeedback('');
  };

  const onKeyDown = (e) => {
    if (e.key === 'Escape') {
      closeResults();
      hideInfoCard();
    }
  };

  if (form) form.addEventListener('submit', onSubmit);
  if (input) input.addEventListener('input', onInput);
  if (clearBtn) clearBtn.addEventListener('click', onClear);
  if (typeof window !== 'undefined') window.addEventListener('keydown', onKeyDown);

  const closeBtn = infoCard?.querySelector('#earth-info-close');
  if (closeBtn) closeBtn.addEventListener('click', hideInfoCard);

  return {
    performSearch,
    selectCandidate,
    showInfoCard,
    hideInfoCard,
    closeResults,
    setFeedback,
    getActiveCandidates: () => [...activeCandidates],
    dispose() {
      if (disposed) return;
      disposed = true;
      if (form) form.removeEventListener('submit', onSubmit);
      if (input) input.removeEventListener('input', onInput);
      if (clearBtn) clearBtn.removeEventListener('click', onClear);
      if (typeof window !== 'undefined') window.removeEventListener('keydown', onKeyDown);
      if (closeBtn) closeBtn.removeEventListener('click', hideInfoCard);
      closeResults();
      hideInfoCard();
    }
  };
}
