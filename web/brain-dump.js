/**
 * LUMINA DAILY BRAIN DUMP CONTROLLER (web/brain-dump.js)
 * Quick-capture thought panel with categorization, inline editing,
 * search/filter, and direct conversion to Lumina tasks and reminders.
 */

export function setupBrainDump({ getConfig = () => ({}), notice = () => {}, send = () => {} } = {}) {
  const panel = document.getElementById('brain-dump-panel');
  if (!panel) {
    console.warn('Brain Dump panel element (#brain-dump-panel) not found in DOM');
    return { open: () => {}, close: () => {}, refresh: () => {} };
  }

  const closeBtn = document.getElementById('brain-dump-close');
  const inputEl = document.getElementById('bd-input');
  const categorySelect = document.getElementById('bd-category');
  const addBtn = document.getElementById('bd-add');
  const itemsContainer = document.getElementById('bd-items');
  const searchInput = document.getElementById('bd-search-input');
  const counterEl = document.getElementById('bd-counter');
  const footerStatsEl = document.getElementById('bd-footer-stats');
  const filterPillsContainer = panel.querySelector('.bd-filter-pills');

  let currentCategoryFilter = 'all';
  let currentStatusFilter = 'active'; // 'active' | 'archived' | 'all'
  let searchQuery = '';
  let items = [];
  let editingItemId = null;
  let convertingItemId = null;

  function getToken() {
    return getConfig()?.token || '';
  }

  function getHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    const token = getToken();
    if (token) headers['X-Lumina-Token'] = token;
    return headers;
  }

  async function apiCall(method = 'GET', data = null) {
    let url = '/api/brain-dump';
    const options = {
      method,
      headers: getHeaders()
    };

    if (method === 'GET' && data) {
      const params = new URLSearchParams(data);
      url += `?${params.toString()}`;
    } else if (method === 'POST' && data) {
      options.body = JSON.stringify(data);
    }

    try {
      const res = await fetch(url, options);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      return await res.json();
    } catch (err) {
      notice(`Brain Dump error: ${err.message}`);
      throw err;
    }
  }

  async function loadItems() {
    try {
      const params = {};
      if (currentStatusFilter && currentStatusFilter !== 'all') {
        params.status = currentStatusFilter;
      }
      if (currentCategoryFilter && currentCategoryFilter !== 'all') {
        params.category = currentCategoryFilter;
      }
      if (searchQuery.trim()) {
        params.query = searchQuery.trim();
      }

      const res = await apiCall('GET', params);
      if (res.ok && Array.isArray(res.items)) {
        items = res.items;
        renderItems();
      }
    } catch (err) {
      console.error('Failed to load brain dump items:', err);
    }
  }

  function formatTime(isoStr) {
    if (!isoStr) return '';
    try {
      const date = new Date(isoStr);
      if (isNaN(date.getTime())) return isoStr;
      const now = new Date();
      const diffMs = now - date;
      const diffSec = Math.floor(diffMs / 1000);
      if (diffSec < 60) return 'Just now';
      const diffMin = Math.floor(diffSec / 60);
      if (diffMin < 60) return `${diffMin}m ago`;
      const diffHrs = Math.floor(diffMin / 60);
      if (diffHrs < 24) return `${diffHrs}h ago`;
      return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    } catch {
      return isoStr;
    }
  }

  function renderItems() {
    if (!itemsContainer) return;
    itemsContainer.innerHTML = '';

    // Update counter & footer
    const totalCount = items.length;
    if (counterEl) {
      counterEl.textContent = `${totalCount} item${totalCount === 1 ? '' : 's'}`;
    }
    if (footerStatsEl) {
      const activeCount = items.filter(i => i.status === 'active').length;
      footerStatsEl.textContent = `${activeCount} active thought${activeCount === 1 ? '' : 's'}`;
    }

    if (items.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'bd-empty';
      empty.innerHTML = `
        <div class="bd-empty-icon" aria-hidden="true">✎</div>
        <p><strong>Clear mind, ready space.</strong></p>
        <p>Type a quick note, task, or thought above and hit Enter.</p>
      `;
      itemsContainer.appendChild(empty);
      return;
    }

    items.forEach(item => {
      const itemEl = document.createElement('article');
      itemEl.className = 'bd-item';
      itemEl.dataset.id = item.id;
      itemEl.dataset.status = item.status;

      // Category badge
      const catBadge = document.createElement('span');
      catBadge.className = 'bd-cat';
      catBadge.dataset.cat = item.category;
      catBadge.textContent = item.category;
      itemEl.appendChild(catBadge);

      // Item Body
      const bodyEl = document.createElement('div');
      bodyEl.className = 'bd-item-body';

      if (editingItemId === item.id) {
        // Inline Edit Mode
        const editInput = document.createElement('input');
        editInput.className = 'bd-edit-input';
        editInput.value = item.text;
        editInput.maxLength = 4096;

        const editActions = document.createElement('div');
        editActions.className = 'bd-edit-actions';

        const saveBtn = document.createElement('button');
        saveBtn.className = 'bd-add-btn';
        saveBtn.textContent = 'Save';
        saveBtn.addEventListener('click', async () => {
          const newText = editInput.value.trim();
          if (newText) {
            await handleUpdate(item.id, newText);
          }
        });

        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = 'Cancel';
        cancelBtn.addEventListener('click', () => {
          editingItemId = null;
          renderItems();
        });

        editActions.appendChild(saveBtn);
        editActions.appendChild(cancelBtn);

        bodyEl.appendChild(editInput);
        bodyEl.appendChild(editActions);

        editInput.addEventListener('keydown', e => {
          if (e.key === 'Enter') saveBtn.click();
          if (e.key === 'Escape') cancelBtn.click();
        });
      } else {
        // Normal View Mode
        const textEl = document.createElement('div');
        textEl.className = 'bd-item-text';
        textEl.textContent = item.text;
        bodyEl.appendChild(textEl);

        const metaEl = document.createElement('div');
        metaEl.className = 'bd-item-meta';

        const timeSpan = document.createElement('span');
        timeSpan.textContent = formatTime(item.created_at);
        metaEl.appendChild(timeSpan);

        if (item.converted) {
          const convSpan = document.createElement('span');
          convSpan.className = 'bd-converted';
          const convType = item.converted.type === 'reminder' ? 'Reminder' : 'Task';
          convSpan.textContent = `✓ Converted to ${convType}`;
          metaEl.appendChild(convSpan);
        }

        bodyEl.appendChild(metaEl);
      }

      itemEl.appendChild(bodyEl);

      // Actions
      const actionsEl = document.createElement('div');
      actionsEl.className = 'bd-item-actions';

      if (item.status === 'active') {
        // Complete button
        const compBtn = document.createElement('button');
        compBtn.className = 'bd-action-complete';
        compBtn.title = 'Mark as completed';
        compBtn.textContent = '✓ Done';
        compBtn.addEventListener('click', () => handleComplete(item.id, itemEl));
        actionsEl.appendChild(compBtn);

        // Edit button
        const editBtn = document.createElement('button');
        editBtn.title = 'Edit item';
        editBtn.textContent = 'Edit';
        editBtn.addEventListener('click', () => {
          editingItemId = item.id;
          convertingItemId = null;
          renderItems();
        });
        actionsEl.appendChild(editBtn);

        // Convert button
        const convBtn = document.createElement('button');
        convBtn.title = 'Convert to Task or Reminder';
        convBtn.textContent = 'Convert ▾';
        convBtn.addEventListener('click', () => {
          convertingItemId = convertingItemId === item.id ? null : item.id;
          renderItems();
        });
        actionsEl.appendChild(convBtn);

        // Archive button
        const archBtn = document.createElement('button');
        archBtn.title = 'Archive item';
        archBtn.textContent = 'Archive';
        archBtn.addEventListener('click', () => handleArchive(item.id));
        actionsEl.appendChild(archBtn);

        // Delete button
        const delBtn = document.createElement('button');
        delBtn.className = 'bd-action-delete';
        delBtn.title = 'Delete item';
        delBtn.textContent = '×';
        delBtn.addEventListener('click', () => handleDelete(item.id));
        actionsEl.appendChild(delBtn);
      } else {
        // Completed or Archived: restore or delete
        const restBtn = document.createElement('button');
        restBtn.title = 'Restore to active thoughts';
        restBtn.textContent = 'Restore';
        restBtn.addEventListener('click', () => handleRestore(item.id));
        actionsEl.appendChild(restBtn);

        const delBtn = document.createElement('button');
        delBtn.className = 'bd-action-delete';
        delBtn.title = 'Permanently delete item';
        delBtn.textContent = 'Delete';
        delBtn.addEventListener('click', () => handleDelete(item.id));
        actionsEl.appendChild(delBtn);
      }

      itemEl.appendChild(actionsEl);

      // Conversion drawer
      if (convertingItemId === item.id && item.status === 'active') {
        const drawer = document.createElement('div');
        drawer.className = 'bd-convert-drawer';

        // Convert to Task button
        const taskBtn = document.createElement('button');
        taskBtn.className = 'bd-add-btn';
        taskBtn.textContent = 'Convert to Task';
        taskBtn.addEventListener('click', async () => {
          await handleConvertToTask(item.id, item.text);
        });
        drawer.appendChild(taskBtn);

        // Convert to Reminder section
        const remLabel = document.createElement('label');
        remLabel.textContent = 'Reminder Time:';
        const remInput = document.createElement('input');
        remInput.type = 'datetime-local';

        // Default to 1 hour from now formatted as YYYY-MM-DDTHH:MM
        const defaultDue = new Date(Date.now() + 60 * 60 * 1000);
        const pad = n => String(n).padStart(2, '0');
        const defaultDueStr = `${defaultDue.getFullYear()}-${pad(defaultDue.getMonth() + 1)}-${pad(defaultDue.getDate())}T${pad(defaultDue.getHours())}:${pad(defaultDue.getMinutes())}`;
        remInput.value = defaultDueStr;

        const remBtn = document.createElement('button');
        remBtn.className = 'bd-add-btn';
        remBtn.textContent = 'Convert to Reminder';
        remBtn.addEventListener('click', async () => {
          if (!remInput.value) {
            notice('Please select a reminder time.');
            return;
          }
          await handleConvertToReminder(item.id, remInput.value);
        });

        remLabel.appendChild(remInput);
        drawer.appendChild(remLabel);
        drawer.appendChild(remBtn);

        const cancelDrawerBtn = document.createElement('button');
        cancelDrawerBtn.textContent = 'Cancel';
        cancelDrawerBtn.addEventListener('click', () => {
          convertingItemId = null;
          renderItems();
        });
        drawer.appendChild(cancelDrawerBtn);

        itemEl.appendChild(drawer);
      }

      itemsContainer.appendChild(itemEl);
    });
  }

  async function handleCreate() {
    if (!inputEl) return;
    const text = inputEl.value.trim();
    if (!text) {
      inputEl.focus();
      return;
    }
    const category = categorySelect?.value || 'inbox';

    try {
      const res = await apiCall('POST', { action: 'create', text, category });
      if (res.ok) {
        inputEl.value = '';
        notice(`Captured to ${category}`);
        await loadItems();
      }
    } catch {
      // Error notification handled by apiCall
    }
  }

  async function handleUpdate(id, text, category = null) {
    try {
      const payload = { action: 'update', id, text };
      if (category) payload.category = category;
      const res = await apiCall('POST', payload);
      if (res.ok) {
        editingItemId = null;
        notice('Thought updated');
        await loadItems();
      }
    } catch {
      // Error handled
    }
  }

  async function handleComplete(id, element) {
    if (element) {
      element.classList.add('completing');
    }
    setTimeout(async () => {
      try {
        const res = await apiCall('POST', { action: 'complete', id });
        if (res.ok) {
          notice('Thought completed');
          await loadItems();
        }
      } catch {
        if (element) element.classList.remove('completing');
      }
    }, 250);
  }

  async function handleArchive(id) {
    try {
      const res = await apiCall('POST', { action: 'archive', id });
      if (res.ok) {
        notice('Thought archived');
        await loadItems();
      }
    } catch {
      // Error handled
    }
  }

  async function handleRestore(id) {
    try {
      const res = await apiCall('POST', { action: 'restore', id });
      if (res.ok) {
        notice('Thought restored to active');
        await loadItems();
      }
    } catch {
      // Error handled
    }
  }

  async function handleDelete(id) {
    try {
      const res = await apiCall('POST', { action: 'delete', id });
      if (res.ok) {
        notice('Thought deleted');
        await loadItems();
      }
    } catch {
      // Error handled
    }
  }

  async function handleConvertToTask(id, text) {
    try {
      const res = await apiCall('POST', { action: 'convert_to_task', id });
      if (res.ok) {
        convertingItemId = null;
        notice('Converted to Lumina Task (archived in dump)');
        // Start or register the task if desired
        try {
          await fetch('/api/tasks', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ action: 'start', instruction: text })
          });
          notice('Task queued in Lumina');
        } catch {
          // If tasks start fails, conversion itself succeeded
        }
        await loadItems();
      }
    } catch {
      // Error handled
    }
  }

  async function handleConvertToReminder(id, dueAt) {
    try {
      // Convert dueAt from local to ISO
      let dueIso = dueAt;
      try {
        const d = new Date(dueAt);
        dueIso = d.toISOString();
      } catch {}

      const res = await apiCall('POST', {
        action: 'convert_to_reminder',
        id,
        due_at: dueIso,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
      });
      if (res.ok) {
        convertingItemId = null;
        notice('Converted to scheduled Lumina Reminder');
        await loadItems();
      }
    } catch {
      // Error handled
    }
  }

  // Event Listeners Wiring
  if (addBtn) {
    addBtn.addEventListener('click', handleCreate);
  }

  if (inputEl) {
    inputEl.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleCreate();
      }
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      panel.close();
    });
  }

  // Filter pills
  if (filterPillsContainer) {
    filterPillsContainer.addEventListener('click', e => {
      const pill = e.target.closest('.bd-filter-pill');
      if (!pill) return;

      filterPillsContainer.querySelectorAll('.bd-filter-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');

      const filterCat = pill.dataset.filter;
      const filterStatus = pill.dataset.status;

      if (filterStatus) {
        currentStatusFilter = filterStatus;
        currentCategoryFilter = 'all';
      } else if (filterCat) {
        currentCategoryFilter = filterCat;
        currentStatusFilter = 'active';
      }

      loadItems();
    });
  }

  // Search input with debounce
  let searchTimer = null;
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        searchQuery = searchInput.value;
        loadItems();
      }, 200);
    });
  }

  // Open triggers
  const openButtons = [
    document.getElementById('brain-dump-open'),
    document.getElementById('brain-dump-topbar-open')
  ].filter(Boolean);

  function open() {
    panel.showModal();
    inputEl?.focus?.();
    loadItems();
  }

  function close() {
    panel.close();
  }

  openButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      open();
    });
  });

  return {
    open,
    close,
    refresh: loadItems,
    state: () => {},
    event: message => {
      if (message?.type === 'brain_dump_change' || message?.type === 'brain_dump_updated') {
        loadItems();
      }
    }
  };
}
