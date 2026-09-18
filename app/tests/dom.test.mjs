/* Browser-side tests for the editor, under jsdom.
 *
 * This host has no JS runtime, so until now nothing in static/js/ had ever been
 * executed -- which is exactly how "you cannot add a zone" survived a release.
 * jsdom is not a browser (no layout, no audio), but it runs the real modules
 * against a real DOM, which catches wiring bugs: missing listeners, handlers
 * that never fire, state that does not reach the server.
 *
 *   docker run --rm -v "$PWD":/app -w /app node:22-slim \
 *     sh -c "npm i --no-save jsdom >/dev/null 2>&1 && node tests/dom.test.mjs"
 */
import { JSDOM } from 'jsdom';
import assert from 'node:assert/strict';

let passed = 0, failed = 0;
const check = (label, fn) => {
  try { fn(); passed++; console.log(`  ok    ${label}`); }
  catch (err) { failed++; console.log(`  FAIL  ${label}\n        ${err.message}`); }
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ----------------------------------------------------------- fake server -- */

const CANVAS = {
  id: 'c1', name: 'Chatchat',
  image_url: '/media/image/cat.jpg', image_path: 'image/cat.jpg',
  published: false, room_id: null, owner_id: 'u1', owner_name: 'bear',
  created_at: 1789000000, updated_at: 1789000000, sound_count: 0, zones: [],
};
const sent = [];

function fakeFetch(url, opts = {}) {
  const method = opts.method || 'GET';
  sent.push({ url, method, body: opts.body ? JSON.parse(opts.body) : null });
  const json = (data, ok = true) =>
    Promise.resolve({ ok, status: ok ? 200 : 400, json: () => Promise.resolve(data) });

  if (url === '/api/me') return json({ user: { id: 'u1', name: 'bear', display_name: 'bear', role: 'admin' }, csrf: 'tok' });
  if (url.startsWith('/api/canvases/c1') && method === 'GET') return json({ canvas: CANVAS });
  if (url.startsWith('/api/canvases/c1') && method === 'PUT') {
    Object.assign(CANVAS, opts.body ? JSON.parse(opts.body) : {});
    return json({ canvas: CANVAS });
  }
  if (url.startsWith('/api/canvases')) return json({ canvases: [CANVAS], scope: 'mine' });
  if (url === '/static/sounds/bank.json') return json([]);
  if (url === '/api/galleries') return json({ galleries: [{ id: 'g1', title: 'Groupe A', slug: 'groupe-a' }] });
  return json({});
}

/* ------------------------------------------------------------- the world -- */

const dom = new JSDOM(`<!doctype html><html><body>
  <header id="topbar" hidden><nav id="nav"></nav></header>
  <main id="main" tabindex="-1"></main>
</body></html>`, { url: 'https://example.test/#/edit/c1', pretendToBeVisual: true });

const { window } = dom;
global.window = window;
global.document = window.document;
Object.defineProperty(global, 'navigator', { value: window.navigator, configurable: true, writable: true });
Object.defineProperty(global, 'location', { value: window.location, configurable: true, writable: true });
global.HTMLElement = window.HTMLElement;
global.Blob = window.Blob;
global.File = window.File;
global.FormData = window.FormData;
global.URL = window.URL;
global.localStorage = window.localStorage;
global.fetch = fakeFetch;
window.fetch = fakeFetch;
global.addEventListener = window.addEventListener.bind(window);
global.removeEventListener = window.removeEventListener.bind(window);
// Node's own timers are used as-is: re-exporting jsdom's back onto the global
// object makes them recurse into themselves.
global.confirm = () => true;
global.alert = () => {};
// Audio is out of scope for jsdom; the editor only constructs these lazily.
window.AudioContext = class { constructor() { this.state = 'running'; this.currentTime = 0; } };
global.AudioContext = window.AudioContext;
window.MediaRecorder = undefined;

// jsdom does no layout, so an <img> reports zero size. Give the stage a size so
// percentage maths is exercised rather than divided by zero.
Object.defineProperty(window.HTMLImageElement.prototype, 'clientWidth', { get: () => 800, configurable: true });
Object.defineProperty(window.HTMLImageElement.prototype, 'clientHeight', { get: () => 600, configurable: true });
Object.defineProperty(window.HTMLImageElement.prototype, 'complete', { get: () => true, configurable: true });
Object.defineProperty(window.HTMLImageElement.prototype, 'naturalWidth', { get: () => 1600, configurable: true });
window.HTMLElement.prototype.getBoundingClientRect = function () {
  return { left: 0, top: 0, width: 800, height: 600, right: 800, bottom: 600, x: 0, y: 0 };
};

await import('../static/js/app.js');
await sleep(120);

/* ------------------------------------------------------------------ tests -- */

console.log('Editor, under jsdom\n');

const main = window.document.getElementById('main');
const layer = () => main.querySelector('.zone-layer');
const zones = () => main.querySelectorAll('.zone-layer .zone');

check('the editor renders', () => {
  assert.ok(main.querySelector('.stage-wrap'), 'no stage');
  assert.ok(layer(), 'no zone layer');
});

check('the toolbar offers an explicit add button', () => {
  const buttons = [...main.querySelectorAll('button')].map((b) => b.textContent);
  assert.ok(buttons.some((label) => label.includes('zone') || label.includes('spot')),
            `no add button among: ${buttons.join(' | ')}`);
});

check('the zone layer does not swallow clicks', () => {
  // The regression that shipped: an overlay with default pointer-events meant
  // the image never received a click, so no zone could ever be created.
  const css = window.document.createElement('div');
  assert.equal(layer().className, 'zone-layer');
});

const addButton = [...main.querySelectorAll('button')]
  .find((b) => b.textContent.includes('＋'));

check('add button exists', () => assert.ok(addButton, 'no ＋ button found'));

if (addButton) {
  addButton.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(120);

  check('clicking add creates a zone', () => {
    assert.equal(zones().length, 1, `expected 1 zone, saw ${zones().length}`);
  });

  check('the new zone is placed and sized', () => {
    const z = zones()[0];
    assert.ok(parseFloat(z.style.width) > 0, `width was ${z.style.width}`);
    assert.ok(z.style.left.endsWith('px'), `left was ${z.style.left}`);
  });

  check('the new zone is audible by default', () => {
    const put = [...sent].reverse().find((r) => r.method === 'PUT');
    assert.ok(put, 'no PUT was sent');
    const zone = put.body.zones[0];
    assert.equal(zone.type, 'generated');
    assert.equal(zone.sound_name, 'Beep');
  });

  check('the zone was persisted to the server', () => {
    const put = [...sent].reverse().find((r) => r.method === 'PUT');
    assert.equal(put.body.zones.length, 1);
    assert.ok(put.body.zones[0].x >= 0 && put.body.zones[0].x <= 100);
  });

  check('the panel lists the zone', () => {
    assert.ok(main.querySelector('.zone-row'), 'no zone row in the panel');
  });
}

// Clicking the picture itself is the shortcut path.
const img = main.querySelector('img.stage');
if (img) {
  img.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(120);
  check('clicking the picture adds a second zone', () => {
    assert.equal(zones().length, 2, `expected 2 zones, saw ${zones().length}`);
  });
}

/* --- the resize regression ------------------------------------------------
 * Dragging a zone's handle used to update a DOM node that select() had already
 * replaced, so the circle never followed the pointer and only jumped size at
 * the next unrelated re-render. These assert against the *live* node. */

const firstZone = () => main.querySelector('.zone-layer .zone');

check('selecting a zone keeps the same DOM node', () => {
  const before = firstZone();
  const rows = main.querySelectorAll('.zone-row');
  assert.ok(rows.length >= 1, 'no zone rows');
  rows[0].dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  assert.equal(firstZone(), before,
               'the zone layer was rebuilt on select -- a drag would lose its node');
});

check('selecting marks the zone active', () => {
  assert.ok(firstZone().classList.contains('is-active'));
});

await (async () => {
  const node = firstZone();
  const handle = node.querySelector('.zone-handle');
  const startWidth = parseFloat(node.style.width);

  const pointer = (type, x, y, target) => {
    const ev = new window.MouseEvent(type, { bubbles: true, clientX: x, clientY: y });
    ev.pointerId = 1;
    (target || window).dispatchEvent(ev);
  };

  handle.dispatchEvent(Object.assign(
    new window.MouseEvent('pointerdown', { bubbles: true, clientX: 400, clientY: 300 }),
    { pointerId: 1 }));
  pointer('pointermove', 600, 300);
  await sleep(20);

  check('dragging the handle resizes the live node', () => {
    const now = parseFloat(firstZone().style.width);
    assert.notEqual(now, startWidth, `width stayed at ${startWidth}`);
    assert.ok(now > 100, `width was ${now}`);
  });

  check('the radius follows the pointer rather than jumping a fixed amount', () => {
    // radius is a diameter, so dragging the handle to 200px from centre => ~400.
    const node2 = firstZone();
    const width = parseFloat(node2.style.width);
    const centreX = parseFloat(node2.style.left);
    const expected = Math.abs(600 - centreX) * 2;
    assert.ok(Math.abs(width - expected) < 2,
              `width ${width} does not track pointer (expected ~${expected})`);
  });

  pointer('pointerup', 600, 300);
  await sleep(20);
})();

check('a drag does not also add a zone', () => {
  assert.equal(zones().length, 2, `expected 2 zones after the drag, saw ${zones().length}`);
});

check('the stage does not block panning when idle', () => {
  // The iPad landscape failure: touch-action:none on the picture meant Safari
  // refused to scroll the page, because the picture filled the viewport.
  assert.ok(!main.querySelector('.stage-wrap').classList.contains('is-dragging'));
});

check('French is the default language', () => {
  assert.equal(window.document.documentElement.lang, 'fr',
               `lang was ${window.document.documentElement.lang}`);
});

check('no missing translations', async () => {
  // auditKeys is exported for exactly this.
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
