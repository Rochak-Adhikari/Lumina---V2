/**
 * LUMINA COMMAND DECK CONTROLLER (web/command-deck.js)
 * First-class operational command & observability panel for Lumina.
 * Design Authority: docs/command-deck/
 */

// Pure helper: Secret sanitizer for diagnostic strings
export const SECRET_PATTERN = /(bearer\s+|api[_-]?key\s*[=:]\s*|token\s*[=:]\s*|password\s*[=:]\s*)[^\s,;]+/gi;

export function sanitizeSecrets(text) {
  if (typeof text !== 'string') return '';
  return text.replace(SECRET_PATTERN, '$1[REDACTED]');
}

// Pure helper: Map runtime cognitive states to UI presentation
export function mapRuntimeState(state) {
  const norm = String(state || 'IDLE').toUpperCase();
  switch (norm) {
    case 'IDLE':
      return { label: 'Ready', class: 'ready' };
    case 'LISTENING':
      return { label: 'Listening', class: 'listening' };
    case 'THINKING':
      return { label: 'Processing', class: 'thinking' };
    case 'EXECUTING':
      return { label: 'Executing', class: 'executing' };
    case 'SPEAKING':
      return { label: 'Speaking', class: 'speaking' };
    case 'INTERRUPTED':
      return { label: 'Interrupted', class: 'thinking' };
    case 'WAITING_FOR_USER':
      return { label: 'Action Required', class: 'waiting_for_user' };
    case 'ERROR':
      return { label: 'Attention Needed', class: 'error' };
    default:
      return { label: norm.toLowerCase(), class: 'idle' };
  }
}

// Pure helper: Map task session states
export function mapTaskState(status) {
  const norm = String(status || 'RUNNING').toUpperCase();
  switch (norm) {
    case 'RUNNING':
      return { label: 'Active', class: 'listening' };
    case 'WAITING_FOR_USER':
      return { label: 'Waiting for Input', class: 'waiting_for_user' };
    case 'COMPLETED':
      return { label: 'Completed', class: 'ready' };
    case 'ERROR':
      return { label: 'Failed', class: 'error' };
    case 'CANCELLING':
      return { label: 'Stopping...', class: 'thinking' };
    case 'CANCELLED':
      return { label: 'Cancelled', class: 'idle' };
    case 'CANCEL_FAILED':
      return { label: 'Halt Failed', class: 'error' };
    case 'REMOVING':
      return { label: 'Removing...', class: 'thinking' };
    default:
      return { label: norm, class: 'idle' };
  }
}

// Pure helper: Format duration in seconds
export function formatDuration(seconds) {
  if (typeof seconds !== 'number' || isNaN(seconds) || seconds < 0) return '0s';
  const sec = Math.floor(seconds);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const remSec = sec % 60;
  if (min < 60) return `${min}m ${remSec}s`;
  const hrs = Math.floor(min / 60);
  const remMin = min % 60;
  return `${hrs}h ${remMin}m`;
}

// Pure helper: Format relative timestamp
export function formatRelativeTime(epochMs, now = Date.now()) {
  if (!epochMs || isNaN(epochMs)) return 'unknown';
  const diffSec = Math.floor((now - epochMs) / 1000);
  if (diffSec < 3) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  const min = Math.floor(diffSec / 60);
  if (min < 60) return `${min}m ago`;
  const date = new Date(epochMs);
  return date.toTimeString().split(' ')[0];
}

// Bounded Event Buffer for real-time operational feeds (Capped at maxSize, default 150)
export class BoundedEventBuffer {
  constructor(maxSize = 150) {
    this.maxSize = maxSize;
    this.events = [];
    this.seenIds = new Set();
  }

  push(event) {
    if (!event || !event.id) return false;
    if (this.seenIds.has(event.id)) return false;

    this.seenIds.add(event.id);
    this.events.unshift(event); // newest first

    if (this.events.length > this.maxSize) {
      const evicted = this.events.pop();
      if (evicted && evicted.id) {
        this.seenIds.delete(evicted.id);
      }
    }
    return true;
  }

  filter(category = 'all') {
    if (category === 'all') return [...this.events];
    return this.events.filter(e => e.category === category);
  }

  clear() {
    this.events = [];
    this.seenIds.clear();
  }

  size() {
    return this.events.length;
  }
}

/**
 * Main Controller setup function
 */
