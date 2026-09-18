/* Imagery -- self-hosted. Application shell, router and views.
 *
 * Plain ES modules, no build step: this host has no JS runtime, so anything
 * requiring bundling could not be verified here at all. It also keeps the
 * container small and the deployment a single `docker compose up`.
 */
import { api, setCsrf } from './api.js';
import { t, lang, setLang, LANGS, auditKeys } from './i18n.js';
import { ZonePlayer, DEFAULT_VOLUME, GENERATED_PRESETS } from './audio.js';
import { Recorder, isSupported as canRecord, filenameFor } from './recorder.js';

const main = document.getElementById('main');
const topbar = document.getElementById('topbar');
const nav = document.getElementById('nav');

const state = { user: null, canvases: [], scope: 'mine', player: null };

/* ---------------------------------------------------------------- helpers */

const el = (tag, attrs = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === false || v == null) continue;
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return node;
};

const show = (...nodes) => { main.replaceChildren(...nodes); main.focus({ preventScroll: true }); };

function notice(message, kind = 'error') {
  return el('div', { class: `notice notice-${kind}`, role: kind === 'error' ? 'alert' : 'status' }, message);
}

function plural(n) { return n === 1 ? t('sound') : t('sounds'); }

function formatDate(seconds) {
  if (!seconds) return t('never');
  return new Date(seconds * 1000).toLocaleDateString(lang(), {
    year: 'numeric', month: 'short', day: 'numeric',
  });
}

/** A passphrase field with a real show/hide button -- typing a long phrase
 *  blind is the single biggest cause of failed sign-ins for this audience. */
function passphraseField(id, label, hint) {
  const input = el('input', { type: 'password', id, autocomplete: 'current-password', required: true });
  const toggle = el('button', {
    type: 'button', class: 'btn pass-toggle', 'aria-pressed': 'false',
    onclick: () => {
      const shown = input.type === 'text';
      input.type = shown ? 'password' : 'text';
      toggle.textContent = shown ? t('show') : t('hide');
      toggle.setAttribute('aria-pressed', String(!shown));
      input.focus();
    },
  }, t('show'));
  return {
    input,
    node: el('div', { class: 'field' },
      el('label', { for: id }, label),
      el('div', { class: 'pass-wrap' }, input, toggle),
      hint ? el('div', { class: 'hint' }, hint) : null),
  };
}

/* ------------------------------------------------------------------ chrome */

function renderNav() {
  nav.replaceChildren();
  if (!state.user) { topbar.hidden = true; return; }
  topbar.hidden = false;

  const picker = el('select', {
    'aria-label': t('language'),
    onchange: (e) => { setLang(e.target.value); route(); },
  }, ...LANGS.map((code) => el('option', { value: code, selected: code === lang() }, code.toUpperCase())));

  nav.append(
    el('a', { class: 'btn', href: '#/' }, t('galleries')),
    state.user.role === 'admin' ? el('a', { class: 'btn', href: '#/people' }, t('people')) : null,
    picker,
    el('button', {
      class: 'btn', onclick: async () => {
        await api.logout().catch(() => {});
        state.user = null; setCsrf(''); location.hash = '#/';
        route();
      },
    }, t('signOut')),
  );
}

/* ------------------------------------------------------------------- login */

function viewLogin(message) {
  const name = el('input', { type: 'text', id: 'name', autocomplete: 'username', required: true, autofocus: true });
  const pass = passphraseField('pass', t('passphrase'), t('passHint'));
  const trusted = el('input', { type: 'checkbox', id: 'trusted', checked: true });
  const box = el('div', { id: 'msg' }, message ? notice(message) : null);

  const submit = async (event) => {
    event.preventDefault();
    box.replaceChildren();
    try {
      const res = await api.login(name.value.trim(), pass.input.value, trusted.checked);
      setCsrf(res.csrf); state.user = res.user;
      location.hash = '#/';
      route();
    } catch (err) {
      box.replaceChildren(notice(err.message));
      pass.input.value = ''; pass.input.focus();
    }
  };

  show(el('div', { class: 'login-wrap' },
    el('div', { class: 'card' },
      el('h1', {}, 'Imagery'),
      el('p', { class: 'muted' }, t('tagline')),
      box,
      el('form', { onsubmit: submit },
        el('div', { class: 'field' },
          el('label', { for: 'name' }, t('yourName')), name),
        pass.node,
        el('div', { class: 'field' },
          el('div', { class: 'check' },
            trusted,
            el('label', { for: 'trusted' },
              t('staySignedIn'),
              el('div', { class: 'hint' }, t('stayHint'))))),
        el('button', { class: 'btn btn-primary btn-lg', type: 'submit', style: 'width:100%' },
          t('signIn'))))));
}

