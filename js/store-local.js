// PenWorks stroke storage for U2: on this device only, in localStorage under pw.strokes.<page_id>,
// as the array of stroke records (the strokes table's shape). U3 swaps this one file for Supabase
// plus an offline queue; nothing else in the app reads these keys.

const PREFIX = 'pw.strokes.';

export function load(pageId) {
  try {
    const a = JSON.parse(localStorage.getItem(PREFIX + pageId) || '[]');
    return Array.isArray(a) ? a : [];
  } catch (_) { return []; }
}

export function save(pageId, strokes) {
  try {
    if (strokes.length) localStorage.setItem(PREFIX + pageId, JSON.stringify(strokes));
    else localStorage.removeItem(PREFIX + pageId);
    return true;
  } catch (e) { console.warn('Strokes not kept on this device', e); return false; }
}

export function clear(pageId) {
  try { localStorage.removeItem(PREFIX + pageId); } catch (_) { /* ignore */ }
}

// every page that has strokes kept here (for the tidy-up of pages that are gone for good)
export function pageIds() {
  const out = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(PREFIX)) out.push(k.slice(PREFIX.length));
    }
  } catch (_) { /* ignore */ }
  return out;
}

// Page bookmarks (pw-v4r): the page record carries `bookmark` (true / false, default false), like its paper and
// orientation. Until U3 it is kept here, on this device only: pw.bookmark.<page_id> = '1' while the page is
// bookmarked. U3 maps the `bookmark` field to a pages.bookmark column (boolean, default false) and drops these keys.
const MARK = 'pw.bookmark.';

export function bookmarked(pageId) {
  try { return localStorage.getItem(MARK + pageId) === '1'; } catch (_) { return false; }
}

export function keepBookmark(pageId, on) {
  try {
    if (on) localStorage.setItem(MARK + pageId, '1');
    else localStorage.removeItem(MARK + pageId);
  } catch (e) { console.warn('Bookmark not kept on this device', e); }
}
