// Lumina Continuity Panel: Daily Review + Search & Evidence Integration
// Evidence and candidate proposals are rendered strictly as text nodes, never executable HTML.

export function formatLocalDate(d = new Date()) {
  const date = d instanceof Date ? d : new Date(d);
  if (isNaN(date.getTime())) return new Date().toISOString().slice(0, 10);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function shiftDateString(dateStr, daysOffset = 0) {
  if (!dateStr || !/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return formatLocalDate();
  const [y, m, d] = dateStr.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  date.setDate(date.getDate() + daysOffset);
  return formatLocalDate(date);
}

export function formatCandidateSummary(candidate) {
  if (!candidate) return 'Unknown candidate';
  const p = candidate.proposal_json;
  if (!p) {
    return candidate.proposed_fact || candidate.title || candidate.id || 'Empty proposal';
  }
  if (typeof p === 'string') {
    try {
      const parsed = JSON.parse(p);
      return formatCandidateSummary({ ...candidate, proposal_json: parsed });
    } catch {
      return p;
    }
  }
  if (typeof p === 'object') {
    if (p.error) return `[Restricted: ${p.error}]`;
    const core = p.object_value || p.description || p.chosen_option || p.title || p.prediction || p.pattern || p.name;
    if (core) {
      if (p.predicate && p.subject) {
        return `${p.subject} ${p.predicate}: ${core}`;
      }
      return core;
    }
  }
  return candidate.proposed_fact || candidate.id || 'Candidate proposal';
}

export function formatRelativeTime(isoString) {
  if (!isoString) return '';
  const date = new Date(isoString);
  if (isNaN(date.getTime())) return String(isoString);
  return date.toLocaleString();
}

export function createSafeElement(tag, text = '', className = '', doc = (typeof document !== 'undefined' ? document : null)) {
  if (!doc) {
    return { tagName: tag.toUpperCase(), textContent: text, className, children: [] };
  }
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

export function setupContinuity({ getConfig, notice }) {
  const $ = id => document.getElementById(id);
  const panel = $('continuity-panel');
  if (!panel) return;

  // Active state
  let currentTab = 'review';
  let selectedDate = formatLocalDate();
  let candidateFilter = 'pending';
  let searchSelected = null;
  let searchBusy = false;

  // ─────────────────────────────────────────────────────────────
  // Tab Navigation
  // ─────────────────────────────────────────────────────────────
  function switchTab(tabId) {
    currentTab = tabId;
    const isReview = tabId === 'review';
    const isSearch = tabId === 'search';
    const isSummary = tabId === 'summary';
    const tabReview = $('continuity-tab-review');
    const tabSearch = $('continuity-tab-search');
    const tabSummary = $('continuity-tab-summary');
    const viewReview = $('continuity-view-review');
    const viewSearch = $('continuity-view-search');
    const viewSummary = $('continuity-view-summary');

    if (tabReview) {
      tabReview.classList.toggle('active', isReview);
      tabReview.setAttribute('aria-selected', isReview ? 'true' : 'false');
      tabReview.setAttribute('tabindex', isReview ? '0' : '-1');
    }
    if (tabSearch) {
      tabSearch.classList.toggle('active', isSearch);
      tabSearch.setAttribute('aria-selected', isSearch ? 'true' : 'false');
      tabSearch.setAttribute('tabindex', isSearch ? '0' : '-1');
    }
    if (tabSummary) {
      tabSummary.classList.toggle('active', isSummary);
      tabSummary.setAttribute('aria-selected', isSummary ? 'true' : 'false');
      tabSummary.setAttribute('tabindex', isSummary ? '0' : '-1');
    }
    if (viewReview) viewReview.hidden = !isReview;
    if (viewSearch) viewSearch.hidden = !isSearch;
    if (viewSummary) viewSummary.hidden = !isSummary;

    if (isReview) {
      loadDailyReview();
    } else if (isSearch) {
      searchRefresh();
    } else if (isSummary) {
      loadProfileSummary();
    }
  }

  async function loadProfileSummary() {
    const contentEl = $('summary-content');
    const statusEl = $('summary-status-bar');
    if (statusEl) {
      statusEl.textContent = 'Loading persistent user summary…';
      statusEl.hidden = false;
    }
    try {
      const res = await fetch('/api/continuity?action=user_summary', {
        headers: { 'X-Lumina-Token': getConfig().token }
      });
      const data = await res.json();
      if (data.ok && data.summary) {
        if (contentEl) contentEl.textContent = data.summary.text || JSON.stringify(data.summary, null, 2);
        if (statusEl) statusEl.textContent = `Summary version ${data.summary.version || 1} · Updated ${data.summary.updated_at || 'recently'}`;
      } else {
        if (contentEl) contentEl.textContent = 'No persistent user summary available yet.';
        if (statusEl) statusEl.hidden = true;
      }
    } catch (e) {
      if (contentEl) contentEl.textContent = 'Failed to load summary: ' + e.message;
      if (statusEl) statusEl.hidden = true;
    }
  }

  const tabReviewBtn = $('continuity-tab-review');
  const tabSearchBtn = $('continuity-tab-search');
  const tabSummaryBtn = $('continuity-tab-summary');
  if (tabReviewBtn) tabReviewBtn.onclick = () => switchTab('review');
  if (tabSearchBtn) tabSearchBtn.onclick = () => switchTab('search');
  if (tabSummaryBtn) tabSummaryBtn.onclick = () => switchTab('summary');
  const summaryRefreshBtn = $('summary-refresh-btn');
  if (summaryRefreshBtn) summaryRefreshBtn.onclick = loadProfileSummary;

  const tabsNav = document.querySelector('.continuity-tabs');
  if (tabsNav) {
    tabsNav.addEventListener('keydown', e => {
      if (e.key === 'ArrowRight' && currentTab === 'review') {
        switchTab('search');
        if (tabSearchBtn) tabSearchBtn.focus();
      } else if (e.key === 'ArrowLeft' && currentTab === 'search') {
        switchTab('review');
        if (tabReviewBtn) tabReviewBtn.focus();
      }
    });
  }

  // ─────────────────────────────────────────────────────────────
  // Daily Reflection
  // ─────────────────────────────────────────────────────────────
  async function loadDailyReflection(targetDate) {
    if (!targetDate) targetDate = selectedDate;
    selectedDate = targetDate;
    const dateInput = $('review-date-picker');
    if (dateInput) dateInput.value = selectedDate;

    const statusBar = $('review-status-bar');
    const errorBox = $('review-error-box');
    const errorMsg = $('review-error-msg');
    const emptyState = $('review-reflection-empty');
    const summaryText = $('review-summary-text');
    const dateTag = $('review-reflection-date');
    const tzBadge = $('review-tz-badge');
    const qualityBox = $('review-quality-notes');
    const loopsList = $('review-loops-list');
    const loopsCount = $('review-loops-count');

    if (statusBar) {
      statusBar.textContent = `Loading reflection for ${selectedDate}…`;
      statusBar.hidden = false;
    }
    if (errorBox) errorBox.hidden = true;

    try {
      let res = await fetch(`/api/continuity?action=reflection&date=${encodeURIComponent(selectedDate)}`, {
        headers: { 'X-Lumina-Token': getConfig().token }
      });
      if (res.status === 404) {
        res = await fetch(`/api/continuity/reflection?date=${encodeURIComponent(selectedDate)}`, {
          headers: { 'X-Lumina-Token': getConfig().token }
        });
      }
      const data = await res.json();
      if (!res.ok || !data.ok) {
        let msg = data.error;
        if (!msg) {
          msg = `HTTP ${res.status}: Reflection unavailable.`;
        } else if (msg === 'Invalid request.' && res.status === 400) {
          msg = 'Daily reflection is not active on this server instance (server restart required to load Gate 3 routes).';
        }
        throw new Error(msg);
      }

      const ref = data.reflection || data || {};
      const dateVal = ref.date || ref.period?.date || selectedDate;
      const tzVal = ref.timezone || ref.period?.timezone || 'Asia/Kathmandu';
      if (dateTag) dateTag.textContent = dateVal;
      if (tzBadge) tzBadge.textContent = tzVal;

      // Summary
      if (summaryText) {
        summaryText.textContent = ref.deterministic_summary || ref.summary || 'No recorded activity for this day.';
      }

      // Metrics
      const metrics = ref.activity_metrics || ref.metrics || {};
      const setMetric = (id, val) => {
        const el = $(id);
        if (el) el.textContent = String(val ?? 0);
      };
      setMetric('metric-sessions', metrics.sessions ?? metrics.user_messages ?? 0);
      setMetric('metric-tasks', metrics.tasks ?? 0);
      setMetric('metric-files', metrics.files ?? 0);
      setMetric('metric-tools', metrics.tools ?? metrics.tool_executions ?? 0);
      setMetric('metric-decisions', metrics.decisions ?? 0);
      setMetric('metric-events', metrics.events ?? metrics.messages ?? 0);

      // Quality notes
      if (qualityBox) {
        qualityBox.replaceChildren();
        const notes = ref.data_quality_notes || [];
        if (notes.length > 0) {
          qualityBox.hidden = false;
          qualityBox.append(createSafeElement('div', 'Data Quality & Context Notes', 'quality-notes-heading'));
          for (const note of notes) {
            qualityBox.append(createSafeElement('div', `• ${note}`, 'quality-note-item'));
          }
        } else {
          qualityBox.hidden = true;
        }
      }

      // Open loops, Unresolved decisions & Goals
      const loops = (ref.open_loops || []).map(l => ({ ...l, _kind: 'loop' }));
      const decisions = (ref.decisions || ref.unresolved_decisions || []).map(d => ({ ...d, _kind: 'decision' }));
      const goals = (ref.goals || []).map(g => ({ ...g, _kind: 'goal' }));
      const allLoops = [...loops, ...decisions, ...goals];

      if (loopsCount) loopsCount.textContent = `${allLoops.length} open`;

      if (loopsList) {
        loopsList.replaceChildren();
        if (allLoops.length === 0) {
          loopsList.append(createSafeElement('div', 'No open loops or unresolved decisions recorded.', 'review-empty-mini'));
        } else {
          for (const item of allLoops) {
            const card = createSafeElement('div', '', 'loop-card');
            const isGoal = item._kind === 'goal' || (item.priority != null && item.chosen_option == null && item.next_action == null);
            const isDec = item._kind === 'decision' || item.chosen_option != null || item.options != null || Boolean(item.context);
            const badgeText = isGoal ? 'Goal' : isDec ? 'Decision' : 'Open Loop';
            const badgeClass = `loop-card-badge ${isGoal ? 'goal' : isDec ? 'decision' : 'loop'}`;
            const topRow = createSafeElement('div', '', 'loop-card-meta');
            topRow.append(
              createSafeElement('span', badgeText, badgeClass),
              createSafeElement('span', item.observed_at || item.created_at ? formatRelativeTime(item.observed_at || item.created_at) : '', 'loop-card-date')
            );
            let desc = item.description || item.object_value || item.title;
            if (!desc) {
              desc = isGoal ? 'Active Goal' : isDec ? `Decision: ${item.context || item.id || 'unresolved'}` : 'Open loop';
            } else if (isDec && !desc.toLowerCase().startsWith('decision')) {
              desc = `Decision: ${desc}`;
            } else if (isGoal && !desc.toLowerCase().startsWith('goal')) {
              desc = `Goal: ${desc}`;
            }
            card.append(topRow, createSafeElement('div', desc, 'loop-card-title'));
            if (item.reasoning) {
              card.append(createSafeElement('div', `Reasoning: ${item.reasoning}`, 'loop-card-desc'));
            }
            loopsList.append(card);
          }
        }
      }

      // Empty state
      const isEmpty = Boolean(ref.is_empty) || (
        (metrics.events ?? 0) === 0 &&
        (metrics.sessions ?? 0) === 0 &&
        (metrics.tasks ?? 0) === 0 &&
        (metrics.tools ?? 0) === 0 &&
        (metrics.decisions ?? 0) === 0 &&
        allLoops.length === 0
      );
      if (emptyState) emptyState.hidden = !isEmpty;

      if (statusBar) {
        statusBar.textContent = `Reflection loaded for ${selectedDate}.`;
        setTimeout(() => {
          if (statusBar.textContent.includes('loaded')) statusBar.hidden = true;
        }, 2200);
      }
    } catch (err) {
      if (statusBar) statusBar.hidden = true;
      if (errorBox) {
        errorBox.hidden = false;
        if (errorMsg) errorMsg.textContent = err.message || 'Error loading reflection.';
      }
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Memory Candidates Review
  // ─────────────────────────────────────────────────────────────
  function renderCandidateCard(c) {
    const card = createSafeElement('div', '', 'candidate-card');
    card.id = `candidate-card-${c.id}`;
    card.dataset.candidateId = c.id;

    // Header: Proposal text + Badges
    const header = createSafeElement('div', '', 'candidate-card-header');
    const summary = formatCandidateSummary(c);
    const title = createSafeElement('h4', summary, 'candidate-card-title');

    const badges = createSafeElement('div', '', 'candidate-badges');
    const statusVal = c.status || 'pending';
    const statusBadge = createSafeElement('span', statusVal, `candidate-badge badge-${statusVal}`);
    badges.append(statusBadge);

    const privClass = c.privacy_class || (c.proposal_json && c.proposal_json.privacy_class) || 'private';
    const privacyBadge = createSafeElement('span', privClass, `candidate-badge badge-privacy ${privClass}`);
    badges.append(privacyBadge);

    header.append(title, badges);
    card.append(header);

    // Metadata
    const metaRow = createSafeElement('div', '', 'candidate-meta');
    const createdStr = c.created_at ? formatRelativeTime(c.created_at) : '';
    const srcType = c.source_event ? `${c.source_event.source_type} (${c.source_event.event_type})` : (c.source_type || 'Event');
    metaRow.append(createSafeElement('span', createdStr ? `${srcType} • ${createdStr}` : srcType));
    card.append(metaRow);

    // Evidence References
    const evList = c.evidence || c.evidence_refs || [];
    if (Array.isArray(evList) && evList.length > 0) {
      const evBox = createSafeElement('div', '', 'candidate-evidence-box');
      evBox.append(createSafeElement('span', 'Evidence: ', 'candidate-evidence-label'));
      for (const ev of evList) {
        const text = typeof ev === 'object' ? `${ev.extraction_method || 'fact'} (${((ev.confidence || 0) * 100).toFixed(0)}%)` : String(ev);
        evBox.append(createSafeElement('span', text, 'evidence-pill'));
      }
      card.append(evBox);
    }

    // Existing rejection note if rejected
    if (c.status === 'rejected' && (c.rejection_reason || c.reason)) {
      card.append(createSafeElement('div', `Rejection reason: ${c.rejection_reason || c.reason}`, 'candidate-rejection-note'));
    }

    // Action buttons (Admit / Defer / Reject) for pending & deferred
    if (c.status === 'pending' || c.status === 'deferred') {
      const actionsRow = createSafeElement('div', '', 'candidate-actions');
      const admitBtn = createSafeElement('button', 'Admit', 'review-action-btn admit');
      admitBtn.type = 'button';
      admitBtn.setAttribute('aria-label', `Admit candidate ${c.id}`);

      const deferBtn = createSafeElement('button', 'Defer', 'review-action-btn defer');
      deferBtn.type = 'button';
      deferBtn.setAttribute('aria-label', `Defer candidate ${c.id}`);

      const rejectBtn = createSafeElement('button', 'Reject', 'review-action-btn reject');
      rejectBtn.type = 'button';
      rejectBtn.setAttribute('aria-label', `Reject candidate ${c.id}`);

      actionsRow.append(admitBtn, deferBtn, rejectBtn);
      card.append(actionsRow);

      // Inline admit confirmation box
      const admitBox = createSafeElement('div', '', 'candidate-admit-box');
      admitBox.hidden = true;
      const admitPrompt = createSafeElement('div', 'Admitting this candidate will save it to persistent memory. Confirm admission?', 'candidate-admit-prompt');
      const admitActionsRow = createSafeElement('div', '', 'candidate-admit-actions');
      const confirmAdmitBtn = createSafeElement('button', 'Confirm Admission', 'review-action-btn admit');
      confirmAdmitBtn.type = 'button';
      const cancelAdmitBtn = createSafeElement('button', 'Cancel', 'review-action-btn secondary');
      cancelAdmitBtn.type = 'button';
      admitActionsRow.append(confirmAdmitBtn, cancelAdmitBtn);
      admitBox.append(admitPrompt, admitActionsRow);
      card.append(admitBox);

      // Inline reject form
      const rejectBox = createSafeElement('div', '', 'candidate-reject-box');
      rejectBox.hidden = true;
      const reasonInput = createSafeElement('input', '', 'candidate-reject-input');
      reasonInput.type = 'text';
      reasonInput.placeholder = 'Optional rejection reason…';
      reasonInput.maxLength = 500;

      const confirmBtn = createSafeElement('button', 'Confirm Rejection', 'review-action-btn reject');
      confirmBtn.type = 'button';
      const cancelBtn = createSafeElement('button', 'Cancel', 'review-action-btn secondary');
      cancelBtn.type = 'button';

      rejectBox.append(reasonInput, confirmBtn, cancelBtn);
      card.append(rejectBox);

      let pendingConfirmationId = null;

      // Admit Handlers
      admitBtn.onclick = async () => {
        admitBtn.disabled = true;
        deferBtn.disabled = true;
        rejectBtn.disabled = true;
        try {
          let resp = await fetch('/api/continuity/candidates/prepare_admit', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Lumina-Token': getConfig().token
            },
            body: JSON.stringify({
              candidate_id: c.id
            })
          });
          if (resp.status === 404) {
            resp = await fetch('/api/continuity', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-Lumina-Token': getConfig().token
              },
              body: JSON.stringify({
                action: 'prepare_admit',
                candidate_id: c.id
              })
            });
          }
          const resData = await resp.json();
          if (!resp.ok || !resData.confirmation_required || !resData.confirmation_id) {
            throw new Error(resData.error || `HTTP ${resp.status}: Failed to prepare candidate admission.`);
          }
          pendingConfirmationId = resData.confirmation_id;
          admitBox.hidden = false;
          actionsRow.hidden = true;
          confirmAdmitBtn.disabled = false;
          cancelAdmitBtn.disabled = false;
        } catch (err) {
          admitBtn.disabled = false;
          deferBtn.disabled = false;
          rejectBtn.disabled = false;
          notice(err.message || 'Error preparing admission.');
        }
      };

      cancelAdmitBtn.onclick = async () => {
        if (pendingConfirmationId) {
          const tok = pendingConfirmationId;
          pendingConfirmationId = null;
          try {
            await fetch('/api/confirm', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-Lumina-Token': getConfig().token
              },
              body: JSON.stringify({
                confirmation_id: tok,
                approve: false
              })
            });
          } catch (_) { }
        }
        admitBox.hidden = true;
        actionsRow.hidden = false;
        admitBtn.disabled = false;
        deferBtn.disabled = false;
        rejectBtn.disabled = false;
      };

      confirmAdmitBtn.onclick = async () => {
        if (!pendingConfirmationId) {
          notice('No active admission authorization found.');
          admitBox.hidden = true;
          actionsRow.hidden = false;
          admitBtn.disabled = false;
          deferBtn.disabled = false;
          rejectBtn.disabled = false;
          return;
        }
        confirmAdmitBtn.disabled = true;
        cancelAdmitBtn.disabled = true;
        const tok = pendingConfirmationId;
        try {
          let resp = await fetch('/api/confirm', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Lumina-Token': getConfig().token
            },
            body: JSON.stringify({
              confirmation_id: tok,
              approve: true
            })
          });
          const resData = await resp.json();
          if (!resp.ok || !resData.ok) {
            throw new Error(resData.error || `HTTP ${resp.status}: Admission confirmation failed.`);
          }
          pendingConfirmationId = null;
          notice('Candidate admitted to persistent memory.');
          statusBadge.textContent = 'admitted';
          statusBadge.className = 'candidate-badge badge-admitted';
          actionsRow.remove();
          admitBox.remove();
          if (rejectBox && rejectBox.remove) {
            rejectBox.remove();
          }
          if (candidateFilter === 'pending') {
            loadCandidates('pending');
          }
        } catch (err) {
          confirmAdmitBtn.disabled = false;
          cancelAdmitBtn.disabled = false;
          notice(err.message || 'Error admitting candidate.');
        }
      };

      // Reject Handlers
      rejectBtn.onclick = () => {
        rejectBox.hidden = false;
        actionsRow.hidden = true;
        if (admitBox) admitBox.hidden = true;
        reasonInput.focus();
      };

      cancelBtn.onclick = () => {
        rejectBox.hidden = true;
        actionsRow.hidden = false;
      };

      confirmBtn.onclick = async () => {
        confirmBtn.disabled = true;
        cancelBtn.disabled = true;
        const reasonVal = reasonInput.value.trim();
        try {
          let resp = await fetch('/api/continuity/candidates/reject', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Lumina-Token': getConfig().token
            },
            body: JSON.stringify({
              candidate_id: c.id,
              reason: reasonVal
            })
          });
          if (resp.status === 404) {
            resp = await fetch('/api/continuity', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-Lumina-Token': getConfig().token
              },
              body: JSON.stringify({
                action: 'reject_candidate',
                candidate_id: c.id,
                reason: reasonVal
              })
            });
          }
          const resData = await resp.json();
          if (!resp.ok || !resData.ok) {
            throw new Error(resData.error || `HTTP ${resp.status}: Failed to reject candidate.`);
          }
          notice('Candidate rejected.');
          statusBadge.textContent = 'rejected';
          statusBadge.className = 'candidate-badge badge-rejected';
          actionsRow.remove();
          rejectBox.remove();
          if (admitBox && admitBox.remove) {
            admitBox.remove();
          }
          if (reasonVal) {
            card.append(createSafeElement('div', `Rejection reason: ${reasonVal}`, 'candidate-rejection-note'));
          }
          if (candidateFilter === 'pending') {
            loadCandidates('pending');
          }
        } catch (err) {
          confirmBtn.disabled = false;
          cancelBtn.disabled = false;
          notice(err.message || 'Error rejecting candidate.');
        }
      };

      // Defer Handlers
      deferBtn.onclick = async () => {
        admitBtn.disabled = true;
        deferBtn.disabled = true;
        rejectBtn.disabled = true;
        try {
          let resp = await fetch('/api/continuity/candidates/defer', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Lumina-Token': getConfig().token
            },
            body: JSON.stringify({
              candidate_id: c.id
            })
          });
          if (resp.status === 404) {
            resp = await fetch('/api/continuity', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-Lumina-Token': getConfig().token
              },
              body: JSON.stringify({
                action: 'defer_candidate',
                candidate_id: c.id
              })
            });
          }
          const resData = await resp.json();
          if (!resp.ok || !resData.ok) {
            throw new Error(resData.error || `HTTP ${resp.status}: Failed to defer candidate.`);
          }
          notice('Candidate deferred for later review.');
          statusBadge.textContent = 'deferred';
          statusBadge.className = 'candidate-badge badge-deferred';
          admitBtn.disabled = false;
          deferBtn.disabled = false;
          rejectBtn.disabled = false;
          if (candidateFilter === 'pending') {
            loadCandidates('pending');
          }
        } catch (err) {
          admitBtn.disabled = false;
          deferBtn.disabled = false;
          rejectBtn.disabled = false;
          notice(err.message || 'Error deferring candidate.');
        }
      };
    }

    return card;
  }

  async function loadCandidates(status = candidateFilter) {
    candidateFilter = status;
    const listEl = $('review-candidates-list');
    const emptyEl = $('review-candidates-empty');
    const statusBar = $('review-status-bar');

    for (const filterBtn of document.querySelectorAll('.candidate-filters .filter-chip')) {
      filterBtn.classList.toggle('active', filterBtn.dataset.filter === status);
    }

    if (statusBar && statusBar.hidden) {
      statusBar.textContent = `Loading candidates (${status})…`;
      statusBar.hidden = false;
    }

    try {
      let res = await fetch(`/api/continuity/candidates?status=${encodeURIComponent(status)}&limit=50`, {
        headers: { 'X-Lumina-Token': getConfig().token }
      });
      if (res.status === 404) {
        res = await fetch(`/api/continuity?action=candidates&status=${encodeURIComponent(status)}&limit=50`, {
          headers: { 'X-Lumina-Token': getConfig().token }
        });
      }
      const data = await res.json();
      if (!res.ok || !data.ok) {
        let msg = data.error;
        if (!msg) {
          msg = `HTTP ${res.status}: Failed to load candidates.`;
        } else if (msg === 'Invalid request.' && res.status === 400) {
          msg = 'Candidate review is not active on this server instance (server restart required to load Gate 3 routes).';
        }
        throw new Error(msg);
      }

      const candidates = data.candidates || [];
      if (listEl) {
        listEl.replaceChildren();
        if (candidates.length === 0) {
          if (emptyEl) emptyEl.hidden = false;
        } else {
          if (emptyEl) emptyEl.hidden = true;
          for (const c of candidates) {
            listEl.append(renderCandidateCard(c));
          }
        }
      }
      if (statusBar && statusBar.textContent.includes('Loading candidates')) {
        statusBar.hidden = true;
      }
    } catch (err) {
      notice(err.message || 'Error loading memory candidates.');
      if (statusBar) statusBar.hidden = true;
    }
  }

  function loadDailyReview() {
    loadDailyReflection(selectedDate);
    loadCandidates(candidateFilter);
  }

  // Toolbar & filter listeners
  const prevBtn = $('review-prev-day');
  if (prevBtn) prevBtn.onclick = () => loadDailyReflection(shiftDateString(selectedDate, -1));

  const nextBtn = $('review-next-day');
  if (nextBtn) nextBtn.onclick = () => loadDailyReflection(shiftDateString(selectedDate, +1));

  const todayBtn = $('review-today-btn');
  if (todayBtn) todayBtn.onclick = () => loadDailyReflection(formatLocalDate());

  const datePicker = $('review-date-picker');
  if (datePicker) {
    datePicker.value = selectedDate;
    datePicker.onchange = e => {
      if (e.target.value) loadDailyReflection(e.target.value);
    };
  }

  const refreshReviewBtn = $('review-refresh-btn');
  if (refreshReviewBtn) refreshReviewBtn.onclick = () => loadDailyReview();

  const retryBtn = $('review-retry-btn');
  if (retryBtn) retryBtn.onclick = () => loadDailyReflection(selectedDate);

  const filterPending = $('candidate-filter-pending');
  if (filterPending) filterPending.onclick = () => loadCandidates('pending');

  const filterDeferred = $('candidate-filter-deferred');
  if (filterDeferred) filterDeferred.onclick = () => loadCandidates('deferred');

  const filterAll = $('candidate-filter-all');
  if (filterAll) filterAll.onclick = () => loadCandidates('all');

  // ─────────────────────────────────────────────────────────────
  // Preserved Search & Evidence Logic
  // ─────────────────────────────────────────────────────────────
  let searchType = 'all';
  let searchStatus = 'all';
  let searchSort = 'newest';
  let searchPage = 1;
  let searchLimit = 10;
  let searchTotalPages = 1;

  async function searchRead(action, extra = {}) {
    const response = await fetch('/api/continuity?' + new URLSearchParams({ action, ...extra }), {
      headers: { 'X-Lumina-Token': getConfig().token }
    });
    const result = await response.json();
    if (!response.ok || result.ok === false) throw Error(result.error || 'Memory is unavailable.');
    return result;
  }

  function searchButton(label, run) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'search-page-btn';
    b.textContent = label;
    b.onclick = (e) => {
      e.stopPropagation();
      run().catch(err => notice(err.message));
    };
    return b;
  }

  function searchDetail(result) {
    const drawer = $('continuity-detail');
    const body = $('search-detail-body');
    const titleEl = $('search-detail-title');
    if (!drawer || !body) return;

    drawer.hidden = false;
    body.replaceChildren();

    const r = result.record || {};
    const kind = result.kind || 'record';
    const titleText = r.object_value || r.description || r.chosen_option || r.title || r.pattern || r.prediction || r.name || kind;
    if (titleEl) {
      titleEl.textContent = `[${kind.toUpperCase()}] ${titleText.length > 60 ? titleText.slice(0, 60) + '…' : titleText}`;
    }

    // Step 1: Record attributes
    const metricsCard = document.createElement('div');
    metricsCard.className = 'evidence-chain-step';
    const s1Num = createSafeElement('div', '1', 'evidence-step-num');
    const s1Content = createSafeElement('div', '', 'evidence-step-content');
    s1Content.append(createSafeElement('div', 'Record Attributes', 'evidence-step-title'));
    const metricsDl = document.createElement('dl');
    for (const [lbl, val] of Object.entries({
      'Record ID': r.id || result.record_id,
      Kind: kind,
      Predicate: r.predicate || null,
      Status: r.status || 'active',
      Privacy: r.privacy_class || 'private',
      Confidence: result.confidence != null ? Number(result.confidence).toFixed(2) : (r.confidence != null ? Number(r.confidence).toFixed(2) : null),
      Freshness: result.freshness != null ? Number(result.freshness).toFixed(2) : null,
      'Created At': r.created_at ? new Date(r.created_at).toLocaleString() : null,
      'Updated At': r.updated_at ? new Date(r.updated_at).toLocaleString() : null
    })) {
      if (val != null) {
        metricsDl.append(createSafeElement('dt', lbl), createSafeElement('dd', String(val)));
      }
    }
    s1Content.append(metricsDl);
    metricsCard.append(s1Num, s1Content);
    body.append(metricsCard);

    // Step 2 & 3: Evidence Chain & Source Events
    const chainCard = document.createElement('div');
    chainCard.className = 'evidence-chain-step';
    const s2Num = createSafeElement('div', '2', 'evidence-step-num');
    const s2Content = createSafeElement('div', '', 'evidence-step-content');
    s2Content.append(createSafeElement('div', 'Evidence Rows & Underlying Events', 'evidence-step-title'));

    const evChain = result.evidence_chain || result.evidence || [];
    if (!evChain.length) {
      s2Content.append(createSafeElement('p', 'No direct evidence records linked.', 'evidence-step-detail'));
    } else {
      const chainList = document.createElement('div');
      chainList.className = 'evidence-chain-container';
      for (const ev of evChain) {
        const itemDiv = document.createElement('div');
        itemDiv.style.borderLeft = '2px solid #00e5ff';
        itemDiv.style.paddingLeft = '8px';
        itemDiv.style.margin = '4px 0';

        const evMeta = createSafeElement('div', `Source: ${ev.source_type || 'system'} · Observed: ${ev.observed_at ? new Date(ev.observed_at).toLocaleString() : 'recorded'} · Confidence: ${ev.confidence != null ? Number(ev.confidence).toFixed(2) : '1.0'}`, 'evidence-step-detail');
        itemDiv.append(evMeta);

        if (ev.event) {
          const evType = ev.event.event_type || 'event';
          const evTime = ev.event.timestamp ? new Date(ev.event.timestamp).toLocaleString() : '';
          const p = ev.event.payload || ev.event.payload_json;
          let textPreview = '';
          if (p && typeof p === 'object') {
            textPreview = p.text || p.quote || p.content || p.description || p.object_value || JSON.stringify(p);
          } else if (typeof p === 'string') {
            textPreview = p;
          }
          const eventDiv = createSafeElement('div', `Event: ${evType} (${evTime})`, 'evidence-step-detail');
          eventDiv.style.color = '#e2e8f0';
          itemDiv.append(eventDiv);
          if (textPreview) {
            const quoteEl = createSafeElement('blockquote', textPreview.length > 300 ? textPreview.slice(0, 300) + '…' : textPreview);
            quoteEl.style.margin = '4px 0';
            quoteEl.style.fontSize = '11px';
            quoteEl.style.color = '#a0aec0';
            itemDiv.append(quoteEl);
          }
        }
        if (ev.session) {
          const sessDiv = createSafeElement('div', `Session: ${ev.session.title || ev.session.id}`, 'evidence-step-detail');
          sessDiv.style.color = '#2979ff';
          itemDiv.append(sessDiv);
        }
        chainList.append(itemDiv);
      }
      s2Content.append(chainList);
    }
    chainCard.append(s2Num, s2Content);
    body.append(chainCard);

    // Step 4: Related Context (Summaries, Sessions, Belief History, Contradictions)
    const ctxCard = document.createElement('div');
    ctxCard.className = 'evidence-chain-step';
    const s4Num = createSafeElement('div', '3', 'evidence-step-num');
    const s4Content = createSafeElement('div', '', 'evidence-step-content');
    s4Content.append(createSafeElement('div', 'Related Summaries & Context', 'evidence-step-title'));

    if (result.related_summaries?.length) {
      const sumList = createSafeElement('div', 'Cited in summaries:', 'evidence-step-detail');
      for (const s of result.related_summaries) {
        sumList.append(createSafeElement('p', `• ${s.title || s.id} (${s.level || 'summary'})`));
      }
      s4Content.append(sumList);
    }
    if (result.related_sessions?.length) {
      const sessList = createSafeElement('div', 'Associated sessions:', 'evidence-step-detail');
      for (const sess of result.related_sessions) {
        sessList.append(createSafeElement('p', `• ${sess.title || sess.id} (${sess.started_at ? sess.started_at.slice(0, 10) : ''})`));
      }
      s4Content.append(sessList);
    }
    if (result.history?.length) {
      const histDiv = createSafeElement('div', 'Belief history:', 'evidence-step-detail');
      for (const h of result.history) {
        histDiv.append(createSafeElement('p', `• ${h.object_value} [${h.status}] · ${new Date(h.valid_from).toLocaleDateString()}`));
      }
      s4Content.append(histDiv);
    }
    if (result.contradictions?.length) {
      s4Content.append(createSafeElement('p', `⚠ ${result.contradictions.length} conflicting relationship(s) recorded. Review evidence carefully.`, 'error-badge'));
    }
    if (!result.related_summaries?.length && !result.related_sessions?.length && !result.history?.length && !result.contradictions?.length) {
      s4Content.append(createSafeElement('p', 'No additional related summaries or conflicting beliefs recorded.', 'evidence-step-detail'));
    }
    ctxCard.append(s4Num, s4Content);
    body.append(ctxCard);

    // Raw JSON details
    const raw = document.createElement('details');
    raw.style.marginTop = '6px';
    raw.append(createSafeElement('summary', 'Inspect complete evidence and relationships JSON'), createSafeElement('pre', JSON.stringify(result, null, 2)));
    body.append(raw);
  }

  function clearSearchSelection() {
    searchSelected = null;
    const detailEl = $('continuity-detail');
    if (detailEl) detailEl.hidden = true;
    for (const id of ['continuity-edit', 'continuity-resolve', 'continuity-remove']) {
      const el = $(id);
      if (el) el.hidden = true;
    }
  }

  async function searchExplain(id) {
    clearSearchSelection();
    const result = await searchRead('explain', { id });
    searchSelected = result.record;
    searchDetail(result);
    const valInput = $('continuity-value');
    if (valInput) valInput.value = result.record?.object_value || '';
    const editForm = $('continuity-edit');
    if (editForm) editForm.hidden = result.kind !== 'fact';
    const resolveBtn = $('continuity-resolve');
    if (resolveBtn) {
      resolveBtn.hidden = !['goal', 'open_loop', 'commitment'].includes(result.kind);
      resolveBtn.dataset.kind = result.kind;
    }
    const removeDiv = $('continuity-remove');
    if (removeDiv) {
      removeDiv.hidden = !['fact', 'decision', 'goal', 'open_loop', 'commitment', 'episode', 'prediction', 'behavior_pattern'].includes(result.kind);
    }
  }

  async function searchRefresh() {
    if (searchBusy) return;
    searchBusy = true;
    try {
      const queryVal = $('continuity-query') ? $('continuity-query').value.trim() : '';
      const [status, state, pagedRes] = await Promise.all([
        searchRead('status'),
        searchRead('continuation'),
        searchRead('search', {
          query: queryVal,
          type: searchType,
          status: searchStatus,
          sort: searchSort,
          page: searchPage,
          limit: searchLimit
        })
      ]);

      const statusEl = $('continuity-status');
      if (statusEl) {
        const goalCount = status.counts?.goal ?? 0;
        const goalPart = goalCount > 0 ? `${goalCount} goals · ` : '';
        statusEl.textContent = `Local memory · ${status.status} · ${status.counts?.fact ?? 0} facts · ${goalPart}${status.counts?.event ?? 0} events`;
      }
      const stateEl = $('continuity-state');
      if (stateEl) {
        stateEl.textContent = state.active_task?.description ||
          state.open_loops?.[0]?.description ||
          (state.goals?.length ? 'Goal: ' + state.goals[0].description : null) ||
          'No recorded unfinished work in this workspace.';
      }

      // Update count label
      const countEl = $('search-results-count');
      if (countEl) {
        if (pagedRes.total === 0) {
          countEl.textContent = 'No matching records found';
        } else {
          countEl.textContent = `Showing ${pagedRes.start_index}–${pagedRes.end_index} of ${pagedRes.total} records`;
        }
      }

      // Update pagination controls
      searchTotalPages = pagedRes.total_pages || 1;
      searchPage = pagedRes.page || 1;
      const pageInfo = $('search-page-info');
      if (pageInfo) {
        pageInfo.textContent = `Page ${searchPage} of ${Math.max(1, searchTotalPages)}`;
      }
      const prevBtn = $('search-prev-page');
      if (prevBtn) prevBtn.disabled = !pagedRes.has_prev;
      const nextBtn = $('search-next-page');
      if (nextBtn) nextBtn.disabled = !pagedRes.has_next;

      // Render cards
      const list = $('continuity-results');
      if (list) {
        list.replaceChildren();
        if (!pagedRes.items?.length) {
          list.append(createSafeElement('div', 'No continuity records match your search and filter criteria.', 'review-empty-state'));
        } else {
          for (const item of pagedRes.items) {
            const card = document.createElement('div');
            card.className = `search-card type-${item.type || 'fact'}`;
            card.tabIndex = 0;
            card.role = 'listitem';

            const header = document.createElement('div');
            header.className = 'search-card-header';
            header.append(
              createSafeElement('span', item.type || 'fact', 'search-card-badge'),
              createSafeElement('span', item.title || item.id, 'search-card-title'),
              createSafeElement('span', item.status || 'active', 'search-card-status')
            );

            const preview = createSafeElement('div', item.preview || '(No preview content)', 'search-card-preview');

            const footer = document.createElement('div');
            footer.className = 'search-card-footer';
            const metaInfo = item.created_at ? new Date(item.created_at).toLocaleDateString() : '';
            const evCountText = item.evidence_count != null ? `${item.evidence_count} evidence` : '';
            footer.append(
              createSafeElement('span', metaInfo),
              createSafeElement('span', evCountText, 'search-card-ev-count')
            );

            card.append(header, preview, footer);
            card.onclick = () => searchExplain(item.id);
            card.onkeydown = (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                searchExplain(item.id);
              }
            };
            list.append(card);
          }
        }
      }

      const noteEl = $('continuity-note');
      if (noteEl) noteEl.textContent = pagedRes.truncated ? 'Results were shortened to fit the context limit.' : '';
    } catch (e) {
      const statusEl = $('continuity-status');
      if (statusEl) statusEl.textContent = e.message;
    } finally {
      searchBusy = false;
    }
  }

  async function searchMutate(tool, arguments_) {
    const response = await fetch('/api/continuity', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Lumina-Token': getConfig().token },
      body: JSON.stringify({ tool, arguments: arguments_ })
    });
    const result = await response.json();
    if (result.confirmation_required) {
      panel.close();
      notice('Review the exact memory change in the confirmation dialog.');
    } else if (!response.ok || !result.ok) {
      throw Error(result.error || 'The change was not applied.');
    }
  }

  // Filter chips listeners
  const typeChips = $('search-type-chips');
  if (typeChips) {
    typeChips.onclick = (e) => {
      const chip = e.target.closest('.search-chip');
      if (!chip) return;
      typeChips.querySelectorAll('.search-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      searchType = chip.dataset.type || 'all';
      searchPage = 1;
      searchRefresh();
    };
  }

  const statusChips = $('search-status-chips');
  if (statusChips) {
    statusChips.onclick = (e) => {
      const chip = e.target.closest('.search-chip');
      if (!chip) return;
      statusChips.querySelectorAll('.search-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      searchStatus = chip.dataset.status || 'all';
      searchPage = 1;
      searchRefresh();
    };
  }

  const clearFiltersBtn = $('search-clear-filters');
  if (clearFiltersBtn) {
    clearFiltersBtn.onclick = () => {
      if (typeChips) {
        typeChips.querySelectorAll('.search-chip').forEach(c => c.classList.toggle('active', c.dataset.type === 'all'));
      }
      if (statusChips) {
        statusChips.querySelectorAll('.search-chip').forEach(c => c.classList.toggle('active', c.dataset.status === 'all'));
      }
      searchType = 'all';
      searchStatus = 'all';
      const qInput = $('continuity-query');
      if (qInput) {
        qInput.value = '';
        const clr = $('continuity-clear-query');
        if (clr) clr.hidden = true;
      }
      searchPage = 1;
      searchRefresh();
    };
  }

  const queryInput = $('continuity-query');
  const clearQueryBtn = $('continuity-clear-query');
  if (queryInput && clearQueryBtn) {
    queryInput.oninput = () => {
      clearQueryBtn.hidden = !queryInput.value;
    };
    clearQueryBtn.onclick = () => {
      queryInput.value = '';
      clearQueryBtn.hidden = true;
      searchPage = 1;
      searchRefresh();
    };
  }

  const sortSelect = $('search-sort-select');
  if (sortSelect) {
    sortSelect.onchange = (e) => {
      searchSort = e.target.value;
      searchRefresh();
    };
  }

  const limitSelect = $('search-limit-select');
  if (limitSelect) {
    limitSelect.onchange = (e) => {
      searchLimit = parseInt(e.target.value, 10) || 10;
      searchPage = 1;
      searchRefresh();
    };
  }

  const prevPageBtn = $('search-prev-page');
  if (prevPageBtn) {
    prevPageBtn.onclick = () => {
      if (searchPage > 1) {
        searchPage--;
        searchRefresh();
      }
    };
  }

  const nextPageBtn = $('search-next-page');
  if (nextPageBtn) {
    nextPageBtn.onclick = () => {
      if (searchPage < searchTotalPages) {
        searchPage++;
        searchRefresh();
      }
    };
  }

  const closeDetailBtn = $('search-detail-close');
  if (closeDetailBtn) {
    closeDetailBtn.onclick = () => {
      clearSearchSelection();
    };
  }

  // Search view event listeners
  const contSearchForm = $('continuity-search');
  if (contSearchForm) contSearchForm.onsubmit = e => { e.preventDefault(); searchRefresh(); };

  const contRefreshBtn = $('continuity-refresh');
  if (contRefreshBtn) contRefreshBtn.onclick = searchRefresh;

  const contTimelineBtn = $('continuity-timeline');
  if (contTimelineBtn) contTimelineBtn.onclick = () => searchRead('timeline').then(r => {
    clearSearchSelection();
    searchDetail(r);
    const raw = $('continuity-detail')?.querySelector('details');
    if (raw) raw.open = true;
  }).catch(e => notice(e.message));

  const contEditForm = $('continuity-edit');
  if (contEditForm) contEditForm.onsubmit = e => {
    e.preventDefault();
    if (searchSelected) {
      const val = $('continuity-value')?.value || '';
      searchMutate('memory_correct', { id: searchSelected.id, new_value: val }).catch(err => notice(err.message));
    }
  };

  const contInvalBtn = $('continuity-invalidate');
  if (contInvalBtn) contInvalBtn.onclick = () => searchSelected && searchMutate('memory_forget', { id: searchSelected.id, mode: 'invalidate' }).catch(e => notice(e.message));

  const contDeleteBtn = $('continuity-delete');
  if (contDeleteBtn) contDeleteBtn.onclick = () => searchSelected && searchMutate('memory_forget', { id: searchSelected.id, mode: 'delete' }).catch(e => notice(e.message));

  const contResolveBtn = $('continuity-resolve');
  if (contResolveBtn) contResolveBtn.onclick = () => {
    if (!searchSelected) return;
    const kind = contResolveBtn.dataset.kind;
    const statusVal = kind === 'goal' ? 'completed' : kind === 'commitment' ? 'fulfilled' : 'resolved';
    searchMutate('memory_resolve', { id: searchSelected.id, status: statusVal }).catch(e => notice(e.message));
  };

  // ─────────────────────────────────────────────────────────────
  // Dialog Open & Global Event Subscriptions
  // ─────────────────────────────────────────────────────────────
  const openBtn = $('continuity-open');
  if (openBtn) {
    openBtn.onclick = () => {
      panel.showModal();
      if (currentTab === 'review') {
        loadDailyReview();
      } else {
        searchRefresh();
      }
    };
  }

  const closeBtn = $('continuity-close');
  if (closeBtn) closeBtn.onclick = () => panel.close();

  window.addEventListener('lumina-event', e => {
    if (e.detail?.type === 'continuity_open') {
      if (!panel.open) panel.showModal();
      if (currentTab === 'review') {
        loadDailyReview();
      } else {
        searchRefresh();
      }
    }
    if (e.detail?.type === 'continuity_inspect') {
      if (!panel.open) panel.showModal();
      switchTab('search');
      searchExplain(e.detail.id).catch(err => notice(err.message));
    }
    if (e.detail?.type === 'continuity_result' && panel.open) {
      if (currentTab === 'review') {
        loadDailyReview();
      } else {
        searchRefresh();
      }
    }
  });
}