function viewSetup(token) {
  const pass = passphraseField('newpass', t('choosePassphrase'), t('passHint'));
  pass.input.autocomplete = 'new-password';
  const box = el('div', {});

  const submit = async (event) => {
    event.preventDefault();
    box.replaceChildren();
    try {
      const res = await api.setup(token, pass.input.value);
      setCsrf(res.csrf); state.user = res.user;
      location.hash = '#/';
      route();
    } catch (err) {
      box.replaceChildren(notice(err.message));
      pass.input.focus();
    }
  };

  show(el('div', { class: 'login-wrap' },
    el('div', { class: 'card' },
      el('h1', {}, t('welcome')),
      el('p', { class: 'muted' }, t('chooseHint')),
      box,
      el('form', { onsubmit: submit },
        pass.node,
        el('button', { class: 'btn btn-primary btn-lg', type: 'submit', style: 'width:100%' },
          t('saveAndStart'))))));
}

/* ----------------------------------------------------------------- gallery */

async function viewGallery() {
  show(el('div', { class: 'page' }, el('p', { class: 'muted' }, t('loading'))));
  const wantAll = state.scope === 'all' && state.user.role === 'admin';
  const data = await api.listCanvases(wantAll);
  state.canvases = data.canvases;

  const fileInput = el('input', {
    type: 'file', accept: 'application/json', class: 'hidden',
    onchange: (e) => importFile(e.target.files[0]),
  });

  const toolbar = el('div', { class: 'toolbar' },
    state.user.role === 'admin' ? el('button', {
      class: 'btn',
      onclick: () => { state.scope = state.scope === 'all' ? 'mine' : 'all'; route(); },
    }, state.scope === 'all' ? t('myGalleries') : t('allGalleries')) : null,
    el('button', { class: 'btn', onclick: () => fileInput.click() }, t('importCanvas')),
    el('button', {
      class: 'btn btn-primary',
      onclick: async () => {
        const created = await api.createCanvas({ name: t('newCanvas') });
        location.hash = `#/edit/${created.canvas.id}`;
      },
    }, t('newCanvas')),
    fileInput);

  const cards = state.canvases.map((canvas) => el('div', { class: 'card' },
    canvas.image_url
      ? el('img', { class: 'thumb', src: canvas.image_url, alt: canvas.name, loading: 'lazy' })
      : el('div', { class: 'thumb' }),
    el('div', { class: 'card-body' },
      el('h2', {}, canvas.name),
      el('p', { class: 'muted' },
        `${canvas.sound_count} ${plural(canvas.sound_count)} · ${formatDate(canvas.created_at)}`
        + (wantAll && canvas.owner_name ? ` · ${canvas.owner_name}` : '')),
      el('div', { class: 'row' },
        el('a', { class: 'btn btn-primary', href: `#/play/${canvas.id}` }, t('open')),
        el('a', { class: 'btn', href: `#/edit/${canvas.id}` }, t('edit')),
        el('button', { class: 'btn', onclick: () => exportCanvas(canvas.id) }, t('download')),
        el('button', {
          class: 'btn btn-danger row-end',
          'aria-label': `${t('del')} ${canvas.name}`,
          onclick: async () => {
            if (!confirm(t('deleteConfirm', { name: canvas.name }))) return;
            await api.deleteCanvas(canvas.id);
            route();
          },
        }, t('del'))))));

  show(el('div', { class: 'page' },
    el('h1', {}, state.scope === 'all' ? t('allGalleries') : t('myGalleries')),
    toolbar,
    cards.length
      ? el('div', { class: 'grid' }, ...cards)
      : el('div', { class: 'card card-body center' },
        el('p', {}, t('noCanvases')),
        el('p', { class: 'muted' }, t('noCanvasesHint')))));
}

