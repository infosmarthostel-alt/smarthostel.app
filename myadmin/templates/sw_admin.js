// admin/service-worker.js
const CACHE_VERSION = 'admin-v1';
const PRECACHE = `precache-${CACHE_VERSION}`;
const RUNTIME = `runtime-${CACHE_VERSION}`;

const PRECACHE_URLS = [
  '/admin/',                   // admin root (dashboard)
  '/admin/dashboard/',
  '/admin/students/',
  '/admin/rooms/',
  '/admin/pending-fees/',
  '/admin/admin_meals_list/',
  '/admin/admin_notifications_list/',
  '/admin/admin_complaints_list/',
  '/admin/export_students_csv/',
  '/admin/offline.html',       // admin-specific offline fallback
  '/media/favicon.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(PRECACHE)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
      .catch(err => {
        // if a precache URL fails, still attempt to continue
        console.warn('Admin SW precache failed', err);
      })
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== PRECACHE && k !== RUNTIME)
          .map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

// network-first helper (for admin pages & APIs)
async function networkFirst(req) {
  const cache = await caches.open(RUNTIME);
  try {
    const resp = await fetch(req);
    if (req.method === 'GET' && resp && resp.status === 200) {
      cache.put(req, resp.clone());
    }
    return resp;
  } catch (err) {
    const cached = await cache.match(req);
    if (cached) return cached;
    return caches.match('/admin/offline.html');
  }
}

// cache-first helper (for static assets)
async function cacheFirst(req) {
  const cached = await caches.match(req);
  if (cached) return cached;
  try {
    const resp = await fetch(req);
    if (req.method === 'GET' && resp && resp.status === 200) {
      const cache = await caches.open(RUNTIME);
      cache.put(req, resp.clone());
    }
    return resp;
  } catch (err) {
    return caches.match('/admin/offline.html');
  }
}

self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);

  // only handle same-origin requests (admin assets/pages are same origin)
  if (url.origin !== location.origin) return;

  // admin-scoped routes -> network-first (fresh admin data)
  if (url.pathname.startsWith('/admin/')) {
    event.respondWith(networkFirst(req));
    return;
  }

  // static resources (css/js/fonts/images) -> cache-first
  if (req.destination === 'style' || req.destination === 'script' || req.destination === 'font' || req.destination === 'image') {
    event.respondWith(cacheFirst(req));
    return;
  }

  // fallback: try cache then network
  event.respondWith(
    caches.match(req).then(cached => cached || fetch(req).catch(() => caches.match('/admin/offline.html')))
  );
});

// support skipWaiting (activate new SW immediately)
self.addEventListener('message', event => {
  if (!event.data) return;
  if (event.data === 'skipWaiting') self.skipWaiting();
});
