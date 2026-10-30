/**
 * web/earth-workspace.js
 * 
 * Lumina Earth — In-Place Workspace Integration Controller (P1.3).
 * Integrates 3D Earth into Lumina's single-page shell navigation rail.
 * Manages view switching, pause-on-hide rendering lifecycle, and resource safety.
 */

import { initEarth } from './earth/earth-prototype.js';

export function setupEarthWorkspace({ getConfig = () => ({}), notice = () => {} } = {}) {
  const earthNavBtn = document.getElementById('earth-open');
  const earthWorkspace = document.getElementById('earth-workspace');
  const presenceSection = document.querySelector('.presence');
  const dashboardBtn = document.querySelector('[data-focus="workspace"]');
  const chatBtn = document.querySelector('[data-focus="message"]');
  const host = document.getElementById('earth-stage');
  const label = document.getElementById('earth-status');

  let view = null;
  let isEarthActive = false;
  let isInitialized = false;

  function showEarth() {
    if (isEarthActive) return;
    isEarthActive = true;

    // 1. Hide presence/chat and reveal Earth workspace
    if (presenceSection) presenceSection.hidden = true;
    if (earthWorkspace) earthWorkspace.hidden = false;

    // 2. Update navigation active state
    document.querySelectorAll('.nav-rail [aria-current]').forEach(item => item.removeAttribute('aria-current'));
    earthNavBtn?.setAttribute('aria-current', 'page');

    // 3. Initialize or resume rendering lifecycle
    if (!isInitialized) {
      isInitialized = true;
      try {
        view = initEarth(host, {
          getHeaders: () => {
            const token = getConfig?.()?.token || window.__luminaConfig?.token;
            return token ? { 'Content-Type': 'application/json', 'X-Lumina-Token': token } : { 'Content-Type': 'application/json' };
          },
          notice,
          onStatus: (state, msg) => {
            if (state === 'error' && label) {
              label.textContent = msg;
              label.dataset.state = 'error';
              label.hidden = false;
            }
          },
          onError: (err) => {
            notice(`Earth initialization error: ${err.message || err}`);
          }
        });
      } catch (err) {
        notice(`Failed to initialize Earth: ${err.message}`);
      }
    } else if (view && typeof view.resume === 'function') {
      view.resume();
    }

    // 4. Accessibility: set focus to search input if available
    const searchInput = document.getElementById('earth-search-input');
    searchInput?.focus({ preventScroll: true });
  }

  function hideEarth() {
    if (!isEarthActive) return;
    isEarthActive = false;

    // 1. Pause Earth renderer to prevent idle GPU work
    if (view && typeof view.pause === 'function') {
      view.pause();
    }

    // 2. Hide Earth workspace and restore presence
    if (earthWorkspace) earthWorkspace.hidden = true;
    if (presenceSection) presenceSection.hidden = false;

    // 3. Remove navigation rail active state
    earthNavBtn?.removeAttribute('aria-current');
  }

  // Navigation rail interactions
  earthNavBtn?.addEventListener('click', (e) => {
    e.preventDefault();
    showEarth();
  });

  // When switching back to Dashboard or Chat
  dashboardBtn?.addEventListener('click', () => {
    hideEarth();
  });

  chatBtn?.addEventListener('click', () => {
    hideEarth();
  });

  // View-switching buttons in the nav rail (Dashboard, Chat, Knowledge search) hide Earth
  document.querySelectorAll('.nav-rail button[data-focus]').forEach(btn => {
    btn.addEventListener('click', () => {
      if (isEarthActive) {
        hideEarth();
      }
    });
  });

  // Modal dialog management: Pause Earth while any modal dialog is open, resume on close
  const allDialogs = document.querySelectorAll('dialog');
  allDialogs.forEach(dialog => {
    dialog.addEventListener('close', () => {
      if (isEarthActive && !dialog.open) {
        const anyModalOpen = Array.from(allDialogs).some(d => d.open);
        if (!anyModalOpen && view && typeof view.resume === 'function') {
          view.resume();
        }
      }
    });
  });

  const dialogObserver = typeof MutationObserver !== 'undefined' ? new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.type === 'attributes' && m.attributeName === 'open') {
        const dialog = m.target;
        if (dialog.open && isEarthActive) {
          view?.pause?.();
        }
      }
    }
  }) : null;

  if (dialogObserver) {
    allDialogs.forEach(dialog => {
      dialogObserver.observe(dialog, { attributes: true, attributeFilter: ['open'] });
    });
  }

  // Document visibility management (e.g. tab switching or window minimization)
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      view?.pause?.();
    } else if (isEarthActive) {
      view?.resume?.();
    }
  });

  // Window resize management: refresh WebGL viewport when visible
  window.addEventListener('resize', () => {
    if (isEarthActive && view && typeof view.resume === 'function') {
      view.resume();
    }
  });

  // Clean teardown on page unload
  window.addEventListener('pagehide', () => {
    if (view && typeof view.dispose === 'function') {
      view.dispose();
      view = null;
    }
  }, { once: true });

  const controller = {
    showEarth,
    hideEarth,
    isEarthActive: () => isEarthActive,
    isPaused: () => !view || (typeof view.isPaused === 'function' ? view.isPaused() : false),
    isInitialized: () => isInitialized,
    getView: () => view,
    dispose: () => {
      hideEarth();
      view?.dispose?.();
      view = null;
      isInitialized = false;
    }
  };

  window.__luminaEarthWorkspace = controller;
  return controller;
}