/* ------------------------------------------------- import / export (v1.0) */

async function exportCanvas(id) {
  const { canvas } = await api.getCanvas(id);
  // Same shape the original app wrote, so a file exported here re-imports there.
  const payload = {
    name: canvas.name,
    image_url: canvas.image_url ? new URL(canvas.image_url, location.origin).href : null,
    sound_zones: canvas.zones,
    created_date: new Date((canvas.created_at || 0) * 1000).toISOString(),
    export_version: '1.0',
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = el('a', { href: url, download: `${canvas.name.replace(/[^\w.-]+/g, '_')}.imagery.json` });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function importFile(file) {
  if (!file) return;
  let data;
  try { data = JSON.parse(await file.text()); } catch (_) { alert(t('somethingWrong')); return; }
  if (!data.export_version || !data.name || !data.sound_zones) { alert(t('somethingWrong')); return; }
  const created = await api.createCanvas({
    name: `${data.name}`,
    zones: data.sound_zones,
  });
  location.hash = `#/edit/${created.canvas.id}`;
}

/* ------------------------------------------------------------ stage layout */

/** Map a zone's percentage position to pixels within the rendered image. */
function makeMapper(img) {
  return (xPercent, yPercent) => ({
    x: (Number(xPercent) || 0) / 100 * img.clientWidth,
    y: (Number(yPercent) || 0) / 100 * img.clientHeight,
  });
}

/* ------------------------------------------------------------------ viewer */

async function viewPlay(id) {
  const { canvas } = await api.getCanvas(id);
  const player = new ZonePlayer();
  state.player && state.player.destroy();
  state.player = player;
  player.setZones(canvas.zones);

  const img = el('img', { class: 'stage', src: canvas.image_url || '', alt: canvas.name });
  const layer = el('div', { class: 'zone-layer' });
  const status = el('p', { class: 'muted', role: 'status' }, t('clickToStart'));

  const unlock = () => {
    if (player.unlock()) status.textContent = t('soundOn');
  };

  const stage = el('div', { class: 'stage-wrap', onpointerdown: unlock }, img, layer);

  img.addEventListener('pointermove', (event) => {
    if (!player.ready) return;
    const box = img.getBoundingClientRect();
    player.update(event.clientX - box.left, event.clientY - box.top, makeMapper(img));
  });
  img.addEventListener('pointerleave', () => player.allOff());

  /* Keyboard path. The original had none: its zones were reachable only by
   * cursor position, so the whole point of the app was unavailable without a
   * mouse. Each zone is a button here, so Tab reaches it and Enter plays it. */
  const drawZones = () => {
    layer.replaceChildren(...canvas.zones.map((zone) => {
      const centre = makeMapper(img)(zone.x, zone.y);
      const size = Number(zone.radius) || 0;   // stored field is a diameter
      const button = el('button', {
        class: 'zone', 'data-readonly': '1',
        style: `left:${centre.x}px;top:${centre.y}px;width:${size}px;height:${size}px`,
        'aria-label': `${t('playZone')}: ${zone.sound_name || ''}`,
        onfocus: () => { unlock(); player.update(centre.x, centre.y, makeMapper(img)); },
        onblur: () => player.allOff(),
        onclick: () => { unlock(); player.update(centre.x, centre.y, makeMapper(img)); },
      }, el('span', { class: 'zone-label' }, zone.sound_name || ''));
      return button;
    }));
  };
  img.addEventListener('load', drawZones);
  if (img.complete) drawZones();
  addEventListener('resize', drawZones, { passive: true });

  show(el('div', { class: 'page' },
    el('div', { class: 'row' },
      el('a', { class: 'btn', href: '#/' }, t('back')),
      el('h1', { style: 'margin:0' }, canvas.name)),
    status,
    el('p', { class: 'muted' }, t('hoverHint')),
    stage));
}



/* The shipped sound bank, described by static/sounds/bank.json. Fetched once
 * per session; a missing file just means the bank tab says so, rather than the
 * picker breaking. */
let bankPromise = null;
function loadBank() {
  if (!bankPromise) {
    bankPromise = fetch('/static/sounds/bank.json', { credentials: 'same-origin' })
      .then((res) => (res.ok ? res.json() : []))
      .catch(() => []);
  }
  return bankPromise;
}

/* ------------------------------------------------------- sound picker ---- */

/**
 * Choose the sound for a zone: record one, upload a file, or use one of the
 * built-in tones. Rendered as three tabs so only one thing is on screen at a
 * time -- the original crammed all of this into a floating panel that covered
 * the toolbar.
 */
function buildSoundPicker(zone, onChange, onError) {
  const wrap = el('div', { class: 'field' });
  let tab = zone.type === 'generated' ? 'generated' : 'bank';

  const body = el('div', {});
  const recorder = new Recorder();
  let pending = null;          // Blob awaiting confirmation
  let timer = null;

  const current = () => {
    if (zone.type === 'generated' && zone.sound_name) {
      return el('p', { class: 'muted' }, `${t('currentSound')}: ${zone.sound_name}`);
    }
    if (zone.url) {
      return el('div', {},
        el('p', { class: 'muted' }, t('currentSound')),
        el('audio', { controls: true, src: zone.url }));
    }
    return el('p', { class: 'muted' }, t('noSoundYet'));
  };

  const tabButton = (key, label) => el('button', {
    class: 'tab', type: 'button', role: 'tab',
    'aria-selected': String(tab === key),
    onclick: () => { if (recorder.recording) recorder.cancel(); tab = key; render(); },
  }, label);

  function renderRecord() {
    if (!canRecord()) {
      body.replaceChildren(el('p', { class: 'muted' }, t('micBlocked')));
      return;
    }
    if (pending) {
      const url = URL.createObjectURL(pending);
      body.replaceChildren(
        el('audio', { controls: true, src: url }),
        el('div', { class: 'row', style: 'margin-top:12px' },
          el('button', {
            class: 'btn btn-ok', type: 'button',
            onclick: async () => {
              try {
                const file = new File([pending], filenameFor(pending),
                                      { type: pending.type || 'audio/webm' });
                const up = await api.upload('audio', file);
                zone.url = up.url;
                zone.type = 'custom';
                pending = null;
                URL.revokeObjectURL(url);
                await onChange();
              } catch (err) { onError(err.message); }
            },
          }, t('useThis')),
          el('button', {
            class: 'btn', type: 'button',
            onclick: () => { pending = null; URL.revokeObjectURL(url); render(); },
          }, t('recordAgain'))));
      return;
    }
    if (recorder.recording) {
      const time = el('span', { class: 'rec-time' }, '0.0s');
      timer = setInterval(() => { time.textContent = recorder.elapsed().toFixed(1) + 's'; }, 100);
      body.replaceChildren(
        el('div', { class: 'rec-row' },
          el('span', { class: 'rec-dot', 'aria-hidden': 'true' }),
          el('span', { role: 'status' }, t('recording')),
          time),
        el('button', {
          class: 'btn btn-danger', type: 'button', style: 'margin-top:12px',
          onclick: async () => {
            clearInterval(timer);
            pending = await recorder.stop();
            render();
          },
        }, t('stopRecording')));
      return;
    }
    body.replaceChildren(
      el('p', { class: 'muted' }, t('tabRecordHint')),
      el('button', {
        class: 'btn btn-danger', type: 'button',
        onclick: async () => {
          try { await recorder.start(); render(); }
          catch (err) { onError(err.message); }
        },
      }, '● ' + t('startRecording')));
  }

  function renderUpload() {
    const input = el('input', {
      type: 'file', accept: 'audio/*', class: 'hidden',
      onchange: async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        try {
          const up = await api.upload('audio', file);
          zone.url = up.url;
          zone.type = 'custom';
          await onChange();
        } catch (err) { onError(err.message); }
      },
    });
    body.replaceChildren(
      el('button', { class: 'btn', type: 'button', onclick: () => input.click() },
        t('chooseSound')),
      input, current());
  }

  function renderBank() {
    body.replaceChildren(el('p', { class: 'muted' }, t('loadingBank')));
    loadBank().then((sounds) => {
      if (tab !== 'bank') return;                       // tab changed while loading
      if (!sounds.length) {
        body.replaceChildren(el('p', { class: 'muted' }, t('bankEmpty')));
        return;
      }
      body.replaceChildren(el('div', { class: 'preset-grid' },
        ...sounds.map((sound) => {
          const label = lang() === 'fr' ? (sound.label_fr || sound.label_en) : sound.label_en;
          return el('div', { class: 'bank-item' },
            el('button', {
              class: 'preset', type: 'button',
              'aria-pressed': String(zone.url === sound.url),
              onclick: async () => {
                zone.url = sound.url;
                zone.type = 'custom';
                if (!zone.sound_name || zone.sound_name === 'Beep') zone.sound_name = label;
                await onChange();
              },
            }, label, el('span', { class: 'hz' }, sound.licence || '')),
            el('audio', { controls: true, preload: 'none', src: sound.url }));
        })));
    });
  }

  function renderGenerated() {
    body.replaceChildren(el('div', { class: 'preset-grid' },
      ...GENERATED_PRESETS.map((preset) => el('button', {
        class: 'preset', type: 'button',
        'aria-pressed': String(zone.type === 'generated' && zone.sound_name === preset.name),
        onclick: async () => {
          zone.type = 'generated';
          zone.sound_name = preset.name;
          zone.url = null;
          await onChange();
        },
      }, preset.name, el('span', { class: 'hz' }, `${preset.freq} Hz · ${preset.type}`)))));
  }

  function render() {
    clearInterval(timer);
    wrap.replaceChildren(
      el('label', {}, t('soundFor')),
      el('div', { class: 'tabs', role: 'tablist' },
        canRecord() ? tabButton('record', t('record')) : null,
        tabButton('bank', t('bank')),
        tabButton('upload', t('upload')),
        tabButton('generated', t('generated'))),
      body);
    if (tab === 'record') renderRecord();
    else if (tab === 'generated') renderGenerated();
    else if (tab === 'bank') renderBank();
    else renderUpload();
  }

  render();
  return wrap;
}

/* ------------------------------------------------------------------ editor */

/** Trailing debounce: the editor saves as you work, without a request per pixel. */
function debounce(fn, ms) {
  let timer = null;
  const wrapped = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => { timer = null; fn(...args); }, ms);
  };
  wrapped.flush = () => { if (timer) { clearTimeout(timer); timer = null; fn(); } };
  return wrapped;
}

