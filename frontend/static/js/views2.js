// ============ ASSETS LIST ============
const AssetFilters = { q: '', status: '', category_id: '', location_id: '', sort: 'asset_tag', order: 'asc' };
let _lookups = { categories: [], locations: [], employees: [] };

async function loadLookups() {
  const [categories, locations, employees] = await Promise.all([
    api('/categories'), api('/locations'), api('/employees'),
  ]);
  _lookups = { categories, locations, employees };
}

async function pageAssets() {
  const page = document.getElementById('page');
  const actions = `
    <button class="btn btn-ghost" onclick="openImport()">${icon('upload', 16)}Import</button>
    <button class="btn btn-ghost" onclick="exportCsv()">${icon('download', 16)}Export</button>
    <button class="btn btn-accent" onclick="openAssetForm()">${icon('plus', 16)}New Asset</button>`;
  page.innerHTML = pageHeader('Assets', null, actions) + loading();
  if (!_lookups.categories.length) { try { await loadLookups(); } catch (e) {} }

  const catOpts = _lookups.categories.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
  const locOpts = _lookups.locations.map(l => `<option value="${l.id}">${esc(l.name)}</option>`).join('');
  page.innerHTML = pageHeader('Assets', null, actions) + `
    <div class="toolbar">
      <div class="search">${icon('search', 17)}<input id="f-q" placeholder="Search by tag, name, serial, model…" value="${esc(AssetFilters.q)}"></div>
      <select class="filter" id="f-status"><option value="">All statuses</option>${STATUSES.map(s => `<option value="${s}">${s[0].toUpperCase() + s.slice(1)}</option>`).join('')}</select>
      <select class="filter" id="f-cat"><option value="">All categories</option>${catOpts}</select>
      <select class="filter" id="f-loc"><option value="">All locations</option>${locOpts}</select>
    </div>
    <div id="asset-table">${loading()}</div>`;

  const q = document.getElementById('f-q');
  let t; q.oninput = () => { clearTimeout(t); t = setTimeout(() => { AssetFilters.q = q.value; loadAssetTable(); }, 250); };
  document.getElementById('f-status').value = AssetFilters.status;
  document.getElementById('f-cat').value = AssetFilters.category_id;
  document.getElementById('f-loc').value = AssetFilters.location_id;
  document.getElementById('f-status').onchange = (e) => { AssetFilters.status = e.target.value; loadAssetTable(); };
  document.getElementById('f-cat').onchange = (e) => { AssetFilters.category_id = e.target.value; loadAssetTable(); };
  document.getElementById('f-loc').onchange = (e) => { AssetFilters.location_id = e.target.value; loadAssetTable(); };
  loadAssetTable();
}

function sortBy(col) {
  if (AssetFilters.sort === col) AssetFilters.order = AssetFilters.order === 'asc' ? 'desc' : 'asc';
  else { AssetFilters.sort = col; AssetFilters.order = 'asc'; }
  loadAssetTable();
}

async function loadAssetTable() {
  const wrap = document.getElementById('asset-table');
  const params = new URLSearchParams();
  Object.entries(AssetFilters).forEach(([k, v]) => { if (v) params.append(k, v); });
  let assets;
  try { assets = await api('/assets?' + params); } catch (e) { toast(e.message, 'err'); return; }

  if (!assets.length) {
    wrap.innerHTML = `<div class="table-wrap"><div class="empty">${icon('box', 44)}<h3>No assets found</h3><p>${AssetFilters.q || AssetFilters.status ? 'Try adjusting your filters.' : 'Add your first asset to get started.'}</p></div></div>`;
    return;
  }
  const arr = (c) => AssetFilters.sort === c ? `<span class="arr">${AssetFilters.order === 'asc' ? '▲' : '▼'}</span>` : '';
  const rows = assets.map(a => `
    <tr onclick="navigate('asset', ${a.id})">
      <td><span class="tag">${esc(a.asset_tag)}</span></td>
      <td><div class="cell-name">${esc(a.name)}</div><div class="cell-sub">${esc(a.manufacturer || a.model || '')}</div></td>
      <td class="muted">${esc(a.category_name || '—')}</td>
      <td>${statusBadge(a.status)}</td>
      <td class="muted">${esc(a.assigned_to_name || '—')}</td>
      <td class="muted">${esc(a.location_name || '—')}</td>
    </tr>`).join('');
  wrap.innerHTML = `
    <div class="table-wrap"><table>
      <thead><tr>
        <th onclick="sortBy('asset_tag')">Tag ${arr('asset_tag')}</th>
        <th onclick="sortBy('name')">Name ${arr('name')}</th>
        <th onclick="sortBy('category_id')">Category</th>
        <th onclick="sortBy('status')">Status ${arr('status')}</th>
        <th>Assigned to</th>
        <th onclick="sortBy('location_id')">Location</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    <p class="muted" style="margin-top:12px;font-size:12.5px">${assets.length} asset${assets.length !== 1 ? 's' : ''}</p>`;
}

// ============ ASSET FORM ============
async function openAssetForm(id = null) {
  if (!_lookups.categories.length) await loadLookups();
  let a = { asset_tag: '', name: '', serial: '', model: '', manufacturer: '', status: 'available', notes: '', purchase_date: '', purchase_cost: '', warranty_expiry: '', category_id: '', location_id: '', assigned_to_id: '' };
  if (id) { try { a = await api('/assets/' + id); } catch (e) { return toast(e.message, 'err'); } }
  const opt = (arr, sel, placeholder) => `<option value="">${placeholder}</option>` + arr.map(x => `<option value="${x.id}" ${String(sel) === String(x.id) ? 'selected' : ''}>${esc(x.name)}</option>`).join('');
  openModal(`
    <div class="modal-head"><h2>${id ? 'Edit Asset' : 'New Asset'}</h2><button class="x-btn" onclick="closeModal()">✕</button></div>
    <form id="asset-form"><div class="modal-body">
      <div class="field-row">
        <div class="field"><label>Asset Tag *</label><input name="asset_tag" value="${esc(a.asset_tag)}" placeholder="IT-0001" required></div>
        <div class="field"><label>Status</label><select name="status">${STATUSES.map(s => `<option value="${s}" ${a.status === s ? 'selected' : ''}>${s[0].toUpperCase() + s.slice(1)}</option>`).join('')}</select></div>
      </div>
      <div class="field"><label>Name *</label><input name="name" value="${esc(a.name)}" placeholder="Dell Latitude 7440" required></div>
      <div class="field-row">
        <div class="field"><label>Manufacturer</label><input name="manufacturer" value="${esc(a.manufacturer)}" placeholder="Dell"></div>
        <div class="field"><label>Model</label><input name="model" value="${esc(a.model)}" placeholder="Latitude 7440"></div>
      </div>
      <div class="field-row">
        <div class="field"><label>Serial Number</label><input name="serial" value="${esc(a.serial)}"></div>
        <div class="field"><label>Category</label><select name="category_id">${opt(_lookups.categories, a.category_id, 'None')}</select></div>
      </div>
      <div class="field-row">
        <div class="field"><label>Location</label><select name="location_id">${opt(_lookups.locations, a.location_id, 'None')}</select></div>
        <div class="field"><label>Assigned to</label><select name="assigned_to_id">${opt(_lookups.employees, a.assigned_to_id, 'Unassigned')}</select></div>
      </div>
      <div class="field-row">
        <div class="field"><label>Purchase Date</label><input type="date" name="purchase_date" value="${a.purchase_date || ''}"></div>
        <div class="field"><label>Purchase Cost</label><input type="number" step="0.01" name="purchase_cost" value="${a.purchase_cost ?? ''}"></div>
      </div>
      <div class="field"><label>Warranty Expiry</label><input type="date" name="warranty_expiry" value="${a.warranty_expiry || ''}"></div>
      <div class="field"><label>Notes</label><textarea name="notes">${esc(a.notes)}</textarea></div>
    </div>
    <div class="modal-foot"><button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button><button type="submit" class="btn btn-primary">${id ? 'Save Changes' : 'Create Asset'}</button></div>
    </form>`);

  document.getElementById('asset-form').onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const payload = {};
    for (const [k, v] of f.entries()) {
      if (['category_id', 'location_id', 'assigned_to_id'].includes(k)) payload[k] = v ? parseInt(v) : null;
      else if (k === 'purchase_cost') payload[k] = v ? parseFloat(v) : null;
      else if (['purchase_date', 'warranty_expiry'].includes(k)) payload[k] = v || null;
      else payload[k] = v;
    }
    const btn = e.target.querySelector('button[type=submit]'); btn.disabled = true;
    try {
      await api(id ? '/assets/' + id : '/assets', { method: id ? 'PUT' : 'POST', json: payload });
      closeModal(); toast(id ? 'Asset updated' : 'Asset created');
      State.route === 'asset' ? pageAssetDetail() : loadAssetTable();
    } catch (err) { toast(err.message, 'err'); btn.disabled = false; }
  };
}

