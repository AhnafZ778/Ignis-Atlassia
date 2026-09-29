/* Online application with an explicit offline landing. Training owns its narrower scope. */
const CACHE = "fireatlas-app-shell-v11";
const SHELL = ["/method.html", "/method.css", "/method.js", "/", "/offline.html", "/styles.css", "/design.css", "/landing.css", "/validity.css", "/app.js", "/story.js", "/landing.js", "/validity.js", "/incident-media/park-fire-flames.jpg", "/incident-media/park-fire-02.jpg", "/incident-media/park-fire-04.jpg", "/incident-media/park-fire-05.jpg", "/incident-media/park-fire-06.jpg", "/incident-media/park-fire.jpg", "/app-icon-192.png", "/app-icon-512.png"];
const DEMO_API = new Set(["/api/meta", "/api/calendar", "/api/harmonization", "/api/briefing", "/api/observations", "/api/map", "/api/context", "/api/presentation", "/api/research"]);
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
  // Only an explicitly requested synthetic example may be replayed offline.
  // Imported observations and current feeds must fail visibly when disconnected.
  if (url.pathname.startsWith("/api/")) {
    const cacheDemo = url.searchParams.get("demo") === "1" && DEMO_API.has(url.pathname);
    event.respondWith(fetch(event.request).then(response => {
      if (cacheDemo && response.ok && response.headers.get("Content-Type")?.includes("application/json")) {
        event.waitUntil(caches.open(CACHE).then(cache => cache.put(event.request, response.clone())));
      }
      return response;
    }).catch(async () => {
      if (cacheDemo) {
        const cached = await (await caches.open(CACHE)).match(event.request);
        if (cached) {
          const headers = new Headers(cached.headers);
          headers.set("X-FireAtlas-Offline-Example", "1");
          return new Response(cached.body, {status:cached.status, statusText:cached.statusText, headers});
        }
      }
      return new Response(JSON.stringify({error:cacheDemo
        ? "Offline: open this synthetic example once while connected."
        : "Offline: imported and current data require the server. Reconnect to refresh."}),
      {status:503, headers:{"Content-Type":"application/json"}});
    }));
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