async function viewEdit(id) {
  const { canvas } = await api.getCanvas(id);

  const model = {
    name: canvas.name,
    imagePath: canvas.image_path,
    zones: canvas.zones.slice(),
  };
  let selectedId = null;

  const img = el('img', { class: 'stage', src: canvas.image_url || '', alt: canvas.name });
  const layer = el('div', { class: 'zone-layer' });
  const stage = el('div', { class: 'stage-wrap' }, img, layer);
  const panel = el('div', { class: 'card panel' });
  const status = el('span', { class: 'save-state', role: 'status' }, '');
  const msg = el('div', {});

  const nameInput = el('input', {
    type: 'text', value: model.name, id: 'cname',
    oninput: (e) => { model.name = e.target.value; saveSoon(); },
  });

  const hasImage = () => !!model.imagePath;

  /* ------------------------------------------------------------- saving -- */

  let saving = false;
  async function saveNow() {
    if (saving) { saveSoon(); return; }
    saving = true;
    status.textContent = t('saving');
    try {
      await api.updateCanvas(id, {
        name: model.name, zones: model.zones, image_path: model.imagePath,
      });
      status.textContent = t('savedOk');
      setTimeout(() => { if (status.textContent === t('savedOk')) status.textContent = ''; }, 2000);
    } catch (err) {
      status.textContent = '';
      msg.replaceChildren(notice(err.message));
    } finally {
      saving = false;
    }
  }
  const saveSoon = debounce(saveNow, 700);

  /* ------------------------------------------------------- zone geometry -- */

  const zoneById = (zid) => model.zones.find((z) => z.id === zid);

  /** Position and size only -- called on every drag frame, so it must stay cheap. */
  function placeZone(zone, node) {
    const centre = makeMapper(img)(zone.x, zone.y);
    const size = Number(zone.radius) || 0;       // stored field is a diameter
    node.style.left = `${centre.x}px`;
    node.style.top = `${centre.y}px`;
    node.style.width = `${size}px`;
    node.style.height = `${size}px`;
  }

  /** Rebuild the zone nodes. Structural only -- never called during a drag. */
  function renderZones() {
    layer.replaceChildren(...model.zones.map((zone) => {
      const node = el('div', {
        class: `zone${selectedId === zone.id ? ' is-active' : ''}`,
        'data-zone': zone.id,
        title: zone.sound_name || '',
        onpointerdown: (event) => beginDrag(event, zone, node, 'move'),
      },
        el('span', { class: 'zone-label' }, zone.sound_name || ''),
        el('div', {
          class: 'zone-handle', title: t('resizeZone'),
          onpointerdown: (event) => beginDrag(event, zone, node, 'resize'),
        }),
        el('button', {
          class: 'zone-del', type: 'button', 'aria-label': `${t('removeZone')}: ${zone.sound_name || ''}`,
          // pointerdown would otherwise start a drag before the click lands
          onpointerdown: (event) => event.stopPropagation(),
          onclick: (event) => { event.stopPropagation(); removeZone(zone.id); },
        }, '✕'));
      placeZone(zone, node);
      return node;
    }));
  }

  function beginDrag(event, zone, node, mode) {
    event.preventDefault();
    event.stopPropagation();
    select(zone.id);
    const box = img.getBoundingClientRect();
    const width = img.clientWidth || 1;
    const height = img.clientHeight || 1;

    const move = (ev) => {
      const px = ev.clientX - box.left;
      const py = ev.clientY - box.top;
      if (mode === 'move') {
        zone.x = Math.max(0, Math.min(100, px / width * 100));
        zone.y = Math.max(0, Math.min(100, py / height * 100));
      } else {
        const centre = makeMapper(img)(zone.x, zone.y);
        // Twice the centre-to-handle distance, because `radius` is a diameter.
        zone.radius = Math.max(20, Math.hypot(px - centre.x, py - centre.y) * 2);
      }
      placeZone(zone, node);          // move the one node, do not rebuild the layer
    };
    const end = () => {
      removeEventListener('pointermove', move);
      removeEventListener('pointerup', end);
      removeEventListener('pointercancel', end);
      saveNow();
    };
    addEventListener('pointermove', move);
    addEventListener('pointerup', end);
    addEventListener('pointercancel', end);
  }

  /* --------------------------------------------------------- zone actions -- */

  function select(zid) {
    selectedId = zid;
    renderZones();
    renderPanel();
  }

  function addZone(xPercent = 50, yPercent = 50) {
    if (!hasImage()) {
      msg.replaceChildren(notice(t('needPicture')));
      return;
    }
    const zone = {
      id: `z${Date.now()}${Math.floor(Math.random() * 1000)}`,
      x: Math.max(0, Math.min(100, xPercent)),
      y: Math.max(0, Math.min(100, yPercent)),
      radius: 220,
      volume: DEFAULT_VOLUME,
      startTime: 0,
      endTime: 0,
      // A built-in tone by default, so a new spot makes a sound immediately
      // instead of being silently empty until a file is attached.
      type: 'generated',
      sound_name: 'Beep',
      url: null,
      effects: { reverbLevel: 0, pitch: 0, lowFreq: 0, midFreq: 0, highFreq: 0, isReversed: false },
    };
    model.zones.push(zone);
    msg.replaceChildren();
    select(zone.id);
    saveNow();
  }

  function removeZone(zid) {
    model.zones = model.zones.filter((z) => z.id !== zid);
    if (selectedId === zid) selectedId = null;
    renderZones();
    renderPanel();
    saveNow();
  }

  // Clicking bare image adds a spot there. This is a shortcut; the button in
  // the toolbar is the discoverable path, and the hint below the stage says so.
  img.addEventListener('click', (event) => {
    if (event.target !== img || !hasImage()) return;
    const box = img.getBoundingClientRect();
    const width = img.clientWidth || 1;
    const height = img.clientHeight || 1;
    addZone((event.clientX - box.left) / width * 100,
            (event.clientY - box.top) / height * 100);
  });

  /* ---------------------------------------------------------------- image -- */

  const imageInput = el('input', {
    type: 'file', accept: 'image/*', class: 'hidden',
    onchange: async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      status.textContent = t('uploading');
      try {
        const up = await api.upload('image', file);
        model.imagePath = up.path;
        img.src = up.url;
        msg.replaceChildren();
        await saveNow();
        renderPanel();
      } catch (err) {
        status.textContent = '';
        msg.replaceChildren(notice(err.message));
      }
    },
  });

  /* ---------------------------------------------------------------- panel -- */

  function slider(labelKey, value, min, max, step, onInput, suffix = '') {
    const out = el('span', {}, String(value) + suffix);
    return el('div', { class: 'slider-row' },
      el('label', {}, el('span', {}, t(labelKey)), out),
      el('input', {
        type: 'range', min, max, step, value,
        oninput: (e) => { out.textContent = e.target.value + suffix; onInput(Number(e.target.value)); },
        onchange: saveNow,
      }));
  }

  function zoneListItem(zone) {
    return el('button', {
      class: `zone-row${selectedId === zone.id ? ' is-active' : ''}`,
      type: 'button',
      onclick: () => select(zone.id),
    },
      el('span', { class: 'zone-row-name' }, zone.sound_name || t('sound')),
      el('span', { class: 'zone-row-kind' },
        zone.type === 'generated' ? t('generated') : (zone.url ? t('record') : t('noSoundYet'))));
  }

  function renderPanel() {
    const list = el('div', { class: 'zone-list' },
      ...(model.zones.length
        ? model.zones.map(zoneListItem)
        : [el('p', { class: 'muted' }, hasImage() ? t('noZonesYet') : t('needPicture'))]));

    const header = el('div', {},
      el('h2', {}, `${t('zones')} (${model.zones.length})`),
      el('button', {
        class: 'btn btn-primary', type: 'button',
        disabled: !hasImage(),
        onclick: () => addZone(),
      }, '＋ ' + t('addZone')),
      list);

    const zone = selectedId ? zoneById(selectedId) : null;
    if (!zone) {
      panel.replaceChildren(header);
      return;
    }

    panel.replaceChildren(header,
      el('hr', { class: 'sep' }),
      el('div', { class: 'field' },
        el('label', { for: 'zname' }, t('zoneName')),
        el('input', {
          type: 'text', id: 'zname', value: zone.sound_name || '',
          oninput: (e) => {
            zone.sound_name = e.target.value;
            const node = layer.querySelector(`[data-zone="${zone.id}"] .zone-label`);
            if (node) node.textContent = e.target.value;
            saveSoon();
          },
        })),
      buildSoundPicker(zone, async () => { await saveNow(); renderZones(); renderPanel(); },
                       (err) => msg.replaceChildren(notice(err))),
      slider('volume', Math.round((zone.volume ?? DEFAULT_VOLUME) * 100), 0, 100, 1,
        (v) => { zone.volume = v / 100; }, '%'),
      slider('reverb', zone.effects.reverbLevel || 0, 0, 100, 1,
        (v) => { zone.effects.reverbLevel = v; }, '%'),
      slider('pitch', zone.effects.pitch || 0, -12, 12, 1,
        (v) => { zone.effects.pitch = v; }),
      slider('lowFreq', zone.effects.lowFreq || 0, -20, 20, 0.5,
        (v) => { zone.effects.lowFreq = v; }),
      slider('midFreq', zone.effects.midFreq || 0, -20, 20, 0.5,
        (v) => { zone.effects.midFreq = v; }),
      slider('highFreq', zone.effects.highFreq || 0, -20, 20, 0.5,
        (v) => { zone.effects.highFreq = v; }),
      el('button', {
        class: 'btn btn-danger', type: 'button',
        onclick: () => removeZone(zone.id),
      }, t('removeZone')));
  }

  /* ----------------------------------------------------------------- mount -- */

  const relayout = () => renderZones();
  img.addEventListener('load', relayout);
  if (img.complete && img.naturalWidth) relayout();
  addEventListener('resize', relayout, { passive: true });

  renderPanel();

  show(el('div', { class: 'page' },
    el('div', { class: 'row' },
      el('a', { class: 'btn', href: '#/' }, t('back')),
      el('a', { class: 'btn', href: `#/play/${id}` }, t('open')),
      el('button', { class: 'btn', type: 'button', onclick: () => imageInput.click() },
        hasImage() ? t('changePicture') : t('choosePicture')),
      imageInput,
      el('button', {
        class: 'btn btn-primary', type: 'button',
        onclick: () => addZone(),
      }, '＋ ' + t('addZone')),
      el('span', { class: 'row-end' }, status),
      el('button', { class: 'btn btn-ok', type: 'button', onclick: saveNow }, t('save'))),
    msg,
    el('div', { class: 'field' },
      el('label', { for: 'cname' }, t('nameThis')), nameInput),
    el('p', { class: 'muted' }, hasImage() ? t('clickToAdd') : t('needPicture')),
    el('div', { class: 'editor-grid' }, stage, panel)));
}

