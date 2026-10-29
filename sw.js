/* PenWorks service worker.
   Network-first for app code so a deploy lands on the next load, cache-first for icons.
   Supabase calls are never cached. The supabase-js library and the fonts are cached network-first.

   U4b: a PDF shared to PenWorks (Android's share sheet, WhatsApp's share button) arrives as a POST to ./share-target/
   (manifest.json share_target). GitHub Pages never sees it: this worker answers it, the page open or not. The file is
   kept in IndexedDB penworks.share (store `files`, key `pending`, one file at a time: the next share replaces it), not in
   the Cache API: the activate step below deletes every cache but this version's, and a share that landed just before an
   update would go with it. Then a 303 to ./?share=1, where the app picks it up (js/pdfin.js sharedFile).

   BUMP THIS VERSION ON EVERY SHIPPABLE CHANGE. */
const CACHE = "pw-v7d";
const SHARE_DB = "penworks.share";

const SHELL = ["./", "./index.html", "./manifest.json", "./css/app.css", "./js/app.js", "./js/api.js",
  "./js/local-backend.js", "./js/page.js", "./js/ink.js", "./js/store.js", "./js/treeq.js", "./js/snap.js", "./js/live.js", "./js/tray.js", "./js/dbg.js",
  "./js/pdfin.js", "./js/pdfview.js",
  "./js/calc/calculator.js", "./js/calc/ui.js", "./js/calc/statlib.js", "./js/calcpanel.js", "./css/calc.css",
  "./icons/icon-192.png", "./icons/icon-512.png", "./vendor/jspdf.umd.min.js",
  "./vendor/pdf.min.mjs", "./vendor/pdf.worker.min.mjs"];
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

// U4b: the shared file, kept before the answer goes (the app may be starting cold and ask for it at once)
function keepShared(file) {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(SHARE_DB, 1);
    r.onupgradeneeded = () => { if (!r.result.objectStoreNames.contains("files")) r.result.createObjectStore("files"); };
    r.onerror = () => reject(r.error);
    r.onsuccess = () => {
      const db = r.result, t = db.transaction(["files"], "readwrite");
      t.objectStore("files").put({ blob: file, name: file.name || "Shared.pdf", at: new Date().toISOString() }, "pending");
      t.oncomplete = () => { db.close(); resolve(); };
      t.onerror = t.onabort = () => { db.close(); reject(t.error); };
    };
  });
}
// the app's address after a share: ./?share=1 (?local=1 carried over, so the tests' twin stays the twin)
function landing(url) {
  const q = new URLSearchParams({ share: "1" });
  if (url.searchParams.has("local")) q.set("local", "1");
  return new URL("./?" + q, self.registration.scope).href;
}
async function shareIn(req, url) {
  try {
    const form = await req.formData();
    const isPdf = (f) => f && typeof f !== "string" && f.size > 0 && (f.type === "application/pdf" || /\.pdf$/i.test(f.name || ""));
    const file = form.getAll("pdf").find(isPdf);
    if (file) await keepShared(file);
  } catch (_) { /* nothing kept: the app says there is nothing to open */ }
  return Response.redirect(landing(url), 303);
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (url.origin === location.origin && url.pathname === new URL("./share-target/", self.registration.scope).pathname) {
    // never cached, never sent to the server (a GET here is a stale address: the app itself)
    e.respondWith(req.method === "POST" ? shareIn(req, url) : Response.redirect(new URL("./", self.registration.scope).href, 303));
    return;
  }
  if (req.method !== "GET") return;
  if (url.origin !== location.origin) {
    if (CDN.includes(url.hostname)) e.respondWith(networkFirst(req, false));
    return;   // Supabase (its database, /storage/ pictures and the Realtime websocket) and everything else: straight to the network
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
