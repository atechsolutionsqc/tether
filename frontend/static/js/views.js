// ============ WHITE-LABEL LOGIN ============
function renderLogin() {
  const b = State.branding || {};
  const isTenant = b.is_tenant;
  const name  = esc(b.name || 'Tether');
  const logo  = b.logo_url;

  const logoHtml = logo
    ? `<img src="${esc(logo)}" alt="${name}" style="max-height:48px;max-width:160px;object-fit:contain;margin-bottom:6px">`
    : `<div class="login-logo"><div class="mark"><span></span></div><b>${name}</b></div>`;

  const demoHtml = State.demo?.enabled ? `
    <div class="demo-divider"><span>or try the demo</span></div>
    <div class="demo-btns">
      <button id="demo-btn-client" class="btn btn-ghost demo-btn" onclick="loginAsDemo('client')">
        ${icon('users', 14)} Client User
      </button>
      <button id="demo-btn-msp" class="btn btn-ghost demo-btn" onclick="loginAsDemo('msp')">
        ${icon('layers', 14)} MSP Admin
      </button>
    </div>` : '';

  document.getElementById('app').innerHTML = `
    <div class="login-wrap">
      <div class="login-card">
        ${logoHtml}
        <h1>Welcome back</h1>
        <p class="sub">${isTenant ? `Sign in to ${name}` : 'Sign in to manage your IT assets.'}</p>
        <form id="login-form">
          <div class="field"><label>Email</label>
            <input name="email" type="email" autocomplete="username"
              placeholder="${isTenant ? 'you@' + esc(b.slug||'yourcompany') + '.com' : 'admin@usetether.ca'}" required></div>
          <div class="field"><label>Password</label>
            <input name="password" type="password" autocomplete="current-password" required></div>
          <button class="btn btn-primary" style="width:100%;justify-content:center;padding:11px" type="submit">
            Sign in
          </button>
          <div style="text-align:center;margin-top:12px">
            <a href="/forgot-password" style="font-size:13px;color:var(--text-muted)">Forgot your password?</a>
          </div>
        </form>
        ${demoHtml}
      </div>
      ${!isTenant ? '' : `<p style="margin-top:16px;font-size:12px;color:rgba(255,255,255,.35);text-align:center">
        Powered by Tether</p>`}
    </div>`;

  document.getElementById('login-form').onsubmit = async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector('button');
    btn.disabled = true; btn.textContent = 'Signing in…';
    const f = new FormData(e.target);
    try { await login(f.get('email'), f.get('password')); }
    catch (err) { toast(err.message, 'err'); btn.disabled = false; btn.textContent = 'Sign in'; }
  };
}

// ============ TOTP CHALLENGE PAGE ============
function renderTotpChallenge(totpToken) {
  document.getElementById('app').innerHTML = `
    <div class="login-wrap">
      <div class="login-card">
        <div class="login-logo"><div class="mark"><span></span></div><b>Tether</b></div>
        <h1>Two-factor authentication</h1>
        <p class="sub">Enter the 6-digit code from your authenticator app.</p>
        <form id="totp-challenge-form">
          <div class="field"><label>Authenticator code</label>
            <input name="code" type="text" inputmode="numeric" pattern="[0-9]*"
              autocomplete="one-time-code" maxlength="8" placeholder="000000" required
              style="letter-spacing:4px;font-size:22px;text-align:center"></div>
          <button class="btn btn-primary" style="width:100%;justify-content:center;padding:11px" type="submit">
            Verify
          </button>
          <div style="text-align:center;margin-top:12px">
            <a href="#" style="font-size:13px;color:var(--text-muted)" onclick="renderLogin();return false">Back to login</a>
          </div>
        </form>
      </div>
    </div>`;

  document.getElementById('totp-challenge-form').onsubmit = async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector('button');
    btn.disabled = true; btn.textContent = 'Verifying…';
    const code = new FormData(e.target).get('code').replace(/\s/g, '');
    try {
      const res = await fetch('/api/auth/totp/authenticate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ totp_token: totpToken, code }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Invalid code');
      }
      const data = await res.json();
      State.token = data.access_token;
      localStorage.setItem('tt_token', State.token);
      await boot();
    } catch (err) {
      toast(err.message, 'err');
      btn.disabled = false; btn.textContent = 'Verify';
    }
  };

  // Auto-focus the code input
  document.querySelector('#totp-challenge-form input[name=code]')?.focus();
}

// ============ INVITE ACCEPT PAGE ============
async function renderInviteAccept(token) {
  const app = document.getElementById('app');
  app.innerHTML = `<div class="login-wrap"><div class="login-card">
    <div class="loading"><div class="spinner"></div></div></div></div>`;

  let inv;
  try {
    inv = await (await fetch('/api/invites/validate/' + token)).json();
    if (!inv.email) throw new Error('Invalid invite');
  } catch (e) {
    app.innerHTML = `<div class="login-wrap"><div class="login-card">
      <div class="login-logo"><div class="mark"><span></span></div><b>Tether</b></div>
      <h1>Invalid invite</h1>
      <p class="sub" style="color:var(--red)">This invite link is invalid, expired or has already been used.</p>
      <button class="btn btn-primary" style="width:100%;justify-content:center;margin-top:16px" onclick="renderLogin()">Go to login</button>
    </div></div>`;
    return;
  }

  applyAccent(inv.tenant_accent);
  const logo = inv.tenant_logo
    ? `<img src="${esc(inv.tenant_logo)}" alt="${esc(inv.tenant_name)}" style="max-height:48px;max-width:160px;object-fit:contain;margin-bottom:6px">`
    : `<div class="login-logo"><div class="mark"><span></span></div><b>${esc(inv.tenant_name)}</b></div>`;

  app.innerHTML = `
    <div class="login-wrap">
      <div class="login-card">
        ${logo}
        <h1>You're invited</h1>
        <p class="sub">Set up your account for <b>${esc(inv.tenant_name)}</b>.<br>
          <span style="color:var(--text-faint);font-size:12px">Role: ${esc(inv.role_name)}</span></p>
        <form id="invite-form">
          <div class="field"><label>Your name</label>
            <input name="name" value="${esc(inv.name)}" placeholder="Jane Smith" required></div>
          <div class="field"><label>Email</label>
            <input type="email" value="${esc(inv.email)}" readonly
              style="background:var(--bg);color:var(--text-muted)"></div>
          <div class="field"><label>Choose a password</label>
            <input name="password" type="password" required minlength="6" placeholder="Min. 6 characters"></div>
          <div class="field"><label>Confirm password</label>
            <input name="confirm" type="password" required minlength="6"></div>
          <button class="btn btn-primary" style="width:100%;justify-content:center;padding:11px" type="submit">
            Create account
          </button>
        </form>
      </div>
    </div>`;

  document.getElementById('invite-form').onsubmit = async (e) => {
    e.preventDefault();
    const f  = new FormData(e.target);
    const pw = f.get('password'), c = f.get('confirm');
    if (pw !== c) return toast('Passwords do not match', 'err');
    const btn = e.target.querySelector('button');
    btn.disabled = true; btn.textContent = 'Creating account…';
    try {
      await (await fetch('/api/invites/accept', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, name: f.get('name'), password: pw }),
      })).json();
      toast('Account created! Please sign in.');
      setTimeout(() => { window.location.href = '/'; }, 1200);
    } catch (err) { toast(err.message || 'Failed', 'err'); btn.disabled = false; btn.textContent = 'Create account'; }
  };
}

