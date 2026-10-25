/* PenWorks service worker.
   Network-first for app code so a deploy lands on the next load, cache-first for icons.
   Supabase calls are never cached. The supabase-js library and the fonts are cached network-first.

   BUMP THIS VERSION ON EVERY SHIPPABLE CHANGE. */
const CACHE = "pw-v4g";

const SHELL = ["./", "./index.html", "./manifest.json", "./css/app.css", "./js/app.js", "./js/api.js",
  "./js/local-backend.js", "./js/page.js", "./js/ink.js", "./js/store-local.js", "./js/tray.js", "./js/dbg.js",
  "./icons/icon-192.png", "./icons/icon-512.png"];
const CDN = ["cdn.jsdelivr.net", "fonts.googleapis.com", "fonts.gstatic.com"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function networkFirst(req, fallback) {
  return fetch(req).then((res) => {
    if (res.ok || res.type === "opaque") {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
    }
    return res;
  }).catch(() => caches.match(req, { ignoreSearch: fallback }).then((hit) => hit || (fallback ? caches.match("./index.html") : Response.error())));
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) {
    if (CDN.includes(url.hostname)) e.respondWith(networkFirst(req, false));
    return;   // Supabase and everything else: straight to the network
  }
  if (/\.png$/.test(url.pathname)) {
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
      return res;
    })));
    return;
  }
  e.respondWith(networkFirst(req, true));
});
