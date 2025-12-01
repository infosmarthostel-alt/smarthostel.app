// /student/service-worker.js
const CACHE_VERSION = 'student-v1';
const PRECACHE = `precache-${CACHE_VERSION}`;
const RUNTIME = `runtime-${CACHE_VERSION}`;
const ORIGIN = self.location.origin;
const OFFLINE_URL = `${ORIGIN}/offline.html`;

// only precache critical static fallback assets — avoid dynamic protected pages here
const PRECACHE_URLS = [
  OFFLINE_URL,
  `${ORIGIN}/media/favicon.png`
];

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(PRECACHE);
    for (const url of PRECACHE_URLS) {
      try {
        const res = await fetch(url, { cache: 'no-cache', credentials: 'same-origin' });
        if (!res || !res.ok) {
          console.warn('Student SW precache skipped (bad response):', url, res && res.status);
          continue;
        }
        await cache.put(url, res.clone());
        console.log('Student SW cached:', url);
      } catch (err) {
        console.warn('Student SW precache failed for', url, err);
      }
    }
    await self.skipWaiting();
    console.log('Student SW install finished');
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== PRECACHE && k !== RUNTIME).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

async function networkFirst(request) {
  const cache = await caches.open(RUNTIME);
  try {
    const response = await fetch(request);
    if (request.method === 'GET' && response && response.status === 200) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    return caches.match(OFFLINE_URL);
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (request.method === 'GET' && response && response.status === 200) {
      const cache = await caches.open(RUNTIME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    return caches.match(OFFLINE_URL);
  }
}

self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);

  // only handle same-origin requests
  if (url.origin !== location.origin) return;

  // navigation requests under /student/ use network-first and then runtime cache, fallback offline
  if (req.mode === 'navigate' && url.pathname.startsWith('/student/')) {
    event.respondWith(networkFirst(req));
    return;
  }

  // static asset requests -> cache-first
  if (['style', 'script', 'font', 'image'].includes(req.destination)) {
    event.respondWith(cacheFirst(req));
    return;
  }

  // default fallback
  event.respondWith(
    caches.match(req).then(cached => cached || fetch(req).catch(() => caches.match(OFFLINE_URL)))
  );
});

// allow messages to skipWaiting / downloadOffline
self.addEventListener('message', event => {
  if (!event.data) return;
  if (event.data === 'skipWaiting') self.skipWaiting();
  if (event.data === 'downloadOffline') {
    // runtime-cache any pages you want to force-capture (not recommended for login-protected pages)
    caches.open(PRECACHE).then(cache => cache.addAll(PRECACHE_URLS).catch(e => console.warn('downloadOffline failed', e)));
  }
});