// ============ SHELL ============
function buildNav() {
  const msp = [
    { id: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
    { id: 'clients',   label: 'Clients',   icon: 'layers' },
    { id: 'msp-users', label: 'Users',     icon: 'users' },
    { id: 'reports',   label: 'Reports',   icon: 'activity' },
    { id: 'billing',   label: 'Plan',      icon: 'dollar' },
    { id: 'settings',  label: 'Settings',  icon: 'settings' },
    { id: 'system',    label: 'System',    icon: 'server' },
  ];
  const client = [
    { id: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
    { id: 'assets',    label: 'Assets',    icon: 'box' },
    { id: 'licences',  label: 'Licences',  icon: 'layers' },
    { id: 'requests',  label: 'Requests',  icon: 'activity' },
    { id: 'categories',label: 'Categories',icon: 'layers' },
    { id: 'locations', label: 'Locations', icon: 'pin' },
    { id: 'employees', label: 'People',    icon: 'users' },
    { id: 'reports',   label: 'Reports',   icon: 'activity' },
  ];
  if (can('users.manage')) client.push({ id: 'team', label: 'Team', icon: 'lock' });
  client.push({ id: 'settings', label: 'Settings', icon: 'settings' });
  const tenantScoped = State.settings?.mode === 'tenant';
  return (isMSP() && !tenantScoped) ? msp : client;
}

function renderApp() {
  // client_viewer (no assets.create) gets the simplified portal
  if (!isMSP() && !can('assets.create')) {
    renderClientPortal();
    return;
  }

  const u   = State.user;
  const nav = buildNav();
  const initial = (u?.name || '?')[0].toUpperCase();

  const navHtml = nav.map(n => `
    <a class="${State.route === n.id ? 'active' : ''}" onclick="navigate('${n.id}')">
      ${icon(n.icon, 18)}${n.label}
    </a>`).join('');

  const logoHtml = State.settings?.logo_url
    ? `<img src="${esc(State.settings.logo_url)}" alt="${esc(State.settings.name)}"
         style="max-height:32px;max-width:130px;object-fit:contain">`
    : `<div class="brand"><div class="mark"><span></span></div>
         <b>${esc(State.settings?.name || 'Tether')}</b>
         ${isMSP() ? '<span class="msp-pill">MSP</span>' : ''}
       </div>`;

  document.getElementById('app').innerHTML = `
    <div class="scrim" id="scrim" onclick="toggleSidebar(false)"></div>
    <div class="shell">
      <aside class="sidebar" id="sidebar">
        <div class="brand-wrap">${logoHtml}</div>
        ${isMSP() ? `<div class="sidebar-context">
          <div class="ctx-label">Viewing</div>
          <div class="ctx-val">${esc(State.settings?.name || 'All Clients')}</div>
          ${State.settings?.mode === 'tenant' ? `
            <button class="btn btn-ghost btn-sm back-to-msp" onclick="backToMsp()">
              ${icon('back', 13)} All Clients
            </button>` : ''}
        </div>` : ''}
        <nav class="nav">${navHtml}</nav>
        <div class="sidebar-foot">
          <div class="who">
            <div class="avatar">${initial}</div>
            <div>
              <b style="color:#fff;font-size:13px">${esc(u?.name || '')}</b>
              <small>${esc(u?.role || '')}</small>
            </div>
          </div>
          <button class="theme-toggle" onclick="toggleDarkMode()" title="Toggle dark mode">${icon('moon', 15)} Dark mode</button>
          <button class="theme-toggle" onclick="_showShortcutHelp()" title="Keyboard shortcuts">${icon('command', 15)} Shortcuts</button>
          <button class="logout-btn" onclick="logout()">${icon('logout', 16)}Sign out</button>
        </div>
      </aside>
      <main class="main">
        <div class="mobile-bar">
          <button onclick="toggleSidebar(true)">${icon('menu', 20)}</button>
          <b style="font-family:var(--display);font-size:18px">${esc(State.settings?.name || 'Tether')}</b>
        </div>
        ${State.demo?.enabled ? `
        <div class="demo-banner">
          ${icon('eye', 15)} Demo mode — data resets hourly.
          <button class="btn btn-ghost btn-sm" style="margin-left:auto" onclick="logout()">Sign out</button>
        </div>` : ''}
        <div id="page"></div>
      </main>
    </div>`;

  const routes = {
    dashboard:  pageDashboard,
    clients:    pageClients,
    'msp-users':pageMspUsers,
    billing:    pageBilling,
    system:     pageAdmin,
    assets:     pageAssets,
    asset:      pageAssetDetail,
    requests:   pageRequests,
    categories: pageCategories,
    locations:  pageLocations,
    employees:  pageEmployees,
    team:       pageTeam,
    settings:   pageSettings,
    reports:             pageReports,
    'reports-warranty':  pageReportWarranty,
    'reports-value':     pageReportValue,
    'reports-depreciation': pageReportDepreciation,
    'reports-age':       pageReportsAge,
    licences:   pageLicences,
    activity:   pageActivity,
  };
  (routes[State.route] || pageDashboard)();
  // Load usage bar asynchronously — non-blocking
  if (isMSP()) loadSidebarUsage();
}

// ============ CLIENT PORTAL ============

let _portalTab = 'overview';
let _portalAssets = [];
let _portalRequests = [];
let _portalEmployeeId = null;

async function renderClientPortal() {
  const u   = State.user;
  const s   = State.settings || {};
  const tenantName = esc(s.name || 'Your Company');

  const logoHtml = s.logo_url
    ? `<img src="${esc(s.logo_url)}" alt="${tenantName}"
         style="max-height:36px;max-width:150px;object-fit:contain">`
    : `<span style="font-family:var(--display);font-size:20px;font-weight:700;
                    color:var(--accent);letter-spacing:-.5px">${tenantName}</span>`;

  document.getElementById('app').innerHTML = `
    <div style="min-height:100vh;background:var(--bg);display:flex;flex-direction:column">
      <header style="background:var(--ink);padding:0 24px;height:56px;display:flex;
                     align-items:center;justify-content:space-between;flex-shrink:0">
        <div>${logoHtml}</div>
        <div style="display:flex;align-items:center;gap:14px">
          <span style="color:rgba(255,255,255,.65);font-size:13.5px">${esc(u?.name || '')}</span>
          <button class="btn btn-ghost btn-sm" style="color:rgba(255,255,255,.7)"
            onclick="logout()">${icon('logout', 14)} Sign out</button>
        </div>
      </header>
      <nav id="portal-nav" style="background:var(--ink);border-top:1px solid rgba(255,255,255,.08);
           padding:0 24px;display:flex;gap:0">
        ${['overview','my-assets','requests'].map(t => `
          <button id="ptab-${t}" onclick="portalSwitchTab('${t}')"
            style="background:none;border:none;border-bottom:2px solid ${_portalTab===t?'var(--accent)':'transparent'};
                   color:${_portalTab===t?'var(--accent)':'rgba(255,255,255,.55)'};
                   padding:12px 18px;font-size:13.5px;font-weight:${_portalTab===t?'600':'400'};
                   cursor:pointer;transition:color .15s,border-color .15s">
            ${t==='overview'?'Overview':t==='my-assets'?'My Assets':'Requests'}
          </button>`).join('')}
      </nav>
      <div id="portal-body" style="flex:1;padding:28px 24px;max-width:960px;width:100%;margin:0 auto">
        <div class="loading"><div class="spinner"></div></div>
      </div>
    </div>`;

  await _portalLoad();
}

async function _portalLoad() {
  try {
    const [assets, requests, empsResp] = await Promise.all([
      api('/assets?limit=200'),
      api('/requests'),
      api('/employees'),
    ]);
    _portalAssets   = assets.items || assets;
    _portalRequests = requests;
    const employees = empsResp.items ?? empsResp;

    // Find employee record matching the logged-in user's email
    const myEmail = (State.user?.email || '').toLowerCase();
    const emp = employees.find(e => (e.email || '').toLowerCase() === myEmail);
    _portalEmployeeId = emp?.id ?? null;
  } catch (e) {
    document.getElementById('portal-body').innerHTML =
      `<p style="color:var(--red)">${esc(e.message)}</p>`;
    return;
  }
  _portalRender();
}

function portalSwitchTab(tab) {
  _portalTab = tab;
  ['overview','my-assets','requests'].forEach(t => {
    const btn = document.getElementById('ptab-' + t);
    if (!btn) return;
    const active = t === tab;
    btn.style.borderBottomColor  = active ? 'var(--accent)' : 'transparent';
    btn.style.color              = active ? 'var(--accent)' : 'rgba(255,255,255,.55)';
    btn.style.fontWeight         = active ? '600' : '400';
  });
  _portalRender();
}

function _portalRender() {
  const body = document.getElementById('portal-body');
  if (!body) return;
  if (_portalTab === 'overview')   body.innerHTML = _portalOverview();
  if (_portalTab === 'my-assets')  body.innerHTML = _portalMyAssets();
  if (_portalTab === 'requests')   body.innerHTML = _portalRequests_html();
  _portalBindSearch();
}

function _myAssets() {
  if (_portalEmployeeId === null) return _portalAssets;
  return _portalAssets.filter(a => a.assigned_to_id === _portalEmployeeId);
}

function _portalOverview() {
  const u          = State.user;
  const s          = State.settings || {};
  const mine       = _myAssets();
  const openReqs   = _portalRequests.filter(r => r.status === 'open' || r.status === 'in_progress');

  const statCard = (label, value, ic) => `
    <div class="stat" style="flex:1;min-width:160px">
      <div class="label">${icon(ic, 15)}${label}</div>
      <div class="value">${value}</div>
    </div>`;

  const assetRows = mine.slice(0, 5).map(a => `
    <tr>
      <td><span class="tag">${esc(a.asset_tag)}</span></td>
      <td>${esc(a.name)}</td>
      <td><span class="badge ${esc(a.status)}">${esc(a.status)}</span></td>
      <td class="muted">${esc(a.location_name || '—')}</td>
    </tr>`).join('') || `<tr><td colspan="4" class="muted" style="padding:16px;text-align:center">No assets assigned to you.</td></tr>`;

  const reqRows = _portalRequests.slice(0, 3).map(r => `
    <div style="display:flex;align-items:center;justify-content:space-between;
                padding:10px 0;border-bottom:1px solid var(--border)">
      <div>
        <div style="font-weight:500;font-size:14px">${esc(r.title)}</div>
        <div class="muted" style="font-size:12px">${fmtDate(r.created_at)}</div>
      </div>
      <span class="badge ${REQ_STATUS_BADGE[r.status]||''}">${REQ_STATUS_LABELS[r.status]||r.status}</span>
    </div>`).join('') || `<p class="muted" style="padding:12px 0">No requests submitted yet.</p>`;

  return `
    <div style="margin-bottom:24px">
      <h2 style="font-size:22px;margin-bottom:4px">Hi ${esc(u?.name?.split(' ')[0] || 'there')},</h2>
      <p class="muted">here's ${esc(s.name || 'your company')}'s IT overview.</p>
    </div>
    <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:28px">
      ${statCard('Assets assigned to me', mine.length, 'box')}
      ${statCard('Open requests', openReqs.length, 'activity')}
    </div>
    <div class="panel" style="margin-bottom:20px">
      <div class="panel-head">
        <h3>Assets assigned to me</h3>
        ${mine.length > 5 ? `<button class="btn btn-ghost btn-sm" onclick="portalSwitchTab('my-assets')">View all</button>` : ''}
      </div>
      <div class="table-wrap" style="border:none;box-shadow:none">
        <table>
          <thead><tr><th>Tag</th><th>Name</th><th>Status</th><th>Location</th></tr></thead>
          <tbody>${assetRows}</tbody>
        </table>
      </div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <h3>Recent requests</h3>
        ${_portalRequests.length > 3 ? `<button class="btn btn-ghost btn-sm" onclick="portalSwitchTab('requests')">View all</button>` : ''}
      </div>
      <div style="padding:4px 0">${reqRows}</div>
    </div>`;
}

function _portalMyAssets() {
  const mine = _myAssets();

  const rows = mine.map(a => `
    <tr>
      <td><span class="tag">${esc(a.asset_tag)}</span></td>
      <td>${esc(a.name)}</td>
      <td><span class="badge ${esc(a.status)}">${esc(a.status)}</span></td>
      <td class="muted">${esc(a.category_name || '—')}</td>
      <td class="muted">${esc(a.location_name || '—')}</td>
      <td class="muted">${a.warranty_expiry ? fmtDate(a.warranty_expiry) : '—'}</td>
    </tr>`).join('') || `<tr><td colspan="6" class="muted" style="padding:32px;text-align:center">No assets assigned to you.</td></tr>`;

  return `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
      <h2 style="font-size:20px">My Assets</h2>
      <div style="display:flex;gap:10px;align-items:center">
        <input id="portal-asset-search" type="search" placeholder="Search…"
          style="padding:7px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);
                 font-size:13.5px;background:var(--surface);color:var(--text);width:200px"
          oninput="portalFilterAssets(this.value)">
        <button class="btn btn-accent btn-sm" onclick="_portalOpenRequestForm()">
          ${icon('plus', 14)} Request new asset
        </button>
      </div>
    </div>
    <div class="table-wrap">
      <table id="portal-asset-table">
        <thead><tr><th>Tag</th><th>Name</th><th>Status</th><th>Category</th><th>Location</th><th>Warranty</th></tr></thead>
        <tbody id="portal-asset-tbody">${rows}</tbody>
      </table>
    </div>`;
}

function _portalRequests_html() {
  const addBtn = `<button class="btn btn-accent btn-sm" onclick="_portalOpenRequestForm()">
    ${icon('plus', 14)} New Request</button>`;

  if (!_portalRequests.length) {
    return `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
        <h2 style="font-size:20px">Requests</h2>${addBtn}
      </div>
      <div class="table-wrap">
        <div class="empty">${icon('activity', 44)}<h3>No requests yet</h3>
          <p>Submit one to get started.</p>
          <button class="btn btn-accent" onclick="_portalOpenRequestForm()">${icon('plus', 15)} New Request</button>
        </div>
      </div>`;
  }

  const rows = _portalRequests.map(r => `
    <tr>
      <td>${esc(r.title)}</td>
      <td><span class="badge ${r.priority === 'urgent' ? 'retired' : r.priority === 'high' ? 'maintenance' : ''}"
        style="font-size:11.5px">${esc(r.priority || 'normal')}</span></td>
      <td><span class="badge ${REQ_STATUS_BADGE[r.status]||''}">${REQ_STATUS_LABELS[r.status]||r.status}</span></td>
      <td class="muted" style="font-size:12.5px">${fmtDate(r.created_at)}</td>
      <td class="muted" style="font-size:12.5px;max-width:220px">${esc(r.notes || '—')}</td>
    </tr>`).join('');

  return `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
      <h2 style="font-size:20px">Requests</h2>${addBtn}
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Title</th><th>Priority</th><th>Status</th><th>Date</th><th>MSP Notes</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function _portalBindSearch() {
  // Re-attach search handler after re-render (tab switch clears DOM)
  const inp = document.getElementById('portal-asset-search');
  if (inp) inp.oninput = () => portalFilterAssets(inp.value);
}

function portalFilterAssets(q) {
  const term = q.toLowerCase();
  const tbody = document.getElementById('portal-asset-tbody');
  if (!tbody) return;
  const mine = _myAssets();
  const filtered = term
    ? mine.filter(a =>
        a.asset_tag.toLowerCase().includes(term) ||
        a.name.toLowerCase().includes(term) ||
        (a.location_name || '').toLowerCase().includes(term) ||
        (a.category_name || '').toLowerCase().includes(term))
    : mine;

  tbody.innerHTML = filtered.map(a => `
    <tr>
      <td><span class="tag">${esc(a.asset_tag)}</span></td>
      <td>${esc(a.name)}</td>
      <td><span class="badge ${esc(a.status)}">${esc(a.status)}</span></td>
      <td class="muted">${esc(a.category_name || '—')}</td>
      <td class="muted">${esc(a.location_name || '—')}</td>
      <td class="muted">${a.warranty_expiry ? fmtDate(a.warranty_expiry) : '—'}</td>
    </tr>`).join('') || `<tr><td colspan="6" class="muted" style="padding:32px;text-align:center">No matching assets.</td></tr>`;
}

function _portalOpenRequestForm() {
  _openRequestFormImpl(async () => {
    const requests = await api('/requests');
    _portalRequests = requests;
    _portalRender();
  });
}

function _openRequestFormImpl(onSuccess) {
  openModal(`
    <div class="modal-head"><h2>New Request</h2>
      <button class="x-btn" onclick="closeModal()">✕</button></div>
    <form id="req-form"><div class="modal-body">
      <div class="field"><label>Title *</label>
        <input name="title" required placeholder="e.g. New laptop for onboarding"></div>
      <div class="field"><label>Priority</label>
        <select name="priority">
          <option value="low">Low</option>
          <option value="normal" selected>Normal</option>
          <option value="high">High</option>
          <option value="urgent">Urgent</option>
        </select></div>
      <div class="field"><label>Description</label>
        <textarea name="description" rows="3" style="resize:vertical"
          placeholder="Any additional details…"></textarea></div>
    </div>
    <div class="modal-foot">
      <button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button type="submit" class="btn btn-primary">Submit Request</button>
    </div></form>`);

  document.getElementById('req-form').onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      await api('/requests', { method: 'POST', json: {
        title:       f.get('title'),
        priority:    f.get('priority'),
        description: f.get('description') || '',
      }});
      closeModal();
      toast('Request submitted');
      if (onSuccess) await onSuccess();
    } catch (err) { toast(err.message, 'err'); }
  };
}

function toggleSidebar(open) {
  document.getElementById('sidebar').classList.toggle('open', open);
  document.getElementById('scrim').classList.toggle('show', open);
}

function pageHeader(title, crumb = '', actions = '') {
  return `<div class="topbar">
    <div>${crumb ? `<div class="crumb">${crumb}</div>` : ''}<h1>${title}</h1></div>
    <div style="display:flex;gap:10px;flex-wrap:wrap">${actions}</div>
  </div>`;
}
function loading() { return `<div class="loading"><div class="spinner"></div></div>`; }

// ============ MSP DASHBOARD ============
async function pageDashboard() {
  const page = document.getElementById('page');
  page.innerHTML = loading();
  let s;
  try { s = await api('/dashboard/stats'); } catch (e) { toast(e.message, 'err'); return; }
  s.mode === 'msp' ? renderMspDashboard(s) : renderTenantDashboard(s);
}

function renderMspDashboard(s) {
  const page = document.getElementById('page');
  // Inject billing banner if needed (uses cached usage data)
  const us = _usageCache;
  let banner = '';
  if (us && us.saas) {
    if (us.trial_expired) {
      banner = `<div class="billing-banner exceeded" style="margin-bottom:18px">${icon('alert',18)}
        <div><b>Your free trial has expired.</b> Assets are locked.
        <span class="usage-upgrade" style="display:inline-flex;margin-left:8px" onclick="navigate('billing')">
          Upgrade now ${icon('arrowOut',13)}</span></div></div>`;
    } else if (us.usage_status === 'exceeded') {
      banner = `<div class="billing-banner exceeded" style="margin-bottom:18px">${icon('alert',18)}
        <div><b>Asset limit reached (${us.total_assets}/${us.asset_limit}).</b>
        <span class="usage-upgrade" style="display:inline-flex;margin-left:8px" onclick="navigate('billing')">
          Upgrade ${icon('arrowOut',13)}</span></div></div>`;
    } else if (us.usage_status === 'warning') {
      banner = `<div class="billing-banner warn" style="margin-bottom:18px">${icon('alert',18)}
        <div>You've used <b>${us.usage_pct}%</b> of your ${us.asset_limit} asset limit.
        <span class="usage-upgrade" style="display:inline-flex;margin-left:8px;color:var(--amber)" onclick="navigate('billing')">
          View plan ${icon('arrowOut',13)}</span></div></div>`;
    } else if (us.tier === 'trial' && us.trial_days_left !== null) {
      banner = `<div class="billing-banner trial" style="margin-bottom:18px">${icon('alert',18)}
        <div><b>Free trial — ${us.trial_days_left} day${us.trial_days_left!==1?'s':''} remaining.</b>
        <span onclick="navigate('billing')" style="margin-left:8px;cursor:pointer;text-decoration:underline">
          View plans</span></div></div>`;
    }
  }
  const card = (label, val, ic, accent = false) => `
    <div class="stat ${accent ? 'stat-accent' : ''}">
      <div class="label">${icon(ic, 15)}${label}</div>
      <div class="value">${val}</div>
    </div>`;

  const rows = s.clients.map(c => `
    <tr id="client-row-${c.id}" class="client-summary-row" style="cursor:pointer" onclick="_toggleClientDrilldown(${c.id}, '${esc(c.slug)}', '${esc(c.name)}', this)">
      <td>
        <span style="display:inline-flex;align-items:center;gap:6px">
          <span id="drill-chevron-${c.id}" style="font-size:11px;color:var(--text-muted);transition:transform .15s">▶</span>
          <b>${esc(c.name)}</b>
          <span class="tag muted" style="font-size:11px">${esc(c.slug)}</span>
        </span>
      </td>
      <td>${c.total_assets}</td>
      <td>${c.deployed}</td>
      <td>$${c.total_value.toLocaleString()}</td>
      <td>${c.expiring_warranties > 0
        ? `<span style="color:var(--amber);font-weight:600">${c.expiring_warranties} expiring</span>`
        : '<span class="muted">—</span>'}</td>
      <td onclick="event.stopPropagation()">
        <button class="btn btn-ghost btn-sm" onclick="previewAsClient(${c.id},'${esc(c.slug)}')" title="Open in new tab as client">
          ${icon('arrowOut', 14)} Preview</button>
      </td>
    </tr>
    <tr id="drill-row-${c.id}" style="display:none">
      <td colspan="6" style="padding:0">
        <div id="drill-body-${c.id}" style="padding:14px 18px;background:var(--bg);border-top:1px solid var(--border)">
        </div>
      </td>
    </tr>`).join('');

  page.innerHTML = pageHeader('MSP Dashboard', 'All Clients') + banner + `
    <div class="stat-grid">
      ${card('Total Clients', s.total_clients, 'layers', true)}
      ${card('Total Assets',  s.total_assets, 'box')}
      ${card('Total Value',   '$' + s.total_value.toLocaleString(), 'dollar')}
      ${card('Expiring Soon', s.expiring_soon, 'alert')}
    </div>
    <div class="panel">
      <div class="panel-head">
        <h3>Client Overview</h3>
        <button class="btn btn-accent btn-sm" onclick="navigate('clients')">${icon('plus', 14)} New Client</button>
      </div>
      <div class="table-wrap" style="border:none;box-shadow:none">
        <table>
          <thead><tr><th>Client</th><th>Assets</th><th>Deployed</th><th>Value</th><th>Warranties</th><th></th></tr></thead>
          <tbody>${rows || '<tr><td colspan="6" style="text-align:center;padding:32px" class="muted">No clients yet.</td></tr>'}</tbody>
        </table>
      </div>
    </div>`;
}

const _drilldownOpen = new Set();

async function _toggleClientDrilldown(tid, slug, name) {
  const row   = document.getElementById(`drill-row-${tid}`);
  const body  = document.getElementById(`drill-body-${tid}`);
  const chev  = document.getElementById(`drill-chevron-${tid}`);
  if (!row || !body) return;

  if (_drilldownOpen.has(tid)) {
    // Collapse
    row.style.display = 'none';
    chev.style.transform = '';
    _drilldownOpen.delete(tid);
    return;
  }

  // Expand
  row.style.display = '';
  chev.style.transform = 'rotate(90deg)';
  _drilldownOpen.add(tid);
  body.innerHTML = `<div style="color:var(--text-muted);font-size:13px">Loading…</div>`;

  try {
    const d = await api(`/dashboard/client/${tid}`);
    const fmt = v => `$${Number(v || 0).toLocaleString()}`;
    const expRows = (d.expiring_warranties || []).map(w =>
      `<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:13px;border-bottom:1px solid var(--border)">
         <span><b>${esc(w.asset_tag)}</b> ${esc(w.name)}</span>
         <span style="color:var(--amber)">${w.warranty_expiry}</span>
       </div>`
    ).join('') || `<div style="font-size:13px;color:var(--text-muted);padding:4px 0">None expiring</div>`;

    const recentRows = (d.recent_activity || []).map(a =>
      `<div style="font-size:13px;padding:3px 0;color:var(--text-muted)">
         <b style="color:var(--text)">${esc(a.asset_tag)}</b> ${a.action === 'checkout' ? 'checked out' : 'checked in'}
         ${a.employee_name ? `to <b>${esc(a.employee_name)}</b>` : ''}
       </div>`
    ).join('') || `<div style="font-size:13px;color:var(--text-muted)">No recent activity</div>`;

    body.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <b style="font-size:15px">${esc(name)}</b>
        <div style="display:flex;gap:8px">
          <button class="btn btn-ghost btn-sm" onclick="previewAsClient(${tid},'${esc(slug)}')">${icon('arrowOut',13)} Open as client</button>
          <button class="btn btn-ghost btn-sm" onclick="jumpToClient('${esc(slug)}')">${icon('layers',13)} Switch to tenant</button>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px">
        ${[
          ['Total', d.total_assets, 'box'],
          ['Deployed', d.deployed, 'arrowOut'],
          ['Available', d.available, 'check'],
          ['Value', fmt(d.total_value), 'dollar'],
        ].map(([label, val, ic]) => `
          <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 12px">
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">${label}</div>
            <div style="font-size:20px;font-weight:700">${val}</div>
          </div>`).join('')}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:6px">Expiring Warranties</div>
          ${expRows}
        </div>
        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:6px">Recent Activity</div>
          ${recentRows}
        </div>
      </div>`;
  } catch(e) {
    body.innerHTML = `<span style="color:var(--red);font-size:13px">${esc(e.message)}</span>`;
  }
}

function renderTenantDashboard(s) {
  const page = document.getElementById('page');
  const card = (label, val, ic, accent = false) => `
    <div class="stat ${accent ? 'stat-accent' : ''}">
      <div class="label">${icon(ic, 15)}${label}</div>
      <div class="value">${val}</div>
    </div>`;

  const expiring = (s.expiring_warranties || []).length
    ? s.expiring_warranties.map(w => `
        <div class="expiring-row">
          <div><b>${esc(w.name)}</b> <span class="tag muted">${esc(w.asset_tag)}</span></div>
          <span class="w-date">${fmtDate(w.warranty_expiry)}</span>
        </div>`).join('')
    : `<p class="muted" style="padding:8px 0">No warranties expiring in the next 30 days.</p>`;

  const activity = (s.recent_activity || []).length
    ? `<ul class="timeline">${s.recent_activity.map(a => `
        <li>
          <div class="t-action">${a.action === 'checkout' ? 'Checked out' : 'Checked in'}
            <span class="tag">${esc(a.asset_tag)}</span></div>
          <div class="muted" style="font-size:13px">${esc(a.employee_name || 'Unassigned')}</div>
          <div class="t-time">${timeAgo(a.timestamp)}</div>
        </li>`).join('')}</ul>`
    : `<p class="muted" style="padding:8px 0">No activity yet.</p>`;

  const overdueCount = s.overdue_maintenance || 0;
  const upcomingMaint = (s.upcoming_maintenance || []).length
    ? `<ul class="timeline">${(s.upcoming_maintenance || []).map(m => `
        <li>
          <div class="t-action"><b>${esc(m.title)}</b>
            ${m.maintenance_type ? `<span class="tag muted">${esc(m.maintenance_type)}</span>` : ''}
            <a style="cursor:pointer;color:var(--accent)" onclick="navigate('asset',${m.asset_id})">${esc(m.asset_tag)}</a>
          </div>
          <div class="t-time">${fmtDate(m.due_date)}</div>
        </li>`).join('')}</ul>`
    : `<p class="muted" style="padding:8px 0">No maintenance due in the next 30 days.</p>`;

  page.innerHTML = pageHeader('Dashboard', esc(s.tenant_name || State.settings?.name || '')) + `
    <div class="stat-grid">
      ${card('Total Assets', s.total_assets, 'box', true)}
      ${card('Deployed',     s.deployed,     'arrowOut')}
      ${card('Available',    s.available,    'check')}
      ${card('Total Value',  money(s.total_value), 'dollar')}
      ${overdueCount > 0 ? card('Overdue Maintenance', overdueCount, 'tool', false) : ''}
    </div>
    <div class="grid-2">
      <div class="panel"><div class="panel-head"><h3>Assets by Category</h3></div>
        <div class="panel-body"><canvas id="catChart" height="150"></canvas></div></div>
      <div class="panel"><div class="panel-head"><h3>Status Breakdown</h3></div>
        <div class="panel-body"><canvas id="statusChart" height="150"></canvas></div></div>
    </div>
    <div class="grid-2">
      <div class="panel">
        <div class="panel-head">
          <h3>Recent Activity</h3>
          <button class="btn btn-ghost btn-sm" onclick="navigate('activity')">View all</button>
        </div>
        <div class="panel-body">${activity}</div>
      </div>
      <div class="panel"><div class="panel-head"><h3>${icon('alert', 16)} Expiring Warranties</h3></div>
        <div class="panel-body">${expiring}</div></div>
    </div>
    <div class="grid-2">
      <div class="panel"><div class="panel-head"><h3>${icon('tool', 16)} Upcoming Maintenance</h3></div>
        <div class="panel-body">${upcomingMaint}</div></div>
    </div>`;
  drawCharts(s);
}

function drawCharts(s) {
  if (typeof Chart === 'undefined') return;
  const accent = '#aacf0a', palette = ['#15171c', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#ec4899'];
  const catEl = document.getElementById('catChart');
  const stEl  = document.getElementById('statusChart');
  if (!catEl || !stEl) return;
  if ((s.by_category || []).length) {
    new Chart(catEl, { type: 'bar',
      data: { labels: s.by_category.map(c => c.name),
              datasets: [{ data: s.by_category.map(c => c.count), backgroundColor: accent, borderRadius: 6, maxBarThickness: 38 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#eef0f3' } }, x: { grid: { display: false } } }, responsive: true, maintainAspectRatio: false }
    });
  } else catEl.parentElement.innerHTML = `<p class="muted">${(s.total_assets || 0) > 0 ? 'No categorized assets yet.' : 'No assets yet.'}</p>`;
  const sd = (s.by_status || []).filter(x => x.count > 0);
  if (sd.length) {
    new Chart(stEl, { type: 'doughnut',
      data: { labels: sd.map(x => x.name), datasets: [{ data: sd.map(x => x.count), backgroundColor: palette, borderWidth: 2, borderColor: '#fff' }] },
      options: { plugins: { legend: { position: 'right', labels: { boxWidth: 12, padding: 14, font: { family: 'IBM Plex Sans' } } } }, cutout: '62%', responsive: true, maintainAspectRatio: false }
    });
  } else stEl.parentElement.innerHTML = '<p class="muted">No assets yet.</p>';
}

function jumpToClient(slug) {
  const h = location.hostname;
  const port = location.port ? ':' + location.port : '';

  // Localhost development: subdomains may not align with BASE_DOMAIN, so use tenant query scope.
  if (h === 'localhost' || h === '127.0.0.1') {
    window.location.href = `${location.protocol}//${h}${port}/?tenant=${encodeURIComponent(slug)}`;
    return;
  }

  window.location.href = `//${slug}.${h}${port}`;
}

function backToMsp() {
  const h = location.hostname;
  const port = location.port ? ':' + location.port : '';
  if (h === 'localhost' || h === '127.0.0.1') {
    window.location.href = `${location.protocol}//${h}${port}/`;
    return;
  }
  // Strip the leading subdomain to get back to the root domain
  const parts = h.split('.');
  const base = parts.length > 2 ? parts.slice(1).join('.') : h;
  window.location.href = `//${base}${port}`;
}

async function previewAsClient(tid, slug) {
  try {
    const data = await api(`/admin/tenants/${tid}/preview-token`, { method: 'POST' });
    const h = location.hostname;
    const port = location.port ? ':' + location.port : '';
    let url;
    if (h === 'localhost' || h === '127.0.0.1') {
      url = `${location.protocol}//${h}${port}/?preview_token=${encodeURIComponent(data.token)}&tenant=${encodeURIComponent(slug)}`;
    } else {
      url = `//${slug}.${h}${port}/?preview_token=${encodeURIComponent(data.token)}`;
    }
    window.open(url, '_blank');
  } catch (e) {
    toast(e.message, 'err');
  }
}

// ============ MSP CLIENTS PAGE ============
async function pageClients() {
  const page = document.getElementById('page');
  const addBtn = `<button class="btn btn-accent" onclick="openClientForm()">${icon('plus', 16)}New Client</button>`;
  page.innerHTML = pageHeader('Clients', 'MSP', addBtn) + loading();
  let clients;
  try { clients = await api('/tenants'); } catch (e) { toast(e.message, 'err'); return; }

  if (!clients.length) {
    page.innerHTML = pageHeader('Clients', 'MSP', addBtn) +
      `<div class="table-wrap"><div class="empty">${icon('layers', 44)}<h3>No clients yet</h3>
        <p>Create your first client to get started.</p></div></div>`;
    return;
  }

  const rows = clients.map(c => `
    <tr>
      <td><b class="client-link" onclick="jumpToClient('${esc(c.slug)}')">${esc(c.name)}</b></td>
      <td><span class="tag">${esc(c.slug)}</span></td>
      <td>${c.asset_count}</td>
      <td>${c.user_count}</td>
      <td><span class="badge ${c.active ? 'available' : 'retired'}">${c.active ? 'Active' : 'Inactive'}</span></td>
      <td>
        <div style="display:flex;gap:6px">
          <button class="btn btn-ghost btn-sm" onclick="openClientForm(${c.id})">${icon('edit', 14)}</button>
          <button class="btn btn-ghost btn-sm" onclick="openClientUsers(${c.id},'${esc(c.name)}')">${icon('users', 14)} Users</button>
          <button class="btn btn-ghost btn-sm" onclick="openInviteForm(${c.id},'${esc(c.name)}')">${icon('plus', 14)} Invite</button>
          <button class="btn btn-ghost btn-sm" title="Preview as client" onclick="previewAsClient(${c.id},'${esc(c.slug)}')">${icon('eye', 14)}</button>
          <button class="btn btn-ghost btn-sm" onclick="jumpToClient('${esc(c.slug)}')">${icon('arrowOut', 14)}</button>
          <button class="btn btn-danger btn-sm" onclick="deleteClient(${c.id})">${icon('trash', 14)}</button>
        </div>
      </td>
    </tr>`).join('');

  page.innerHTML = pageHeader('Clients', 'MSP', addBtn) + `
    <div class="table-wrap"><table>
      <thead><tr><th>Name</th><th>Slug / Subdomain</th><th>Assets</th><th>Users</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    <p class="muted" style="margin-top:12px;font-size:12.5px">${clients.length} client${clients.length !== 1 ? 's' : ''}</p>`;
}

function openClientForm(id = null) {
  openModal(`
    <div class="modal-head"><h2>${id ? 'Edit Client' : 'New Client'}</h2>
      <button class="x-btn" onclick="closeModal()">✕</button></div>
    <form id="client-form"><div class="modal-body">
      <div class="field"><label>Company Name *</label>
        <input name="name" id="cf-name" placeholder="Acme Corp" required></div>
      <div class="field"><label>Slug *
        <span style="font-weight:400;color:var(--text-muted)"> — becomes acme.usetether.ca</span></label>
        <input name="slug" id="cf-slug" placeholder="acme" required pattern="[a-z0-9-]+"
          title="Lowercase letters, numbers and hyphens only"></div>
      <div class="field-row">
        <div class="field"><label>Currency</label>
          <select name="currency">${['USD','EUR','GBP','CAD','AUD','JPY','INR'].map(c => `<option>${c}</option>`).join('')}</select></div>
        <div class="field"><label>Accent Colour</label>
          <input name="accent_color" type="color" value="#d4f034" style="height:40px;cursor:pointer"></div>
      </div>
      <div class="field"><label>Logo URL</label>
        <input name="logo_url" placeholder="https://…"></div>
    </div>
    <div class="modal-foot">
      <button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button type="submit" class="btn btn-primary">${id ? 'Save Changes' : 'Create Client'}</button>
    </div></form>`);

  const nameIn = document.getElementById('cf-name');
  const slugIn = document.getElementById('cf-slug');
  if (!id) {
    nameIn.oninput = () => {
      slugIn.value = nameIn.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    };
  } else {
    api('/tenants/' + id).then(t => {
      nameIn.value = t.name; slugIn.value = t.slug;
      document.querySelector('[name=currency]').value = t.currency;
      document.querySelector('[name=accent_color]').value = t.accent_color || '#d4f034';
      document.querySelector('[name=logo_url]').value = t.logo_url || '';
    });
  }

  document.getElementById('client-form').onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const body = { name: f.get('name'), slug: f.get('slug'), currency: f.get('currency'),
                   accent_color: f.get('accent_color'), logo_url: f.get('logo_url') };
    const btn = e.target.querySelector('[type=submit]'); btn.disabled = true;
    try {
      const result = await api(id ? '/tenants/' + id : '/tenants', { method: id ? 'PUT' : 'POST', json: body });
      if (!id) {
        closeModal();
        toast('Client created');
        openOnboardingWizard(result.id, result.name, result.slug);
      } else {
        closeModal(); toast('Client updated'); pageClients();
      }
    } catch (err) { toast(err.message, 'err'); btn.disabled = false; }
  };
}

async function deleteClient(id) {
  if (!confirm('Delete this client and ALL their data? This cannot be undone.')) return;
  try { await api('/tenants/' + id, { method: 'DELETE' }); toast('Client deleted'); pageClients(); }
  catch (e) { toast(e.message, 'err'); }
}

// ============ ONBOARDING WIZARD ============
const _wizard = { tenantId: null, tenantName: null, slug: null, step: 1 };

async function openOnboardingWizard(tenantId, tenantName, slug) {
  _wizard.tenantId = tenantId;
  _wizard.tenantName = tenantName;
  _wizard.slug = slug;
  _wizard.step = 1;
  _renderWizardStep();
}

function _wizardHdr(step) {
  const steps = ['Invite User', 'Add Categories', 'Done'];
  const dots = steps.map((s, i) => `<span style="display:inline-flex;align-items:center;gap:5px;font-size:12.5px;
    color:${i + 1 === step ? 'var(--accent)' : i + 1 < step ? 'var(--emerald)' : 'var(--text-muted)'}">
    <span style="width:20px;height:20px;border-radius:50%;background:${i + 1 === step ? 'var(--accent)' : i + 1 < step ? 'var(--emerald)' : 'var(--border)'};
      display:grid;place-items:center;font-size:11px;font-weight:700;color:${i + 1 <= step ? '#000' : 'var(--text-muted)'}">
      ${i + 1 < step ? '✓' : i + 1}</span>${s}</span>`).join('<span style="flex:1;height:1px;background:var(--border);margin:0 6px"></span>');
  return `<div style="display:flex;align-items:center;gap:4px;margin-bottom:20px">${dots}</div>`;
}

function _renderWizardStep() {
  const { tenantId, tenantName, slug, step } = _wizard;
  const host = `${slug}.localhost`;
  const headers = { ...State.token ? { 'Authorization': `Bearer ${State.token}` } : {}, host };

  if (step === 1) {
    openModal(`
      <div class="modal-head"><h2>Set up ${esc(tenantName)}</h2><button class="x-btn" onclick="closeModal();pageClients()">✕</button></div>
      <div class="modal-body">
        ${_wizardHdr(1)}
        <p style="margin-bottom:16px;color:var(--text-muted)">Invite the first user for this client. You can skip and do this later.</p>
        <div class="field"><label>Email address</label><input id="wiz-email" type="email" placeholder="admin@client.com"></div>
      </div>
      <div class="modal-foot">
        <button class="btn btn-ghost" onclick="_wizSkip()">Skip</button>
        <button class="btn btn-primary" onclick="_wizInvite()">Send Invite & Continue</button>
      </div>`, 'wide');
  } else if (step === 2) {
    openModal(`
      <div class="modal-head"><h2>Set up ${esc(tenantName)}</h2><button class="x-btn" onclick="closeModal();pageClients()">✕</button></div>
      <div class="modal-body">
        ${_wizardHdr(2)}
        <p style="margin-bottom:14px;color:var(--text-muted)">Default categories have been added. Add any extra categories specific to this client.</p>
        <div id="wiz-cats-list" style="margin-bottom:14px"></div>
        <div style="display:flex;gap:8px">
          <input id="wiz-cat-name" class="field" style="flex:1;margin:0" placeholder="Category name (e.g. Printer)">
          <select id="wiz-cat-icon" style="padding:9px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface);color:var(--text)">
            ${['box','laptop','monitor','tv','smartphone','server','wifi','mouse'].map(ic => `<option value="${ic}">${ic}</option>`).join('')}
          </select>
          <button class="btn btn-accent btn-sm" onclick="_wizAddCat()">Add</button>
        </div>
      </div>
      <div class="modal-foot">
        <button class="btn btn-ghost" onclick="_wizSkip()">Skip</button>
        <button class="btn btn-primary" onclick="_wizStep(3)">Next →</button>
      </div>`, 'wide');
    _wizLoadCats();
  } else {
    openModal(`
      <div class="modal-head"><h2>Setup complete!</h2><button class="x-btn" onclick="closeModal();pageClients()">✕</button></div>
      <div class="modal-body">
        ${_wizardHdr(3)}
        <div style="text-align:center;padding:20px 0">
          <div style="font-size:48px;margin-bottom:12px">🎉</div>
          <h3 style="font-family:var(--display);font-size:20px;margin-bottom:8px">${esc(tenantName)} is ready</h3>
          <p class="muted">You can now import assets, add employees, and configure settings from the client portal.</p>
        </div>
      </div>
      <div class="modal-foot">
        <button class="btn btn-ghost" onclick="closeModal();pageClients()">Back to Clients</button>
        <button class="btn btn-primary" onclick="closeModal();previewAsClient(${tenantId})">Open Client Portal →</button>
      </div>`, 'wide');
  }
}

function _wizStep(n) { _wizard.step = n; _renderWizardStep(); }
function _wizSkip() { _wizStep(_wizard.step + 1); }

async function _wizInvite() {
  const email = (document.getElementById('wiz-email')?.value || '').trim();
  if (!email) { _wizStep(2); return; }
  try {
    let roles = []; try { roles = await api('/users/roles/all'); } catch (_) {}
    const clientAdmin = roles.find(r => r.name === 'client_admin');
    if (clientAdmin) {
      await api('/invites', { method: 'POST', json: {
        email, role_id: clientAdmin.id, tenant_id: _wizard.tenantId
      }});
      toast(`Invite sent to ${email}`);
    }
  } catch (e) { toast(e.message, 'err'); }
  _wizStep(2);
}

async function _wizLoadCats() {
  const wrap = document.getElementById('wiz-cats-list');
  if (!wrap) return;
  try {
    const catsResp = await fetch(`/api/categories`, { headers: {
      'Authorization': `Bearer ${State.token}`,
      'host': `${_wizard.slug}.localhost`,
    }}).then(r => r.json());
    const cats = catsResp.items ?? catsResp;
    wrap.innerHTML = cats.length
      ? `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px">${cats.map(c =>
          `<span class="tag" style="padding:4px 8px;border-radius:6px;background:var(--bg)">${esc(c.name)}</span>`).join('')}</div>`
      : '<p class="muted" style="font-size:13px">No categories yet.</p>';
  } catch (_) {}
}

async function _wizAddCat() {
  const name = (document.getElementById('wiz-cat-name')?.value || '').trim();
  const icon_name = document.getElementById('wiz-cat-icon')?.value || 'box';
  if (!name) return;
  try {
    await fetch('/api/categories', { method: 'POST',
      headers: { 'Authorization': `Bearer ${State.token}`,
                 'host': `${_wizard.slug}.localhost`,
                 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, icon: icon_name }),
    });
    document.getElementById('wiz-cat-name').value = '';
    _wizLoadCats();
  } catch (e) { toast(e.message, 'err'); }
}

// ============ INVITE FORM ============
async function openInviteForm(tenantId, tenantName) {
  let roles = [];
  try { roles = await api('/users/roles/all'); } catch (_) {}
  const clientRoles = roles.filter(r => !r.is_msp_role);

  openModal(`
    <div class="modal-head"><h2>Invite User — ${esc(tenantName)}</h2>
      <button class="x-btn" onclick="closeModal()">✕</button></div>
    <form id="invite-form"><div class="modal-body">
      <p class="muted" style="margin-bottom:14px">Generate an invite link to send to the user. They'll set their own password.</p>
      <div class="field"><label>Email address *</label>
        <input name="email" type="email" required placeholder="user@example.com"></div>
      <div class="field"><label>Name (optional)</label>
        <input name="name" placeholder="Jane Smith"></div>
      <div class="field"><label>Role *</label>
        <select name="role_id" required>
          ${clientRoles.map(r => `<option value="${r.id}">${esc(r.description || r.name)}</option>`).join('')}
        </select></div>
      <div class="field"><label>Expires in</label>
        <select name="expires_hours">
          <option value="24">24 hours</option>
          <option value="72" selected>3 days</option>
          <option value="168">7 days</option>
        </select></div>
    </div>
    <div class="modal-foot">
      <button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button type="submit" class="btn btn-primary">${icon('plus', 15)} Generate Invite Link</button>
    </div></form>`);

  document.getElementById('invite-form').onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const btn = e.target.querySelector('[type=submit]'); btn.disabled = true;
    try {
      const inv = await api('/invites', { method: 'POST', json: {
        email: f.get('email'), name: f.get('name'), role_id: parseInt(f.get('role_id')),
        tenant_id: tenantId, expires_hours: parseInt(f.get('expires_hours')),
      }});
      const full = `${location.origin}${inv.invite_url}`;
      closeModal();
      openModal(`
        <div class="modal-head"><h2>Invite Link Ready</h2>
          <button class="x-btn" onclick="closeModal()">✕</button></div>
        <div class="modal-body">
          <p class="muted" style="margin-bottom:14px">
            Share this link with <b>${esc(f.get('email'))}</b>. It expires in ${f.get('expires_hours')} hours.
          </p>
          <div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);
                      padding:12px 14px;font-family:var(--mono);font-size:12.5px;word-break:break-all;
                      user-select:all">${esc(full)}</div>
          <button class="btn btn-primary" style="margin-top:14px;width:100%;justify-content:center"
            onclick="copyInviteLink('${esc(full)}')">
            ${icon('download', 15)} Copy link
          </button>
        </div>
        <div class="modal-foot">
          <button class="btn btn-ghost" onclick="closeModal()">Close</button>
        </div>`);
    } catch (err) { toast(err.message, 'err'); btn.disabled = false; }
  };
}

// ============ MSP USERS PAGE ============
async function pageMspUsers() {
  const page = document.getElementById('page');
  const addBtn = `<button class="btn btn-accent" onclick="openUserForm()">${icon('plus', 16)}New User</button>`;
  page.innerHTML = pageHeader('All Users', 'MSP', addBtn) + loading();
  let users = [], tenants = [], roles = [];
  try { [users, tenants, roles] = await Promise.all([api('/users'), api('/tenants'), api('/users/roles/all')]); }
  catch (e) { toast(e.message, 'err'); return; }

  if (!users.length) {
    page.innerHTML = pageHeader('All Users', 'MSP', addBtn) +
      `<div class="table-wrap"><div class="empty">${icon('users', 44)}<h3>No users</h3></div></div>`;
    return;
  }

  const rows = users.map(u => `
    <tr>
      <td><b>${esc(u.name)}</b><div class="cell-sub">${esc(u.email)}</div></td>
      <td>${esc(u.tenant_name || 'MSP Staff')}</td>
      <td><span class="tag">${esc(u.role_name || '')}</span></td>
      <td><span class="badge ${u.active ? 'available' : 'retired'}">${u.active ? 'Active' : 'Inactive'}</span></td>
      <td>
        <div style="display:flex;gap:6px">
          <button class="btn btn-ghost btn-sm" onclick="openUserForm(${u.tenant_id || 'null'}, ${u.id})">${icon('edit', 14)}</button>
          <button class="btn btn-ghost btn-sm" onclick="openPermEditor(${u.id},'${esc(u.name)}')">${icon('lock', 14)} Perms</button>
          <button class="btn btn-danger btn-sm" onclick="deleteUser(${u.id}, pageMspUsers)">${icon('trash', 14)}</button>
        </div>
      </td>
    </tr>`).join('');

  page.innerHTML = pageHeader('All Users', 'MSP', addBtn) + `
    <div class="table-wrap"><table>
      <thead><tr><th>Name</th><th>Tenant</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
}

async function openClientUsers(tenantId, tenantName) {
  let users = [], roles = [];
  try { [users, roles] = await Promise.all([api('/users?tenant_id=' + tenantId), api('/users/roles/all')]); }
  catch (e) { return toast(e.message, 'err'); }

  openModal(`
    <div class="modal-head"><h2>${esc(tenantName)} — Users</h2>
      <button class="x-btn" onclick="closeModal()">✕</button></div>
    <div class="modal-body" id="cu-body"></div>
    <div class="modal-foot" style="gap:8px">
      <button class="btn btn-ghost" onclick="openInviteForm(${tenantId},'${esc(tenantName)}')">${icon('plus', 14)} Invite</button>
      <button class="btn btn-accent" onclick="openUserForm(${tenantId})">${icon('plus', 14)} Add User</button>
    </div>`, true);

  const body = document.getElementById('cu-body');
  if (!users.length) { body.innerHTML = '<p class="muted">No users yet. Invite someone to get started.</p>'; return; }
  body.innerHTML = `<div class="chip-grid">${users.map(u => `
    <div class="chip">
      <div class="ci">
        <div class="ico" style="background:var(--ink);color:var(--accent)">
          <b style="font-family:var(--display)">${esc(u.name[0].toUpperCase())}</b></div>
        <div><b>${esc(u.name)}</b>
          <small>${esc(u.email)}<br>${esc(u.role_name || '')}</small></div>
      </div>
      <div class="acts">
        <button class="icon-btn" onclick="openUserForm(${tenantId},${u.id})">${icon('edit', 16)}</button>
        <button class="icon-btn" onclick="openPermEditor(${u.id},'${esc(u.name)}')">${icon('lock', 16)}</button>
        <button class="icon-btn danger" onclick="deleteClientUserAndRefresh(${u.id},${tenantId},'${esc(tenantName)}')">${icon('trash', 16)}</button>
      </div>
    </div>`).join('')}</div>`;
}

async function deleteClientUserAndRefresh(userId, tenantId, tenantName) {
  await deleteUser(userId, () => openClientUsers(tenantId, tenantName));
}

async function openUserForm(tenantId = null, userId = null) {
  let roles = [], tenants = [], u = { name: '', email: '', role_id: '', active: true, is_msp_staff: false };
  try { [roles, tenants] = await Promise.all([api('/users/roles/all'), isMSP() ? api('/tenants') : Promise.resolve([])]); }
  catch (_) {}
  if (userId) { try { const all = await api('/users'); u = all.find(x => x.id === userId) || u; } catch (_) {} }

  const tenantOpts = isMSP()
    ? `<option value="">MSP Staff (no tenant)</option>` +
      tenants.map(t => `<option value="${t.id}" ${(tenantId && t.id == tenantId) || (u.tenant_id && t.id == u.tenant_id) ? 'selected' : ''}>${esc(t.name)}</option>`).join('')
    : '';
  const roleOpts = roles
    .filter(r => isMSP() || !r.is_msp_role)
    .map(r => `<option value="${r.id}" ${u.role_id == r.id ? 'selected' : ''}>${esc(r.description || r.name)}</option>`).join('');

  openModal(`
    <div class="modal-head"><h2>${userId ? 'Edit User' : 'New User'}</h2>
      <button class="x-btn" onclick="closeModal()">✕</button></div>
    <form id="user-form"><div class="modal-body">
      <div class="field-row">
        <div class="field"><label>Full Name *</label><input name="name" value="${esc(u.name)}" required></div>
        <div class="field"><label>Email *</label><input name="email" type="email" value="${esc(u.email)}" required></div>
      </div>
      <div class="field"><label>Password ${userId ? '(blank = keep current)' : '*'}</label>
        <input name="password" type="password" ${userId ? '' : 'required'} minlength="6"></div>
      <div class="field-row">
        <div class="field"><label>Role *</label><select name="role_id" required>${roleOpts}</select></div>
        ${isMSP() ? `<div class="field"><label>Tenant</label><select name="tenant_id">${tenantOpts}</select></div>` : ''}
      </div>
      ${isMSP() ? `<div class="field" style="display:flex;align-items:center;gap:10px">
        <input type="checkbox" name="is_msp_staff" id="msp-chk" ${u.is_msp_staff ? 'checked' : ''}>
        <label for="msp-chk" style="margin:0">MSP Staff (access all tenants)</label></div>` : ''}
      <div class="field" style="display:flex;align-items:center;gap:10px">
        <input type="checkbox" name="active" id="active-chk" ${u.active !== false ? 'checked' : ''}>
        <label for="active-chk" style="margin:0">Account active</label></div>
    </div>
    <div class="modal-foot">
      <button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button type="submit" class="btn btn-primary">${userId ? 'Save Changes' : 'Create User'}</button>
    </div></form>`);

  document.getElementById('user-form').onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const body = {
      name: f.get('name'), email: f.get('email'),
      role_id: parseInt(f.get('role_id')), active: !!f.get('active'),
      is_msp_staff: !!f.get('is_msp_staff'),
      tenant_id: f.get('tenant_id') ? parseInt(f.get('tenant_id')) : (tenantId || null),
    };
    if (f.get('password')) body.password = f.get('password');
    const btn = e.target.querySelector('[type=submit]'); btn.disabled = true;
    try {
      await api(userId ? '/users/' + userId : '/users', { method: userId ? 'PUT' : 'POST', json: body });
      closeModal(); toast(userId ? 'User updated' : 'User created');
      if (isMSP()) pageMspUsers(); else pageTeam();
    } catch (err) { toast(err.message, 'err'); btn.disabled = false; }
  };
}

async function deleteUser(id, callback) {
  if (!confirm('Delete this user?')) return;
  try { await api('/users/' + id, { method: 'DELETE' }); toast('User deleted'); if (callback) callback(); }
  catch (e) { toast(e.message, 'err'); }
}

// ============ PERMISSION EDITOR ============
async function openPermEditor(userId, userName) {
  let data;
  try { data = await api('/users/' + userId + '/permissions'); }
  catch (e) { return toast(e.message, 'err'); }

  const ALL = [
    ['assets.view','View assets'],['assets.create','Create assets'],['assets.edit','Edit assets'],
    ['assets.delete','Delete assets'],['assets.checkout','Check out'],['assets.checkin','Check in'],
    ['assets.import','CSV import'],['assets.export','CSV export'],['categories.manage','Categories'],
    ['locations.manage','Locations'],['employees.manage','People'],['users.manage','Manage team'],
    ['reports.view','Reports'],['settings.manage','Settings'],
  ];

  const rows = ALL.map(([key, label]) => {
    const inRole = data.role_permissions.includes(key);
    const ov = data.overrides[key];
    const effective = data.effective.includes(key);
    const state = ov === true ? 'granted' : ov === false ? 'revoked' : 'role';
    return `<tr>
      <td>${label}<br><span class="tag muted" style="font-size:11px">${key}</span></td>
      <td style="text-align:center">${inRole ? icon('check', 16) : '<span class="muted">—</span>'}</td>
      <td style="text-align:center"><span class="badge ${effective ? 'available' : 'retired'}">${effective ? 'Yes' : 'No'}</span></td>
      <td><div style="display:flex;gap:5px">
        <button class="btn btn-ghost btn-sm ${state === 'granted' ? 'btn-active' : ''}"
          onclick="setPerm(${userId},'${key}',true)">Grant</button>
        <button class="btn btn-ghost btn-sm ${state === 'revoked' ? 'btn-active' : ''}"
          onclick="setPerm(${userId},'${key}',false)">Revoke</button>
        <button class="btn btn-ghost btn-sm ${state === 'role' ? 'btn-active' : ''}"
          onclick="clearPerm(${userId},'${key}')">Default</button>
      </div></td>
    </tr>`;
  }).join('');

  openModal(`
    <div class="modal-head"><h2>Permissions — ${esc(userName)}</h2>
      <button class="x-btn" onclick="closeModal()">✕</button></div>
    <div class="modal-body">
      <p class="muted" style="margin-bottom:12px">Override permissions on top of the role defaults.</p>
      <div style="max-height:420px;overflow-y:auto">
        <table class="table-wrap" style="border:none;box-shadow:none">
          <thead><tr><th>Permission</th><th>In Role</th><th>Effective</th><th>Override</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
    <div class="modal-foot"><button class="btn btn-primary" onclick="closeModal()">Done</button></div>`, true);
}

async function setPerm(userId, key, granted) {
  try { await api('/users/' + userId + '/permissions', { method: 'PUT', json: { permission_key: key, granted } }); openPermEditor(userId, ''); }
  catch (e) { toast(e.message, 'err'); }
}
async function clearPerm(userId, key) {
  try { await api('/users/' + userId + '/permissions/' + key, { method: 'DELETE' }); openPermEditor(userId, ''); }
  catch (e) { toast(e.message, 'err'); }
}

async function copyInviteLink(link) {
  try {
    await navigator.clipboard.writeText(link);
    toast('Copied!');
  } catch (_) {
    toast('Unable to copy link', 'err');
  }
}

// ============ PUBLIC ASSET CHECK-IN PAGE ============
async function renderPublicCheckin(token) {
  const app = document.getElementById('app');
  app.innerHTML = `<div class="login-wrap"><div class="login-card"><div class="loading"><div class="spinner"></div></div></div></div>`;

  let info;
  try {
    const r = await fetch(`/api/assets/public/checkin/${token}`);
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: 'Link not found or already used' }));
      throw new Error(err.detail || 'Invalid link');
    }
    info = await r.json();
  } catch (e) {
    app.innerHTML = `<div class="login-wrap"><div class="login-card">
      <div class="login-logo"><div class="mark"><span></span></div><b>Tether</b></div>
      <h1 style="color:var(--red)">Link unavailable</h1>
      <p class="sub">${esc(e.message)}</p>
    </div></div>`;
    return;
  }

  app.innerHTML = `
    <div class="login-wrap">
      <div class="login-card">
        <div class="login-logo"><div class="mark"><span></span></div><b>Tether</b></div>
        <h1>Return asset</h1>
        <p class="sub">Confirm you are returning this asset:</p>
        <div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px 16px;margin:14px 0">
          <div style="font-family:var(--mono);font-size:15px;font-weight:700">${esc(info.asset_tag)}</div>
          <div style="font-size:14px;margin-top:4px">${esc(info.asset_name)}</div>
          ${info.assigned_to ? `<div style="font-size:12.5px;color:var(--text-muted);margin-top:4px">Assigned to ${esc(info.assigned_to)}</div>` : ''}
        </div>
        <button id="checkin-btn" class="btn btn-primary" style="width:100%;justify-content:center;padding:11px" onclick="_submitPublicCheckin('${token}')">
          Check In Asset
        </button>
        <div id="checkin-result"></div>
      </div>
    </div>`;
}

async function _submitPublicCheckin(token) {
  const btn = document.getElementById('checkin-btn');
  btn.disabled = true; btn.textContent = 'Checking in…';
  try {
    const r = await fetch(`/api/assets/public/checkin/${token}`, { method: 'POST' });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Check-in failed');
    document.getElementById('checkin-result').innerHTML = `
      <div style="margin-top:16px;padding:12px 16px;background:var(--emerald)18;border:1px solid var(--emerald)44;border-radius:var(--radius-sm);color:var(--emerald);font-weight:600">
        ✓ ${esc(d.asset_tag)} checked in successfully
      </div>`;
    btn.style.display = 'none';
  } catch (e) {
    document.getElementById('checkin-result').innerHTML = `<p style="color:var(--red);margin-top:12px">${esc(e.message)}</p>`;
    btn.disabled = false; btn.textContent = 'Check In Asset';
  }
}

// ============ FORGOT PASSWORD PAGE ============
function renderForgotPasswordPage() {
  document.getElementById('app').innerHTML = `
    <div class="login-wrap">
      <div class="login-card">
        <div class="login-logo"><div class="mark"><span></span></div><b>Tether</b></div>
        <h1>Reset password</h1>
        <p class="sub">Enter your email and we'll send a reset link.</p>
        <form id="forgot-form">
          <div class="field"><label>Email</label>
            <input name="email" type="email" placeholder="you@example.com" required></div>
          <button class="btn btn-primary" style="width:100%;justify-content:center;padding:11px" type="submit">
            Send reset link
          </button>
        </form>
        <div style="text-align:center;margin-top:14px">
          <a href="/" style="font-size:13px;color:var(--text-muted)">Back to sign in</a>
        </div>
      </div>
    </div>`;

  document.getElementById('forgot-form').onsubmit = async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector('button');
    btn.disabled = true; btn.textContent = 'Sending…';
    const email = new FormData(e.target).get('email');
    try {
      await fetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      // Always show success to prevent user enumeration
      document.getElementById('app').innerHTML = `
        <div class="login-wrap"><div class="login-card">
          <div style="text-align:center;padding:16px 0">
            <div style="font-size:40px;margin-bottom:16px">📬</div>
            <h2 style="margin-bottom:10px">Check your inbox</h2>
            <p class="sub">If that email is registered, a reset link is on its way.
            Check your spam folder if you don't see it within a minute.</p>
            <a href="/" class="btn btn-primary" style="margin-top:20px;display:inline-flex">Back to sign in</a>
          </div>
        </div></div>`;
    } catch(err) {
      toast(err.message, 'err');
      btn.disabled = false; btn.textContent = 'Send reset link';
    }
  };
}

// ============ RESET PASSWORD PAGE ============
async function renderPasswordResetPage(token) {
  const app = document.getElementById('app');
  app.innerHTML = `<div class="login-wrap"><div class="login-card">
    <div class="loading"><div class="spinner"></div></div></div></div>`;

  // Validate token first
  let info;
  try {
    const r = await fetch(`/api/auth/reset-password/${token}`);
    if (!r.ok) throw new Error((await r.json()).detail || 'Invalid link');
    info = await r.json();
  } catch(err) {
    app.innerHTML = `
      <div class="login-wrap"><div class="login-card" style="text-align:center">
        <div style="font-size:40px;margin-bottom:16px">⚠️</div>
        <h2 style="margin-bottom:10px">Link expired</h2>
        <p class="sub">${esc(err.message)}</p>
        <a href="/forgot-password" class="btn btn-primary" style="margin-top:20px;display:inline-flex">
          Request a new link
        </a>
      </div></div>`;
    return;
  }

  app.innerHTML = `
    <div class="login-wrap">
      <div class="login-card">
        <div class="login-logo"><div class="mark"><span></span></div><b>Tether</b></div>
        <h1>Set new password</h1>
        <p class="sub">Resetting password for <strong>${esc(info.email)}</strong></p>
        <form id="reset-form">
          <div class="field"><label>New password</label>
            <input name="password" type="password" minlength="8"
              placeholder="At least 8 characters" required></div>
          <div class="field"><label>Confirm password</label>
            <input name="confirm" type="password" minlength="8"
              placeholder="Repeat your new password" required></div>
          <button class="btn btn-primary" style="width:100%;justify-content:center;padding:11px" type="submit">
            Set password
          </button>
        </form>
      </div>
    </div>`;

  document.getElementById('reset-form').onsubmit = async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector('button');
    const f   = new FormData(e.target);
    const pw  = f.get('password');
    const cfm = f.get('confirm');
    if (pw !== cfm) { toast('Passwords do not match', 'err'); return; }
    btn.disabled = true; btn.textContent = 'Saving…';
    try {
      const r = await fetch('/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: pw }),
      });
      if (!r.ok) throw new Error((await r.json()).detail);
      app.innerHTML = `
        <div class="login-wrap"><div class="login-card" style="text-align:center">
          <div style="font-size:40px;margin-bottom:16px">✅</div>
          <h2 style="margin-bottom:10px">Password updated</h2>
          <p class="sub">Your password has been changed. You can now sign in.</p>
          <a href="/" class="btn btn-primary" style="margin-top:20px;display:inline-flex">Sign in</a>
        </div></div>`;
    } catch(err) {
      toast(err.message, 'err');
      btn.disabled = false; btn.textContent = 'Set password';
    }
  };
}

// ============ SIGNUP PAGE ============
async function renderSignupPage() {
  document.getElementById('app').innerHTML = `
    <div class="login-wrap">
      <div class="login-card" style="max-width:440px">
        <div class="login-logo"><div class="mark"><span></span></div><b>Tether</b></div>
        <h1>Start your free trial</h1>
        <p class="sub">30 days free · No credit card · Cancel anytime</p>
        <form id="signup-form" novalidate>
          <div class="field"><label>Your name</label>
            <input name="name" type="text" placeholder="Jane Smith" required autocomplete="name"></div>
          <div class="field"><label>MSP / company name</label>
            <input name="msp_name" type="text" placeholder="Acme IT Solutions" required></div>
          <div class="field"><label>Work email</label>
            <input name="email" type="email" placeholder="you@yourcompany.com" required autocomplete="email"></div>
          <div class="field"><label>Password <span style="color:var(--text-faint);font-weight:400">(min 8 chars)</span></label>
            <input name="password" type="password" minlength="8" required autocomplete="new-password"></div>
          <label style="display:flex;align-items:flex-start;gap:10px;margin-bottom:18px;cursor:pointer;font-size:13.5px;color:var(--text-muted)">
            <input name="agree_terms" type="checkbox" required style="margin-top:3px;flex-shrink:0">
            I agree to the <a href="https://usetether.ca/terms" target="_blank" style="color:var(--accent)">Terms of Service</a>
            and <a href="https://usetether.ca/privacy" target="_blank" style="color:var(--accent)">Privacy Policy</a>
          </label>
          <button class="btn btn-accent" style="width:100%;justify-content:center;padding:12px;font-size:15px" type="submit">
            Start free trial
          </button>
        </form>
        <p style="text-align:center;margin-top:18px;font-size:13px;color:var(--text-muted)">
          Already have an account? <a href="/" style="color:var(--accent)">Sign in</a>
        </p>
      </div>
    </div>`;

  document.getElementById('signup-form').onsubmit = async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector('button[type=submit]');
    const f   = new FormData(e.target);

    if (!f.get('agree_terms')) {
      toast('Please agree to the Terms of Service to continue', 'err'); return;
    }
    if (f.get('password').length < 8) {
      toast('Password must be at least 8 characters', 'err'); return;
    }

    btn.disabled = true; btn.textContent = 'Creating account…';

    try {
      const r = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name:        f.get('name'),
          email:       f.get('email'),
          password:    f.get('password'),
          msp_name:    f.get('msp_name'),
          agree_terms: true,
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Signup failed');

      // Store token and boot
      localStorage.setItem('token', data.access_token);
      toast(`Welcome to Tether! Your 30-day trial has started.`);
      await boot();
    } catch(err) {
      toast(err.message, 'err');
      btn.disabled = false;
      btn.textContent = 'Start free trial';
    }
  };
}
