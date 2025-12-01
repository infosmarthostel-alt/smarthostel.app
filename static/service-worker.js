// service-worker.js
const CACHE_VERSION = 'v1';
const PRECACHE = `precache-${CACHE_VERSION}`;
const RUNTIME = `runtime-${CACHE_VERSION}`;

// Edit this list to include the root pages & static assets you want pre-cached.
// Keep offline.html in templates/static (see instructions below).
const PRECACHE_URLS = [
  '/',                       // main landing / root (student home)
  '/s_home/',                // example student home url
  '/meals_today/',
  '/student_submit_complaint/',
  '/student_pay_page/',
  '/profile_view/',
  '/dashboard/',
  '/offline.html',           // fallback when offline
  '/static/favicon.png'
];

self.addEventListener('install', event => {
  // Precache important resources
  event.waitUntil(
    caches.open(PRECACHE)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  // Clean up old caches
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(k => k !== PRECACHE && k !== RUNTIME)
            .map(k => caches.delete(k))
      );
    }).then(() => self.clients.claim())
  );
});

// Helper: network-first for navigation / api (try network, fallback to cache)
async function networkFirst(request) {
  const cache = await caches.open(RUNTIME);
  try {
    const response = await fetch(request);
    // optionally cache successful GET responses
    if (request.method === 'GET' && response && response.status === 200) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    const precached = await caches.open(PRECACHE).then(c => c.match('/offline.html'));
    return precached || Response.error();
  }
}

// Helper: cache-first for static assets (fast)
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
    return caches.match('/offline.html');
  }
}

self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);

  // Only handle same-origin requests (optional: adjust if you want cross-origin caching)
  if (url.origin !== location.origin) {
    // Let the browser handle cross-origin (CDNs, analytics). Could add special rules here.
    return;
  }

  // Navigation requests (HTML pages). Use network-first so pages stay fresh.
  if (req.mode === 'navigate' || (req.method === 'GET' && req.headers.get('accept')?.includes('text/html'))) {
    event.respondWith(networkFirst(req));
    return;
  }

  // API requests (adjust path to match your API endpoints)
  if (url.pathname.startsWith('/api/') || url.pathname.includes('/ajax/')) {
    // network-first for API so clients get up-to-date data; fallback to cached result
    event.respondWith(networkFirst(req));
    return;
  }

  // Static assets: CSS, JS, font, images -> cache-first for speed
  if (req.destination === 'style' || req.destination === 'script' || req.destination === 'font' || req.destination === 'image') {
    event.respondWith(cacheFirst(req));
    return;
  }

  // Default fallback: try cache then network
  event.respondWith(
    caches.match(req).then(cached => cached || fetch(req).catch(() => caches.match('/offline.html')))
  );
});

// Support for skipWaiting message and manual offline download
self.addEventListener('message', event => {
  if (!event.data) return;
  if (event.data === 'skipWaiting') {
    self.skipWaiting();
  }
  if (event.data === 'downloadOffline') {
    caches.open(PRECACHE).then(cache => cache.addAll(PRECACHE_URLS));
  }
});
