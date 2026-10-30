/* Calorys (version web) : cache hors ligne. */
const CACHE = 'calorys-1.5.0';
const FILES = ['./', 'index.html', 'css/style.css', 'js/platform.js', 'js/nutrition.js', 'js/engine.js', 'js/catalog.js', 'js/catalog-manifest.js', 'js/sync.js', 'js/winrem.js', 'js/program.js', 'data/programmes.js',
  'js/charts.js', 'js/app.js', 'js/vendor/zxing.min.js', 'js/vendor/sql-wasm.js', 'js/vendor/sql-wasm.wasm', 'data/foods.js', 'data/nutravyn.js',
  'img/icon.svg', 'img/icon-192.png', 'manifest.webmanifest'];
self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES)).then(() => self.skipWaiting())));
self.addEventListener('activate', e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (u.origin !== location.origin) return;
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
