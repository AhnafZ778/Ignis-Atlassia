/* Bump this version whenever a file in this offline pack changes. */
const CACHE = "fireatlas-training-shell-v2";
const ASSETS = ["/training.html", "/styles.css", "/training.css", "/design.css", "/ui.js",
  "/training.js", "/training-state.js", "/training-store.js", "/training-offline.js",
  "/vendor/leaflet.js", "/vendor/leaflet.css", "/favicon.svg",
  "/fonts/dm-sans.ttf", "/fonts/space-grotesk.ttf"];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS.map(path => new Request(path, {cache:"reload"})))));
});
self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name.startsWith("fireatlas-training-shell-") && name !== CACHE) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || !ASSETS.includes(url.pathname)) return;
  event.respondWith(caches.open(CACHE).then(async cache => (await cache.match(url.pathname)) || fetch(event.request)));
});
