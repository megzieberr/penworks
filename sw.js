/* PenWorks service worker.
   Network-first for app code so a deploy lands on the next load, cache-first for icons.
   pw-v8p (4 Nov): GitHub Pages answers every file with Cache-Control: max-age=600, so a plain fetch() inside the 10 minutes
   after a load is the tablet's OWN http cache saying "fresh" with the OLD file (her four reopens after pw-v8o still showed
   the 1000-row bug). App files are now fetched with cache: "no-cache" (revalidated against GitHub's ETag: a 304 when
   nothing changed) and the install step takes fresh copies (cache: "reload").
   Supabase calls are never cached. The supabase-js library and the fonts are cached network-first.

   U4b: a PDF shared to PenWorks (Android's share sheet, WhatsApp's share button) arrives as a POST to ./share-target/
   (manifest.json share_target). GitHub Pages never sees it: this worker answers it, the page open or not. The file is
   kept in IndexedDB penworks.share (store `files`, key `pending`, one share at a time: the next share replaces it), not in
   the Cache API: the activate step below deletes every cache but this version's, and a share that landed just before an
   update would go with it. Then a 303 to ./?share=1, where the app picks it up (js/pdfin.js sharedFiles).

   pw-v8r (5 Nov): the parallel half of the U5g snap removed (her tablet verdict); perpendicular only.
   pw-v8s (5 Nov): calculator.js refreshed from Blipwork 21a3f23, the root sign and the brackets grow with what is inside.
   pw-v8t (5 Nov): calculator.js refreshed from Blipwork c6a63cc, SHIFT °'" = FACT shows a whole answer's prime factors.
   pw-v8u (5 Nov): calculator.js refreshed from Blipwork ceacd2d, FACT measured: Math ERROR when it cannot factor, S⇔D leaves the list.
   pw-v8v (5 Nov): the calculator's face redrawn as her fx-991ZA (light body, keys filled by their label, the small words above), its colours hers (pw.calcFace).
   pw-v8w (5 Nov): eight soft pastel chips for the calculator's body under the Body row (her ask: the body was very bright).
   pw-v8x (5 Nov): seven face fixes, CSS only: FACT, x-square, fraction and root keys drawn like the real ones, words closer to their keys, a real four-key arrow pad.
   pw-v8y (6 Nov): All notes on top of the folder view and the app opens on it every time; the phone grid in two columns, the folders in a drawer.
   pw-v8z (6 Nov): an open note's bar shows its folder as a small chip (a tap moves it) and a star that pins it to the top; on the phone both sit in the ... menu.
   pw-v9a (6 Nov): every thumb in the page list has a ribbon button, grey or blue, one tap bookmarks the page; the big page's ribbon is the same blue.
   pw-v9b (6 Nov): Select on the notes grid ticks notes to move, bin or merge them (Undo for a while after); the page list's Select moves pages to another note.
   pw-v9c (6 Nov): sticky notes: the + menu's Sticky puts a coloured square beside the page; write on it, drag it into the margin or onto a page, resize it by its corner.
   pw-v9d (7 Nov): a picture shared from WhatsApp lands like a PDF: the manifest's second files entry (image), every shared PDF and picture kept as a list in the form's order, each picture a new page.
   pw-v9e (7 Nov): Cut out: a selected picture's wand chip opens a sheet where a tap takes its background away (a fussiness slider, Everywhere, no AI); Done keeps a new PNG.
   pw-v9f (11 Nov): the page number sits on each page (never printed), ink moves across pages, Copy clears the selection.

   BUMP THIS VERSION ON EVERY SHIPPABLE CHANGE. */
const CACHE = "pw-v9f";
const SHARE_DB = "penworks.share";

const SHELL = ["./", "./index.html", "./manifest.json", "./css/app.css", "./js/app.js", "./js/api.js",
  "./js/local-backend.js", "./js/page.js", "./js/ink.js", "./js/store.js", "./js/treeq.js", "./js/snap.js", "./js/live.js", "./js/tray.js", "./js/dbg.js",
  "./js/pdfin.js", "./js/pdfview.js", "./js/pdfout.js", "./js/cutout.js",
  "./js/calc/calculator.js", "./js/calc/ui.js", "./js/calc/statlib.js", "./js/calcpanel.js", "./js/tools.js", "./js/align.js", "./css/calc.css",
  "./icons/icon-192.png", "./icons/icon-512.png", "./vendor/pdf-lib.min.js",
  "./vendor/pdf.min.mjs", "./vendor/pdf.worker.min.mjs"];
const CDN = ["cdn.jsdelivr.net", "fonts.googleapis.com", "fonts.gstatic.com"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL.map((u) => new Request(u, { cache: "reload" })))).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function networkFirst(req, fallback) {
  // same-origin (the app's own files, `fallback` true): past the http cache, revalidated with GitHub each time. A navigation
  // request cannot be re-wrapped (mode "navigate"), so the url is fetched as a plain GET instead.
  const get = fallback ? fetch(req.url, { cache: "no-cache", credentials: "same-origin" }) : fetch(req);
  return get.then((res) => {
    if (res.ok || res.type === "opaque") {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
    }
    return res;
  }).catch(() => caches.match(req, { ignoreSearch: fallback }).then((hit) => hit || (fallback ? caches.match("./index.html") : Response.error())));
}

// U4b: the shared files, kept before the answer goes (the app may be starting cold and ask for it at once).
// pw-v9d: a list, { files: [{ blob, name, type }], at } (one PDF = a list of one); the next share replaces it whole
function keepShared(files) {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(SHARE_DB, 1);
    r.onupgradeneeded = () => { if (!r.result.objectStoreNames.contains("files")) r.result.createObjectStore("files"); };
    r.onerror = () => reject(r.error);
    r.onsuccess = () => {
      const db = r.result, t = db.transaction(["files"], "readwrite");
      t.objectStore("files").put({ files, at: new Date().toISOString() }, "pending");
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
// pw-v9d: every file under `pdf` (her installed app posts there until it is reinstalled) or `image` that is a PDF or a
// picture, in the order the form gives them; a caption, a text-only share or any other file: nothing kept
const PICS = { "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp" };
async function shareIn(req, url) {
  try {
    const form = await req.formData();
    const real = (f) => f && typeof f !== "string" && f.size > 0;
    const isPdf = (f) => real(f) && (f.type === "application/pdf" || /\.pdf$/i.test(f.name || ""));
    const isPic = (f) => real(f) && (Object.hasOwn(PICS, f.type) || /\.(png|jpe?g|webp)$/i.test(f.name || ""));
    const files = [];
    for (const [k, f] of form.entries()) {
      if (k !== "pdf" && k !== "image") continue;
      if (isPdf(f)) files.push({ blob: f, name: f.name || "Shared.pdf", type: "application/pdf" });
      else if (isPic(f)) files.push({ blob: f, name: f.name || "Shared picture" + (PICS[f.type] || ""), type: Object.hasOwn(PICS, f.type) ? f.type : "" });
    }
    if (files.length) await keepShared(files);
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
