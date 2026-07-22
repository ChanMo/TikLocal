'use strict';

const workerUrl = new URL(self.location.href);
const appVersion = workerUrl.searchParams.get('v') || 'dev';
const cachePrefix = 'tiklocal-public-';
const publicCache = `${cachePrefix}${appVersion}`;

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(
      names
        .filter((name) => name.startsWith(cachePrefix) && name !== publicCache)
        .map((name) => caches.delete(name)),
    );
    await self.clients.claim();
  })());
});

function isPublicAsset(url) {
  if (url.origin !== self.location.origin) return false;
  if (url.pathname.startsWith('/pwa/icon-')) return true;
  return url.pathname.startsWith('/static/') && url.searchParams.has('v');
}

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (!isPublicAsset(url)) return;

  event.respondWith((async () => {
    const cache = await caches.open(publicCache);
    const cached = await cache.match(event.request);
    if (cached) return cached;

    const response = await fetch(event.request);
    if (response.ok && response.type === 'basic') {
      await cache.put(event.request, response.clone());
    }
    return response;
  })());
});
