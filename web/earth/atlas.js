/**
 * web/earth/atlas.js
 * 
 * Lumina Earth — Atlas UI & Saved Places Controller (P1.5).
 * Connects P1.4 persistent waypoint storage to a premium, dark, cinematic
 * saved-places experience with multi-waypoint 3D globe visualization.
 */

import { formatCoordinates } from './search.js';

/**
 * Escapes user-controlled text to prevent HTML injection.
 * @param {string} str - Raw input
 * @returns {string} Sanitized string
 */
export function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Formats an ISO 8601 UTC timestamp into a human-friendly relative time string.
 * @param {string} isoString - ISO UTC timestamp
 * @param {Date} [now=new Date()] - Reference instant
 * @returns {string} e.g. "Just now", "5m ago", "2h ago", "Yesterday", "3d ago", or "Oct 30"
 */
export function formatRelativeTime(isoString, now = new Date()) {
  if (!isoString) return '';
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return '';
  const nowDate = now instanceof Date ? now : new Date(now);
  const diffSec = Math.max(0, Math.floor((nowDate.getTime() - d.getTime()) / 1000));

  if (diffSec < 45) return 'Just now';
  if (diffSec < 90) return '1 min ago';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Creates an authenticated client for Lumina Earth waypoint CRUD operations.
 */
export function createAtlasApiClient({
  getHeaders = () => ({ 'Content-Type': 'application/json' }),
  baseUrl = '/api/earth/waypoints',
  historyBaseUrl = '/api/earth/history',
  fetchFn = (typeof window !== 'undefined' ? window.fetch.bind(window) : null)
} = {}) {
  const req = async (url, options = {}) => {
    if (!fetchFn) throw new Error('Fetch API is unavailable.');
    const headers = { ...getHeaders(), ...(options.headers || {}) };
    const res = await fetchFn(url, { ...options, headers });
    const data = await res.json().catch(() => null);

    if (!res.ok) {
      const err = new Error(data?.error || `Request failed with status ${res.status}`);
      err.status = res.status;
      err.code = data?.status || 'request_error';
      err.details = data;
      throw err;
    }
    return data;
  };

  return {
    async list({ limit = 100, offset = 0 } = {}) {
      const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
      return req(`${baseUrl}?${params.toString()}`, { method: 'GET' });
    },
    async get(id) {
      if (!id) throw new Error('Waypoint ID is required.');
      return req(`${baseUrl}/${encodeURIComponent(id)}`, { method: 'GET' });
    },
    async create(body) {
      return req(baseUrl, {
        method: 'POST',
        body: JSON.stringify(body)
      });
    },
    async update(id, changes) {
      if (!id) throw new Error('Waypoint ID is required.');
      return req(`${baseUrl}/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        body: JSON.stringify(changes)
      });
    },
    async delete(id) {
      if (!id) throw new Error('Waypoint ID is required.');
      return req(`${baseUrl}/${encodeURIComponent(id)}`, {
        method: 'DELETE'
      });
    },
    async listHistory({ limit = 100, offset = 0 } = {}) {
      const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
      return req(`${historyBaseUrl}?${params.toString()}`, { method: 'GET' });
    },
    async getHistory(id) {
      if (!id) throw new Error('History ID is required.');
      return req(`${historyBaseUrl}/${encodeURIComponent(id)}`, { method: 'GET' });
    },
    async createHistory(body) {
      return req(historyBaseUrl, {
        method: 'POST',
        body: JSON.stringify(body)
      });
    },
    async deleteHistory(id) {
      if (!id) throw new Error('History ID is required.');
      return req(`${historyBaseUrl}/${encodeURIComponent(id)}`, {
        method: 'DELETE'
      });
    },
    async clearHistory() {
      return req(historyBaseUrl, {
        method: 'DELETE'
      });
    }
  };
}

/**
 * Sets up and manages the Atlas saved places panel, create/edit workflows,
 * empty/loading/error states, and multi-marker synchronization on the globe.
 */
export function createAtlasController({
  panel,
  toggleBtn,
  toggleLabel,
  saveBtn,
  infoCard,
  earthView,
  apiClient,
  notice = () => {},
  onSelectWaypoint = () => {},
  onSelectHistory = () => {}
} = {}) {
  let waypoints = [];
  let historyItems = [];
  let activeTab = 'saved';
  let historyLoaded = false;
  let isHistoryLoading = false;
  let selectedWaypointId = null;
  let isOpen = false;
  let isLoading = false;
  let isPendingAction = false;
  let activeCandidate = null;
  let editingWaypointId = null;
  let confirmingDeleteId = null;
  let pagination = { total: 0, limit: 100, offset: 0 };
  let disposed = false;

  // DOM sub-element references: Waypoints
  const countBadge = panel?.querySelector('#earth-atlas-count');
  const refreshBtn = panel?.querySelector('#earth-atlas-refresh');
  const newBtn = panel?.querySelector('#earth-atlas-new-btn');
  const closeBtn = panel?.querySelector('#earth-atlas-close');
  const listContainer = panel?.querySelector('#earth-atlas-list');
  const emptyState = panel?.querySelector('#earth-atlas-empty');
  const emptySaveBtn = panel?.querySelector('#earth-atlas-empty-save');
  const loadingState = panel?.querySelector('#earth-atlas-loading');
  const errorBanner = panel?.querySelector('#earth-atlas-error');
  const errorMsg = panel?.querySelector('#earth-atlas-error-msg');
  const retryBtn = panel?.querySelector('#earth-atlas-retry');
  const formContainer = panel?.querySelector('#earth-atlas-form-wrap');
  const form = panel?.querySelector('#earth-atlas-form');
  const formTitle = panel?.querySelector('#earth-atlas-form-title');
  const nameInput = panel?.querySelector('#earth-atlas-name');
  const categorySelect = panel?.querySelector('#earth-atlas-category');
  const descInput = panel?.querySelector('#earth-atlas-desc');
  const coordsDisplay = panel?.querySelector('#earth-atlas-coords');
  const submitBtn = panel?.querySelector('#earth-atlas-submit');
  const cancelBtn = panel?.querySelector('#earth-atlas-cancel');
  const formFeedback = panel?.querySelector('#earth-atlas-form-feedback');
  const paginationContainer = panel?.querySelector('#earth-atlas-pagination');
  const paginationInfo = panel?.querySelector('#earth-atlas-page-info');
  const prevBtn = panel?.querySelector('#earth-atlas-prev');
  const nextBtn = panel?.querySelector('#earth-atlas-next');

  // DOM sub-element references: Tabs & History (P1.6)
  const tabSaved = panel?.querySelector('#earth-atlas-tab-saved');
  const tabHistory = panel?.querySelector('#earth-atlas-tab-history');
  const savedBadge = panel?.querySelector('#earth-atlas-saved-badge');
  const historyBadge = panel?.querySelector('#earth-atlas-history-badge');
  const savedSection = panel?.querySelector('#earth-atlas-saved-section');
  const historySection = panel?.querySelector('#earth-atlas-history-section');
  const historyList = panel?.querySelector('#earth-history-list');
  const historyEmpty = panel?.querySelector('#earth-history-empty');
  const historyLoading = panel?.querySelector('#earth-history-loading');
  const historyClearBtn = panel?.querySelector('#earth-history-clear-btn');
  const historyConfirm = panel?.querySelector('#earth-history-confirm');
  const historyConfirmBtn = panel?.querySelector('#earth-history-confirm-btn');
  const historyCancelBtn = panel?.querySelector('#earth-history-cancel-btn');

  // Coordinates for the form
  let formLatitude = null;
  let formLongitude = null;

  function updateToggleState() {
    if (toggleBtn) {
      toggleBtn.setAttribute('aria-pressed', String(isOpen));
    }
    if (toggleLabel) {
      toggleLabel.textContent = `Atlas (${waypoints.length})`;
    }
    if (savedBadge) {
      savedBadge.textContent = String(pagination.total || waypoints.length);
    }
    if (historyBadge) {
      historyBadge.textContent = String(historyItems.length);
    }
    if (countBadge) {
      countBadge.textContent = String(activeTab === 'history' ? historyItems.length : (pagination.total || waypoints.length));
    }
  }

  function switchTab(tab) {
    activeTab = tab;
    if (tab === 'saved') {
      if (tabSaved) {
        tabSaved.classList.add('active');
        tabSaved.setAttribute('aria-selected', 'true');
      }
      if (tabHistory) {
        tabHistory.classList.remove('active');
        tabHistory.setAttribute('aria-selected', 'false');
      }
      if (savedSection) savedSection.hidden = false;
      if (historySection) historySection.hidden = true;
      if (newBtn) newBtn.hidden = false;
      updateToggleState();
    } else if (tab === 'history') {
      if (tabHistory) {
        tabHistory.classList.add('active');
        tabHistory.setAttribute('aria-selected', 'true');
      }
      if (tabSaved) {
        tabSaved.classList.remove('active');
        tabSaved.setAttribute('aria-selected', 'false');
      }
      if (savedSection) savedSection.hidden = true;
      if (historySection) historySection.hidden = false;
      if (newBtn) newBtn.hidden = true;
      updateToggleState();
      if (!historyLoaded && !isHistoryLoading) {
        loadHistory();
      }
    }
  }

  function setPanelVisibility(open) {
    isOpen = open;
    if (panel) {
      panel.hidden = !open;
    }
    updateToggleState();
  }

  function showLoading(loading) {
    isLoading = loading;
    if (loadingState) loadingState.hidden = !loading;
    if (refreshBtn) refreshBtn.disabled = loading;
  }

  function showError(message) {
    if (errorBanner) {
      if (message) {
        errorBanner.hidden = false;
        if (errorMsg) errorMsg.textContent = message;
      } else {
        errorBanner.hidden = true;
      }
    }
  }

  function setFormFeedback(message, isError = false) {
    if (!formFeedback) return;
    if (!message) {
      formFeedback.hidden = true;
      formFeedback.textContent = '';
      formFeedback.className = 'earth-atlas-form-feedback';
    } else {
      formFeedback.hidden = false;
      formFeedback.textContent = message;
      formFeedback.className = `earth-atlas-form-feedback ${isError ? 'error' : 'success'}`;
    }
  }

  function resetForm() {
    editingWaypointId = null;
    formLatitude = null;
    formLongitude = null;
    if (form) form.reset();
    if (coordsDisplay) coordsDisplay.textContent = '—';
    setFormFeedback('');
    if (formContainer) formContainer.hidden = true;
    if (submitBtn) submitBtn.disabled = false;
  }

  function openCreateForm(candidate = null) {
    resetForm();
    const target = candidate || activeCandidate;
    if (formTitle) formTitle.textContent = 'Save Place to Atlas';
    if (submitBtn) submitBtn.textContent = 'Save Place';

    if (target) {
      formLatitude = target.latitude;
      formLongitude = target.longitude;
      if (nameInput) nameInput.value = target.name || '';
      if (coordsDisplay) coordsDisplay.textContent = formatCoordinates(target.latitude, target.longitude);
      if (categorySelect) categorySelect.value = target.category || 'city';
    } else {
      formLatitude = 0;
      formLongitude = 0;
      if (coordsDisplay) coordsDisplay.textContent = 'Select a location on globe or search';
    }

    if (formContainer) formContainer.hidden = false;
    setPanelVisibility(true);
    nameInput?.focus();
  }

  function openEditForm(waypoint) {
    if (!waypoint) return;
    resetForm();
    editingWaypointId = waypoint.id;
    formLatitude = waypoint.latitude;
    formLongitude = waypoint.longitude;

    if (formTitle) formTitle.textContent = 'Edit Saved Place';
    if (submitBtn) submitBtn.textContent = 'Save Changes';
    if (nameInput) nameInput.value = waypoint.name || '';
    if (descInput) descInput.value = waypoint.description || '';
    if (categorySelect) categorySelect.value = waypoint.category || '';
    if (coordsDisplay) coordsDisplay.textContent = formatCoordinates(waypoint.latitude, waypoint.longitude);

    if (formContainer) formContainer.hidden = false;
    setPanelVisibility(true);
    nameInput?.focus();
  }

  function reconcileGlobeMarkers() {
    if (earthView && typeof earthView.setWaypoints === 'function') {
      earthView.setWaypoints(waypoints);
      if (selectedWaypointId) {
        earthView.highlightWaypointMarker?.(selectedWaypointId);
      }
    }
  }

  function renderList() {
    if (!listContainer) return;
    const doc = listContainer.ownerDocument || document;
    listContainer.innerHTML = '';

    const hasItems = waypoints.length > 0;
    if (emptyState) emptyState.hidden = hasItems;
    if (listContainer) listContainer.hidden = !hasItems;

    if (emptySaveBtn) {
      emptySaveBtn.disabled = !activeCandidate;
    }

    // Render pagination controls if total exceeds limit
    if (paginationContainer) {
      const showPaging = pagination.total > pagination.limit;
      paginationContainer.hidden = !showPaging;
      if (showPaging && paginationInfo) {
        const start = pagination.offset + 1;
        const end = Math.min(pagination.offset + pagination.limit, pagination.total);
        paginationInfo.textContent = `${start}–${end} of ${pagination.total}`;
        if (prevBtn) prevBtn.disabled = pagination.offset === 0;
        if (nextBtn) nextBtn.disabled = end >= pagination.total;
      }
    }

    waypoints.forEach(w => {
      const isSelected = w.id === selectedWaypointId;
      const isConfirming = w.id === confirmingDeleteId;

      const card = doc.createElement('div');
      card.className = `earth-atlas-card ${isSelected ? 'selected' : ''}`;
      card.setAttribute('role', 'option');
      card.setAttribute('aria-selected', String(isSelected));
      card.dataset.waypointId = w.id;

      // Header row
      const headerRow = doc.createElement('div');
      headerRow.className = 'earth-atlas-card-header';

      const titleWrap = doc.createElement('div');
      titleWrap.className = 'earth-atlas-card-title-wrap';

      const pinIcon = doc.createElement('span');
      pinIcon.className = 'earth-atlas-card-icon';
      pinIcon.textContent = '📍';

      const title = doc.createElement('span');
      title.className = 'earth-atlas-card-name';
      title.textContent = w.name;
      title.title = w.name;

      titleWrap.appendChild(pinIcon);
      titleWrap.appendChild(title);
      headerRow.appendChild(titleWrap);

      if (w.category) {
        const catBadge = doc.createElement('span');
        catBadge.className = 'earth-atlas-card-cat';
        catBadge.textContent = w.category;
        headerRow.appendChild(catBadge);
      }
      card.appendChild(headerRow);

      // Coordinates
      const coords = doc.createElement('div');
      coords.className = 'earth-atlas-card-coords';
      coords.textContent = formatCoordinates(w.latitude, w.longitude);
      card.appendChild(coords);

      // Description (if present)
      if (w.description) {
        const desc = doc.createElement('div');
        desc.className = 'earth-atlas-card-desc';
        desc.textContent = w.description;
        card.appendChild(desc);
      }

      // Action toolbar or Delete confirmation
      const actionRow = doc.createElement('div');
      actionRow.className = 'earth-atlas-card-actions';

      if (isConfirming) {
        const confirmWrap = doc.createElement('div');
        confirmWrap.className = 'earth-atlas-confirm-wrap';

        const confirmMsg = doc.createElement('span');
        confirmMsg.className = 'earth-atlas-confirm-msg';
        confirmMsg.textContent = 'Delete this place?';

        const doDeleteBtn = doc.createElement('button');
        doDeleteBtn.type = 'button';
        doDeleteBtn.className = 'earth-btn-sm earth-btn-danger';
        doDeleteBtn.textContent = 'Delete';
        doDeleteBtn.disabled = isPendingAction;
        doDeleteBtn.onclick = (e) => {
          e?.stopPropagation?.();
          deleteWaypoint(w.id);
        };

        const cancelDelBtn = doc.createElement('button');
        cancelDelBtn.type = 'button';
        cancelDelBtn.className = 'earth-btn-sm earth-btn-secondary';
        cancelDelBtn.textContent = 'Cancel';
        cancelDelBtn.onclick = (e) => {
          e?.stopPropagation?.();
          confirmingDeleteId = null;
          renderList();
        };

        confirmWrap.appendChild(confirmMsg);
        confirmWrap.appendChild(doDeleteBtn);
        confirmWrap.appendChild(cancelDelBtn);
        actionRow.appendChild(confirmWrap);
      } else {
        const flyBtn = doc.createElement('button');
        flyBtn.type = 'button';
        flyBtn.className = 'earth-btn-sm earth-btn-primary';
        flyBtn.textContent = 'Fly To';
        flyBtn.onclick = (e) => {
          e?.stopPropagation?.();
          selectWaypoint(w.id, { fly: true });
        };

        const editBtn = doc.createElement('button');
        editBtn.type = 'button';
        editBtn.className = 'earth-btn-sm earth-btn-secondary';
        editBtn.textContent = 'Edit';
        editBtn.onclick = (e) => {
          e?.stopPropagation?.();
          openEditForm(w);
        };

        const delBtn = doc.createElement('button');
        delBtn.type = 'button';
        delBtn.className = 'earth-btn-sm earth-btn-danger-outline';
        delBtn.textContent = 'Delete';
        delBtn.onclick = (e) => {
          e?.stopPropagation?.();
          confirmingDeleteId = w.id;
          renderList();
        };

        actionRow.appendChild(flyBtn);
        actionRow.appendChild(editBtn);
        actionRow.appendChild(delBtn);
      }

      card.appendChild(actionRow);

      // Click card to select
      card.onclick = () => {
        selectWaypoint(w.id, { fly: true });
      };

      listContainer.appendChild(card);
    });

    updateToggleState();
  }

  async function loadWaypoints({ offset = 0 } = {}) {
    if (isLoading || !apiClient) return;
    showLoading(true);
    showError('');

    try {
      const res = await apiClient.list({ limit: pagination.limit, offset });
      waypoints = res?.waypoints || [];
      pagination.total = res?.total ?? waypoints.length;
      pagination.limit = res?.limit ?? 100;
      pagination.offset = res?.offset ?? 0;

      // Ensure selectedWaypointId still exists in waypoints
      if (selectedWaypointId && !waypoints.some(w => w.id === selectedWaypointId)) {
        selectedWaypointId = null;
      }

      renderList();
      reconcileGlobeMarkers();
    } catch (err) {
      console.error('Failed to load waypoints:', err);
      showError(err.message || 'Unable to load saved places. Please retry.');
    } finally {
      showLoading(false);
    }
  }

  function selectWaypoint(id, { fly = true } = {}) {
    const wp = waypoints.find(w => w.id === id);
    if (!wp) return;

    selectedWaypointId = id;
    renderList();

    // Highlight marker on globe
    if (earthView) {
      earthView.highlightWaypointMarker?.(id);
      if (fly && typeof earthView.flyTo === 'function') {
        earthView.flyTo(wp.latitude, wp.longitude);
      }
    }

    // Populate info card if available
    if (infoCard) {
      const titleEl = infoCard.querySelector('#earth-info-title');
      const subEl = infoCard.querySelector('#earth-info-sub');
      const detailsEl = infoCard.querySelector('#earth-info-details');

      if (titleEl) titleEl.textContent = wp.name;
      if (subEl) subEl.textContent = [wp.category, 'Saved Place'].filter(Boolean).join(' · ');
      if (detailsEl) {
        const coords = formatCoordinates(wp.latitude, wp.longitude);
        const desc = wp.description ? `<span class="earth-info-badge earth-info-badge-desc">${escapeHtml(wp.description)}</span>` : '';
        detailsEl.innerHTML = `<span class="earth-info-badge">${coords}</span>${desc}`;
      }
      infoCard.hidden = false;
    }

    onSelectWaypoint(wp);
  }

  async function handleFormSubmit(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (isPendingAction || !apiClient) return;

    const name = nameInput?.value?.trim() || '';
    if (!name) {
      setFormFeedback('Name is required.', true);
      nameInput?.focus();
      return;
    }
    if (name.length > 120) {
      setFormFeedback('Name must be 120 characters or fewer.', true);
      return;
    }

    const description = descInput?.value?.trim() || null;
    const category = categorySelect?.value?.trim() || null;

    if (formLatitude == null || formLongitude == null || !Number.isFinite(formLatitude) || !Number.isFinite(formLongitude)) {
      setFormFeedback('Valid coordinates are required.', true);
      return;
    }

    isPendingAction = true;
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Saving…';
    }
    setFormFeedback('Saving to Atlas…', false);

    try {
      if (editingWaypointId) {
        // PATCH existing waypoint
        const updates = { name, description, category };
        const res = await apiClient.update(editingWaypointId, updates);
        const updated = res?.waypoint;
        notice(`Updated place: ${name}`);
        resetForm();
        await loadWaypoints({ offset: pagination.offset });
        if (updated?.id) selectWaypoint(updated.id, { fly: false });
      } else {
        // POST new waypoint
        const payload = {
          name,
          latitude: formLatitude,
          longitude: formLongitude,
          description,
          category
        };
        const res = await apiClient.create(payload);
        const created = res?.waypoint;
        notice(`Saved to Atlas: ${name}`);
        resetForm();
        await loadWaypoints({ offset: 0 });
        if (created?.id) selectWaypoint(created.id, { fly: true });
      }
    } catch (err) {
      console.error('Failed to save waypoint:', err);
      setFormFeedback(err.message || 'Failed to save place.', true);
    } finally {
      isPendingAction = false;
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = editingWaypointId ? 'Save Changes' : 'Save Place';
      }
    }
  }

  async function deleteWaypoint(id) {
    if (isPendingAction || !apiClient) return;
    const wp = waypoints.find(w => w.id === id);
    const placeName = wp?.name || 'Saved place';

    isPendingAction = true;

    try {
      await apiClient.delete(id);
      confirmingDeleteId = null;
      notice(`Deleted: ${placeName}`);

      if (selectedWaypointId === id) {
        selectedWaypointId = null;
        if (infoCard) infoCard.hidden = true;
      }

      await loadWaypoints({ offset: pagination.offset });
    } catch (err) {
      console.error('Failed to delete waypoint:', err);
      notice(`Delete failed: ${err.message || 'Unknown error'}`);
    } finally {
      isPendingAction = false;
    }
  }

  function renderHistory() {
    if (!historyList) return;
    const doc = historyList.ownerDocument || (typeof document !== 'undefined' ? document : null);
    if (!doc) return;
    historyList.innerHTML = '';

    const hasItems = historyItems.length > 0;
    if (historyEmpty) historyEmpty.hidden = hasItems;
    if (historyList) historyList.hidden = !hasItems;
    if (historyClearBtn) historyClearBtn.disabled = !hasItems;

    updateToggleState();

    historyItems.forEach(h => {
      const card = doc.createElement('div');
      card.className = 'earth-history-card';
      card.setAttribute('role', 'option');
      card.dataset.historyId = h.id;

      // Header row
      const header = doc.createElement('div');
      header.className = 'earth-history-card-header';

      const title = doc.createElement('span');
      title.className = 'earth-history-card-title';
      title.textContent = h.name;
      title.title = h.name;

      const timeAgo = doc.createElement('span');
      timeAgo.className = 'earth-history-card-time';
      timeAgo.textContent = formatRelativeTime(h.searched_at);

      header.appendChild(title);
      header.appendChild(timeAgo);
      card.appendChild(header);

      // Subtitle
      const subParts = [h.admin1, h.country].filter(Boolean);
      const subText = subParts.length > 0 ? subParts.join(', ') : (h.display_name || '');
      if (subText) {
        const sub = doc.createElement('div');
        sub.className = 'earth-history-card-sub';
        sub.textContent = subText;
        card.appendChild(sub);
      }

      // Meta info
      const meta = doc.createElement('div');
      meta.className = 'earth-history-card-meta';

      const coords = doc.createElement('span');
      coords.textContent = formatCoordinates(h.latitude, h.longitude);
      meta.appendChild(coords);

      if (h.timezone) {
        const tz = doc.createElement('span');
        tz.className = 'earth-history-card-tz';
        tz.textContent = h.timezone;
        meta.appendChild(tz);
      }
      card.appendChild(meta);

      // Actions
      const actions = doc.createElement('div');
      actions.className = 'earth-history-card-actions';

      const revisitBtn = doc.createElement('button');
      revisitBtn.type = 'button';
      revisitBtn.className = 'earth-btn-sm earth-btn-primary';
      revisitBtn.textContent = 'Revisit';
      revisitBtn.onclick = (e) => {
        e?.stopPropagation?.();
        selectHistory(h);
      };

      const delBtn = doc.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'earth-btn-sm earth-btn-danger-outline';
      delBtn.textContent = 'Delete';
      delBtn.onclick = (e) => {
        e?.stopPropagation?.();
        deleteHistoryItem(h.id);
      };

      actions.appendChild(revisitBtn);
      actions.appendChild(delBtn);
      card.appendChild(actions);

      card.onclick = () => {
        selectHistory(h);
      };

      historyList.appendChild(card);
    });
  }

  async function loadHistory() {
    if (isHistoryLoading || !apiClient || typeof apiClient.listHistory !== 'function') return;
    isHistoryLoading = true;
    if (historyLoading) historyLoading.hidden = false;

    try {
      const res = await apiClient.listHistory({ limit: 100 });
      historyItems = res?.history || [];
      historyLoaded = true;
      renderHistory();
    } catch (err) {
      console.error('Failed to load search history:', err);
      notice(`History load error: ${err.message || 'Unknown error'}`);
    } finally {
      isHistoryLoading = false;
      if (historyLoading) historyLoading.hidden = true;
    }
  }

  async function recordHistory(candidate) {
    if (!candidate || !candidate.name || candidate.latitude == null || candidate.longitude == null) return;
    if (!apiClient || typeof apiClient.createHistory !== 'function') return;

    const payload = {
      name: candidate.name,
      latitude: Number(candidate.latitude),
      longitude: Number(candidate.longitude),
      display_name: candidate.display_name || candidate.name,
      country: candidate.country || null,
      country_code: candidate.country_code || null,
      admin1: candidate.admin1 || null,
      timezone: candidate.timezone || null
    };

    try {
      const res = await apiClient.createHistory(payload);
      const entry = res?.entry;
      if (entry) {
        const existingIdx = historyItems.findIndex(h => h.id === entry.id || (Math.abs(h.latitude - entry.latitude) < 0.001 && Math.abs(h.longitude - entry.longitude) < 0.001));
        if (existingIdx !== -1) {
          historyItems.splice(existingIdx, 1);
        }
        historyItems.unshift(entry);
        if (historyItems.length > 100) historyItems.pop();
        historyLoaded = true;
        renderHistory();
      }
    } catch (err) {
      console.warn('Failed to record search history:', err);
    }
  }

  async function deleteHistoryItem(id) {
    if (!apiClient || typeof apiClient.deleteHistory !== 'function') return;
    try {
      await apiClient.deleteHistory(id);
      historyItems = historyItems.filter(h => h.id !== id);
      renderHistory();
      notice('Removed search history item');
    } catch (err) {
      console.error('Failed to delete history item:', err);
      notice(`Delete failed: ${err.message || 'Unknown error'}`);
    }
  }

  async function clearAllHistory() {
    if (!apiClient || typeof apiClient.clearHistory !== 'function') return;
    try {
      await apiClient.clearHistory();
      historyItems = [];
      if (historyConfirm) historyConfirm.hidden = true;
      renderHistory();
      notice('Cleared search history');
    } catch (err) {
      console.error('Failed to clear search history:', err);
      notice(`Clear history failed: ${err.message || 'Unknown error'}`);
    }
  }

  function selectHistory(h) {
    const candidate = {
      name: h.name,
      latitude: h.latitude,
      longitude: h.longitude,
      display_name: h.display_name,
      country: h.country,
      country_code: h.country_code,
      admin1: h.admin1,
      timezone: h.timezone
    };
    onSelectHistory(candidate);
  }

  // Wire event handlers
  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      setPanelVisibility(!isOpen);
      if (isOpen && waypoints.length === 0 && !isLoading) {
        loadWaypoints();
      }
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      setPanelVisibility(false);
      resetForm();
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      if (activeTab === 'history') {
        loadHistory();
      } else {
        loadWaypoints({ offset: pagination.offset });
      }
    });
  }

  if (tabSaved) {
    tabSaved.addEventListener('click', () => switchTab('saved'));
  }

  if (tabHistory) {
    tabHistory.addEventListener('click', () => switchTab('history'));
  }

  if (historyClearBtn) {
    historyClearBtn.addEventListener('click', () => {
      if (historyConfirm) historyConfirm.hidden = false;
    });
  }

  if (historyConfirmBtn) {
    historyConfirmBtn.addEventListener('click', () => {
      clearAllHistory();
    });
  }

  if (historyCancelBtn) {
    historyCancelBtn.addEventListener('click', () => {
      if (historyConfirm) historyConfirm.hidden = true;
    });
  }

  if (newBtn) {
    newBtn.addEventListener('click', () => {
      openCreateForm();
    });
  }

  if (emptySaveBtn) {
    emptySaveBtn.addEventListener('click', () => {
      openCreateForm();
    });
  }

  if (retryBtn) {
    retryBtn.addEventListener('click', () => {
      loadWaypoints({ offset: pagination.offset });
    });
  }

  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      openCreateForm();
    });
  }

  if (form) {
    form.addEventListener('submit', handleFormSubmit);
  }

  if (cancelBtn) {
    cancelBtn.addEventListener('click', resetForm);
  }

  if (prevBtn) {
    prevBtn.addEventListener('click', () => {
      const prevOffset = Math.max(0, pagination.offset - pagination.limit);
      loadWaypoints({ offset: prevOffset });
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener('click', () => {
      const nextOffset = pagination.offset + pagination.limit;
      if (nextOffset < pagination.total) {
        loadWaypoints({ offset: nextOffset });
      }
    });
  }

  if (savedSection || historySection) {
    switchTab('saved');
  } else {
    updateToggleState();
  }

  return {
    open: () => setPanelVisibility(true),
    close: () => setPanelVisibility(false),
    toggle: () => setPanelVisibility(!isOpen),
    refresh: () => loadWaypoints({ offset: pagination.offset }),
    loadWaypoints,
    selectWaypoint,
    openCreateForm,
    openEditForm,
    deleteWaypoint,
    setCurrentCandidate(candidate) {
      activeCandidate = candidate;
      if (saveBtn) {
        saveBtn.disabled = !candidate;
        if (candidate) {
          saveBtn.title = `Save "${candidate.name}" to Atlas`;
        }
      }
      if (emptySaveBtn) {
        emptySaveBtn.disabled = !candidate;
      }
    },
    getWaypoints: () => [...waypoints],
    getSelectedWaypointId: () => selectedWaypointId,
    isOpen: () => isOpen,
    switchTab,
    loadHistory,
    recordHistory,
    deleteHistoryItem,
    clearAllHistory,
    selectHistory,
    getHistory: () => [...historyItems],
    getActiveTab: () => activeTab,
    dispose() {
      if (disposed) return;
      disposed = true;
      resetForm();
      waypoints = [];
      historyItems = [];
      selectedWaypointId = null;
      reconcileGlobeMarkers();
    }
  };
}