// ============ ASSET DETAIL ============
async function pageAssetDetail() {
  const page = document.getElementById('page');
  page.innerHTML = loading();
  let a, history;
  try { [a, history] = await Promise.all([api('/assets/' + State.param), api('/assets/' + State.param + '/history')]); }
  catch (e) { toast(e.message, 'err'); navigate('assets'); return; }

  const back = `<button class="btn btn-ghost btn-sm" onclick="navigate('assets')">${icon('back', 16)}Back</button>`;
  const checkAction = a.status === 'deployed'
    ? `<button class="btn btn-ghost" onclick="openCheckin(${a.id})">${icon('arrowIn', 16)}Check In</button>`
    : `<button class="btn btn-accent" onclick="openCheckout(${a.id})">${icon('arrowOut', 16)}Check Out</button>`;
  const actions = `${checkAction}<button class="btn btn-ghost" onclick="openAssetForm(${a.id})">${icon('edit', 16)}Edit</button><button class="btn btn-danger" onclick="deleteAsset(${a.id})">${icon('trash', 16)}</button>`;

  const row = (k, v) => `<div class="drow"><div class="k">${k}</div><div class="v">${v}</div></div>`;
  const timeline = history.length
    ? `<ul class="timeline">${history.map(h => `<li><div class="t-action">${h.action === 'checkout' ? 'Checked out' : 'Checked in'}${h.employee_name ? ' — ' + esc(h.employee_name) : ''}</div>${h.note ? `<div class="muted" style="font-size:13px">${esc(h.note)}</div>` : ''}<div class="t-time">${fmtDate(h.timestamp)} · ${timeAgo(h.timestamp)}</div></li>`).join('')}</ul>`
    : `<p class="muted">No checkout history yet.</p>`;

  page.innerHTML = `
    <div style="margin-bottom:14px">${back}</div>
    ${pageHeader(esc(a.name), `<span class="tag">${esc(a.asset_tag)}</span> · ${statusBadge(a.status)}`, actions)}
    <div class="detail-grid">
      <div class="panel">
        <div class="panel-head"><h3>Details</h3></div>
        <div class="panel-body"><div class="detail-rows">
          ${row('Manufacturer', esc(a.manufacturer || '—'))}
          ${row('Model', esc(a.model || '—'))}
          ${row('Serial Number', a.serial ? `<span class="tag">${esc(a.serial)}</span>` : '—')}
          ${row('Category', esc(a.category_name || '—'))}
          ${row('Location', esc(a.location_name || '—'))}
          ${row('Assigned to', esc(a.assigned_to_name || 'Unassigned'))}
          ${row('Purchase Date', fmtDate(a.purchase_date))}
          ${row('Purchase Cost', money(a.purchase_cost))}
          ${row('Warranty Expiry', fmtDate(a.warranty_expiry))}
          ${row('Added', fmtDate(a.created_at))}
        </div>
        ${a.notes ? `<div style="margin-top:16px"><div class="k" style="font-size:12px;color:var(--text-muted);margin-bottom:5px">Notes</div><p>${esc(a.notes)}</p></div>` : ''}
        </div>
      </div>
      <div>
        <div class="panel" style="margin-bottom:18px">
          <div class="panel-head"><h3>QR Label</h3></div>
          <div class="panel-body qr-box">
            <img src="/api/assets/${a.id}/qr" alt="QR code">
            <p class="muted" style="margin-top:10px;font-size:12.5px">Encodes <span class="tag">${esc(a.asset_tag)}</span></p>
            <a class="btn btn-ghost btn-sm" style="margin-top:10px" href="/api/assets/${a.id}/qr" download="${esc(a.asset_tag)}.png">${icon('download', 15)}Download</a>
          </div>
        </div>
        <div class="panel">
          <div class="panel-head"><h3>${icon('activity', 16)} History</h3></div>
          <div class="panel-body">${timeline}</div>
        </div>
      </div>
    </div>`;
}

async function deleteAsset(id) {
  if (!confirm('Delete this asset permanently? This cannot be undone.')) return;
  try { await api('/assets/' + id, { method: 'DELETE' }); toast('Asset deleted'); navigate('assets'); }
  catch (e) { toast(e.message, 'err'); }
}

// ============ CHECKOUT / CHECKIN ============
async function openCheckout(id) {
  if (!_lookups.employees.length) await loadLookups();
  const opts = _lookups.employees.map(e => `<option value="${e.id}">${esc(e.name)}${e.department ? ' · ' + esc(e.department) : ''}</option>`).join('');
  openModal(`
    <div class="modal-head"><h2>Check Out Asset</h2><button class="x-btn" onclick="closeModal()">✕</button></div>
    <form id="co-form"><div class="modal-body">
      <div class="field"><label>Assign to person</label><select name="employee_id">${opts || '<option value="">No people added yet</option>'}</select></div>
      <div class="field"><label>Note (optional)</label><input name="note" placeholder="e.g. for new hire onboarding"></div>
    </div><div class="modal-foot"><button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button><button type="submit" class="btn btn-accent">Check Out</button></div></form>`);
  document.getElementById('co-form').onsubmit = async (e) => {
    e.preventDefault(); const f = new FormData(e.target);
    try { await api(`/assets/${id}/checkout`, { method: 'POST', json: { employee_id: f.get('employee_id') ? parseInt(f.get('employee_id')) : null, note: f.get('note') } }); closeModal(); toast('Asset checked out'); pageAssetDetail(); }
    catch (err) { toast(err.message, 'err'); }
  };
}

async function openCheckin(id) {
  openModal(`
    <div class="modal-head"><h2>Check In Asset</h2><button class="x-btn" onclick="closeModal()">✕</button></div>
    <form id="ci-form"><div class="modal-body">
      <p class="muted" style="margin-bottom:14px">This will mark the asset as available and clear its assignment.</p>
      <div class="field"><label>Note (optional)</label><input name="note" placeholder="e.g. returned in good condition"></div>
    </div><div class="modal-foot"><button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button><button type="submit" class="btn btn-primary">Check In</button></div></form>`);
  document.getElementById('ci-form').onsubmit = async (e) => {
    e.preventDefault(); const f = new FormData(e.target);
    try { await api(`/assets/${id}/checkin`, { method: 'POST', json: { note: f.get('note') } }); closeModal(); toast('Asset checked in'); pageAssetDetail(); }
    catch (err) { toast(err.message, 'err'); }
  };
}