export function setupCommandDeck({ getConfig, notice, send }) {
  const $ = id => document.getElementById(id);
  const panel = $('command-deck-panel');
  if (!panel) return null;

  // Local Controller State
  const buffer = new BoundedEventBuffer(150);
  let activeFilter = 'all';
  let tasks = [];
  let currentState = null;
  let connectionStatus = 'connected';
  let lastUpdateEpoch = Date.now();
  let refreshTimer = null;
  let openerElement = null;
  let workspaceFilesCount = null;

  // Safe DOM helper
  function el(tag, className = '', text = '') {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  // Section error boundary wrapper
  function safeSection(sectionId, renderFn) {
    try {
      renderFn();
    } catch (err) {
      console.error(`CommandDeck: Render failed for ${sectionId}:`, err);
      const container = $(sectionId);
      if (container) {
        container.replaceChildren();
        const errBox = el('div', 'cd-section-error', 'Readout temporarily unavailable.');
        container.append(errBox);
      }
    }
  }

  // CD-F001: Render Live Status Header Strip
  function renderLiveStatus() {
    safeSection('cd-live-status', () => {
      const container = $('cd-live-status');
      if (!container) return;
      container.replaceChildren();

      // Adjust container classes for stale/disconnected
      container.className = 'cd-live-strip';
      const isStale = (Date.now() - lastUpdateEpoch) > 25000;
      if (connectionStatus !== 'connected') {
        container.classList.add('disconnected');
      } else if (isStale) {
        container.classList.add('stale');
      }

      // 1. Connection & Core Runtime Cognitive Pill
      const stateInfo = connectionStatus !== 'connected'
        ? { label: 'DISCONNECTED', class: 'error' }
        : currentState
          ? mapRuntimeState(currentState?.state)
          : { label: 'Connecting…', class: 'thinking' };
      const stateItem = el('div', 'cd-status-item');
      stateItem.append(el('span', '', 'STATUS:'));
      const statePill = el('span', `cd-pill ${stateInfo.class}`, stateInfo.label);
      stateItem.append(statePill);
      container.append(stateItem);

      container.append(el('div', 'cd-strip-divider'));

      // 2. Active Tool / Operation
      const toolItem = el('div', 'cd-status-item');
      toolItem.append(el('span', '', 'OPERATION:'));
      const activeTool = currentState?.current_tool;
      const toolText = el('strong', '', activeTool ? activeTool : (connectionStatus !== 'connected' ? 'Unavailable' : 'System Idle'));
      toolItem.append(toolText);
      container.append(toolItem);

      container.append(el('div', 'cd-strip-divider'));

      // 3. Provider State
      const provItem = el('div', 'cd-status-item');
      provItem.append(el('span', '', 'PROVIDER:'));
      const prov = currentState?.provider_status;
      const provLabel = connectionStatus !== 'connected' ? 'Offline' :
        prov === 'local' ? 'Local Mode' :
        prov === 'connected' ? 'Online: Gemini Live' :
        prov === 'connecting' ? 'Connecting...' : 'Provider Offline';
      provItem.append(el('strong', '', provLabel));
      container.append(provItem);

      // 4. Pending Approvals Indicator
      const pendingCount = (currentState?.control_safety?.unresolved ? 1 : 0) +
        (currentState?.pending_approvals_count || 0);
      if (pendingCount > 0) {
        container.append(el('div', 'cd-strip-divider'));
        const approvalBtn = el('button', 'cd-approval-badge', `⚠ ${pendingCount} PENDING APPROVAL`);
        approvalBtn.type = 'button';
        approvalBtn.onclick = () => {
          panel.close();
          window.dispatchEvent(new CustomEvent('lumina-event', { detail: { type: 'confirmation_open' } }));
        };
        container.append(approvalBtn);
      }

      // 5. Freshness / Stale Tag
      container.append(el('div', 'cd-strip-divider'));
      const freshnessItem = el('div', 'cd-status-item');
      if (connectionStatus !== 'connected') {
        freshnessItem.append(el('span', 'cd-stale-tag', '● RECONNECTING...'));
      } else if (isStale) {
        freshnessItem.append(el('span', 'cd-stale-tag', '⚠ DATA STALE'));
      } else {
        freshnessItem.append(el('span', '', `Synced ${formatRelativeTime(lastUpdateEpoch)}`));
      }
      container.append(freshnessItem);
    });
  }

  // CD-F002: Render Mission Control Task List
  function renderTasks() {
    safeSection('cd-task-list', () => {
      const container = $('cd-task-list');
      const countLabel = $('cd-task-count');
      if (!container) return;
      container.replaceChildren();

      if (countLabel) {
        countLabel.textContent = `${tasks.length} ${tasks.length === 1 ? 'task' : 'tasks'}`;
      }

      if (!tasks.length) {
        container.append(el('div', 'cd-empty', 'No active or recent agent tasks in this session.'));
        return;
      }

      tasks.forEach(task => {
        const item = el('article', 'cd-task-item');

        // Header: Worker tag, Task ID, and Status
        const header = el('div', 'cd-task-header');
        const identity = el('div', 'cd-task-identity');
        identity.append(el('span', 'cd-worker-tag', task.worker || 'Agent'));
        identity.append(el('span', 'cd-task-id', `#${String(task.task_id || '').slice(0, 8)}`));
        header.append(identity);

        const statusInfo = mapTaskState(task.status);
        header.append(el('span', `cd-pill ${statusInfo.class}`, statusInfo.label));
        item.append(header);

        // Body: Truncated instruction
        const instruction = el('p', 'cd-task-instruction', sanitizeSecrets(task.instruction || task.summary || 'No description recorded.'));
        item.append(instruction);

        // Footer: Duration & Actions
        const footer = el('div', 'cd-task-footer');
        const durationSec = task.completed_at ? (task.completed_at - (task.created_at || task.completed_at)) :
          task.created_at ? (Date.now() / 1000 - task.created_at) : 0;
        footer.append(el('span', '', `Duration: ${formatDuration(durationSec)}`));

        const actions = el('div', 'cd-task-actions');
        const inspectBtn = el('button', 'cd-btn-sm', 'Inspect');
        inspectBtn.type = 'button';
        inspectBtn.onclick = () => openDrawer(task);
        actions.append(inspectBtn);

        // Cancel action with 2-step confirmation for RUNNING tasks
        if (task.status === 'RUNNING') {
          const cancelBtn = el('button', 'cd-btn-sm cd-btn-danger', 'Cancel');
          cancelBtn.type = 'button';
          cancelBtn.onclick = async () => {
            if (cancelBtn.dataset.confirming !== 'true') {
              cancelBtn.dataset.confirming = 'true';
              cancelBtn.textContent = 'Confirm Halt?';
              setTimeout(() => {
                cancelBtn.dataset.confirming = 'false';
                cancelBtn.textContent = 'Cancel';
              }, 4000);
              return;
            }
            try {
              cancelBtn.disabled = true;
              cancelBtn.textContent = 'Halting...';
              const token = getConfig()?.token;
              // Step 1: Request confirmation token
              const step1 = await fetch('/api/tasks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...(token ? { 'X-Lumina-Token': token } : {}) },
                body: JSON.stringify({ action: 'request_cancel', task_id: task.task_id })
              });
              const r1 = await step1.json();
              if (!step1.ok || !r1.confirmation_id) throw Error(r1.error || 'Failed to request cancel.');

              // Step 2: Confirm cancellation
              const step2 = await fetch('/api/tasks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...(token ? { 'X-Lumina-Token': token } : {}) },
                body: JSON.stringify({ action: 'cancel', task_id: task.task_id, confirmation_id: r1.confirmation_id })
              });
              const r2 = await step2.json();
              if (!step2.ok) throw Error(r2.error || 'Cancel failed.');
              notice('Task cancellation requested.');
              await fetchTasks();
            } catch (err) {
              notice(err.message);
              cancelBtn.disabled = false;
              cancelBtn.textContent = 'Cancel';
            }
          };
          actions.append(cancelBtn);
        }

        footer.append(actions);
        item.append(footer);
        container.append(item);
      });
    });
  }

  // CD-F003: Render Operational Activity Feed
  function renderFeed() {
    safeSection('cd-feed-list', () => {
      const container = $('cd-feed-list');
      const countLabel = $('cd-feed-count');
      if (!container) return;
      container.replaceChildren();

      const items = buffer.filter(activeFilter);
      if (countLabel) {
        countLabel.textContent = `${items.length} ${items.length === 1 ? 'event' : 'events'}`;
      }

      if (!items.length) {
        container.append(el('div', 'cd-empty', 'No operational events recorded for this category.'));
        return;
      }

      items.forEach(ev => {
        const row = el('div', 'cd-feed-item');

        // Timestamp
        const timeStr = formatRelativeTime(ev.timestamp);
        row.append(el('span', 'cd-feed-time', timeStr));

        // Category Icon
        let iconChar = '⚙';
        if (ev.category === 'task') iconChar = '◈';
        else if (ev.category === 'approval') iconChar = '⚠';
        else if (ev.category === 'error') iconChar = '✖';
        else if (ev.category === 'system') iconChar = '✓';
        row.append(el('span', `cd-feed-icon ${ev.category}`, iconChar));

        // Content
        const content = el('div', 'cd-feed-content');
        content.append(el('div', 'cd-feed-title', sanitizeSecrets(ev.title || 'System Event')));
        if (ev.detail) {
          content.append(el('div', 'cd-feed-detail', sanitizeSecrets(ev.detail)));
        }
        row.append(content);
        container.append(row);
      });

      const boundedNotice = el('div', 'cd-feed-footer', 'Recent bounded history (max 150 events). Earlier records preserved in session logs.');
      container.append(boundedNotice);
    });
  }

  // CD-F004: Render Workspace Context Monitor
  function renderWorkspace() {
    safeSection('cd-workspace-section', () => {
      const pathEl = $('cd-workspace-path');
      const uploadsEl = $('cd-workspace-uploads');
      const config = getConfig();
      const rootPath = config?.root || 'Unconfigured root';

      if (pathEl) {
        pathEl.textContent = rootPath;
        pathEl.title = rootPath;
      }

      if (uploadsEl) {
        if (typeof workspaceFilesCount === 'number') {
          uploadsEl.textContent = `${workspaceFilesCount} file${workspaceFilesCount === 1 ? '' : 's'} in upload sandbox`;
        } else {
          uploadsEl.textContent = 'Workspace sandbox active';
        }
      }
    });
  }

  // CD-F005: Render System Watch Alerts
  function renderSystemWatch() {
    safeSection('cd-system-watch', () => {
      const container = $('cd-system-watch');
      if (!container) return;
      container.replaceChildren();

      const alerts = [];

      // Connection alerts
      if (connectionStatus !== 'connected') {
        alerts.push({
          severity: 'critical',
          text: 'Transport Disconnected: Connection to the local Python runtime was lost. Local tools are paused.'
        });
      }

      // Safety Authority alerts
      if (currentState?.control_safety?.quarantined) {
        alerts.push({
          severity: 'critical',
          text: 'Safety Quarantine Active: External changes detected. Live computer effects remain blocked.'
        });
      }

      if (currentState?.control_safety?.unresolved) {
        alerts.push({
          severity: 'warning',
          text: 'Safeguards Pending: Unresolved control state requires user attention.'
        });
      }

      // Runtime Error alerts
      if (Array.isArray(currentState?.errors) && currentState.errors.length) {
        currentState.errors.forEach(err => {
          alerts.push({
            severity: 'critical',
            text: `Runtime Exception: ${sanitizeSecrets(typeof err === 'string' ? err : err.message || 'Unknown fault')}`
          });
        });
      }

      // Provider warning
      if (currentState?.provider_status === 'failed' || currentState?.provider_status === 'unavailable') {
        alerts.push({
          severity: 'warning',
          text: 'Reasoning Provider Offline: Online analysis is currently unavailable. Local capabilities remain active.'
        });
      }

      // Telemetry staleness warning
      if (connectionStatus === 'connected' && (Date.now() - lastUpdateEpoch) > 25000) {
        alerts.push({
          severity: 'warning',
          text: 'Data Telemetry Stale: No heartbeat or update received within 25 seconds.'
        });
      }

      if (!alerts.length) {
        const healthyCard = el('div', 'cd-alert-item healthy', '✓ All monitored subsystems operational. No active faults.');
        container.append(healthyCard);
        return;
      }

      alerts.forEach(a => {
        container.append(el('div', `cd-alert-item ${a.severity}`, a.text));
      });
    });
  }

  // CD-F006: Task Diagnostics Drawer
  function openDrawer(task) {
    const drawer = $('cd-drawer');
    if (!drawer) return;
    drawer.hidden = false;

    $('cd-drawer-title').textContent = `${task.worker || 'Task'} Diagnostics`;
    $('cd-drawer-id').textContent = task.task_id || 'unknown';
    $('cd-drawer-status').textContent = task.status || 'unknown';
    $('cd-drawer-created').textContent = task.created_at ? new Date(task.created_at * 1000).toLocaleString() : 'unknown';
    $('cd-drawer-exit').textContent = task.exit_code != null ? String(task.exit_code) : 'N/A';

    const instructionPre = $('cd-drawer-instruction');
    if (instructionPre) {
      instructionPre.textContent = sanitizeSecrets(task.instruction || task.messages?.[0] || 'No instruction');
    }

    const filesPre = $('cd-drawer-files');
    if (filesPre) {
      const files = Array.isArray(task.changed_files) ? task.changed_files : [];
      filesPre.textContent = files.length ? files.join('\n') : 'No file changes recorded.';
    }

    const errorPre = $('cd-drawer-error');
    if (errorPre) {
      errorPre.textContent = sanitizeSecrets(task.error || task.summary || task.result || 'None');
    }

    // Focus close button for accessibility
    const drawerCloseBtn = $('cd-drawer-close');
    if (drawerCloseBtn) drawerCloseBtn.focus();

    // Markdown copy button
    const copyBtn = $('cd-drawer-copy');
    if (copyBtn) {
      copyBtn.onclick = async () => {
        const md = [
          `# Lumina Task Diagnostic [${task.task_id || 'unknown'}]`,
          `- Worker: ${task.worker || 'unknown'}`,
          `- Status: ${task.status || 'unknown'}`,
          `- Created: ${task.created_at ? new Date(task.created_at * 1000).toISOString() : 'N/A'}`,
          `- Completed: ${task.completed_at ? new Date(task.completed_at * 1000).toISOString() : 'N/A'}`,
          `- Exit Code: ${task.exit_code != null ? task.exit_code : 'N/A'}`,
          `\n## Instruction\n${sanitizeSecrets(task.instruction || task.messages?.[0] || 'None')}`,
          `\n## Modified Files\n${Array.isArray(task.changed_files) && task.changed_files.length ? task.changed_files.join('\n') : 'None'}`,
          `\n## Result / Error\n${sanitizeSecrets(task.error || task.summary || task.result || 'None')}`
        ].join('\n');
        try {
          await navigator.clipboard.writeText(md);
          notice('Task diagnostics copied as Markdown.');
        } catch {
          notice('Clipboard access unavailable.');
        }
      };
    }
  }

  function closeDrawer() {
    const drawer = $('cd-drawer');
    if (drawer) drawer.hidden = true;
  }

  // Backend REST Sync
  async function fetchState() {
    try {
      const token = getConfig()?.token;
      const res = await fetch('/api/state', { headers: token ? { 'X-Lumina-Token': token } : {} });
      if (!res.ok) return;
      const data = await res.json();
      handleState(data);
    } catch (e) {
      console.warn('CommandDeck: fetchState failed:', e.message);
    }
  }

  async function fetchTasks() {
    try {
      const token = getConfig()?.token;
      const res = await fetch('/api/tasks', { headers: token ? { 'X-Lumina-Token': token } : {} });
      if (!res.ok) throw Error('Tasks unavailable');
      const data = await res.json();
      tasks = Array.isArray(data.tasks) ? data.tasks : [];
      lastUpdateEpoch = Date.now();
      if (panel.open) renderTasks();
    } catch (e) {
      console.warn('CommandDeck: fetchTasks failed:', e.message);
    }
  }

  async function fetchAudit() {
    try {
      const token = getConfig()?.token;
      const res = await fetch('/api/audit', { headers: token ? { 'X-Lumina-Token': token } : {} });
      if (!res.ok) return;
      const data = await res.json();
      const rawEvents = Array.isArray(data?.events) ? data.events : (Array.isArray(data) ? data : []);
      rawEvents.forEach(item => {
        if (!item || typeof item !== 'object') return;
        const op = String(item.operation || 'event');
        const st = String(item.status || '');
        const target = item.tool || item.worker || item.task_id || '';
        const id = `audit-${item.time || ''}-${op}-${st}-${target}`;
        const category = op === 'worker' || op === 'agent_task' ? 'task' :
          op === 'confirmation' ? 'approval' : 'tool';
        buffer.push({
          id,
          timestamp: (item.time || (Date.now() / 1000)) * 1000,
          category,
          title: `${op}: ${st}`,
          detail: target ? `Target: ${target}` : null
        });
      });
      lastUpdateEpoch = Date.now();
      if (panel.open) renderFeed();
    } catch {
      // Non-fatal
    }
  }

  async function fetchWorkspace() {
    try {
      const token = getConfig()?.token;
      if (!token) return;
      const res = await fetch('/api/files', { headers: { 'X-Lumina-Token': token } });
      if (res.ok) {
        const data = await res.json();
        const list = Array.isArray(data) ? data : (Array.isArray(data?.files) ? data.files : []);
        workspaceFilesCount = list.length;
      }
    } catch {
      // Non-fatal
    }
    if (panel.open) renderWorkspace();
  }

  // Full Refresh
  async function refresh() {
    await Promise.allSettled([fetchState(), fetchTasks(), fetchAudit(), fetchWorkspace()]);
    if (panel.open) {
      renderLiveStatus();
      renderWorkspace();
      renderSystemWatch();
      renderTasks();
      renderFeed();
    }
  }

  // Modal Open / Close Handlers
  function openPanel() {
    openerElement = document.activeElement;
    panel.showModal();
    closeDrawer();
    renderLiveStatus();
    renderWorkspace();
    renderSystemWatch();
    renderTasks();
    renderFeed();
    refresh();

    // Focus close button for accessibility
    const closeBtn = $('command-deck-close');
    if (closeBtn) closeBtn.focus();

    // Periodic 3s refresh while open to update relative time without masking stale data
    clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
      if (panel.open) {
        renderLiveStatus();
      }
    }, 3000);
  }

  function closePanel() {
    clearInterval(refreshTimer);
    closeDrawer();
    panel.close();
    if (openerElement && typeof openerElement.focus === 'function') {
      openerElement.focus();
    }
  }

  // Wire UI DOM Buttons
  const openNavBtn = $('command-deck-open');
  if (openNavBtn) openNavBtn.onclick = openPanel;

  const openTopbarBtn = $('command-deck-topbar-open');
  if (openTopbarBtn) openTopbarBtn.onclick = openPanel;

  const closeBtn = $('command-deck-close');
  if (closeBtn) closeBtn.onclick = closePanel;

  const drawerCloseBtn = $('cd-drawer-close');
  if (drawerCloseBtn) drawerCloseBtn.onclick = closeDrawer;

  // Backdrop click closes dialog
  panel.addEventListener('click', event => {
    if (event.target === panel) closePanel();
  });

  // Escape key handler: closes drawer first if open, else dialog
  panel.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      const drawer = $('cd-drawer');
      if (drawer && !drawer.hidden) {
        event.stopPropagation();
        event.preventDefault();
        closeDrawer();
      }
    }
  });

  // Copy Workspace Path Button
  const copyPathBtn = $('cd-copy-path');
  if (copyPathBtn) {
    copyPathBtn.onclick = async () => {
      const rootPath = getConfig()?.root || '';
      try {
        await navigator.clipboard.writeText(rootPath);
        notice('Workspace path copied.');
      } catch {
        notice('Clipboard access unavailable.');
      }
    };
  }

  // Filter Bar Buttons
  document.querySelectorAll('.cd-filter-pill').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('.cd-filter-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeFilter = btn.dataset.filter || 'all';
      renderFeed();
    };
  });

  // Handle Ingestion of State and WebSocket Events
  function handleState(state) {
    currentState = state;
    lastUpdateEpoch = Date.now();
    connectionStatus = 'connected';
    if (panel.open) {
      renderLiveStatus();
      renderSystemWatch();
    }
  }

  function handleEvent(msg) {
    if (!msg || typeof msg !== 'object' || !msg.type) return;

    if (msg.type === 'state' && msg.data) {
      handleState(msg.data);
      return;
    }

    if (msg.type === 'connection_opened' || msg.type === 'client_ready') {
      connectionStatus = 'connected';
      lastUpdateEpoch = Date.now();
      refresh();
      return;
    }

    if (msg.type === 'connection_closed') {
      connectionStatus = 'disconnected';
      if (panel.open) {
        renderLiveStatus();
        renderSystemWatch();
      }
      return;
    }

    if (msg.type === 'agent_result' && msg.data) {
      const d = msg.data;
      const existingIdx = tasks.findIndex(t => t.task_id === d.task_id);
      if (existingIdx >= 0) {
        tasks[existingIdx] = { ...tasks[existingIdx], ...d };
      } else {
        tasks.unshift({
          task_id: d.task_id,
          worker: d.worker,
          status: d.status,
          summary: d.summary,
          created_at: Date.now() / 1000
        });
      }
      buffer.push({
        id: `agent-${d.task_id}-${d.status}-${Date.now()}`,
        timestamp: Date.now(),
        category: 'task',
        title: `Task ${d.worker || 'Agent'}: ${d.status}`,
        detail: d.summary || null
      });
      lastUpdateEpoch = Date.now();
      fetchTasks();
      if (panel.open) {
        renderTasks();
        renderFeed();
      }
      return;
    }

    if (msg.type === 'capability_result') {
      const toolName = msg.tool || 'Local Tool';
      const d = msg.data || {};
      buffer.push({
        id: `tool-${toolName}-${Date.now()}`,
        timestamp: Date.now(),
        category: 'tool',
        title: `Tool: ${toolName}`,
        detail: d.message || (d.ok ? 'Completed successfully' : d.error || 'Execution finished')
      });
      lastUpdateEpoch = Date.now();
      if (panel.open) renderFeed();
      return;
    }

    if (msg.type === 'phase2_result') {
      const toolName = msg.tool || 'Automation';
      const d = msg.data || {};
      buffer.push({
        id: `p2-${toolName}-${Date.now()}`,
        timestamp: Date.now(),
        category: 'tool',
        title: `Automation: ${toolName}`,
        detail: d.message || d.status || (d.ok ? 'Completed' : 'Operation finished')
      });
      lastUpdateEpoch = Date.now();
      if (panel.open) renderFeed();
      return;
    }

    if (msg.type === 'continuity_result') {
      const toolName = msg.tool || 'Memory';
      const d = msg.data || {};
      buffer.push({
        id: `continuity-${toolName}-${Date.now()}`,
        timestamp: Date.now(),
        category: 'system',
        title: `Memory: ${toolName}`,
        detail: d.message || (d.ok ? 'Updated knowledge memory' : d.error || 'Finished')
      });
      lastUpdateEpoch = Date.now();
      if (panel.open) renderFeed();
      return;
    }

    if (msg.type === 'confirmation' && msg.data) {
      const c = msg.data;
      buffer.push({
        id: `conf-${c.confirmation_id || Date.now()}`,
        timestamp: Date.now(),
        category: 'approval',
        title: `Security Approval Requested: ${c.tool || 'Action'}`,
        detail: c.message || null
      });
      lastUpdateEpoch = Date.now();
      if (panel.open) {
        renderLiveStatus();
        renderFeed();
        renderSystemWatch();
      }
      return;
    }

    if (msg.type === 'confirmation_resolved') {
      buffer.push({
        id: `conf-res-${msg.confirmation_id || Date.now()}`,
        timestamp: Date.now(),
        category: 'approval',
        title: 'Approval Resolved',
        detail: msg.confirmation_id ? `ID: ${msg.confirmation_id}` : null
      });
      lastUpdateEpoch = Date.now();
      if (panel.open) {
        renderLiveStatus();
        renderFeed();
        renderSystemWatch();
      }
      return;
    }

    if (msg.type === 'announcement' && msg.text) {
      buffer.push({
        id: `ann-${Date.now()}`,
        timestamp: Date.now(),
        category: 'system',
        title: 'Announcement',
        detail: msg.text
      });
      lastUpdateEpoch = Date.now();
      if (panel.open) renderFeed();
      return;
    }

    if (msg.type === 'notice' && msg.text) {
      buffer.push({
        id: `notice-${Date.now()}`,
        timestamp: Date.now(),
        category: 'system',
        title: 'System Notice',
        detail: msg.text
      });
      lastUpdateEpoch = Date.now();
      if (panel.open) renderFeed();
      return;
    }
  }

  // Subscribe to window event bus
  const eventListener = e => handleEvent(e.detail);
  window.addEventListener('lumina-event', eventListener);

  return {
    open: openPanel,
    close: closePanel,
    event: handleEvent,
    state: handleState,
    refresh,
    buffer,
    getTasks: () => [...tasks],
    getState: () => currentState,
    getConnectionStatus: () => connectionStatus,
    destroy: () => {
      clearInterval(refreshTimer);
      window.removeEventListener('lumina-event', eventListener);
      if (panel.open) panel.close();
    }
  };
}
