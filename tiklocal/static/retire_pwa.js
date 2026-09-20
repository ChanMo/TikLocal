// Remove only TikLocal's old worker and public asset caches; never register a worker.
(async () => {
  try {
    if ('serviceWorker' in navigator) {
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.filter((registration) => {
        const worker = registration.active || registration.waiting || registration.installing;
        if (!worker) return false;
        const url = new URL(worker.scriptURL);
        return url.origin === location.origin && url.pathname === '/service-worker.js';
      }).map((registration) => registration.unregister()));
    }
    if ('caches' in window) {
      const names = await caches.keys();
      await Promise.all(names.filter((name) => name.startsWith('tiklocal-public-'))
        .map((name) => caches.delete(name)));
    }
  } catch (error) {
    console.warn('TikLocal legacy cache cleanup will retry on the next visit.', error);
  }
})();
