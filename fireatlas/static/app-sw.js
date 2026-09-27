/* Online application with an explicit offline landing. Training owns its narrower scope. */
const CACHE = "fireatlas-app-shell-v1";
const SHELL = ["/offline.html", "/app-icon-192.png", "/app-icon-512.png"];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)));
});
self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name.startsWith("fireatlas-app-shell-") && name !== CACHE) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  // Never cache API responses or substitute generated/stale data for a failed request.
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).catch(async () => {
      return (await caches.open(CACHE)).match("/offline.html");
    }));
  }
});
