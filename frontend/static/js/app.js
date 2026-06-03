// ============ STATE ============
const State = {
  token:    localStorage.getItem('tt_token') || null,
  user:     null,
  settings: { name: 'Tether', currency: 'USD', logo_url: '', accent_color: '#d4f034', mode: 'tenant' },
  branding: null,   // public branding from /api/public/branding
  route:    'dashboard',
  param:    null,
};

function isMSP()   { return !!State.user?.is_msp_staff; }
function can(perm) { return isMSP() || (State.user?.permissions || []).includes(perm); }

// ============ API ============
async function api(path, opts = {}) {
  const headers = opts.headers || {};
  if (State.token) headers['Authorization'] = `Bearer ${State.token}`;
  if (opts.json) { headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(opts.json); }
  const res = await fetch('/api' + path, { ...opts, headers });
  if (res.status === 401) { logout(); throw new Error('Session expired'); }
  if (!res.ok) {
    let msg = 'Request failed';
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res;
}

// ============ AUTH ============
async function login(email, password) {
  const res = await fetch('/api/auth/login', {
    method: 'POST', body: new URLSearchParams({ username: email, password }),
  });
  if (!res.ok) {
    let msg = 'Incorrect email or password';
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  State.token = (await res.json()).access_token;
  localStorage.setItem('tt_token', State.token);
  await boot();
}

function logout() {
  State.token = null; State.user = null;
  localStorage.removeItem('tt_token');
  renderLogin();
}

// ============ TOAST ============
function toast(msg, type = 'ok') {
  const root = document.getElementById('toast-root');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `${icon(type === 'ok' ? 'check' : 'alert', 16)}<span>${esc(msg)}</span>`;
  root.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; setTimeout(() => el.remove(), 300); }, 3200);
}

// ============ MODAL ============
function openModal(html, wide = false) {
  document.getElementById('modal-root').innerHTML =
    `<div class="modal-overlay" onclick="if(event.target===this)closeModal()">
       <div class="modal${wide ? ' wide' : ''}">${html}</div>
     </div>`;
}
function closeModal() { document.getElementById('modal-root').innerHTML = ''; }

// ============ HELPERS ============
function esc(s) {
  return (s ?? '').toString().replace(/[&<>"]/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
function money(v) {
  if (v == null) return '—';
  const sym = { USD: '$', EUR: '€', GBP: '£', CAD: 'C$', AUD: 'A$', JPY: '¥', INR: '₹' }[State.settings.currency] || '';
  return sym + Number(v).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}
function fmtDate(s) {
  if (!s) return '—';
  return new Date(s).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}
function timeAgo(s) {
  const diff = (new Date() - new Date(s)) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  if (diff < 604800) return Math.floor(diff / 86400) + 'd ago';
  return fmtDate(s);
}
const STATUSES = ['available', 'deployed', 'maintenance', 'retired'];
function statusBadge(s) { return `<span class="badge ${s}">${s}</span>`; }
function applyAccent(color) {
  if (color) document.documentElement.style.setProperty('--accent', color);
}

// ============ ROUTER ============
function navigate(route, param = null) {
  State.route = route; State.param = param;
  window.location.hash = param ? `${route}/${param}` : route;
  renderApp();
}
function parseHash() {
  const h = window.location.hash.replace('#', '');
  if (!h) return { route: 'dashboard', param: null };
  const [route, ...rest] = h.split('/');
  return { route, param: rest.join('/') || null };
}
window.addEventListener('hashchange', () => {
  if (!State.token) return;
  const { route, param } = parseHash();
  State.route = route; State.param = param;
  renderApp();
});

// ============ BOOT ============
async function boot() {
  try {
    [State.user, State.settings] = await Promise.all([api('/auth/me'), api('/settings')]);
    applyAccent(State.settings.accent_color);
    const { route, param } = parseHash();
    State.route = route; State.param = param;
    renderApp();
  } catch (e) { logout(); }
}

async function fetchBranding() {
  try {
    State.branding = await (await fetch('/api/public/branding')).json();
    applyAccent(State.branding.accent_color);
  } catch (_) {
    State.branding = { name: 'Tether', logo_url: '', accent_color: '#d4f034', is_tenant: false };
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  await fetchBranding();
  // Signup page
  if (path === '/signup') {
    renderSignupPage();
    return;
  }

  // Check if this is a password reset URL
  const path = window.location.pathname;
  if (path.startsWith('/reset-password/')) {
    renderPasswordResetPage(path.split('/reset-password/')[1]);
    return;
  }
  if (path === '/forgot-password') {
    renderForgotPasswordPage();
    return;
  }

  // Check if this is an invite URL: /invite/<token>
  if (path.startsWith('/invite/')) {
    const token = path.split('/invite/')[1];
    renderInviteAccept(token);
    return;
  }
  if (State.token) boot(); else renderLogin();
});
