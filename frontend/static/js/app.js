// ============ STATE ============
const State = {
  token:    localStorage.getItem('tt_token') || null,
  user:     null,
  settings: { name: 'Tether', currency: 'USD', logo_url: '', accent_color: '#d4f034', mode: 'tenant' },
  branding: null,   // public branding from /api/public/branding
  demo:     null,   // demo credentials from /api/public/demo (null when not in demo mode)
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

  // Keep tenant context in local MSP flows where UI uses ?tenant=<slug>.
  const tenantParam = new URLSearchParams(window.location.search).get('tenant');
  let apiPath = path;
  if (tenantParam) {
    const joiner = apiPath.includes('?') ? '&' : '?';
    apiPath = `${apiPath}${joiner}tenant=${encodeURIComponent(tenantParam)}`;
  }

  const res = await fetch('/api' + apiPath, { ...opts, headers });
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

// ============ LEGACY INLINE ACTION DISPATCHER ============
// Existing views render many onclick attributes. Under strict CSP we block
// inline execution and route click handling through this external script.
function _splitActionArgs(raw) {
  const out = [];
  let cur = '';
  let quote = null;
  let depth = 0;

  for (let i = 0; i < raw.length; i++) {
    const ch = raw[i];
    const prev = i > 0 ? raw[i - 1] : '';

    if (quote) {
      cur += ch;
      if (ch === quote && prev !== '\\') quote = null;
      continue;
    }

    if (ch === '"' || ch === "'") {
      quote = ch;
      cur += ch;
      continue;
    }
    if (ch === '(') { depth++; cur += ch; continue; }
    if (ch === ')') { depth = Math.max(0, depth - 1); cur += ch; continue; }

    if (ch === ',' && depth === 0) {
      out.push(cur.trim());
      cur = '';
      continue;
    }
    cur += ch;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

function _parseActionArg(token) {
  if (token === 'null') return null;
  if (token === 'true') return true;
  if (token === 'false') return false;
  if (/^-?\d+(\.\d+)?$/.test(token)) return Number(token);
  if ((token.startsWith('"') && token.endsWith('"')) ||
      (token.startsWith("'") && token.endsWith("'"))) {
    return token.slice(1, -1)
      .replace(/\\'/g, "'")
      .replace(/\\\"/g, '"')
      .replace(/\\n/g, '\n')
      .replace(/\\r/g, '\r')
      .replace(/\\t/g, '\t')
      .replace(/\\\\/g, '\\');
  }
  // Identifier (e.g. pageTeam, currentBillingInterval)
  if (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(token)) {
    if (token in window) return window[token];
    return undefined;
  }
  throw new Error(`Unsupported action token: ${token}`);
}

function _runInlineAction(code, event, el) {
  // Keep overlay close behavior used by modal markup.
  if (code === 'if(event.target===this)closeModal()') {
    if (event.target === el) closeModal();
    return;
  }

  const m = code.match(/^([A-Za-z_$][A-Za-z0-9_$]*)\((.*)\)\s*;?$/);
  if (!m) throw new Error(`Unsupported action expression: ${code}`);

  const fnName = m[1];
  const argsRaw = m[2].trim();
  const fn = window[fnName];
  if (typeof fn !== 'function') throw new Error(`Action function not found: ${fnName}`);

  const args = argsRaw ? _splitActionArgs(argsRaw).map(_parseActionArg) : [];
  fn.apply(window, args);
}

document.addEventListener('click', (event) => {
  const el = event.target.closest('[onclick]');
  if (!el) return;
  const code = (el.getAttribute('onclick') || '').trim();
  if (!code) return;

  event.preventDefault();
  event.stopPropagation();

  try {
    _runInlineAction(code, event, el);
  } catch (err) {
    console.error('Action dispatch error:', err, code);
  }
}, true);

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
    [State.branding, State.demo] = await Promise.all([
      fetch('/api/public/branding').then(r => r.json()),
      fetch('/api/public/demo').then(r => r.json()).catch(() => ({ enabled: false })),
    ]);
    applyAccent(State.branding.accent_color);
  } catch (_) {
    State.branding = { name: 'Tether', logo_url: '', accent_color: '#d4f034', is_tenant: false };
    State.demo     = { enabled: false };
  }
}

async function loginAsDemo(role) {
  const creds = role === 'msp' ? State.demo?.msp : State.demo?.client;
  if (!creds) return;
  const btn = document.getElementById(`demo-btn-${role}`);
  if (btn) { btn.disabled = true; btn.textContent = 'Signing in…'; }
  try { await login(creds.email, creds.password); }
  catch (err) { toast(err.message, 'err'); if (btn) { btn.disabled = false; btn.textContent = role === 'msp' ? 'MSP Admin' : 'Client User'; } }
}

document.addEventListener('DOMContentLoaded', async () => {
  await fetchBranding();

  // Consume a preview token from the URL (set by previewAsClient()).
  // Stored only in State — not localStorage — so it expires with the tab.
  const urlParams = new URLSearchParams(window.location.search);
  const previewToken = urlParams.get('preview_token');
  if (previewToken) {
    State.token = previewToken;
    urlParams.delete('preview_token');
    const qs = urlParams.toString();
    window.history.replaceState({}, '',
      window.location.pathname + (qs ? '?' + qs : '') + window.location.hash);
  }

  const path = window.location.pathname;

  // Signup page
  if (path === '/signup') {
    renderSignupPage();
    return;
  }

  // Check if this is a password reset URL
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
