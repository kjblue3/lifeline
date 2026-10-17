'use strict';

(() => {
  const notice = document.getElementById('pwa-status');
  if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
  window.addEventListener('load', async () => {
    try {
      await navigator.serviceWorker.register('/assets/sw.js', { scope: '/assets/', updateViaCache: 'none' });
      // ready only resolves for a controlled page within the worker's scope.
      if (location.pathname.startsWith('/assets/')) {
        await navigator.serviceWorker.ready;
        if (notice) notice.textContent = 'App interface saved for offline access. AI is not installed on this phone; chat requires a connected local backend.';
      }
    } catch {
      if (notice) notice.textContent = 'Offline app setup could not finish. Reopen LifeLine online to retry. AI is not installed on this phone.';
    }
  });
})();
