// Lumina Earth P0.1 — Pre-flight environment check, error handling & watchdog.
// Loaded as a standard deferred script so it runs under both HTTP and file:// protocols.
(function () {
  'use strict';

  function init() {
    var statusEl = document.getElementById('earth-status');
    var stageEl = document.getElementById('earth-stage');
    if (!statusEl) return;

    function showError(htmlMessage) {
      statusEl.innerHTML = htmlMessage;
      statusEl.dataset.state = 'error';
      statusEl.style.display = 'block';
      statusEl.hidden = false;
      if (stageEl) stageEl.dataset.earthState = 'error';
    }

    // 1. Detect file:// protocol immediately
    if (window.location.protocol === 'file:') {
      showError(
        '<strong>Cannot run directly from a file:// URL</strong><br><br>' +
        'Browsers block local 3D ES modules on <code>file://</code> origins due to security restrictions.<br>' +
        'Please open the prototype through Lumina\'s local server:<br><br>' +
        '<a href="http://127.0.0.1:8764/assets/earth/earth-prototype.html" style="color:#5b9dff;text-decoration:underline;font-weight:600">' +
        'http://127.0.0.1:8764/assets/earth/earth-prototype.html</a><br><br>' +
        '<small style="color:#8a92a0">Ensure Lumina is running (e.g. <code>.\\.venv\\Scripts\\python.exe -m lumina.desktop_backend</code>).</small>'
      );
      return;
    }

    // 2. Global error listener to intercept module script load failures or syntax errors
    window.addEventListener('error', function (event) {
      if (stageEl && stageEl.dataset.earthState === 'ready') return;
      var msg = event.message || (event.target && event.target.src ? 'Failed to load script: ' + event.target.src : 'Script execution error');
      showError(
        '<strong>Earth prototype initialization failed</strong><br><br>' +
        '<span style="color:#ff8a8a">' + msg + '</span><br><br>' +
        '<small style="color:#8a92a0">Check the developer console (F12) for detailed logs.</small>'
      );
    }, true);

    // 3. Unhandled promise rejection listener
    window.addEventListener('unhandledrejection', function (event) {
      if (stageEl && stageEl.dataset.earthState === 'ready') return;
      var reason = event.reason ? (event.reason.message || String(event.reason)) : 'Promise rejected';
      showError(
        '<strong>Asynchronous initialization error</strong><br><br>' +
        '<span style="color:#ff8a8a">' + reason + '</span>'
      );
    });

    // 4. Watchdog timer: If still stuck on initial state after 4 seconds
    setTimeout(function () {
      if (!stageEl) return;
      var currentState = stageEl.dataset.earthState;
      if (!currentState || currentState === 'idle') {
        showError(
          '<strong>Initialization timed out</strong><br><br>' +
          'The Earth 3D module did not start within 4 seconds.<br>' +
          'Please verify that Lumina is running on <a href="http://127.0.0.1:8764" style="color:#5b9dff">http://127.0.0.1:8764</a> and reload.'
        );
      }
    }, 4000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
