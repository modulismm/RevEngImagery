/* Thin API client. Carries the CSRF token on every mutating request. */

let csrf = '';

export function setCsrf(token) { csrf = token || ''; }

async function request(method, path, body, isForm) {
  const opts = { method, headers: {}, credentials: 'same-origin' };
  if (method !== 'GET') opts.headers['X-CSRF-Token'] = csrf;
  if (body !== undefined) {
    if (isForm) opts.body = body;
    else { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  }
  const res = await fetch(path, opts);
  let data = null;
  try { data = await res.json(); } catch (_) { /* empty body is fine */ }
  if (!res.ok) {
    const err = new Error((data && data.error) || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

export const api = {
  me: () => request('GET', '/api/me'),
  login: (name, passphrase, trusted) =>
    request('POST', '/api/login', { name, passphrase, trusted }),
  logout: () => request('POST', '/api/logout'),
  setup: (token, passphrase) => request('POST', `/api/setup/${token}`, { passphrase }),
  changePassphrase: (current, passphrase) =>
    request('POST', '/api/passphrase', { current, passphrase }),

  listCanvases: (all) => request('GET', `/api/canvases${all ? '?all=1' : ''}`),
  getCanvas: (id) => request('GET', `/api/canvases/${id}`),
  createCanvas: (data) => request('POST', '/api/canvases', data),
  updateCanvas: (id, data) => request('PUT', `/api/canvases/${id}`, data),
  deleteCanvas: (id) => request('DELETE', `/api/canvases/${id}`),

  listGalleries: () => request('GET', '/api/galleries'),
  createGallery: (data) => request('POST', '/api/galleries', data),
  updateGallery: (id, data) => request('PUT', `/api/galleries/${id}`, data),
  deleteGallery: (id) => request('DELETE', `/api/galleries/${id}`),
  galleryPublic: (slug) => request('GET', `/api/g/${slug}`),
  galleryUnlock: (slug, pin) => request('POST', `/api/g/${slug}/unlock`, { pin }),
  galleryCanvases: (slug) => request('GET', `/api/g/${slug}/canvases`),
  galleryJoin: (slug, data) => request('POST', `/api/g/${slug}/join`, data),
  resetUser: (id) => request('POST', `/api/users/${id}/reset`),
  exportUser: (id) => request('GET', `/api/users/${id}/export`),
  deleteUser: (id) => request('DELETE', `/api/users/${id}`),

  listUsers: () => request('GET', '/api/users'),
  addUser: (data) => request('POST', '/api/users', data),

  upload(kind, file) {
    const fd = new FormData();
    fd.append('file', file);
    return request('POST', `/api/upload/${kind}`, fd, true);
  },
};
