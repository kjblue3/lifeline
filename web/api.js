'use strict';

window.LifeLineAPI = (() => {
  // Future integrations are intentionally unavailable. No speculative routes are called.
  const config = Object.freeze({
    endpoints: Object.freeze({ status: '/api/status', ask: '/api/ask', medicalSearch: null, tripPrepare: null, tripStatus: null }),
    capabilities: Object.freeze({ medicalSearch: false, tripPrepare: false, tripStatus: false })
  });
  async function request(path, options = {}, timeout = 30000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(path, { ...options, signal: controller.signal, cache: 'no-store', credentials: 'same-origin' });
      const result = await response.json();
      if (!response.ok || result?.ok !== true) {
        const error = new Error(typeof result?.error?.message === 'string' ? result.error.message : 'The service could not complete the request.');
        error.status = response.status;
        throw error;
      }
      if (!result.data || typeof result.data !== 'object') throw new Error('The service returned an unreadable response.');
      return result.data;
    } finally {
      clearTimeout(timer);
    }
  }
  return Object.freeze({
    config,
    status: () => request(config.endpoints.status, {}, 8000),
    // The backend is stateless: never transmit the visible history or demo profile.
    ask: (question) => request(config.endpoints.ask, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question })
    })
  });
})();

// A same-origin API response proves backend reachability, not internet access.
// No confirmed external connectivity field exists in the current API.
window.LifeLineConnectivity = Object.freeze({
  current: () => ({ state: 'unknown', label: 'Internet Connection Unknown' })
});

window.LifeLineStatus = (() => {
  let pending = null;
  return Object.freeze({
    read() {
      if (!pending) pending = window.LifeLineAPI.status().finally(() => { pending = null; });
      return pending;
    },
    subscribe(onStatus, onError) {
      let stopped = false;
      let timer;
      async function poll() {
        try {
          const data = await window.LifeLineStatus.read();
          if (!stopped) onStatus(data);
        } catch (error) {
          if (!stopped) onError(error);
        } finally {
          if (!stopped) timer = setTimeout(poll, 4000);
        }
      }
      void poll();
      return () => { stopped = true; clearTimeout(timer); };
    }
  });
})();
