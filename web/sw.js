'use strict';

// Bump the shell version whenever a bundled file changes. Never cache API data.
const CACHE = 'lifeline-shell-v6';
const SHELL = [
  '/assets/index.html',
  '/assets/styles.css',
  '/assets/api.js',
  '/assets/medical-library.js',
  '/assets/voice.js',
  '/assets/app.js',
  '/assets/response.js',
  '/assets/preparedness-library.js',
  '/assets/preparedness.js',
  '/assets/pwa.js',
  '/assets/manifest.webmanifest',
  '/assets/icons/lifeline.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(
    SHELL.map((url) => new Request(url, { cache: 'reload' }))
  )));
  // Updated workers wait for old app windows to close, avoiding mixed versions.
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((name) => name.startsWith('lifeline-shell-') && name !== CACHE)
      .map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin ||
      url.search || !SHELL.includes(url.pathname)) return;
  event.respondWith(caches.open(CACHE).then(async (cache) =>
    (await cache.match(url.pathname)) || fetch(event.request)
  ));
});