// ============ CSV ============
async function exportCsv() {
  try {
    const res = await api('/assets/export/csv');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'assets.csv'; a.click();
    URL.revokeObjectURL(url); toast('Export downloaded');
  } catch (e) { toast(e.message, 'err'); }
}

function openImport() {
  openModal(`
    <div class="modal-head"><h2>Import Assets from CSV</h2><button class="x-btn" onclick="closeModal()">✕</button></div>
    <div class="modal-body">
      <p class="muted" style="margin-bottom:14px">Upload a CSV with columns: <span class="tag">asset_tag</span>, name, serial, model, manufacturer, status, category, location, assigned_to, purchase_date, purchase_cost, warranty_expiry, notes. Categories, locations and people are created automatically. Existing tags are updated.</p>
      <div class="field"><input type="file" id="csv-file" accept=".csv"></div>
      <div id="import-result"></div>
    </div>
    <div class="modal-foot"><button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button><button type="button" class="btn btn-primary" onclick="doImport()">Import</button></div>`);
}

async function doImport() {
  const input = document.getElementById('csv-file');
  if (!input.files.length) return toast('Choose a CSV file first', 'err');
  const fd = new FormData(); fd.append('file', input.files[0]);
  try {
    const r = await api('/assets/import/csv', { method: 'POST', body: fd });
    document.getElementById('import-result').innerHTML = `<div class="card" style="padding:14px;margin-top:6px"><b>${r.created} created</b>, <b>${r.updated} updated</b>.${r.errors.length ? `<div style="color:var(--red);margin-top:8px;font-size:13px">${r.errors.slice(0, 5).map(esc).join('<br>')}</div>` : ''}</div>`;
    _lookups = { categories: [], locations: [], employees: [] };
    toast(`Imported ${r.created + r.updated} assets`);
  } catch (e) { toast(e.message, 'err'); }
}

// ============ CATEGORIES / LOCATIONS / PEOPLE ============
const ICON_CHOICES = ['box', 'laptop', 'monitor', 'tv', 'smartphone', 'server', 'wifi', 'mouse'];

async function pageCategories() {
  const page = document.getElementById('page');
  page.innerHTML = pageHeader('Categories', null, `<button class="btn btn-accent" onclick="openCatForm()">${icon('plus', 16)}New Category</button>`) + loading();
  let cats; try { cats = await api('/categories'); } catch (e) { return toast(e.message, 'err'); }
  _lookups.categories = cats;
  const body = cats.length ? `<div class="chip-grid">${cats.map(c => `
    <div class="chip"><div class="ci"><div class="ico">${icon(c.icon || 'box', 20)}</div><div><b>${esc(c.name)}</b><small>${c.asset_count} asset${c.asset_count !== 1 ? 's' : ''}</small></div></div>
    <div class="acts"><button class="icon-btn" onclick="openCatForm(${c.id})">${icon('edit', 16)}</button><button class="icon-btn danger" onclick="delLookup('categories', ${c.id}, 'Category')">${icon('trash', 16)}</button></div></div>`).join('')}</div>`
    : `<div class="card"><div class="empty">${icon('layers', 44)}<h3>No categories</h3></div></div>`;
  page.innerHTML = pageHeader('Categories', null, `<button class="btn btn-accent" onclick="openCatForm()">${icon('plus', 16)}New Category</button>`) + body;
}

async function openCatForm(id = null) {
  let c = { name: '', icon: 'box' };
  if (id) c = _lookups.categories.find(x => x.id === id) || c;
  openModal(`
    <div class="modal-head"><h2>${id ? 'Edit' : 'New'} Category</h2><button class="x-btn" onclick="closeModal()">✕</button></div>
    <form id="cat-form"><div class="modal-body">
      <div class="field"><label>Name *</label><input name="name" value="${esc(c.name)}" required></div>
      <div class="field"><label>Icon</label><select name="icon">${ICON_CHOICES.map(i => `<option value="${i}" ${c.icon === i ? 'selected' : ''}>${i}</option>`).join('')}</select></div>
    </div><div class="modal-foot"><button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button><button type="submit" class="btn btn-primary">Save</button></div></form>`);
  document.getElementById('cat-form').onsubmit = async (e) => {
    e.preventDefault(); const f = new FormData(e.target);
    try { await api(id ? '/categories/' + id : '/categories', { method: id ? 'PUT' : 'POST', json: { name: f.get('name'), icon: f.get('icon') } }); closeModal(); toast('Saved'); pageCategories(); }
    catch (err) { toast(err.message, 'err'); }
  };
}

async function pageLocations() {
  const page = document.getElementById('page');
  page.innerHTML = pageHeader('Locations', null, `<button class="btn btn-accent" onclick="openLocForm()">${icon('plus', 16)}New Location</button>`) + loading();
  let locs; try { locs = await api('/locations'); } catch (e) { return toast(e.message, 'err'); }
  _lookups.locations = locs;
  const body = locs.length ? `<div class="chip-grid">${locs.map(l => `
    <div class="chip"><div class="ci"><div class="ico">${icon('pin', 20)}</div><div><b>${esc(l.name)}</b><small>${l.address ? esc(l.address) + ' · ' : ''}${l.asset_count} asset${l.asset_count !== 1 ? 's' : ''}</small></div></div>
    <div class="acts"><button class="icon-btn" onclick="openLocForm(${l.id})">${icon('edit', 16)}</button><button class="icon-btn danger" onclick="delLookup('locations', ${l.id}, 'Location')">${icon('trash', 16)}</button></div></div>`).join('')}</div>`
    : `<div class="card"><div class="empty">${icon('pin', 44)}<h3>No locations</h3></div></div>`;
  page.innerHTML = pageHeader('Locations', null, `<button class="btn btn-accent" onclick="openLocForm()">${icon('plus', 16)}New Location</button>`) + body;
}

async function openLocForm(id = null) {
  let l = { name: '', address: '' };
  if (id) l = _lookups.locations.find(x => x.id === id) || l;
  openModal(`
    <div class="modal-head"><h2>${id ? 'Edit' : 'New'} Location</h2><button class="x-btn" onclick="closeModal()">✕</button></div>
    <form id="loc-form"><div class="modal-body">
      <div class="field"><label>Name *</label><input name="name" value="${esc(l.name)}" required></div>
      <div class="field"><label>Address</label><input name="address" value="${esc(l.address)}"></div>
    </div><div class="modal-foot"><button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button><button type="submit" class="btn btn-primary">Save</button></div></form>`);
  document.getElementById('loc-form').onsubmit = async (e) => {
    e.preventDefault(); const f = new FormData(e.target);
    try { await api(id ? '/locations/' + id : '/locations', { method: id ? 'PUT' : 'POST', json: { name: f.get('name'), address: f.get('address') } }); closeModal(); toast('Saved'); pageLocations(); }
    catch (err) { toast(err.message, 'err'); }
  };
}

async function pageEmployees() {
  const page = document.getElementById('page');
  page.innerHTML = pageHeader('People', null, `<button class="btn btn-accent" onclick="openEmpForm()">${icon('plus', 16)}New Person</button>`) + loading();
  let emps; try { emps = await api('/employees'); } catch (e) { return toast(e.message, 'err'); }
  _lookups.employees = emps;
  const body = emps.length ? `<div class="chip-grid">${emps.map(e => `
    <div class="chip"><div class="ci"><div class="ico" style="background:var(--ink);color:var(--accent)"><b style="font-family:var(--display)">${esc(e.name[0].toUpperCase())}</b></div><div><b>${esc(e.name)}</b><small>${e.department ? esc(e.department) + ' · ' : ''}${e.asset_count} asset${e.asset_count !== 1 ? 's' : ''}</small></div></div>
    <div class="acts"><button class="icon-btn" onclick="openEmpForm(${e.id})">${icon('edit', 16)}</button><button class="icon-btn danger" onclick="delLookup('employees', ${e.id}, 'Person')">${icon('trash', 16)}</button></div></div>`).join('')}</div>`
    : `<div class="card"><div class="empty">${icon('users', 44)}<h3>No people yet</h3><p>Add people to assign assets to them.</p></div></div>`;
  page.innerHTML = pageHeader('People', null, `<button class="btn btn-accent" onclick="openEmpForm()">${icon('plus', 16)}New Person</button>`) + body;
}