/* ------------------------------------------------------------------ people */

async function viewPeople() {
  const { users } = await api.listUsers();
  const box = el('div', {});
  const nameInput = el('input', { type: 'text', id: 'pname' });
  const roleInput = el('select', { id: 'prole' },
    el('option', { value: 'user' }, t('roleUser')),
    el('option', { value: 'admin' }, t('roleAdmin')));

  const add = async (event) => {
    event.preventDefault();
    try {
      const res = await api.addUser({ name: nameInput.value.trim(), role: roleInput.value });
      const url = new URL(res.setup_url, location.origin).href.replace('/setup/', '/#/setup/');
      box.replaceChildren(el('div', { class: 'notice notice-ok' },
        el('p', {}, t('setupLink')),
        el('input', { type: 'text', value: url, readonly: true, onclick: (e) => e.target.select() })));
      nameInput.value = '';
      setTimeout(route, 50);
    } catch (err) { box.replaceChildren(notice(err.message)); }
  };

  show(el('div', { class: 'page' },
    el('h1', {}, t('people')),
    box,
    el('div', { class: 'card panel' },
      el('h2', {}, t('addPerson')),
      el('form', { onsubmit: add },
        el('div', { class: 'field' }, el('label', { for: 'pname' }, t('personName')), nameInput),
        el('div', { class: 'field' }, el('label', { for: 'prole' }, t('role')), roleInput),
        el('button', { class: 'btn btn-primary', type: 'submit' }, t('addPerson')))),
    el('div', { class: 'card', style: 'margin-top:20px;overflow-x:auto' },
      el('table', {},
        el('thead', {}, el('tr', {},
          el('th', {}, t('yourName')), el('th', {}, t('role')),
          el('th', {}, t('galleries')), el('th', {}, t('lastSeen')))),
        el('tbody', {}, ...users.map((u) => el('tr', {},
          el('td', {}, u.display_name),
          el('td', {}, u.role === 'admin' ? t('roleAdmin') : t('roleUser')),
          el('td', {}, String(u.canvases)),
          el('td', { class: 'muted' },
            u.needs_setup ? t('pending') : formatDate(u.last_seen_at)))))))));
}

/* ------------------------------------------------------------------ router */

async function route() {
  const hash = location.hash.replace(/^#/, '') || '/';
  const setupMatch = hash.match(/^\/setup\/(.+)$/);
  renderNav();

  if (setupMatch) { viewSetup(setupMatch[1]); return; }
  if (!state.user) { viewLogin(); return; }

  try {
    const play = hash.match(/^\/play\/(.+)$/);
    const edit = hash.match(/^\/edit\/(.+)$/);
    if (play) await viewPlay(play[1]);
    else if (edit) await viewEdit(edit[1]);
    else if (hash === '/people' && state.user.role === 'admin') await viewPeople();
    else await viewGallery();
  } catch (err) {
    if (err.status === 401) { state.user = null; viewLogin(err.message); return; }
    show(el('div', { class: 'page' }, notice(err.message || t('somethingWrong'))));
  }
}

addEventListener('hashchange', route);

(async function start() {
  const gaps = auditKeys();
  if (Object.keys(gaps).length) console.warn('[i18n] incomplete translations', gaps);
  try {
    const me = await api.me();
    if (me.user) { state.user = me.user; setCsrf(me.csrf); }
  } catch (_) { /* not signed in */ }
  route();
})();
