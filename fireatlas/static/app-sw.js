/* Online application with an explicit offline landing. Training owns its narrower scope. */
const CACHE = "fireatlas-app-shell-v2";
const SHELL = ["/", "/offline.html", "/styles.css", "/design.css", "/landing.css", "/app.js", "/story.js", "/landing.js", "/app-icon-192.png", "/app-icon-512.png"];
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
  // Keep last successful demo responses available when the network drops.
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(fetch(event.request).then(response => {
      if (response.ok) caches.open(CACHE).then(cache => cache.put(event.request, response.clone()));
      return response;
    }).catch(async () => (await caches.open(CACHE)).match(event.request) || new Response(JSON.stringify({error:"Offline: open the prepared demo once while connected."}), {status:503, headers:{"Content-Type":"application/json"}})));
    return;
  }
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).then(response => {
      if (response.ok) caches.open(CACHE).then(cache => cache.put(event.request, response.clone()));
      return response;
    }).catch(async () => {
      return (await caches.open(CACHE)).match(event.request) || (await caches.open(CACHE)).match("/") || (await caches.open(CACHE)).match("/offline.html");
    }));
  }
});