async function openEmpForm(id = null) {
  let e = { name: '', email: '', department: '' };
  if (id) e = _lookups.employees.find(x => x.id === id) || e;
  openModal(`
    <div class="modal-head"><h2>${id ? 'Edit' : 'New'} Person</h2><button class="x-btn" onclick="closeModal()">✕</button></div>
    <form id="emp-form"><div class="modal-body">
      <div class="field"><label>Name *</label><input name="name" value="${esc(e.name)}" required></div>
      <div class="field-row"><div class="field"><label>Email</label><input name="email" type="email" value="${esc(e.email)}"></div>
      <div class="field"><label>Department</label><input name="department" value="${esc(e.department)}"></div></div>
    </div><div class="modal-foot"><button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button><button type="submit" class="btn btn-primary">Save</button></div></form>`);
  document.getElementById('emp-form').onsubmit = async (ev) => {
    ev.preventDefault(); const f = new FormData(ev.target);
    try { await api(id ? '/employees/' + id : '/employees', { method: id ? 'PUT' : 'POST', json: { name: f.get('name'), email: f.get('email'), department: f.get('department') } }); closeModal(); toast('Saved'); pageEmployees(); }
    catch (err) { toast(err.message, 'err'); }
  };
}

async function delLookup(type, id, label) {
  if (!confirm(`Delete this ${label.toLowerCase()}?`)) return;
  try { await api(`/${type}/${id}`, { method: 'DELETE' }); toast(`${label} deleted`); ({ categories: pageCategories, locations: pageLocations, employees: pageEmployees }[type])(); }
  catch (e) { toast(e.message, 'err'); }
}

// ============ SETTINGS ============
async function pageSettings() {
  const page = document.getElementById('page');
  const s = State.settings;
  const canEdit = can('settings.manage');
  page.innerHTML = pageHeader('Settings') + `
    <div style="max-width:560px;display:flex;flex-direction:column;gap:18px">
      <div class="panel"><div class="panel-head"><h3>Organisation</h3></div><div class="panel-body">
        <form id="settings-form">
          <div class="field"><label>Name</label>
            <input name="name" value="${esc(s.name)}" ${canEdit?'':'readonly'}></div>
          <div class="field-row">
            <div class="field"><label>Currency</label>
              <select name="currency" ${canEdit?'':'disabled'}>
                ${['USD','EUR','GBP','CAD','AUD','JPY','INR'].map(c=>`<option ${s.currency===c?'selected':''}>${c}</option>`).join('')}
              </select></div>
            <div class="field"><label>Accent Colour</label>
              <input name="accent_color" type="color" value="${esc(s.accent_color||'#d4f034')}"
                style="height:40px;cursor:pointer" ${canEdit?'':'disabled'}></div>
          </div>
          <div class="field"><label>Logo URL</label>
            <input name="logo_url" value="${esc(s.logo_url||'')}" placeholder="https://…" ${canEdit?'':'readonly'}></div>
          ${canEdit?`<button class="btn btn-primary" type="submit">Save Settings</button>`:''}
        </form>
      </div></div>
      <div class="panel"><div class="panel-head"><h3>${icon('lock',16)} Change Password</h3></div><div class="panel-body">
        <form id="pw-form">
          <div class="field"><label>Current Password</label>
            <input name="current_password" type="password" required></div>
          <div class="field"><label>New Password</label>
            <input name="new_password" type="password" required minlength="6"></div>
          <button class="btn btn-primary" type="submit">Update Password</button>
        </form>
      </div></div>
    </div>`;

  if (canEdit) {
    document.getElementById('settings-form').onsubmit = async (e) => {
      e.preventDefault(); const f = new FormData(e.target);
      const body = {name:f.get('name'),currency:f.get('currency'),
                    accent_color:f.get('accent_color'),logo_url:f.get('logo_url')};
      try {
        await api('/settings',{method:'PUT',json:body});
        State.settings = {...State.settings, ...body};
        document.documentElement.style.setProperty('--accent', body.accent_color);
        toast('Settings saved');
      } catch(err) { toast(err.message,'err'); }
    };
  }
  document.getElementById('pw-form').onsubmit = async (e) => {
    e.preventDefault(); const f = new FormData(e.target);
    try {
      await api('/auth/change-password',{method:'POST',
        json:{current_password:f.get('current_password'),new_password:f.get('new_password')}});
      toast('Password updated'); e.target.reset();
    } catch(err) { toast(err.message,'err'); }
  };
}

// ============ TEAM PAGE (client users) ============
async function pageTeam() {
  if (!can('users.manage')) { navigate('dashboard'); return; }
  const page = document.getElementById('page');
  page.innerHTML = pageHeader('Team', null,
    `<button class="btn btn-accent" onclick="openUserForm(${State.user?.tenant_id})">${icon('plus',16)}New User</button>`) + loading();
  let [users, roles] = [[],[]];
  try { [users,roles] = await Promise.all([api('/users'), api('/users/roles/all')]); }
  catch(e) { toast(e.message,'err'); return; }

  if (!users.length) {
    page.innerHTML = pageHeader('Team',null,`<button class="btn btn-accent" onclick="openUserForm(${State.user?.tenant_id})">${icon('plus',16)}New User</button>`) +
      `<div class="table-wrap"><div class="empty">${icon('users',44)}<h3>No team members yet</h3></div></div>`;
    return;
  }

  const rows = users.map(u=>`
    <tr>
      <td>
        <div style="display:flex;align-items:center;gap:10px">
          <div class="avatar" style="width:32px;height:32px;font-size:13px;flex-shrink:0">${esc(u.name[0].toUpperCase())}</div>
          <div><b>${esc(u.name)}</b><div class="cell-sub">${esc(u.email)}</div></div>
        </div>
      </td>
      <td><span class="tag">${esc(u.role_name||'')}</span></td>
      <td><span class="badge ${u.active?'available':'retired'}">${u.active?'Active':'Inactive'}</span></td>
      <td>
        <div style="display:flex;gap:6px">
          <button class="btn btn-ghost btn-sm" onclick="openUserForm(${u.tenant_id},${u.id})">${icon('edit',14)}</button>
          <button class="btn btn-ghost btn-sm" onclick="openPermEditor(${u.id},'${esc(u.name)}')">${icon('lock',14)}</button>
          <button class="btn btn-danger btn-sm" onclick="deleteUser(${u.id},pageTeam)">${icon('trash',14)}</button>
        </div>
      </td>
    </tr>`).join('');

  page.innerHTML = pageHeader('Team',null,`<button class="btn btn-accent" onclick="openUserForm(${State.user?.tenant_id})">${icon('plus',16)}New User</button>`) + `
    <div class="table-wrap"><table>
      <thead><tr><th>Member</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
}

// ============ REQUESTS PAGE ============
const REQ_PRIORITY_COLORS = { low:'#9ca3af', normal:'#3b82f6', high:'#f59e0b', urgent:'#ef4444' };
const REQ_STATUS_LABELS   = { open:'Open', in_progress:'In Progress', fulfilled:'Fulfilled', declined:'Declined' };
const REQ_STATUS_BADGE    = { open:'deployed', in_progress:'maintenance', fulfilled:'available', declined:'retired' };

async function pageRequests() {
  const page = document.getElementById('page');
  const addBtn = `<button class="btn btn-accent" onclick="openRequestForm()">${icon('plus',16)}New Request</button>`;
  page.innerHTML = pageHeader('Asset Requests', null, addBtn) + loading();
  let reqs;
  try { reqs = await api('/requests'); } catch(e) { toast(e.message,'err'); return; }

  if (!reqs.length) {
    page.innerHTML = pageHeader('Asset Requests', null, addBtn) +
      `<div class="table-wrap"><div class="empty">${icon('activity',44)}
        <h3>No requests yet</h3>
        <p>Submit a request when you need new hardware or equipment.</p>
      </div></div>`;
    return;
  }

  const rows = reqs.map(r => `
    <tr onclick="openRequestDetail(${r.id})" style="cursor:pointer">
      <td>
        <div style="display:flex;align-items:center;gap:8px">
          <span style="width:8px;height:8px;border-radius:50%;background:${REQ_PRIORITY_COLORS[r.priority]||'#9ca3af'};flex-shrink:0"></span>
          <b>${esc(r.title)}</b>
        </div>
      </td>
      <td><span class="badge ${REQ_STATUS_BADGE[r.status]||''}">
        ${REQ_STATUS_LABELS[r.status]||r.status}</span></td>
      <td class="muted">${esc(r.priority)}</td>
      <td class="muted">${esc(r.requested_by_name||'—')}</td>
      <td class="muted">${fmtDate(r.created_at)}</td>
    </tr>`).join('');

  page.innerHTML = pageHeader('Asset Requests', null, addBtn) + `
    <div class="table-wrap"><table>
      <thead><tr><th>Title</th><th>Status</th><th>Priority</th><th>Requested by</th><th>Date</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    <p class="muted" style="margin-top:12px;font-size:12.5px">${reqs.length} request${reqs.length!==1?'s':''}</p>`;
}

function openRequestForm() {
  openModal(`
    <div class="modal-head"><h2>New Asset Request</h2>
      <button class="x-btn" onclick="closeModal()">✕</button></div>
    <form id="req-form"><div class="modal-body">
      <div class="field"><label>What do you need? *</label>
        <input name="title" placeholder="e.g. MacBook Pro for new hire" required></div>
      <div class="field"><label>Details</label>
        <textarea name="description" placeholder="Any specs, quantities, urgency context…" rows="4"></textarea></div>
      <div class="field"><label>Priority</label>
        <select name="priority">
          <option value="low">Low</option>
          <option value="normal" selected>Normal</option>
          <option value="high">High</option>
          <option value="urgent">Urgent</option>
        </select></div>
    </div>
    <div class="modal-foot">
      <button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button type="submit" class="btn btn-primary">Submit Request</button>
    </div></form>`);

  document.getElementById('req-form').onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const btn = e.target.querySelector('[type=submit]'); btn.disabled = true;
    try {
      await api('/requests', { method:'POST', json:{
        title: f.get('title'), description: f.get('description'), priority: f.get('priority')
      }});
      closeModal(); toast('Request submitted'); pageRequests();
    } catch(err) { toast(err.message,'err'); btn.disabled=false; }
  };
}

async function openRequestDetail(id) {
  let reqs;
  try { reqs = await api('/requests'); } catch(e) { return toast(e.message,'err'); }
  const r = reqs.find(x => x.id === id);
  if (!r) return;

  const canUpdate = isMSP() || can('assets.edit');
  const statusOpts = Object.entries(REQ_STATUS_LABELS).map(([v,l])=>
    `<option value="${v}" ${r.status===v?'selected':''}>${l}</option>`).join('');

  openModal(`
    <div class="modal-head">
      <div>
        <div class="crumb" style="font-size:12px;color:var(--text-muted)">Request #${r.id}</div>
        <h2>${esc(r.title)}</h2>
      </div>
      <button class="x-btn" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-body">
      <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap">
        <span class="badge ${REQ_STATUS_BADGE[r.status]||''}">${REQ_STATUS_LABELS[r.status]||r.status}</span>
        <span style="display:flex;align-items:center;gap:5px;font-size:13px;color:var(--text-muted)">
          <span style="width:8px;height:8px;border-radius:50%;background:${REQ_PRIORITY_COLORS[r.priority]}"></span>
          ${esc(r.priority)} priority
        </span>
        <span class="muted" style="font-size:13px">by ${esc(r.requested_by_name||'Unknown')} · ${fmtDate(r.created_at)}</span>
      </div>
      ${r.description ? `<p style="margin-bottom:16px;white-space:pre-wrap">${esc(r.description)}</p>` : ''}
      ${r.notes ? `<div class="card" style="padding:12px 14px;margin-bottom:14px;background:var(--bg)">
        <div class="crumb" style="font-size:11.5px;margin-bottom:4px">MSP Notes</div>
        <p style="white-space:pre-wrap">${esc(r.notes)}</p></div>` : ''}
      ${canUpdate ? `<form id="req-update-form">
        <div class="field-row" style="margin-top:14px">
          <div class="field"><label>Update Status</label>
            <select name="status">${statusOpts}</select></div>
        </div>
        <div class="field"><label>Notes / Response</label>
          <textarea name="notes" rows="3" placeholder="Add a note visible to the client…">${esc(r.notes||'')}</textarea></div>
      </form>` : ''}
    </div>
    <div class="modal-foot" style="justify-content:space-between">
      <button class="btn btn-danger" onclick="deleteRequest(${r.id})">${icon('trash',14)}</button>
      <div style="display:flex;gap:8px">
        <button class="btn btn-ghost" onclick="closeModal()">Close</button>
        ${canUpdate ? `<button class="btn btn-primary" onclick="saveRequestUpdate(${r.id})">Save Update</button>` : ''}
      </div>
    </div>`);
}

async function saveRequestUpdate(id) {
  const f = new FormData(document.getElementById('req-update-form'));
  try {
    await api('/requests/' + id, { method:'PUT', json:{ status:f.get('status'), notes:f.get('notes') }});
    closeModal(); toast('Request updated'); pageRequests();
  } catch(e) { toast(e.message,'err'); }
}

async function deleteRequest(id) {
  if (!confirm('Delete this request?')) return;
  try { await api('/requests/'+id,{method:'DELETE'}); closeModal(); toast('Request deleted'); pageRequests(); }
  catch(e) { toast(e.message,'err'); }
}

// ============ BILLING PAGE ============
async function pageBilling() {
  const page = document.getElementById('page');
  page.innerHTML = pageHeader('Plan & Usage', 'MSP') + loading();
  let status, tiers;
  try { [status, tiers] = await Promise.all([api('/billing/status'), api('/billing/tiers')]); }
  catch(e) { toast(e.message,'err'); return; }

  if (!status.saas) {
    page.innerHTML = pageHeader('Plan & Usage', 'MSP') + `
      <div class="panel" style="max-width:560px">
        <div class="panel-head"><h3>Self-hosted installation</h3></div>
        <div class="panel-body">
          <p class="muted" style="margin-bottom:14px">
            You're running Tether on your own infrastructure. There are no asset limits and no billing.
          </p>
          <p class="muted">
            Want the hosted version for your clients?
            Visit <a href="https://usetether.ca" target="_blank" style="color:var(--accent)">usetether.ca</a>
            to create a SaaS account.
          </p>
        </div>
      </div>`;
    return;
  }

  // Build banner
  let banner = '';
  if (status.trial_expired) {
    banner = `<div class="billing-banner exceeded">${icon('alert',18)}
      <div><b>Your free trial has expired.</b> Assets are locked — upgrade to continue adding assets.</div>
      </div>`;
  } else if (status.tier === 'trial' && status.trial_days_left !== null) {
    banner = `<div class="billing-banner trial">${icon('alert',18)}
      <div><b>Free trial — ${status.trial_days_left} day${status.trial_days_left!==1?'s':''} remaining.</b>
      Upgrade any time to keep full access.</div></div>`;
  } else if (status.usage_status === 'exceeded') {
    banner = `<div class="billing-banner exceeded">${icon('alert',18)}
      <div><b>Asset limit reached.</b> You've used all ${status.asset_limit} assets on your
      ${status.tier_name} plan. Upgrade to add more.</div></div>`;
  } else if (status.usage_status === 'warning') {
    banner = `<div class="billing-banner warn">${icon('alert',18)}
      <div><b>Approaching your limit.</b> You've used ${status.usage_pct}% of your
      ${status.asset_limit} asset limit.</div></div>`;
  }

  // Usage bar
  const fillClass = status.usage_status === 'exceeded' ? 'exceeded' : status.usage_status === 'warning' ? 'warn' : '';
  const limitLabel = status.asset_limit ? `${status.total_assets} / ${status.asset_limit}` : `${status.total_assets} (unlimited)`;
  const pctWidth   = status.asset_limit ? Math.min(100, status.usage_pct) : 0;

  // Tier cards
  const tierCards = tiers.map(t => `
    <div class="tier-card ${t.key === status.tier ? 'active' : ''}" onclick="selectTier('${t.key}')">
      <div class="tc-name">${esc(t.name)}</div>
      <div class="tc-price">${t.price_cad ? `$${t.price_cad}<small>/mo CAD</small>` : t.key==='enterprise'?'Custom':'Free'}</div>
      <div class="tc-desc">${esc(t.description)}</div>
      ${t.key === status.tier ? `<div style="margin-top:10px;font-size:12px;font-weight:600;color:var(--accent-deep)">✓ Current plan</div>` : ''}
    </div>`).join('');

  page.innerHTML = pageHeader('Plan & Usage', 'MSP') + banner + `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;max-width:800px">
      <div class="panel">
        <div class="panel-head"><h3>Current Usage</h3></div>
        <div class="panel-body">
          <div style="margin-bottom:16px">
            <div style="font-size:13px;color:var(--text-muted);margin-bottom:6px">Managed Assets</div>
            <div style="font-family:var(--display);font-size:34px;font-weight:700">${status.total_assets}
              ${status.asset_limit?`<span style="font-size:16px;color:var(--text-muted);font-weight:500"> / ${status.asset_limit}</span>`:''}
            </div>
            ${status.asset_limit ? `
            <div class="usage-bar-track" style="margin-top:10px">
              <div class="usage-bar-fill ${fillClass}" style="width:${pctWidth}%"></div>
            </div>
            <div style="font-size:12px;color:var(--text-muted);margin-top:5px">${status.usage_pct}% used</div>` : ''}
          </div>
          <div class="drow"><div class="k">Plan</div><div class="v">${esc(status.tier_name)}</div></div>
          ${status.trial_days_left !== null ? `<div class="drow"><div class="k">Trial ends</div><div class="v">${status.trial_days_left} days</div></div>` : ''}
          ${status.billing_email ? `<div class="drow"><div class="k">Billing email</div><div class="v">${esc(status.billing_email)}</div></div>` : ''}
        </div>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>What's included</h3></div>
        <div class="panel-body">
          <div class="drow"><div class="k">Clients</div><div class="v">Unlimited</div></div>
          <div class="drow"><div class="k">Users</div><div class="v">Unlimited</div></div>
          <div class="drow"><div class="k">Asset requests</div><div class="v">Included</div></div>
          <div class="drow"><div class="k">QR labels</div><div class="v">Included</div></div>
          <div class="drow"><div class="k">CSV import/export</div><div class="v">Included</div></div>
          <div class="drow"><div class="k">White-label login</div><div class="v">Included</div></div>
        </div>
      </div>
    </div>

    <div style="max-width:800px">
      <h3 style="font-family:var(--display);font-size:18px;margin:28px 0 4px">Choose a plan</h3>
      <p class="muted" style="margin-bottom:0;font-size:13px">Unlimited clients and users on every plan. Upgrade or downgrade any time.</p>
      <div class="tier-grid">${tierCards}</div>
      <p class="muted" style="margin-top:16px;font-size:12.5px">
        To upgrade, contact <a href="mailto:billing@usetether.ca" style="color:var(--accent)">billing@usetether.ca</a>
        or visit <a href="https://usetether.ca/pricing" target="_blank" style="color:var(--accent)">usetether.ca/pricing</a>.
        Annual billing saves 2 months.
      </p>
    </div>`;
}

function selectTier(key) {
  // In a real SaaS this would redirect to a Stripe checkout.
  // For now, show a contact prompt.
  const msgs = {
    enterprise: 'For Enterprise pricing, email billing@usetether.ca or call your ATech Solutions account manager.',
    starter:    'To switch to the Starter plan, email billing@usetether.ca.',
    growth:     'To switch to the Growth plan, email billing@usetether.ca.',
    scale:      'To switch to the Scale plan, email billing@usetether.ca.',
  };
  toast(msgs[key] || 'Contact billing@usetether.ca to change your plan.');
}

// ============ USAGE BAR (sidebar) ============
let _usageCache = null;

async function loadSidebarUsage() {
  if (!isMSP()) return;
  try {
    _usageCache = await api('/billing/status');
    renderSidebarUsage(_usageCache);
  } catch(_) {}
}

function renderSidebarUsage(status) {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar || !status || !status.saas) return;

  // Don't show for self-hosted
  const existing = document.getElementById('sidebar-usage');
  if (existing) existing.remove();

  const fillClass = status.usage_status === 'exceeded' ? 'exceeded'
                  : status.usage_status === 'warning'  ? 'warn' : '';
  const pctWidth  = status.asset_limit ? Math.min(100, status.usage_pct) : 0;
  const limitTxt  = status.asset_limit ? `${status.total_assets}/${status.asset_limit}` : `${status.total_assets}`;

  const el = document.createElement('div');
  el.id = 'sidebar-usage';
  el.className = 'usage-bar-wrap';
  el.innerHTML = `
    <div class="usage-bar-label"><span>Assets</span><b>${limitTxt}</b></div>
    ${status.asset_limit ? `
    <div class="usage-bar-track">
      <div class="usage-bar-fill ${fillClass}" style="width:${pctWidth}%"></div>
    </div>` : ''}
    ${(status.usage_status !== 'ok' || status.tier === 'trial') ? `
    <div class="usage-upgrade" onclick="navigate('billing')">
      ${icon('arrowOut',12)}
      ${status.trial_expired ? 'Trial expired — upgrade' :
        status.usage_status === 'exceeded' ? 'Limit reached — upgrade' :
        status.usage_status === 'warning'  ? 'Approaching limit' :
        `Trial: ${status.trial_days_left}d left`}
    </div>` : ''}`;

  // Insert before the nav
  const nav = sidebar.querySelector('nav.nav');
  if (nav) sidebar.insertBefore(el, nav);
}

// ============ STRIPE CHECKOUT (called from billing page) ============
let _stripeConfig = null;

async function loadStripeConfig() {
  try {
    _stripeConfig = await api('/stripe/config');
  } catch(_) { _stripeConfig = { enabled: false }; }
}

async function startCheckout(tier, interval) {
  if (!_stripeConfig?.enabled) {
    toast('Stripe is not configured on this installation. Contact billing@usetether.ca to upgrade.', 'warn');
    return;
  }
  const btn = document.getElementById(`checkout-${tier}-${interval}`);
  if (btn) { btn.disabled = true; btn.textContent = 'Redirecting…'; }

  try {
    const r = await api('/stripe/checkout', 'POST', { tier, interval });
    window.location.href = r.checkout_url;
  } catch(err) {
    toast(err.message, 'err');
    if (btn) { btn.disabled = false; btn.textContent = getCheckoutLabel(tier, interval); }
  }
}

async function openCustomerPortal() {
  const btn = document.getElementById('manage-subscription-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Opening…'; }
  try {
    const r = await api('/stripe/portal', 'POST', {});
    window.location.href = r.portal_url;
  } catch(err) {
    toast(err.message, 'err');
    if (btn) { btn.disabled = false; btn.textContent = 'Manage subscription'; }
  }
}

function getCheckoutLabel(tier, interval) {
  return `Upgrade to ${tier.charAt(0).toUpperCase()+tier.slice(1)} (${interval})`;
}

// Enhanced billing page with Stripe integration
async function pageBillingStripe() {
  const page = document.getElementById('page');
  page.innerHTML = pageHeader('Plan & Usage', 'MSP') + loading();

  let status, tiers, stripeConf, subDetails;
  try {
    [status, tiers, stripeConf] = await Promise.all([
      api('/billing/status'),
      api('/billing/tiers'),
      fetch('/api/stripe/config').then(r => r.json()),
    ]);
    if (stripeConf.enabled && status.saas) {
      try { subDetails = await api('/stripe/subscription'); } catch(_) {}
    }
  } catch(e) { toast(e.message, 'err'); return; }

  _stripeConfig = stripeConf;

  if (!status.saas) {
    page.innerHTML = pageHeader('Plan & Usage', 'MSP') + `
      <div class="panel" style="max-width:560px">
        <div class="panel-head"><h3>Self-hosted installation</h3></div>
        <div class="panel-body">
          <p class="muted" style="margin-bottom:14px">
            You're running Tether on your own infrastructure. There are no asset limits and no billing.
          </p>
        </div>
      </div>`;
    return;
  }

  // Build banner
  let banner = '';
  if (status.trial_expired) {
    banner = `<div class="billing-banner exceeded">
      <b>Your free trial has expired.</b> Upgrade to continue adding assets.
      </div>`;
  } else if (status.usage_status === 'exceeded') {
    banner = `<div class="billing-banner exceeded">
      <b>Asset limit reached (${status.total_assets}/${status.asset_limit}).</b> Upgrade to add more.
      </div>`;
  } else if (status.usage_status === 'warning') {
    banner = `<div class="billing-banner warn">
      <b>Approaching limit:</b> ${status.usage_pct}% of your ${status.asset_limit} asset limit used.
      </div>`;
  } else if (status.tier === 'trial' && status.trial_days_left !== null) {
    banner = `<div class="billing-banner trial">
      <b>Free trial — ${status.trial_days_left} day${status.trial_days_left!==1?'s':''} remaining.</b>
      Upgrade to keep full access after the trial ends.
      </div>`;
  }

  // Active subscription block
  let subBlock = '';
  if (subDetails?.has_subscription) {
    const cancelNote = subDetails.cancel_at_period_end
      ? `<span style="color:var(--amber)"> · Cancels ${subDetails.current_period_end}</span>` : '';
    subBlock = `
      <div class="panel" style="margin-bottom:18px">
        <div class="panel-head"><h3>Active subscription</h3></div>
        <div class="panel-body">
          <div class="drow"><div class="k">Plan</div><div class="v">${esc(status.tier_name)} (${esc(subDetails.billing_interval)})</div></div>
          <div class="drow"><div class="k">Renews</div><div class="v">${esc(subDetails.current_period_end || '—')}${cancelNote}</div></div>
          <div class="drow"><div class="k">Status</div><div class="v">${esc(subDetails.status || '—')}</div></div>
          <div style="margin-top:14px">
            <button id="manage-subscription-btn" class="btn btn-ghost" onclick="openCustomerPortal()">
              Manage subscription
            </button>
          </div>
        </div>
      </div>`;
  }

  // Billing interval toggle
  const billingToggle = stripeConf.enabled ? `
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:28px">
      <span style="font-size:14px;color:var(--text-muted)">Billing:</span>
      <div style="display:flex;background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden">
        <button id="toggle-monthly" onclick="setBillingInterval('monthly')"
          style="padding:7px 16px;font-size:13px;font-weight:600;border:none;cursor:pointer;
                 background:var(--accent);color:var(--ink);font-family:var(--sans)">Monthly</button>
        <button id="toggle-annual" onclick="setBillingInterval('annual')"
          style="padding:7px 16px;font-size:13px;font-weight:600;border:none;cursor:pointer;
                 background:transparent;color:var(--text-muted);font-family:var(--sans)">
          Annual <span style="font-size:11px;color:var(--emerald);margin-left:4px">Save 17%</span>
        </button>
      </div>
    </div>` : '';

  // Tier cards
  const ANNUAL_DISCOUNT = 0.8333; // 2 months free = 10/12
  const billableTiers = tiers.filter(t => t.key !== 'trial' && t.key !== 'enterprise' && t.key !== 'selfhosted');

  const tierCards = billableTiers.map(t => {
    const isCurrent = t.key === status.tier;
    const monthlyPrice = t.price_cad;
    const annualPrice  = t.price_cad ? Math.round(t.price_cad * ANNUAL_DISCOUNT) : null;
    const priceHtml = t.price_cad
      ? `<div class="tc-price monthly-price">$${monthlyPrice}<small>/mo CAD</small></div>
         <div class="tc-price annual-price" style="display:none">$${annualPrice}<small>/mo CAD · billed annually</small></div>`
      : `<div class="tc-price">Custom</div>`;

    const ctaHtml = isCurrent
      ? `<div style="margin-top:10px;font-size:12px;font-weight:600;color:var(--accent-deep)">✓ Current plan</div>`
      : stripeConf.enabled
        ? `<button id="checkout-${t.key}-monthly" class="btn btn-ghost" style="margin-top:12px;width:100%;justify-content:center"
             onclick="startCheckout('${t.key}', currentBillingInterval)">
             Upgrade to ${esc(t.name)}
           </button>`
        : `<div style="margin-top:10px;font-size:12px;color:var(--text-muted)">
             Email <a href="mailto:billing@usetether.ca" style="color:var(--accent)">billing@usetether.ca</a> to upgrade
           </div>`;

    return `
      <div class="tier-card ${isCurrent ? 'active' : ''}">
        <div class="tc-name">${esc(t.name)}</div>
        ${priceHtml}
        <div class="tc-desc">${esc(t.description)}</div>
        ${ctaHtml}
      </div>`;
  }).join('');

  // Usage stat
  const pctWidth = status.asset_limit ? Math.min(100, status.usage_pct) : 0;
  const fillClass = status.usage_status === 'exceeded' ? 'exceeded' : status.usage_status === 'warning' ? 'warn' : '';

  page.innerHTML = pageHeader('Plan & Usage', 'MSP') + banner + subBlock + `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;max-width:800px;margin-bottom:28px">
      <div class="panel">
        <div class="panel-head"><h3>Current usage</h3></div>
        <div class="panel-body">
          <div style="font-size:13px;color:var(--text-muted);margin-bottom:6px">Managed assets</div>
          <div style="font-family:var(--display);font-size:34px;font-weight:700">${status.total_assets}
            ${status.asset_limit ? `<span style="font-size:16px;color:var(--text-muted);font-weight:500"> / ${status.asset_limit}</span>` : ''}
          </div>
          ${status.asset_limit ? `
          <div class="usage-bar-track" style="margin-top:10px">
            <div class="usage-bar-fill ${fillClass}" style="width:${pctWidth}%"></div>
          </div>
          <div style="font-size:12px;color:var(--text-muted);margin-top:5px">${status.usage_pct}% used</div>` : ''}
        </div>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>Plan details</h3></div>
        <div class="panel-body">
          <div class="drow"><div class="k">Plan</div><div class="v">${esc(status.tier_name)}</div></div>
          ${status.trial_days_left !== null ? `<div class="drow"><div class="k">Trial ends</div><div class="v">${status.trial_days_left} days</div></div>` : ''}
          ${status.billing_email ? `<div class="drow"><div class="k">Billing email</div><div class="v">${esc(status.billing_email)}</div></div>` : ''}
        </div>
      </div>
    </div>

    <h3 style="font-family:var(--display);font-size:18px;margin:0 0 14px">Choose a plan</h3>
    ${billingToggle}
    <div class="tier-grid" style="max-width:800px">${tierCards}</div>

    <p class="muted" style="margin-top:16px;font-size:12.5px">
      Need Enterprise or have questions?
      <a href="mailto:billing@usetether.ca" style="color:var(--accent)">billing@usetether.ca</a>
      · Annual billing saves 2 months.
    </p>`;
}

let currentBillingInterval = 'monthly';

function setBillingInterval(interval) {
  currentBillingInterval = interval;
  const monthly = document.getElementById('toggle-monthly');
  const annual  = document.getElementById('toggle-annual');
  if (monthly && annual) {
    monthly.style.background = interval === 'monthly' ? 'var(--accent)' : 'transparent';
    monthly.style.color      = interval === 'monthly' ? 'var(--ink)'    : 'var(--text-muted)';
    annual.style.background  = interval === 'annual'  ? 'var(--accent)' : 'transparent';
    annual.style.color       = interval === 'annual'  ? 'var(--ink)'    : 'var(--text-muted)';
  }
  document.querySelectorAll('.monthly-price').forEach(el => el.style.display = interval === 'monthly' ? '' : 'none');
  document.querySelectorAll('.annual-price').forEach(el => el.style.display  = interval === 'annual'  ? '' : 'none');

  // Update checkout button labels
  ['starter','growth','scale'].forEach(tier => {
    const btn = document.getElementById(`checkout-${tier}-monthly`);
    if (btn) {
      btn.id = `checkout-${tier}-${interval}`;
      btn.onclick = () => startCheckout(tier, interval);
    }
  });
}

// ============ SYSTEM STATUS / ADMIN PAGE ============
async function pageAdmin() {
  const page = document.getElementById('page');
  page.innerHTML = pageHeader('System', 'MSP') + loading();

  let status;
  try { status = await api('/admin/status'); }
  catch(e) { toast(e.message, 'err'); return; }

  const svc = status.services;

  const statusDot = (ok) => ok
    ? `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--emerald);box-shadow:0 0 5px var(--emerald)"></span>`
    : `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--amber)"></span>`;

  page.innerHTML = pageHeader('System', 'MSP') + `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;max-width:800px">

      <div class="panel">
        <div class="panel-head"><h3>Database</h3></div>
        <div class="panel-body">
          <div class="drow"><div class="k">Assets</div><div class="v">${status.database.total_assets}</div></div>
          <div class="drow"><div class="k">Clients</div><div class="v">${status.database.total_tenants}</div></div>
          <div class="drow"><div class="k">Users</div><div class="v">${status.database.total_users}</div></div>
          <div class="drow"><div class="k">Mode</div><div class="v">${status.deployment_mode}</div></div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head"><h3>Services</h3></div>
        <div class="panel-body">
          <div class="drow"><div class="k">${statusDot(svc.email_configured)} Email</div>
            <div class="v">${svc.email_provider}</div></div>
          <div class="drow"><div class="k">${statusDot(svc.stripe_configured)} Stripe</div>
            <div class="v">${svc.stripe_configured ? 'Configured' : 'Not configured'}</div></div>
          <div class="drow"><div class="k">${statusDot(svc.backup_configured)} Backups</div>
            <div class="v">${svc.backup_enabled ? (svc.backup_configured ? 'Configured' : 'Enabled but not configured') : 'Disabled'}</div></div>
          <div class="drow"><div class="k">${statusDot(svc.warranty_alerts)} Warranty alerts</div>
            <div class="v">${svc.warranty_alerts ? `Every day (${svc.warranty_window_days}d window)` : 'Disabled'}</div></div>
        </div>
      </div>

    </div>

    <!-- Backup section -->
    <div class="panel" style="max-width:800px;margin-top:18px">
      <div class="panel-head">
        <h3>Backup</h3>
        <div style="display:flex;gap:10px">
          <button class="btn btn-ghost btn-sm" onclick="listBackups()">View backups</button>
          <button class="btn btn-accent btn-sm" onclick="runBackupNow()">Run now</button>
        </div>
      </div>
      <div class="panel-body">
        ${svc.backup_configured
          ? `<p class="muted">Automated backups active. Destination: <code>${status.services.backup_destination}</code></p>`
          : `<p class="muted">Backups not configured. Set <code>BACKUP_ENABLED=true</code> and S3 credentials in your <code>.env</code> to enable automated backups.</p>`}
        <div id="backup-output"></div>
      </div>
    </div>

    <!-- Warranty alerts section -->
    <div class="panel" style="max-width:800px;margin-top:18px">
      <div class="panel-head">
        <h3>Warranty alerts</h3>
        <button class="btn btn-ghost btn-sm" onclick="triggerWarrantyAlerts()">Send now</button>
      </div>
      <div class="panel-body">
        ${svc.warranty_alerts && svc.email_configured
          ? `<p class="muted">Sends daily at 08:00 UTC. Covers assets expiring within ${svc.warranty_window_days} days.</p>`
          : `<p class="muted">Warranty alerts require <code>WARRANTY_ALERTS_ENABLED=true</code> and an email provider configured in <code>.env</code>.</p>`}
      </div>
    </div>`;
}

async function runBackupNow() {
  const out = document.getElementById('backup-output');
  if (out) out.innerHTML = '<div class="muted" style="margin-top:12px">Running backup…</div>';
  try {
    const r = await api('/admin/backup/run', 'POST', {});
    if (out) out.innerHTML = `<div style="margin-top:12px;padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:8px;font-size:13px">
      <div style="color:var(--emerald);font-weight:600;margin-bottom:6px">Backup complete</div>
      <div class="drow"><div class="k">File</div><div class="v"><code>${esc(r.file)}</code></div></div>
      <div class="drow"><div class="k">Size</div><div class="v">${r.size_kb} KB</div></div>
      <div class="drow"><div class="k">Destination</div><div class="v">${esc(r.destination)}</div></div>
    </div>`;
  } catch(e) {
    if (out) out.innerHTML = `<div style="margin-top:12px;color:var(--red)">${esc(e.message)}</div>`;
    toast(e.message, 'err');
  }
}

async function listBackups() {
  const out = document.getElementById('backup-output');
  if (out) out.innerHTML = '<div class="muted" style="margin-top:12px">Loading…</div>';
  try {
    const r = await api('/admin/backup/list');
    if (!r.backups?.length) {
      if (out) out.innerHTML = '<div class="muted" style="margin-top:12px">No backups found.</div>';
      return;
    }
    const rows = r.backups.map(b => `<tr>
      <td><code style="font-size:12px">${esc(b.key.split('/').pop())}</code></td>
      <td>${b.size_kb} KB</td>
      <td>${esc(b.last_modified)}</td>
    </tr>`).join('');
    if (out) out.innerHTML = `<div style="margin-top:14px">
      <table class="data-table" style="font-size:13px">
        <thead><tr><th>File</th><th>Size</th><th>Created</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`;
  } catch(e) { toast(e.message, 'err'); }
}

async function triggerWarrantyAlerts() {
  try {
    const r = await api('/admin/alerts/warranty', 'POST', {});
    toast(`Warranty alerts sent. Assets in window: ${r.assets_in_window}`);
  } catch(e) { toast(e.message, 'err'); }
}
