// ============ ASSETS LIST ============
const AssetFilters = { q: '', status: '', category_id: '', location_id: '', department: '', sort: 'asset_tag', order: 'asc', page: 1 };
let _lookups = { categories: [], locations: [], employees: [] };
let selectedAssetIds = new Set();

async function loadLookups() {
  const [cats, locs, emps] = await Promise.all([
    api('/categories'), api('/locations'), api('/employees'),
  ]);
  _lookups = {
    categories: cats.items ?? cats,
    locations:  locs.items ?? locs,
    employees:  emps.items ?? emps,
  };
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
  let depts = [];
  try { depts = await api('/employees/departments'); } catch (_) {}
  const deptOpts = depts.map(d => `<option value="${esc(d)}">${esc(d)}</option>`).join('');
  let savedViews = [];
  try { savedViews = await api('/saved-filters'); } catch (_) {}
  const savedViewOpts = savedViews.map(v => `<option value="${v.id}">${esc(v.name)}</option>`).join('');
  page.innerHTML = pageHeader('Assets', null, actions) + `
    <div class="toolbar">
      <div class="search">${icon('search', 17)}<input id="f-q" placeholder="Search by tag, name, serial, model…" value="${esc(AssetFilters.q)}"></div>
      <select class="filter" id="f-status"><option value="">All statuses</option>${STATUSES.map(s => `<option value="${s}">${s[0].toUpperCase() + s.slice(1)}</option>`).join('')}</select>
      <select class="filter" id="f-cat"><option value="">All categories</option>${catOpts}</select>
      <select class="filter" id="f-loc"><option value="">All locations</option>${locOpts}</select>
      ${deptOpts ? `<select class="filter" id="f-dept"><option value="">All departments</option>${deptOpts}</select>` : ''}
      <button class="btn btn-ghost btn-sm" onclick="openSaveFilterModal()" title="Save current filters as a named view">${icon('bookmark', 14)} Save View</button>
      ${savedViewOpts ? `<select class="filter" id="f-saved" style="max-width:160px" onchange="loadSavedFilter(this.value, ${JSON.stringify(savedViews)})"><option value="">Saved views…</option>${savedViewOpts}</select>` : ''}
    </div>
    <div id="asset-table">${loading()}</div>`;

  const q = document.getElementById('f-q');
  let t; q.oninput = () => { clearTimeout(t); t = setTimeout(() => { AssetFilters.q = q.value; AssetFilters.page = 1; selectedAssetIds.clear(); loadAssetTable(); }, 250); };
  document.getElementById('f-status').value = AssetFilters.status;
  document.getElementById('f-cat').value = AssetFilters.category_id;
  document.getElementById('f-loc').value = AssetFilters.location_id;
  document.getElementById('f-status').onchange = (e) => { AssetFilters.status = e.target.value; AssetFilters.page = 1; selectedAssetIds.clear(); loadAssetTable(); };
  document.getElementById('f-cat').onchange = (e) => { AssetFilters.category_id = e.target.value; AssetFilters.page = 1; selectedAssetIds.clear(); loadAssetTable(); };
  document.getElementById('f-loc').onchange = (e) => { AssetFilters.location_id = e.target.value; AssetFilters.page = 1; selectedAssetIds.clear(); loadAssetTable(); };
  if (document.getElementById('f-dept')) {
    document.getElementById('f-dept').value = AssetFilters.department;
    document.getElementById('f-dept').onchange = (e) => { AssetFilters.department = e.target.value; AssetFilters.page = 1; selectedAssetIds.clear(); loadAssetTable(); };
  }
  loadAssetTable();
}

function sortBy(col) {
  if (AssetFilters.sort === col) AssetFilters.order = AssetFilters.order === 'asc' ? 'desc' : 'asc';
  else { AssetFilters.sort = col; AssetFilters.order = 'asc'; }
  AssetFilters.page = 1;
  selectedAssetIds.clear();
  loadAssetTable();
}

async function openSaveFilterModal() {
  openModal(`
    <div class="modal-head"><h2>Save View</h2><button class="x-btn" onclick="closeModal()">✕</button></div>
    <div class="modal-body">
      <p class="muted" style="margin-bottom:14px">Save the current filters as a named view so you can re-apply them quickly.</p>
      <div class="field"><label>View name</label><input id="save-view-name" placeholder="e.g. Deployed Laptops – Head Office" autofocus></div>
    </div>
    <div class="modal-foot">
      <button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button type="button" class="btn btn-primary" onclick="doSaveFilter()">Save</button>
    </div>`);
}

async function doSaveFilter() {
  const name = (document.getElementById('save-view-name')?.value || '').trim();
  if (!name) return toast('Enter a name for this view', 'err');
  const filters = {
    q:           AssetFilters.q           || undefined,
    status:      AssetFilters.status      || undefined,
    category_id: AssetFilters.category_id || undefined,
    location_id: AssetFilters.location_id || undefined,
    department:  AssetFilters.department  || undefined,
  };
  Object.keys(filters).forEach(k => filters[k] === undefined && delete filters[k]);
  try {
    await api('/saved-filters', { method: 'POST', json: { name, filters } });
    closeModal();
    toast('View saved');
    loadAssets();
  } catch (e) { toast(e.message, 'err'); }
}

function loadSavedFilter(id, views) {
  if (!id) return;
  const view = views.find(v => String(v.id) === String(id));
  if (!view) return;
  const f = view.filters || {};
  AssetFilters.q           = f.q           || '';
  AssetFilters.status      = f.status      || '';
  AssetFilters.category_id = f.category_id || '';
  AssetFilters.location_id = f.location_id || '';
  AssetFilters.department  = f.department  || '';
  AssetFilters.page        = 1;
  selectedAssetIds.clear();
  loadAssets();
}

function goPrevPage() { if (AssetFilters.page > 1) { AssetFilters.page--; selectedAssetIds.clear(); loadAssetTable(); } }
function goNextPage(pages) { if (AssetFilters.page < pages) { AssetFilters.page++; selectedAssetIds.clear(); loadAssetTable(); } }

async function loadAssetTable() {
  const wrap = document.getElementById('asset-table');
  const params = new URLSearchParams();
  Object.entries(AssetFilters).forEach(([k, v]) => { if (v) params.append(k, v); });
  let data;
  try { data = await api('/assets?' + params); } catch (e) { toast(e.message, 'err'); return; }

  const { items, total, page, pages } = data;

  if (!items.length) {
    selectedAssetIds.clear();
    wrap.innerHTML = `<div class="table-wrap"><div class="empty">${icon('box', 44)}<h3>No assets found</h3><p>${AssetFilters.q || AssetFilters.status ? 'Try adjusting your filters.' : 'Add your first asset to get started.'}</p></div></div>`;
    return;
  }

  const arr = (c) => AssetFilters.sort === c ? `<span class="arr">${AssetFilters.order === 'asc' ? '▲' : '▼'}</span>` : '';
  const visibleIds = items.map(a => a.id);
  const allChecked = visibleIds.length > 0 && visibleIds.every(id => selectedAssetIds.has(id));

  const rows = items.map(a => {
    const checked = selectedAssetIds.has(a.id) ? 'checked' : '';
    return `<tr onclick="navigate('asset', ${a.id})">
      <td onclick="event.stopPropagation()" style="width:36px;padding:0 6px">
        <input type="checkbox" class="asset-cb" data-id="${a.id}" ${checked}
          onchange="_assetCbChange(this)" onclick="event.stopPropagation()">
      </td>
      <td><span class="tag">${esc(a.asset_tag)}</span></td>
      <td><div class="cell-name">${esc(a.name)}</div><div class="cell-sub">${esc(a.manufacturer || a.model || '')}</div></td>
      <td class="muted">${esc(a.category_name || '—')}</td>
      <td>${statusBadge(a.status)}</td>
      <td class="muted">${esc(a.assigned_to_name || '—')}</td>
      <td class="muted">${esc(a.location_name || '—')}</td>
    </tr>`;
  }).join('');

  const pagination = pages > 1 ? `
    <div class="pagination">
      <button class="btn btn-ghost btn-sm" onclick="goPrevPage()" ${page <= 1 ? 'disabled' : ''}>← Prev</button>
      <span class="page-info">Page ${page} of ${pages}</span>
      <button class="btn btn-ghost btn-sm" onclick="goNextPage(${pages})" ${page >= pages ? 'disabled' : ''}>Next →</button>
    </div>` : '';

  const locOpts = _lookups.locations.map(l => `<option value="${l.id}">${esc(l.name)}</option>`).join('');
  const n = selectedAssetIds.size;
  const bulkBar = `
    <div id="bulk-bar" style="${n ? '' : 'display:none'}padding:10px 14px;background:var(--surface);
         border:1px solid var(--border);border-radius:8px;margin-bottom:10px;
         display:${n ? 'flex' : 'none'};align-items:center;gap:10px;flex-wrap:wrap">
      <span style="font-size:13.5px;font-weight:600;color:var(--accent)">${n} selected</span>
      <div style="position:relative;display:inline-block">
        <button class="btn btn-ghost btn-sm" onclick="_toggleBulkMenu('bulk-status-menu',event)">
          Change Status ▾
        </button>
        <div id="bulk-status-menu" style="display:none;position:absolute;left:0;top:100%;margin-top:4px;
             background:var(--surface);border:1px solid var(--border);border-radius:8px;
             box-shadow:0 4px 16px rgba(0,0,0,.15);min-width:150px;z-index:100;padding:4px 0">
          ${['available','deployed','maintenance','retired'].map(s =>
            `<div class="menu-item" onclick="_bulkStatus('${s}')">${s[0].toUpperCase()+s.slice(1)}</div>`
          ).join('')}
        </div>
      </div>
      <div style="position:relative;display:inline-block">
        <button class="btn btn-ghost btn-sm" onclick="_toggleBulkMenu('bulk-loc-menu',event)">
          Move Location ▾
        </button>
        <div id="bulk-loc-menu" style="display:none;position:absolute;left:0;top:100%;margin-top:4px;
             background:var(--surface);border:1px solid var(--border);border-radius:8px;
             box-shadow:0 4px 16px rgba(0,0,0,.15);min-width:180px;z-index:100;padding:4px 0">
          ${_lookups.locations.map(l =>
            `<div class="menu-item" onclick="_bulkLocation(${l.id})">${esc(l.name)}</div>`
          ).join('') || '<div class="menu-item muted">No locations</div>'}
        </div>
      </div>
      ${can('assets.delete') ? `<button class="btn btn-ghost btn-sm" style="color:var(--red)" onclick="_bulkDelete()">Delete</button>` : ''}
      <button class="btn btn-ghost btn-sm" onclick="_printLabels()">Print Labels</button>
      <button class="btn btn-ghost btn-sm" onclick="_clearBulkSelection()">Clear</button>
    </div>`;

  wrap.innerHTML = `
    ${bulkBar}
    <div class="table-wrap"><table>
      <thead><tr>
        <th style="width:36px;padding:0 6px">
          <input type="checkbox" id="select-all-cb" ${allChecked ? 'checked' : ''}
            onchange="_selectAllChange(this, [${visibleIds.join(',')}])">
        </th>
        <th onclick="sortBy('asset_tag')">Tag ${arr('asset_tag')}</th>
        <th onclick="sortBy('name')">Name ${arr('name')}</th>
        <th onclick="sortBy('category_id')">Category</th>
        <th onclick="sortBy('status')">Status ${arr('status')}</th>
        <th>Assigned to</th>
        <th onclick="sortBy('location_id')">Location</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    ${pagination}
    <p class="muted" style="margin-top:8px;font-size:12.5px">${total} asset${total !== 1 ? 's' : ''}</p>`;
}

function _assetCbChange(cb) {
  const id = parseInt(cb.dataset.id, 10);
  if (cb.checked) selectedAssetIds.add(id);
  else selectedAssetIds.delete(id);
  _refreshBulkBar();
}

function _selectAllChange(cb, ids) {
  if (cb.checked) ids.forEach(id => selectedAssetIds.add(id));
  else ids.forEach(id => selectedAssetIds.delete(id));
  // sync individual checkboxes
  document.querySelectorAll('.asset-cb').forEach(el => {
    el.checked = selectedAssetIds.has(parseInt(el.dataset.id, 10));
  });
  _refreshBulkBar();
}

function _refreshBulkBar() {
  const bar = document.getElementById('bulk-bar');
  if (!bar) return;
  const n = selectedAssetIds.size;
  bar.style.display = n ? 'flex' : 'none';
  const label = bar.querySelector('span');
  if (label) label.textContent = `${n} selected`;
}

function _clearBulkSelection() {
  selectedAssetIds.clear();
  document.querySelectorAll('.asset-cb').forEach(el => { el.checked = false; });
  const allCb = document.getElementById('select-all-cb');
  if (allCb) allCb.checked = false;
  _refreshBulkBar();
}

function _toggleBulkMenu(id, e) {
  e.stopPropagation();
  const m = document.getElementById(id);
  if (!m) return;
  // close other open menus first
  ['bulk-status-menu','bulk-loc-menu'].forEach(mid => {
    if (mid !== id) { const el = document.getElementById(mid); if (el) el.style.display = 'none'; }
  });
  m.style.display = m.style.display === 'none' ? '' : 'none';
  const hide = () => { m.style.display = 'none'; document.removeEventListener('click', hide); };
  if (m.style.display !== 'none') document.addEventListener('click', hide);
}

async function _bulkStatus(status) {
  const el = document.getElementById('bulk-status-menu');
  if (el) el.style.display = 'none';
  const ids = [...selectedAssetIds];
  if (!ids.length) return;
  try {
    const r = await api('/assets/bulk/status', 'POST', { asset_ids: ids, status });
    toast(`${r.updated} asset${r.updated !== 1 ? 's' : ''} updated${r.skipped ? `, ${r.skipped} skipped` : ''}`);
    selectedAssetIds.clear();
    loadAssetTable();
  } catch(e) { toast(e.message, 'err'); }
}

async function _bulkLocation(location_id) {
  const el = document.getElementById('bulk-loc-menu');
  if (el) el.style.display = 'none';
  const ids = [...selectedAssetIds];
  if (!ids.length) return;
  try {
    const r = await api('/assets/bulk/location', 'POST', { asset_ids: ids, location_id });
    toast(`${r.updated} asset${r.updated !== 1 ? 's' : ''} moved${r.skipped ? `, ${r.skipped} skipped` : ''}`);
    selectedAssetIds.clear();
    loadAssetTable();
  } catch(e) { toast(e.message, 'err'); }
}

async function _bulkDelete() {
  const ids = [...selectedAssetIds];
  if (!ids.length) return;
  if (!confirm(`Delete ${ids.length} asset${ids.length !== 1 ? 's' : ''}? This cannot be undone.`)) return;
  try {
    const r = await api('/assets/bulk/delete', 'POST', { asset_ids: ids });
    toast(`${r.deleted} asset${r.deleted !== 1 ? 's' : ''} deleted${r.skipped ? `, ${r.skipped} skipped` : ''}`);
    selectedAssetIds.clear();
    loadAssetTable();
  } catch(e) { toast(e.message, 'err'); }
}

function _printLabels() {
  const ids = [...selectedAssetIds];
  if (!ids.length) return;
  openModal(`
    <h3 style="margin-bottom:16px">Print Labels</h3>
    <p style="font-size:13px;color:var(--text-muted);margin-bottom:14px">
      ${ids.length} asset${ids.length !== 1 ? 's' : ''} selected. Choose a label size, then print or save as PDF from the browser.
    </p>
    <div class="field"><label>Label size</label>
      <select id="label-size">
        <option value="small">Small (5 per row)</option>
        <option value="medium" selected>Medium (4 per row)</option>
        <option value="large">Large (3 per row)</option>
      </select>
    </div>
    <div style="display:flex;gap:10px;margin-top:18px">
      <button class="btn btn-primary" id="label-print-btn">Open Print Page</button>
      <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
    </div>`, false);

  document.getElementById('label-print-btn').onclick = async () => {
    const btn = document.getElementById('label-print-btn');
    btn.disabled = true; btn.textContent = 'Generating…';
    const size = document.getElementById('label-size').value;
    try {
      const res = await fetch('/api/assets/labels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${State.token}` },
        body: JSON.stringify({ asset_ids: ids, size }),
      });
      if (!res.ok) { const e = await res.json().catch(()=>{}); throw new Error(e?.detail || 'Failed'); }
      const html = await res.text();
      const w = window.open('', '_blank');
      w.document.write(html);
      w.document.close();
      closeModal();
    } catch(e) { toast(e.message, 'err'); btn.disabled = false; btn.textContent = 'Open Print Page'; }
  };
}

// ============ ASSET FORM ============
async function openAssetForm(id = null) {
  if (!_lookups.categories.length) await loadLookups();
  let a = { asset_tag: '', name: '', serial: '', model: '', manufacturer: '', status: 'available', notes: '', purchase_date: '', purchase_cost: '', warranty_expiry: '', useful_life_years: '', salvage_value: '', category_id: '', location_id: '', assigned_to_id: '', custom_fields: [] };
  if (id) { try { a = await api('/assets/' + id); } catch (e) { return toast(e.message, 'err'); } }

  // Load custom field defs (may fail silently on tenants with none defined)
  let cfDefs = [];
  try { cfDefs = await api('/custom-fields/defs'); } catch (_) {}

  const opt = (arr, sel, placeholder) => `<option value="">${placeholder}</option>` + arr.map(x => `<option value="${x.id}" ${String(sel) === String(x.id) ? 'selected' : ''}>${esc(x.name)}</option>`).join('');

  // Build existing cf value map
  const cfValMap = {};
  if (a.custom_fields) a.custom_fields.forEach(cf => { cfValMap[cf.field_def_id] = cf.value; });

  const cfSection = cfDefs.length ? `
    <div style="border-top:1px solid var(--border);margin-top:14px;padding-top:14px">
      <div style="font-size:12.5px;font-weight:600;color:var(--text-muted);margin-bottom:12px">Custom Fields</div>
      ${cfDefs.map(d => {
        const val = cfValMap[d.id] ?? '';
        const inp = d.field_type === 'boolean'
          ? `<select name="cf_${d.id}"><option value="" ${!val?'selected':''}>—</option><option value="true" ${val==='true'?'selected':''}>Yes</option><option value="false" ${val==='false'?'selected':''}>No</option></select>`
          : d.field_type === 'date'
          ? `<input type="date" name="cf_${d.id}" value="${esc(val)}">`
          : d.field_type === 'number'
          ? `<input type="number" step="any" name="cf_${d.id}" value="${esc(val)}">`
          : `<input type="${d.field_type === 'url' ? 'url' : 'text'}" name="cf_${d.id}" value="${esc(val)}">`;
        return `<div class="field"><label>${esc(d.label)}${d.required ? ' *' : ''}</label>${inp}</div>`;
      }).join('')}
    </div>` : '';

  openModal(`
    <div class="modal-head"><h2>${id ? 'Edit Asset' : 'New Asset'}</h2><button class="x-btn" onclick="closeModal()">✕</button></div>
    <form id="asset-form"><div class="modal-body">
      <div class="field-row">
        <div class="field"><label>Asset Tag *</label><input name="asset_tag" value="${esc(a.asset_tag) || (id ? '' : esc(State.settings?.asset_tag_prefix || ''))}" placeholder="${esc((State.settings?.asset_tag_prefix || '') + '0001')}" required></div>
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
      <div style="border-top:1px solid var(--border);margin-top:14px;padding-top:14px">
        <div style="font-size:12.5px;font-weight:600;color:var(--text-muted);margin-bottom:12px">Depreciation (optional)</div>
        <div class="field-row">
          <div class="field"><label>Useful Life (years)</label>
            <input type="number" name="useful_life_years" min="1" max="50"
                   value="${a.useful_life_years || ''}" placeholder="e.g. 3"></div>
          <div class="field"><label>Salvage Value</label>
            <input type="number" step="0.01" name="salvage_value" min="0"
                   value="${a.salvage_value ?? ''}" placeholder="e.g. 100"></div>
        </div>
      </div>
      ${cfSection}
      <div class="field"><label>Notes</label><textarea name="notes">${esc(a.notes)}</textarea></div>
    </div>
    <div class="modal-foot"><button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button><button type="submit" class="btn btn-primary">${id ? 'Save Changes' : 'Create Asset'}</button></div>
    </form>`);

  document.getElementById('asset-form').onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const payload = {};
    const cfValues = [];
    for (const [k, v] of f.entries()) {
      if (k.startsWith('cf_')) {
        const defId = parseInt(k.slice(3));
        cfValues.push({ field_def_id: defId, value: v || '' });
      } else if (['category_id', 'location_id', 'assigned_to_id'].includes(k)) payload[k] = v ? parseInt(v) : null;
      else if (k === 'useful_life_years') payload[k] = v ? parseInt(v) : null;
      else if (['purchase_cost', 'salvage_value'].includes(k)) payload[k] = v ? parseFloat(v) : null;
      else if (['purchase_date', 'warranty_expiry'].includes(k)) payload[k] = v || null;
      else payload[k] = v;
    }
    const btn = e.target.querySelector('button[type=submit]'); btn.disabled = true;
    try {
      const saved = await api(id ? '/assets/' + id : '/assets', { method: id ? 'PUT' : 'POST', json: payload });
      const assetId = saved.id || id;
      if (cfValues.length && assetId) {
        try { await api(`/custom-fields/values/${assetId}`, { method: 'PUT', json: cfValues }); } catch (_) {}
      }
      closeModal(); toast(id ? 'Asset updated' : 'Asset created');
      State.route === 'asset' ? pageAssetDetail() : loadAssetTable();
    } catch (err) { toast(err.message, 'err'); btn.disabled = false; }
  };
}

// ============ ASSET DETAIL ============
async function pageAssetDetail() {
  const page = document.getElementById('page');
  page.innerHTML = loading();
  let a, history, notes;
  try {
    [a, history, notes] = await Promise.all([
      api('/assets/' + State.param),
      api('/assets/' + State.param + '/history'),
      api('/assets/' + State.param + '/notes').catch(() => []),
    ]);
  } catch (e) { toast(e.message, 'err'); navigate('assets'); return; }

  const back = `<button class="btn btn-ghost btn-sm" onclick="navigate('assets')">${icon('back', 16)}Back</button>`;
  const checkAction = a.status === 'deployed'
    ? `<button class="btn btn-ghost" onclick="openCheckin(${a.id})">${icon('arrowIn', 16)}Check In</button>`
    : `<button class="btn btn-accent" onclick="openCheckout(${a.id})">${icon('arrowOut', 16)}Check Out</button>`;
  const actions = `${checkAction}<button class="btn btn-ghost" onclick="openAssetForm(${a.id})">${icon('edit', 16)}Edit</button><button class="btn btn-danger" onclick="deleteAsset(${a.id})">${icon('trash', 16)}</button>`;

  const row = (k, v) => `<div class="drow"><div class="k">${k}</div><div class="v">${v}</div></div>`;
  const timeline = history.length
    ? `<ul class="timeline">${history.map(h => `<li><div class="t-action">${h.action === 'checkout' ? 'Checked out' : 'Checked in'}${h.employee_name ? ' — ' + esc(h.employee_name) : ''}</div>${h.note ? `<div class="muted" style="font-size:13px">${esc(h.note)}</div>` : ''}<div class="t-time">${fmtDate(h.timestamp)} · ${timeAgo(h.timestamp)}</div></li>`).join('')}</ul>`
    : `<p class="muted">No checkout history yet.</p>`;

  const cfPanel = _renderCustomFieldsPanel(a.custom_fields, a.id);

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
            <img id="asset-qr-img" alt="QR code">
            <p class="muted" style="margin-top:10px;font-size:12.5px">Encodes <span class="tag">${esc(a.asset_tag)}</span></p>
            <button class="btn btn-ghost btn-sm" style="margin-top:10px" onclick="downloadQr(${a.id}, '${esc(a.asset_tag)}')">${icon('download', 15)}Download</button>
            ${can('assets.edit') ? `<button class="btn btn-ghost btn-sm" style="margin-top:6px" onclick="generateCheckinLink(${a.id})">${icon('link', 15)}Self-service link</button>` : ''}
          </div>
        </div>
        <div class="panel">
          <div class="panel-head"><h3>${icon('activity', 16)} History</h3></div>
          <div class="panel-body">${timeline}</div>
        </div>
      </div>
    </div>
    ${_renderDepreciationPanel(a.depreciation, a.id)}
    ${cfPanel}
    <div class="panel" style="margin-top:18px" id="photos-panel">
      <div class="panel-head"><h3>${icon('image', 16)} Photos</h3>
        ${can('assets.edit') ? `<label class="btn btn-ghost btn-sm" style="cursor:pointer">${icon('upload',14)} Add photo<input type="file" accept="image/*" style="display:none" onchange="_uploadAssetPhoto(${a.id},this)"></label>` : ''}
      </div>
      <div class="panel-body" id="photos-list">${loading()}</div>
    </div>
    <div class="panel" style="margin-top:18px" id="maintenance-panel">
      <div class="panel-head"><h3>${icon('tool', 16)} Maintenance</h3>
        ${can('assets.edit') ? `<button class="btn btn-ghost btn-sm" onclick="openMaintenanceForm(${a.id})">${icon('plus',14)} Schedule</button>` : ''}
      </div>
      <div class="panel-body" id="maintenance-list">${loading()}</div>
    </div>
    <div class="panel" style="margin-top:18px" id="notes-panel">
      <div class="panel-head"><h3>${icon('edit', 16)} Notes Log</h3></div>
      <div class="panel-body" id="notes-list">
        ${_renderNotesList(notes)}
      </div>
      ${can('assets.edit') ? `
      <div style="padding:0 20px 16px">
        <div class="field" style="margin-bottom:8px">
          <textarea id="note-input" rows="3" placeholder="Add a note…" style="width:100%;padding:9px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface);color:var(--text);font-family:inherit;font-size:14px;resize:vertical"></textarea>
        </div>
        <button class="btn btn-primary btn-sm" onclick="addAssetNote(${a.id})">Add Note</button>
      </div>` : ''}
    </div>`;

  loadQrImage(a.id);
  api(`/assets/${a.id}/photos`).then(photos => {
    const el = document.getElementById('photos-list');
    if (el) el.innerHTML = _renderPhotosList(photos, a.id);
  }).catch(() => {});
  api(`/assets/${a.id}/maintenance`).then(items => {
    const el = document.getElementById('maintenance-list');
    if (el) el.innerHTML = _renderMaintenanceList(items, a.id);
  }).catch(() => {});
}

function _renderPhotosList(photos, assetId) {
  if (!photos || !photos.length) {
    return `<p class="muted" style="font-size:13.5px">No photos yet.</p>`;
  }
  return `<div style="display:flex;flex-wrap:wrap;gap:10px">${photos.map(p => `
    <div style="position:relative">
      <a href="${esc(p.url)}" target="_blank" rel="noopener">
        <img src="${esc(p.url)}" alt="Asset photo"
          style="width:120px;height:90px;object-fit:cover;border-radius:var(--radius-sm);border:1px solid var(--border);display:block">
      </a>
      ${can('assets.edit') ? `<button onclick="deleteAssetPhoto(${p.id},${assetId})"
        style="position:absolute;top:4px;right:4px;background:rgba(0,0,0,0.55);border:none;
               border-radius:50%;width:22px;height:22px;cursor:pointer;color:#fff;
               display:flex;align-items:center;justify-content:center;padding:0"
        title="Delete photo">${icon('x',12)}</button>` : ''}
    </div>`).join('')}</div>`;
}

async function _uploadAssetPhoto(assetId, input) {
  const file = input.files?.[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  input.value = '';
  try {
    const r = await fetch(`/api/assets/${assetId}/photos`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${State.token}`, 'x-tenant': State.settings?.slug || '' },
      body: fd,
    });
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Upload failed'); }
    const photos = await api(`/assets/${assetId}/photos`).catch(() => []);
    const el = document.getElementById('photos-list');
    if (el) el.innerHTML = _renderPhotosList(photos, assetId);
    toast('Photo uploaded');
  } catch (e) { toast(e.message, 'err'); }
}

async function deleteAssetPhoto(photoId, assetId) {
  if (!confirm('Delete this photo?')) return;
  try {
    await api(`/assets/${assetId}/photos/${photoId}`, { method: 'DELETE' });
    const photos = await api(`/assets/${assetId}/photos`).catch(() => []);
    const el = document.getElementById('photos-list');
    if (el) el.innerHTML = _renderPhotosList(photos, assetId);
    toast('Photo deleted');
  } catch (e) { toast(e.message, 'err'); }
}

const _MAINT_STATUS_COLOR = { scheduled: '#3b82f6', overdue: '#ef4444', done: '#22c55e' };

function _renderMaintenanceList(items, assetId) {
  if (!items || !items.length) {
    return `<p class="muted" style="font-size:13.5px">No maintenance scheduled.</p>`;
  }
  return `<ul class="timeline">${items.map(m => {
    const color = _MAINT_STATUS_COLOR[m.status] || '#6b7280';
    const badge = `<span style="display:inline-block;padding:1px 8px;border-radius:12px;font-size:11px;font-weight:600;background:${color}18;color:${color}">${m.status}</span>`;
    return `<li>
      <div class="t-action">
        <b>${esc(m.title)}</b> ${badge}
        ${m.maintenance_type ? `<span class="muted" style="font-size:12px"> · ${esc(m.maintenance_type)}</span>` : ''}
        <div class="muted" style="font-size:12px;margin-top:2px">Due: ${m.due_date}${m.assigned_to_name ? ` · ${esc(m.assigned_to_name)}` : ''}${m.notes ? ` · ${esc(m.notes)}` : ''}</div>
      </div>
      <div class="t-time">
        ${can('assets.edit') && m.status !== 'done' ? `<button class="btn btn-ghost btn-sm" style="padding:2px 8px;font-size:11px" onclick="completeMaintenance(${m.id},${assetId})">${icon('check',12)} Done</button>` : ''}
        ${can('assets.edit') ? `<button class="btn btn-ghost btn-sm" style="padding:2px 6px;font-size:11px;color:var(--red)" onclick="deleteMaintenance(${m.id},${assetId})">${icon('trash',12)}</button>` : ''}
      </div>
    </li>`;
  }).join('')}</ul>`;
}

function openMaintenanceForm(assetId) {
  openModal(`
    <div class="modal-head"><h2>Schedule Maintenance</h2><button class="x-btn" onclick="closeModal()">✕</button></div>
    <div class="modal-body">
      <div class="field"><label>Title *</label><input id="maint-title" type="text" placeholder="e.g. Annual inspection"></div>
      <div class="field"><label>Type</label><input id="maint-type" type="text" placeholder="e.g. Inspection, Repair, Cleaning"></div>
      <div class="field"><label>Due date *</label><input id="maint-due" type="date"></div>
      <div class="field"><label>Notes</label><textarea id="maint-notes" rows="2" style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface);color:var(--text)"></textarea></div>
    </div>
    <div class="modal-foot">
      <button class="btn" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" onclick="_submitMaintenance(${assetId})">Schedule</button>
    </div>`);
}

async function _submitMaintenance(assetId) {
  const title = document.getElementById('maint-title')?.value.trim();
  const due   = document.getElementById('maint-due')?.value;
  if (!title) return toast('Title is required', 'err');
  if (!due)   return toast('Due date is required', 'err');
  try {
    await api(`/assets/${assetId}/maintenance`, { method: 'POST', json: {
      title, maintenance_type: document.getElementById('maint-type')?.value.trim() || '',
      due_date: due, notes: document.getElementById('maint-notes')?.value.trim() || '',
    }});
    closeModal();
    const items = await api(`/assets/${assetId}/maintenance`).catch(() => []);
    const el = document.getElementById('maintenance-list');
    if (el) el.innerHTML = _renderMaintenanceList(items, assetId);
    toast('Maintenance scheduled');
  } catch (e) { toast(e.message, 'err'); }
}

async function completeMaintenance(maintenanceId, assetId) {
  try {
    await api(`/assets/${assetId}/maintenance/${maintenanceId}/complete`, { method: 'PATCH' });
    const items = await api(`/assets/${assetId}/maintenance`).catch(() => []);
    const el = document.getElementById('maintenance-list');
    if (el) el.innerHTML = _renderMaintenanceList(items, assetId);
    toast('Marked as done');
  } catch (e) { toast(e.message, 'err'); }
}

async function deleteMaintenance(maintenanceId, assetId) {
  if (!confirm('Delete this maintenance task?')) return;
  try {
    await api(`/assets/${assetId}/maintenance/${maintenanceId}`, { method: 'DELETE' });
    const items = await api(`/assets/${assetId}/maintenance`).catch(() => []);
    const el = document.getElementById('maintenance-list');
    if (el) el.innerHTML = _renderMaintenanceList(items, assetId);
    toast('Deleted');
  } catch (e) { toast(e.message, 'err'); }
}

function _renderNotesList(notes) {
  if (!notes || !notes.length) return `<p class="muted" style="font-size:13.5px">No notes yet.</p>`;
  return `<ul class="timeline">${notes.map(n => `
    <li>
      <div class="t-action" style="white-space:pre-wrap">${esc(n.body)}</div>
      <div class="t-time">${esc(n.author_name)} · ${fmtDate(n.created_at)} · ${timeAgo(n.created_at)}
        ${can('assets.edit') ? `<button class="btn btn-ghost btn-sm" style="padding:2px 6px;font-size:11px;margin-left:8px;color:var(--red)" onclick="deleteAssetNote(${n.id})">${icon('trash',12)}</button>` : ''}
      </div>
    </li>`).join('')}</ul>`;
}

async function addAssetNote(assetId) {
  const input = document.getElementById('note-input');
  const body = (input?.value || '').trim();
  if (!body) return toast('Enter a note first', 'err');
  try {
    await api(`/assets/${assetId}/notes`, { method: 'POST', json: { body } });
    input.value = '';
    const updated = await api(`/assets/${assetId}/notes`).catch(() => []);
    document.getElementById('notes-list').innerHTML = _renderNotesList(updated);
    toast('Note added');
  } catch (e) { toast(e.message, 'err'); }
}

async function deleteAssetNote(noteId) {
  if (!confirm('Delete this note?')) return;
  const assetId = State.param;
  try {
    await api(`/assets/${assetId}/notes/${noteId}`, { method: 'DELETE' });
    const updated = await api(`/assets/${assetId}/notes`).catch(() => []);
    document.getElementById('notes-list').innerHTML = _renderNotesList(updated);
    toast('Note deleted');
  } catch (e) { toast(e.message, 'err'); }
}

async function generateCheckinLink(assetId) {
  try {
    const r = await api(`/assets/${assetId}/checkin-token`, { method: 'POST' });
    const url = `${window.location.origin}/checkin/${r.token}`;
    openModal(`
      <div class="modal-head"><h2>Self-service check-in link</h2><button class="x-btn" onclick="closeModal()">✕</button></div>
      <div class="modal-body">
        <p class="muted" style="margin-bottom:12px">Share this link with the employee to let them check in the asset without logging in. The link is single-use and expires in 7 days.</p>
        <div style="display:flex;gap:8px;align-items:center">
          <input id="checkin-link-url" value="${esc(url)}" readonly
            style="flex:1;padding:9px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg);color:var(--text);font-family:var(--mono);font-size:12px">
          <button class="btn btn-accent btn-sm" onclick="navigator.clipboard.writeText('${esc(url)}').then(()=>toast('Copied'))">Copy</button>
        </div>
      </div>
      <div class="modal-foot"><button class="btn btn-ghost" onclick="closeModal()">Close</button></div>`);
  } catch (e) { toast(e.message, 'err'); }
}

async function loadQrImage(assetId) {
  const img = document.getElementById('asset-qr-img');
  if (!img) return;
  try {
    const res = await api(`/assets/${assetId}/qr`);
    const blob = await res.blob();
    img.src = URL.createObjectURL(blob);
  } catch (e) {
    img.alt = 'QR unavailable';
  }
}

async function downloadQr(assetId, assetTag) {
  try {
    const res = await api(`/assets/${assetId}/qr`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${assetTag}.png`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    toast(e.message || 'Unable to download QR', 'err');
  }
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
    <div class="modal-foot">
      <button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button type="button" class="btn btn-ghost" id="import-preview-btn" onclick="doImportPreview()">Preview</button>
      <button type="button" class="btn btn-primary" id="import-confirm-btn" style="display:none" onclick="doImport()">Confirm Import</button>
    </div>`);
}

async function doImportPreview() {
  const input = document.getElementById('csv-file');
  if (!input.files.length) return toast('Choose a CSV file first', 'err');
  const fd = new FormData(); fd.append('file', input.files[0]);
  const btn = document.getElementById('import-preview-btn');
  btn.disabled = true; btn.textContent = 'Analysing…';
  try {
    const r = await api('/assets/import/csv/preview', { method: 'POST', body: fd });
    const s = r.summary;
    const errHtml = r.errors.length
      ? `<div style="margin-top:10px"><b style="color:var(--red)">${s.errors} error${s.errors !== 1 ? 's' : ''}</b><ul style="margin:4px 0 0 18px;font-size:13px;color:var(--red)">${r.errors.slice(0, 10).map(e => `<li>Row ${e.row}: ${esc(e.error || e.message || '')}</li>`).join('')}${r.errors.length > 10 ? `<li>…and ${r.errors.length - 10} more</li>` : ''}</ul></div>` : '';
    const cfHtml = r.new_cf_defs.length
      ? `<div style="margin-top:8px;font-size:13px" class="muted">New custom field columns: ${r.new_cf_defs.map(c => `<span class="tag">${esc(c)}</span>`).join(' ')}</div>` : '';
    const createsHtml = r.creates.length
      ? `<details style="margin-top:10px"><summary style="cursor:pointer;font-size:13px"><b>${s.creates}</b> new asset${s.creates !== 1 ? 's' : ''}</summary><table class="data-table" style="margin-top:6px;font-size:12px"><thead><tr><th>Tag</th><th>Name</th><th>Category</th><th>Status</th></tr></thead><tbody>${r.creates.slice(0, 50).map(a => `<tr><td>${esc(a.asset_tag)}</td><td>${esc(a.name)}</td><td>${esc(a.category||'')}</td><td>${esc(a.status)}</td></tr>`).join('')}${r.creates.length > 50 ? `<tr><td colspan="4" class="muted">…and ${r.creates.length - 50} more</td></tr>` : ''}</tbody></table></details>` : `<div style="font-size:13px;margin-top:8px">0 new assets</div>`;
    const updatesHtml = r.updates.length
      ? `<details style="margin-top:6px"><summary style="cursor:pointer;font-size:13px"><b>${s.updates}</b> update${s.updates !== 1 ? 's' : ''}</summary><table class="data-table" style="margin-top:6px;font-size:12px"><thead><tr><th>Tag</th><th>Name</th><th>Changes</th></tr></thead><tbody>${r.updates.slice(0, 50).map(a => `<tr><td>${esc(a.asset_tag)}</td><td>${esc(a.name)}</td><td>${a.changes.length ? a.changes.map(c => `${esc(c.field)}: <span style="color:var(--red)">${esc(c.from)}</span> → <span style="color:var(--green)">${esc(c.to)}</span>`).join(', ') : '<span class="muted">no field changes</span>'}</td></tr>`).join('')}${r.updates.length > 50 ? `<tr><td colspan="3" class="muted">…and ${r.updates.length - 50} more</td></tr>` : ''}</tbody></table></details>` : `<div style="font-size:13px;margin-top:4px">0 updates</div>`;
    document.getElementById('import-result').innerHTML = `
      <div class="card" style="padding:14px;margin-top:10px">
        <div style="font-size:14px;font-weight:600;margin-bottom:6px">Preview — ${s.total_rows} row${s.total_rows !== 1 ? 's' : ''}</div>
        ${createsHtml}${updatesHtml}${errHtml}${cfHtml}
      </div>`;
    if (s.creates + s.updates > 0) {
      document.getElementById('import-confirm-btn').style.display = '';
    }
  } catch (e) { toast(e.message, 'err'); }
  finally { btn.disabled = false; btn.textContent = 'Preview'; }
}

async function doImport() {
  const input = document.getElementById('csv-file');
  if (!input.files.length) return toast('Choose a CSV file first', 'err');
  const fd = new FormData(); fd.append('file', input.files[0]);
  const btn = document.getElementById('import-confirm-btn');
  btn.disabled = true; btn.textContent = 'Importing…';
  try {
    const r = await api('/assets/import/csv', { method: 'POST', body: fd });
    document.getElementById('import-result').innerHTML = `<div class="card" style="padding:14px;margin-top:6px;border-color:var(--green)"><b style="color:var(--green)">${r.created} created</b>, <b>${r.updated} updated</b>.${r.errors.length ? `<div style="color:var(--red);margin-top:8px;font-size:13px">${r.errors.slice(0, 5).map(esc).join('<br>')}</div>` : ''}</div>`;
    btn.style.display = 'none';
    _lookups = { categories: [], locations: [], employees: [] };
    toast(`Imported ${r.created + r.updated} assets`);
    loadAssets();
  } catch (e) { toast(e.message, 'err'); btn.disabled = false; btn.textContent = 'Confirm Import'; }
}

// ============ CATEGORIES / LOCATIONS / PEOPLE ============
const ICON_CHOICES = ['box', 'laptop', 'monitor', 'tv', 'smartphone', 'server', 'wifi', 'mouse'];

async function pageCategories() {
  const page = document.getElementById('page');
  page.innerHTML = pageHeader('Categories', null, `<button class="btn btn-accent" onclick="openCatForm()">${icon('plus', 16)}New Category</button>`) + loading();
  let _catsResp; try { _catsResp = await api('/categories'); } catch (e) { return toast(e.message, 'err'); }
  const cats = _catsResp.items ?? _catsResp;
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
  let _locsResp; try { _locsResp = await api('/locations'); } catch (e) { return toast(e.message, 'err'); }
  const locs = _locsResp.items ?? _locsResp;
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
  let _empsResp; try { _empsResp = await api('/employees'); } catch (e) { return toast(e.message, 'err'); }
  const emps = _empsResp.items ?? _empsResp;
  _lookups.employees = emps;
  const body = emps.length ? `<div class="chip-grid">${emps.map(e => `
    <div class="chip"><div class="ci" style="cursor:pointer" onclick="openEmployeeHistory(${e.id})"><div class="ico" style="background:var(--ink);color:var(--accent)"><b style="font-family:var(--display)">${esc(e.name[0].toUpperCase())}</b></div><div><b>${esc(e.name)}</b><small>${e.department ? esc(e.department) + ' · ' : ''}${e.asset_count} asset${e.asset_count !== 1 ? 's' : ''}</small></div></div>
    <div class="acts"><button class="icon-btn" title="Assignment history" onclick="openEmployeeHistory(${e.id})">${icon('clock', 16)}</button>${e.asset_count > 0 ? `<button class="icon-btn" title="Bulk reassign assets" onclick="openBulkReassign(${e.id}, ${JSON.stringify(e.name)})">${icon('shuffle', 16)}</button>` : ''}<button class="icon-btn" onclick="openEmpForm(${e.id})">${icon('edit', 16)}</button><button class="icon-btn danger" onclick="delLookup('employees', ${e.id}, 'Person')">${icon('trash', 16)}</button></div></div>`).join('')}</div>`
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

async function openEmployeeHistory(eid) {
  openModal(`
    <div class="modal-head"><h2>${icon('clock',16)} Assignment History</h2><button class="x-btn" onclick="closeModal()">✕</button></div>
    <div class="modal-body" id="emp-history-body">${loading()}</div>`, true);

  try {
    const data = await api(`/employees/${eid}/history`);
    const emp  = data.employee;
    const hist = data.history;

    const rows = hist.length ? hist.map(h => `
      <tr>
        <td><a href="#" onclick="navigate('asset-detail',${h.asset_id});closeModal();return false"
               style="color:var(--accent);font-weight:600">${esc(h.asset_tag)}</a></td>
        <td>${esc(h.asset_name)}</td>
        <td><span class="badge ${h.action}">${h.action}</span></td>
        <td style="font-size:12px;color:var(--text-muted)">${h.timestamp ? h.timestamp.replace('T',' ').slice(0,16) : '—'}</td>
        <td>${h.currently_assigned
          ? `<span style="font-size:11px;background:rgba(212,240,52,.15);color:var(--accent);padding:2px 7px;border-radius:4px;font-weight:600">Current</span>`
          : ''}</td>
      </tr>`).join('')
      : `<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--text-muted)">No assignment history yet.</td></tr>`;

    document.getElementById('emp-history-body').innerHTML = `
      <div style="margin-bottom:16px">
        <div style="font-size:18px;font-weight:700">${esc(emp.name)}</div>
        ${emp.department ? `<div style="font-size:13px;color:var(--text-muted)">${esc(emp.department)}</div>` : ''}
        ${emp.email ? `<div style="font-size:13px;color:var(--text-muted)">${esc(emp.email)}</div>` : ''}
      </div>
      <div class="table-wrap" style="border:none;box-shadow:none;max-height:400px;overflow-y:auto">
        <table>
          <thead><tr><th>Tag</th><th>Asset</th><th>Action</th><th>Date</th><th></th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  } catch(e) {
    document.getElementById('emp-history-body').innerHTML =
      `<p style="color:var(--red)">${esc(e.message)}</p>`;
  }
}

async function delLookup(type, id, label) {
  if (!confirm(`Delete this ${label.toLowerCase()}?`)) return;
  try {
    await api(`/${type}/${id}`, { method: 'DELETE' });
    toast(`${label} deleted`);
    ({ categories: pageCategories, locations: pageLocations, employees: pageEmployees }[type])();
  } catch (e) {
    if (type === 'employees' && e.message && e.message.includes('assets assigned')) {
      const emp = _lookups.employees.find(x => x.id === id);
      openBulkReassign(id, emp?.name || 'this person');
    } else {
      toast(e.message, 'err');
    }
  }
}

async function openBulkReassign(eid, name) {
  if (!_lookups.employees.length) await loadLookups();
  const others = _lookups.employees.filter(e => e.id !== eid);
  const opts = others.map(e => `<option value="${e.id}">${esc(e.name)}${e.department ? ' · ' + esc(e.department) : ''}</option>`).join('');
  openModal(`
    <div class="modal-head"><h2>Reassign assets</h2><button class="x-btn" onclick="closeModal()">✕</button></div>
    <div class="modal-body">
      <p style="margin-bottom:14px"><b>${esc(name)}</b> still has assets assigned. Reassign them before deleting.</p>
      <div class="field">
        <label>Reassign all assets to</label>
        <select id="reassign-to">
          <option value="">— Unassign (set to available) —</option>
          ${opts}
        </select>
      </div>
    </div>
    <div class="modal-foot">
      <button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button type="button" class="btn btn-primary" onclick="doReassignAndDelete(${eid})">Reassign &amp; Delete</button>
    </div>`);
}

async function doReassignAndDelete(eid) {
  const toId = document.getElementById('reassign-to').value;
  try {
    await api(`/employees/${eid}/reassign`, {
      method: 'POST',
      json: { to_employee_id: toId ? parseInt(toId) : null },
    });
    await api(`/employees/${eid}`, { method: 'DELETE' });
    closeModal();
    toast('Assets reassigned and person deleted');
    pageEmployees();
  } catch (e) { toast(e.message, 'err'); }
}

// ============ SETTINGS ============
async function pageSettings() {
  const page = document.getElementById('page');
  const s = State.settings;
  const canEdit = can('settings.manage');

  const emailBrandPanel = canEdit ? `
    <div class="panel">
      <div class="panel-head">
        <h3>Email Branding</h3>
        <span style="font-size:12px;color:var(--text-muted)">Applied to emails sent to your users</span>
      </div>
      <div class="panel-body">
        <form id="email-brand-form">
          <div class="field"><label>From Name</label>
            <input name="email_from_name" value="${esc(s.email_from_name||'')}"
              placeholder="Acme IT Solutions"></div>
          <div class="field"><label>From Address</label>
            <input name="email_from_address" type="email" value="${esc(s.email_from_address||'')}"
              placeholder="it@acme.com">
            <div style="font-size:11.5px;color:var(--text-muted);margin-top:4px">
              Requires your email provider to allow custom from addresses
            </div>
          </div>
          <div class="field"><label>Logo URL</label>
            <input id="eb-logo" name="email_logo_url" value="${esc(s.email_logo_url||'')}"
              placeholder="https://…"
              oninput="_updateEmailPreview()"></div>
          <div class="field"><label>Accent Colour</label>
            <input id="eb-accent" name="email_accent_color" type="color"
              value="${esc(s.email_accent_color||s.accent_color||'#d4f034')}"
              style="height:40px;cursor:pointer"
              oninput="_updateEmailPreview()"></div>
          <button class="btn btn-primary" type="submit">Save Email Branding</button>
        </form>
        <div style="margin-top:16px;padding:14px;background:var(--bg);border-radius:8px">
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">Preview</div>
          <div id="email-preview">${_emailHeaderPreview(s.email_logo_url||'', s.email_from_name||s.name||'Tether', s.email_accent_color||s.accent_color||'#d4f034')}</div>
        </div>
      </div>
    </div>` : '';

  const canManageCats = can('categories.manage');

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
          <div class="field"><label>Asset Tag Prefix <span class="muted" style="font-weight:400;font-size:12px">(optional — e.g. ACME- )</span></label>
            <input name="asset_tag_prefix" value="${esc(s.asset_tag_prefix||'')}" placeholder="ACME-" maxlength="20" style="text-transform:uppercase" ${canEdit?'':'readonly'}></div>
          <div class="field"><label>Webhook URL <span class="muted" style="font-weight:400;font-size:12px">(optional — receives asset.created, asset.updated, asset.deleted, request.status_changed, warranty.expiring)</span></label>
            <input name="webhook_url" type="url" value="${esc(s.webhook_url||'')}" placeholder="https://hooks.example.com/tether" ${canEdit?'':'readonly'}></div>
          <div class="field"><label>Webhook Secret <span class="muted" style="font-weight:400;font-size:12px">(used to compute X-Tether-Signature HMAC-SHA256)</span></label>
            <input name="webhook_secret" type="password" value="${esc(s.webhook_secret||'')}" placeholder="Leave blank to keep current" autocomplete="off" ${canEdit?'':'readonly'}></div>
          ${canEdit?`<button class="btn btn-primary" type="submit">Save Settings</button>`:''}
        </form>
      </div></div>
      ${emailBrandPanel}
      ${canManageCats ? `<div class="panel" id="cf-panel">
        <div class="panel-head">
          <h3>Custom Fields</h3>
          <button class="btn btn-accent btn-sm" onclick="openCustomFieldForm()">${icon('plus',14)} Add Field</button>
        </div>
        <div class="panel-body" id="cf-list-wrap">${loading()}</div>
      </div>` : ''}
      <div class="panel"><div class="panel-head"><h3>${icon('lock',16)} Change Password</h3></div><div class="panel-body">
        <form id="pw-form">
          <div class="field"><label>Current Password</label>
            <input name="current_password" type="password" required></div>
          <div class="field"><label>New Password</label>
            <input name="new_password" type="password" required minlength="6"></div>
          <button class="btn btn-primary" type="submit">Update Password</button>
        </form>
      </div></div>
      ${State.user?.is_msp_staff ? `<div class="panel" id="totp-panel">
        <div class="panel-head"><h3>${icon('shield',16)} Two-Factor Authentication</h3></div>
        <div class="panel-body" id="totp-panel-body">${loading()}</div>
      </div>` : ''}
    </div>`;

  if (canEdit) {
    document.getElementById('settings-form').onsubmit = async (e) => {
      e.preventDefault(); const f = new FormData(e.target);
      const body = {name:f.get('name'),currency:f.get('currency'),
                    accent_color:f.get('accent_color'),logo_url:f.get('logo_url'),
                    asset_tag_prefix: f.get('asset_tag_prefix') || null,
                    webhook_url: f.get('webhook_url') || null,
                    webhook_secret: f.get('webhook_secret') || null};
      try {
        await api('/settings',{method:'PUT',json:body});
        State.settings = {...State.settings, ...body};
        document.documentElement.style.setProperty('--accent', body.accent_color);
        toast('Settings saved');
      } catch(err) { toast(err.message,'err'); }
    };

    document.getElementById('email-brand-form').onsubmit = async (e) => {
      e.preventDefault(); const f = new FormData(e.target);
      const body = {
        name:               s.name,
        currency:           s.currency,
        logo_url:           s.logo_url || '',
        accent_color:       s.accent_color || '#d4f034',
        email_from_name:    f.get('email_from_name') || null,
        email_from_address: f.get('email_from_address') || null,
        email_logo_url:     f.get('email_logo_url') || null,
        email_accent_color: f.get('email_accent_color') || null,
      };
      try {
        await api('/settings', {method:'PUT', json:body});
        State.settings = {...State.settings,
          email_from_name:    body.email_from_name    || '',
          email_from_address: body.email_from_address || '',
          email_logo_url:     body.email_logo_url     || '',
          email_accent_color: body.email_accent_color || '',
        };
        toast('Email branding saved');
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

  if (canManageCats) _loadCustomFieldList();
  if (State.user?.is_msp_staff) _loadTotpPanel();
}

async function _loadTotpPanel() {
  const wrap = document.getElementById('totp-panel-body');
  if (!wrap) return;
  try {
    const status = await api('/auth/totp/status');
    _renderTotpPanel(wrap, status.enabled);
  } catch(e) { wrap.innerHTML = `<p style="color:var(--red)">${esc(e.message)}</p>`; }
}

function _renderTotpPanel(wrap, enabled) {
  if (enabled) {
    wrap.innerHTML = `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
        <span style="background:var(--green,.4em);color:#fff;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;background:#22c55e">Active</span>
        <span style="font-size:13px;color:var(--text-muted)">Your account is protected with 2FA.</span>
      </div>
      <form id="totp-disable-form">
        <div class="field"><label>Current password to disable 2FA</label>
          <input name="password" type="password" required placeholder="Enter your password"></div>
        <button class="btn btn-danger btn-sm" type="submit">Disable 2FA</button>
      </form>`;
    document.getElementById('totp-disable-form').onsubmit = async (e) => {
      e.preventDefault(); const btn = e.target.querySelector('button');
      btn.disabled = true; btn.textContent = 'Disabling…';
      try {
        await api('/auth/totp',{method:'DELETE',json:{password:new FormData(e.target).get('password')}});
        toast('2FA disabled'); _renderTotpPanel(wrap, false);
      } catch(err) { toast(err.message,'err'); btn.disabled=false; btn.textContent='Disable 2FA'; }
    };
  } else {
    wrap.innerHTML = `
      <p style="font-size:13px;color:var(--text-muted);margin-bottom:14px">
        Add an extra layer of security. You'll need an authenticator app like Google Authenticator, Authy, or 1Password.
      </p>
      <button class="btn btn-primary btn-sm" id="totp-setup-btn">Set up 2FA</button>
      <div id="totp-setup-flow" style="display:none;margin-top:18px"></div>`;
    document.getElementById('totp-setup-btn').onclick = async () => {
      const btn = document.getElementById('totp-setup-btn');
      btn.disabled = true; btn.textContent = 'Loading…';
      try {
        const data = await api('/auth/totp/setup',{method:'POST'});
        btn.style.display = 'none';
        const flow = document.getElementById('totp-setup-flow');
        flow.style.display = '';
        flow.innerHTML = `
          <p style="font-size:13px;margin-bottom:12px">
            Scan this QR code with your authenticator app, then enter the 6-digit code to activate.
          </p>
          <div style="background:#fff;display:inline-block;padding:10px;border-radius:8px;margin-bottom:14px">
            ${data.qr_svg}
          </div>
          <details style="margin-bottom:14px">
            <summary style="font-size:12px;color:var(--text-muted);cursor:pointer">Can't scan? Enter key manually</summary>
            <code style="font-size:12px;word-break:break-all;display:block;margin-top:6px;padding:8px;background:var(--bg);border-radius:6px">${esc(data.secret)}</code>
          </details>
          <form id="totp-verify-form">
            <div class="field"><label>Verification code</label>
              <input name="code" type="text" inputmode="numeric" pattern="[0-9]*"
                autocomplete="one-time-code" maxlength="8" placeholder="000000" required
                style="letter-spacing:4px;font-size:22px;text-align:center;max-width:180px"></div>
            <button class="btn btn-accent" type="submit">Activate 2FA</button>
          </form>`;
        document.getElementById('totp-verify-form').onsubmit = async (ev) => {
          ev.preventDefault(); const vbtn = ev.target.querySelector('button');
          vbtn.disabled=true; vbtn.textContent='Verifying…';
          const code = new FormData(ev.target).get('code').replace(/\s/g,'');
          try {
            await api('/auth/totp/verify',{method:'POST',json:{code}});
            toast('2FA is now active'); _renderTotpPanel(wrap, true);
          } catch(err) { toast(err.message,'err'); vbtn.disabled=false; vbtn.textContent='Activate 2FA'; }
        };
        document.querySelector('#totp-verify-form input[name=code]')?.focus();
      } catch(err) { toast(err.message,'err'); btn.disabled=false; btn.textContent='Set up 2FA'; }
    };
  }
}

function _emailHeaderPreview(logoUrl, brandName, accent) {
  const logo = logoUrl
    ? `<img src="${esc(logoUrl)}" alt="${esc(brandName)}"
         style="max-height:28px;max-width:120px;object-fit:contain;vertical-align:middle">`
    : `<span style="display:inline-flex;align-items:center;gap:8px">
         <span style="background:#21242c;border:1px solid #2e3340;border-radius:6px;
           width:24px;height:24px;display:inline-flex;align-items:center;justify-content:center">
           <span style="color:${esc(accent)};font-size:14px;font-weight:900">+</span>
         </span>
         <b style="color:#fff;font-size:14px">${esc(brandName)}</b>
       </span>`;
  return `<div style="background:#15171c;border-radius:8px;padding:14px 18px;
                      border:1px solid #2e3340;display:flex;align-items:center;gap:12px">
    ${logo}
    <span style="margin-left:auto;background:${esc(accent)};border-radius:6px;
      padding:6px 14px;font-size:12px;font-weight:700;color:#15171c">CTA Button</span>
  </div>`;
}

function _updateEmailPreview() {
  const logo   = document.getElementById('eb-logo')?.value   || '';
  const accent = document.getElementById('eb-accent')?.value || '#d4f034';
  const name   = State.settings?.name || 'Tether';
  const el     = document.getElementById('email-preview');
  if (el) el.innerHTML = _emailHeaderPreview(logo, name, accent);
}

// ── Custom Fields (Settings panel) ───────────────────────────────────────────

const _CF_TYPES = ['text','number','date','boolean','url'];

async function _loadCustomFieldList() {
  const wrap = document.getElementById('cf-list-wrap');
  if (!wrap) return;
  let defs;
  try { defs = await api('/custom-fields/defs'); } catch(e) { wrap.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  if (!defs.length) {
    wrap.innerHTML = `<p class="muted" style="font-size:13.5px">No custom fields defined yet. Add fields like IMEI, VLAN, department code, licence key…</p>`;
    return;
  }
  const rows = defs.map(d => `
    <div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--border)">
      <div style="flex:1">
        <span style="font-weight:500">${esc(d.label)}</span>
        <span class="tag" style="margin-left:6px;font-size:11px">${esc(d.field_type)}</span>
        ${d.required ? `<span class="tag" style="margin-left:4px;font-size:11px;background:var(--accent-muted)">required</span>` : ''}
      </div>
      <button class="btn btn-ghost btn-sm" onclick="openCustomFieldForm(${d.id},'${esc(d.label)}','${d.field_type}',${d.required})">${icon('edit',13)}</button>
      <button class="btn btn-danger btn-sm" onclick="deleteCustomField(${d.id})">${icon('trash',13)}</button>
    </div>`).join('');
  wrap.innerHTML = `<div style="margin:-4px 0">${rows}</div>`;
}

async function openCustomFieldForm(id=null, label='', fieldType='text', required=false) {
  const typeOpts = _CF_TYPES.map(t => `<option value="${t}" ${t===fieldType?'selected':''}>${t}</option>`).join('');
  openModal(`
    <div class="modal-head"><h2>${id?'Edit':'New'} Custom Field</h2><button class="x-btn" onclick="closeModal()">✕</button></div>
    <form id="cf-form"><div class="modal-body">
      <div class="field"><label>Label *</label>
        <input name="label" value="${esc(label)}" placeholder="e.g. IMEI, VLAN, Department Code" required></div>
      <div class="field-row">
        <div class="field"><label>Type</label>
          <select name="field_type">${typeOpts}</select></div>
        <div class="field" style="justify-content:flex-end;padding-top:24px">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" name="required" ${required?'checked':''} style="width:auto">
            <span style="font-size:13.5px">Required</span>
          </label>
        </div>
      </div>
    </div>
    <div class="modal-foot">
      <button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button type="submit" class="btn btn-primary">${id?'Save Changes':'Create Field'}</button>
    </div></form>`);

  document.getElementById('cf-form').onsubmit = async (e) => {
    e.preventDefault(); const f = new FormData(e.target);
    const body = {label: f.get('label'), field_type: f.get('field_type'), required: !!f.get('required')};
    const btn = e.target.querySelector('button[type=submit]'); btn.disabled = true;
    try {
      if (id) await api(`/custom-fields/defs/${id}`, {method:'PUT', json:body});
      else     await api('/custom-fields/defs',         {method:'POST', json:body});
      closeModal(); toast(id ? 'Field updated' : 'Field created');
      _loadCustomFieldList();
    } catch(err) { toast(err.message,'err'); btn.disabled = false; }
  };
}

async function deleteCustomField(id) {
  if (!confirm('Delete this custom field? All values stored for this field will also be removed.')) return;
  try {
    await api(`/custom-fields/defs/${id}`, {method:'DELETE'});
    toast('Custom field deleted');
    _loadCustomFieldList();
  } catch(e) { toast(e.message,'err'); }
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
             onclick="startCheckoutCurrent('${t.key}')">
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

function startCheckoutCurrent(tier) {
  return startCheckout(tier, currentBillingInterval);
}

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
    </div>

    <!-- Audit log section -->
    <div class="panel" style="max-width:800px;margin-top:18px">
      <div class="panel-head">
        <h3>Audit Log</h3>
        <button class="btn btn-accent btn-sm" onclick="pageAuditLog()">View audit log</button>
      </div>
      <div class="panel-body">
        <p class="muted">A record of every action taken in Tether — logins, asset changes, user management, and more.</p>
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

// ── Audit Log ─────────────────────────────────────────────────────────────────

let _auditFilters = { action: '', tenant_id: '', offset: 0, limit: 100 };

async function pageAuditLog() {
  _auditFilters = { action: '', tenant_id: '', offset: 0, limit: 100 };
  const page = document.getElementById('page');
  page.innerHTML = pageHeader('Audit Log', 'MSP') + `
    <div style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-bottom:16px">
      <div>
        <label class="form-label">Action filter</label>
        <input id="af-action" class="form-input" style="width:200px" placeholder="e.g. asset.create"
          oninput="_auditFilters.action=this.value;_auditFilters.offset=0;_loadAuditLog()">
      </div>
      <div>
        <label class="form-label">Tenant ID</label>
        <input id="af-tenant" class="form-input" style="width:120px" type="number" placeholder="All"
          oninput="_auditFilters.tenant_id=this.value;_auditFilters.offset=0;_loadAuditLog()">
      </div>
      <button class="btn btn-ghost btn-sm" onclick="exportAuditLog()">Export CSV</button>
    </div>
    <div id="audit-table-wrap">${loading()}</div>`;
  await _loadAuditLog();
}

async function _loadAuditLog() {
  const wrap = document.getElementById('audit-table-wrap');
  if (!wrap) return;
  wrap.innerHTML = loading();
  const p = new URLSearchParams({ limit: _auditFilters.limit, offset: _auditFilters.offset });
  if (_auditFilters.action)    p.set('action', _auditFilters.action);
  if (_auditFilters.tenant_id) p.set('tenant_id', _auditFilters.tenant_id);
  let data;
  try { data = await api('/admin/audit?' + p); }
  catch(e) { wrap.innerHTML = `<div style="color:var(--red)">${esc(e.message)}</div>`; return; }

  if (!data.items.length) {
    wrap.innerHTML = '<div class="muted">No audit entries found.</div>';
    return;
  }

  const rows = data.items.map(e => `
    <tr class="audit-row" onclick="_toggleAuditDetail(this)">
      <td style="white-space:nowrap;font-size:12px;color:var(--text-muted)">${esc(e.timestamp.replace('T',' ').replace('Z',''))}</td>
      <td>${esc(e.actor_email || '—')}</td>
      <td>${esc(e.tenant_name || '—')}</td>
      <td><code style="font-size:12px">${esc(e.action)}</code></td>
      <td>${esc(e.resource_id || e.resource || '—')}</td>
    </tr>
    <tr class="audit-detail" style="display:none">
      <td colspan="5" style="background:var(--surface);padding:10px 14px;font-size:12.5px">
        ${e.detail ? `<div><strong>Detail:</strong> ${esc(e.detail)}</div>` : ''}
        ${e.ip_address ? `<div><strong>IP:</strong> ${esc(e.ip_address)}</div>` : ''}
        ${e.actor_name ? `<div><strong>Actor:</strong> ${esc(e.actor_name)}</div>` : ''}
      </td>
    </tr>`).join('');

  const totalPages = Math.ceil(data.total / data.limit) || 1;
  const curPage = Math.floor(data.offset / data.limit) + 1;
  const pagBar = totalPages > 1 ? `
    <div class="pagination">
      <button class="btn btn-ghost btn-sm" ${curPage <= 1 ? 'disabled' : ''}
        onclick="_auditFilters.offset=${(curPage-2)*data.limit};_loadAuditLog()">← Prev</button>
      <span class="page-info">Page ${curPage} of ${totalPages} (${data.total} entries)</span>
      <button class="btn btn-ghost btn-sm" ${curPage >= totalPages ? 'disabled' : ''}
        onclick="_auditFilters.offset=${curPage*data.limit};_loadAuditLog()">Next →</button>
    </div>` : `<div class="muted" style="margin-top:8px;font-size:12.5px">${data.total} entries</div>`;

  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr><th>Timestamp</th><th>Actor</th><th>Tenant</th><th>Action</th><th>Resource</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    ${pagBar}`;
}

function _toggleAuditDetail(row) {
  const next = row.nextElementSibling;
  if (next && next.classList.contains('audit-detail')) {
    next.style.display = next.style.display === 'none' ? '' : 'none';
  }
}

async function exportAuditLog() {
  const p = new URLSearchParams();
  if (_auditFilters.action)    p.set('action', _auditFilters.action);
  if (_auditFilters.tenant_id) p.set('tenant_id', _auditFilters.tenant_id);
  const url = `/api/admin/audit/export?${p}`;
  const a = document.createElement('a');
  a.href = url;
  a.download = 'audit-log.csv';
  // Attach auth header via fetch + blob for JWT-authenticated downloads
  try {
    const resp = await fetch(url, { headers: { Authorization: 'Bearer ' + State.token } });
    if (!resp.ok) throw new Error('Export failed');
    const blob = await resp.blob();
    a.href = URL.createObjectURL(blob);
    a.click();
    URL.revokeObjectURL(a.href);
  } catch(e) { toast(e.message, 'err'); }
}

// ── Reports ───────────────────────────────────────────────────────────────────

let _reportDays = 90;

// ── Reports sub-nav helper ────────────────────────────────────────────────────

function _reportsNav(active) {
  const tabs = [
    { id: 'reports',              label: `${icon('activity',14)} Overview` },
    { id: 'reports-warranty',     label: `${icon('alert',14)} Warranty` },
    { id: 'reports-value',        label: `${icon('dollar',14)} Value` },
    { id: 'reports-depreciation', label: `${icon('refresh',14)} Depreciation` },
    { id: 'reports-age',          label: `${icon('clock',14)} Age` },
  ];
  return `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:22px">
    ${tabs.map(t => `<button class="btn ${t.id === active ? 'btn-accent' : 'btn-ghost'} btn-sm"
      onclick="navigate('${t.id}')">${t.label}</button>`).join('')}
  </div>`;
}

async function _downloadReport(type, menuId) {
  if (menuId) { const m = document.getElementById(menuId); if (m) m.style.display = 'none'; }
  const p = new URLSearchParams({ report_type: type });
  if (type === 'warranty') p.set('days', _reportDays);
  const url = `/api/reports/export?${p}`;
  try {
    const resp = await fetch(url, { headers: { Authorization: 'Bearer ' + State.token } });
    if (!resp.ok) throw new Error('Export failed');
    const blob = await resp.blob();
    const cd = resp.headers.get('content-disposition') || '';
    const fname = (cd.match(/filename=([^;]+)/) || [])[1] || `tether-report-${type}.csv`;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = fname;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch(e) { toast(e.message, 'err'); }
}

// ── Reports Overview ──────────────────────────────────────────────────────────

async function pageReports() {
  const page = document.getElementById('page');
  page.innerHTML = pageHeader('Reports') + _reportsNav('reports') + loading();

  let statusData, valueData, deprData;
  try {
    [statusData, valueData, deprData] = await Promise.all([
      api('/reports/assets-by-status'),
      api('/reports/value'),
      api('/reports/depreciation').catch(() => null),
    ]);
  } catch(e) { page.innerHTML += `<p style="color:var(--red)">${esc(e.message)}</p>`; return; }

  const s = statusData.summary;
  const STATUS_COLORS = {
    available:   '#10b981',
    deployed:    '#6366f1',
    maintenance: '#f59e0b',
    retired:     '#6b7280',
  };

  // Big stat row
  const totalValue = valueData.total_value;
  const depSummary = deprData?.summary;

  const statCards = `
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:28px">
      <div class="panel" style="margin:0">
        <div class="panel-body" style="text-align:center;padding:18px 12px">
          <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Total Assets</div>
          <div style="font-size:32px;font-weight:800">${s.total}</div>
        </div>
      </div>
      <div class="panel" style="margin:0">
        <div class="panel-body" style="text-align:center;padding:18px 12px">
          <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Deployed</div>
          <div style="font-size:32px;font-weight:800;color:#6366f1">${s.deployed ?? 0}</div>
        </div>
      </div>
      <div class="panel" style="margin:0">
        <div class="panel-body" style="text-align:center;padding:18px 12px">
          <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Total Value</div>
          <div style="font-size:32px;font-weight:800;color:var(--accent)">${money(totalValue)}</div>
        </div>
      </div>
      ${depSummary ? `
      <div class="panel" style="margin:0">
        <div class="panel-body" style="text-align:center;padding:18px 12px">
          <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Book Value</div>
          <div style="font-size:32px;font-weight:800;color:var(--emerald)">${money(depSummary.total_current_value)}</div>
        </div>
      </div>` : ''}
    </div>`;

  // Status donut chart
  const statusLabels = ['Available', 'Deployed', 'Maintenance', 'Retired'];
  const statusValues = [s.available ?? 0, s.deployed ?? 0, s.maintenance ?? 0, s.retired ?? 0];
  const statusColorsArr = Object.values(STATUS_COLORS);

  // Value bar chart — top 6 categories
  const catSlice = valueData.by_category.slice(0, 6);
  const catLabels = catSlice.map(c => c.category_name);
  const catValues = catSlice.map(c => c.total_value);

  // Nav tiles to sub-reports
  const tiles = [
    { id: 'reports-warranty',     ic: 'alert',    title: 'Warranty Report',   desc: 'Assets with expiring warranties' },
    { id: 'reports-value',        ic: 'dollar',   title: 'Value Report',      desc: 'Asset value by category and tenant' },
    { id: 'reports-depreciation', ic: 'refresh',  title: 'Depreciation',      desc: 'Book values and end-of-life tracking' },
    { id: 'reports-age',          ic: 'clock',    title: 'Age Report',        desc: 'Asset age brackets for refresh planning' },
  ].map(t => `
    <div class="panel" style="margin:0;cursor:pointer" onclick="navigate('${t.id}')">
      <div class="panel-body" style="display:flex;align-items:center;gap:14px;padding:16px 18px">
        <div style="width:40px;height:40px;border-radius:10px;background:var(--accent)18;
                    display:flex;align-items:center;justify-content:center;flex-shrink:0;color:var(--accent)">
          ${icon(t.ic, 20)}
        </div>
        <div>
          <div style="font-weight:600;font-size:14px">${t.title}</div>
          <div style="font-size:12.5px;color:var(--text-muted);margin-top:2px">${t.desc}</div>
        </div>
        <span style="margin-left:auto;color:var(--text-muted)">${icon('back',16)}</span>
      </div>
    </div>`).join('');

  page.innerHTML = pageHeader('Reports') + _reportsNav('reports') + statCards + `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:24px">
      <div class="panel" style="margin:0">
        <div class="panel-head"><h3>Assets by Status</h3></div>
        <div class="panel-body" style="display:flex;align-items:center;justify-content:center;min-height:220px">
          <canvas id="chart-status" width="220" height="220" style="max-width:220px"></canvas>
        </div>
      </div>
      <div class="panel" style="margin:0">
        <div class="panel-head"><h3>Value by Category</h3></div>
        <div class="panel-body" style="min-height:220px;display:flex;align-items:center">
          <canvas id="chart-value" style="width:100%;max-height:220px"></canvas>
        </div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px">
      ${tiles}
    </div>`;

  // Draw status donut
  new Chart(document.getElementById('chart-status'), {
    type: 'doughnut',
    data: {
      labels: statusLabels,
      datasets: [{ data: statusValues, backgroundColor: statusColorsArr, borderWidth: 0, hoverOffset: 6 }],
    },
    options: {
      cutout: '68%',
      plugins: {
        legend: { position: 'bottom', labels: { color: '#9ca3af', font: { size: 12 }, padding: 14 } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed}` } },
      },
    },
  });

  // Draw value bar
  if (catValues.length) {
    new Chart(document.getElementById('chart-value'), {
      type: 'bar',
      data: {
        labels: catLabels,
        datasets: [{
          label: 'Total Value',
          data: catValues,
          backgroundColor: '#d4f03488',
          borderColor: '#d4f034',
          borderWidth: 1,
          borderRadius: 4,
        }],
      },
      options: {
        indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: {
          x: {
            ticks: { color: '#9ca3af', callback: v => money(v) },
            grid: { color: '#ffffff10' },
          },
          y: { ticks: { color: '#9ca3af' }, grid: { display: false } },
        },
      },
    });
  } else {
    document.getElementById('chart-value').closest('.panel-body').innerHTML =
      `<p class="muted" style="text-align:center;width:100%">No valued assets yet</p>`;
  }
}

// ── Warranty Report page ──────────────────────────────────────────────────────

async function pageReportWarranty() {
  const page = document.getElementById('page');
  page.innerHTML = pageHeader('Warranty Report',null,
    `<button class="btn btn-ghost btn-sm" onclick="_downloadReport('warranty')">${icon('download',14)} CSV</button>`)
    + _reportsNav('reports-warranty') + loading();

  const dayOpts = [30,60,90,180].map(d =>
    `<button class="btn btn-sm ${d===_reportDays?'btn-accent':'btn-ghost'}"
       onclick="_reportDays=${d};pageReportWarranty()">${d}d</button>`).join('');

  let items;
  try { items = await api(`/reports/warranty?days=${_reportDays}`); }
  catch(e) {
    document.getElementById('page').innerHTML += `<p style="color:var(--red)">${esc(e.message)}</p>`;
    return;
  }

  const showTenant = isMSP();
  const rows = items.map(w => {
    const d = w.days_remaining;
    const urgent = d <= 7, warn = d <= 30;
    const rowStyle = urgent ? ' style="color:var(--red)"' : warn ? ' style="color:var(--amber)"' : '';
    return `<tr${rowStyle}>
      <td><span class="tag">${esc(w.asset_tag)}</span></td>
      <td>${esc(w.name)}</td>
      ${showTenant ? `<td>${esc(w.tenant_name||'—')}</td>` : ''}
      <td>${esc(w.location_name||'—')}</td>
      <td>${w.warranty_expiry ? fmtDate(w.warranty_expiry) : '—'}</td>
      <td><span class="${urgent?'badge retired':warn?'badge maintenance':'badge available'}">${d != null ? d+'d' : '—'}</span></td>
      <td>${w.purchase_cost != null ? money(w.purchase_cost) : '—'}</td>
    </tr>`;
  }).join('');

  const summary = items.length
    ? `<div style="display:flex;gap:14px;margin-bottom:20px;flex-wrap:wrap">
        <div class="panel" style="margin:0;flex:1;min-width:120px"><div class="panel-body" style="text-align:center;padding:14px">
          <div class="muted" style="font-size:11px;text-transform:uppercase">Expiring</div>
          <div style="font-size:26px;font-weight:700">${items.length}</div>
        </div></div>
        <div class="panel" style="margin:0;flex:1;min-width:120px"><div class="panel-body" style="text-align:center;padding:14px">
          <div class="muted" style="font-size:11px;text-transform:uppercase">Critical (&lt;7d)</div>
          <div style="font-size:26px;font-weight:700;color:var(--red)">${items.filter(w=>w.days_remaining<=7).length}</div>
        </div></div>
        <div class="panel" style="margin:0;flex:1;min-width:120px"><div class="panel-body" style="text-align:center;padding:14px">
          <div class="muted" style="font-size:11px;text-transform:uppercase">Warning (&lt;30d)</div>
          <div style="font-size:26px;font-weight:700;color:var(--amber)">${items.filter(w=>w.days_remaining<=30&&w.days_remaining>7).length}</div>
        </div></div>
      </div>` : '';

  page.innerHTML = pageHeader('Warranty Report', null,
    `<button class="btn btn-ghost btn-sm" onclick="_downloadReport('warranty')">${icon('download',14)} CSV</button>`)
    + _reportsNav('reports-warranty')
    + `<div style="display:flex;align-items:center;gap:8px;margin-bottom:18px">
        <span class="muted" style="font-size:13px">Show expiring within:</span>
        ${dayOpts}
       </div>`
    + summary
    + (items.length
      ? `<div class="panel"><div class="panel-body" style="padding:0">
          <div class="table-wrap" style="border:none;box-shadow:none">
            <table class="data-table">
              <thead><tr>
                <th>Tag</th><th>Name</th>
                ${showTenant ? '<th>Tenant</th>' : ''}
                <th>Location</th><th>Expiry Date</th><th>Days Left</th><th>Purchase Cost</th>
              </tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </div></div>`
      : `<div class="panel"><div class="panel-body"><p class="muted">No warranties expiring in the next ${_reportDays} days.</p></div></div>`);
}

// ── Value Report page ─────────────────────────────────────────────────────────

async function pageReportValue() {
  const page = document.getElementById('page');
  page.innerHTML = pageHeader('Value Report', null,
    `<button class="btn btn-ghost btn-sm" onclick="_downloadReport('value')">${icon('download',14)} CSV</button>`)
    + _reportsNav('reports-value') + loading();

  let data;
  try { data = await api('/reports/value'); }
  catch(e) { page.innerHTML += `<p style="color:var(--red)">${esc(e.message)}</p>`; return; }

  const catRows = data.by_category.map(c => {
    const pct = data.total_value > 0 ? (c.total_value / data.total_value * 100).toFixed(1) : 0;
    return `<tr>
      <td>${esc(c.category_name)}</td>
      <td>${c.count}</td>
      <td style="font-weight:600">${money(c.total_value)}</td>
      <td class="muted">${money(c.avg_value)}</td>
      <td style="width:120px">
        <div style="display:flex;align-items:center;gap:8px">
          <div style="flex:1;height:6px;background:var(--border);border-radius:3px;overflow:hidden">
            <div style="width:${pct}%;height:100%;background:var(--accent);border-radius:3px"></div>
          </div>
          <span style="font-size:12px;color:var(--text-muted);width:36px">${pct}%</span>
        </div>
      </td>
    </tr>`;
  }).join('');

  const topRows = data.top_assets.map((a, i) => `<tr>
    <td class="muted" style="font-size:12px;width:28px">${i+1}</td>
    <td><span class="tag">${esc(a.asset_tag)}</span></td>
    <td>${esc(a.name)}</td>
    ${isMSP() ? `<td class="muted">${esc(a.tenant_name||'—')}</td>` : ''}
    <td style="font-weight:600">${money(a.purchase_cost)}</td>
  </tr>`).join('');

  const tenantPanel = data.by_tenant?.length ? `
    <div class="panel">
      <div class="panel-head"><h3>By Tenant</h3></div>
      <div class="panel-body" style="padding:0">
        <div class="table-wrap" style="border:none;box-shadow:none">
          <table class="data-table">
            <thead><tr><th>Tenant</th><th>Assets</th><th>Total Value</th></tr></thead>
            <tbody>${data.by_tenant.map(t=>`<tr>
              <td>${esc(t.tenant_name)}</td><td>${t.count}</td>
              <td style="font-weight:600">${money(t.total_value)}</td>
            </tr>`).join('')}</tbody>
          </table>
        </div>
      </div>
    </div>` : '';

  page.innerHTML = pageHeader('Value Report', null,
    `<button class="btn btn-ghost btn-sm" onclick="_downloadReport('value')">${icon('download',14)} CSV</button>`)
    + _reportsNav('reports-value') + `
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:24px">
      <div class="panel" style="margin:0"><div class="panel-body" style="text-align:center;padding:20px 12px">
        <div class="muted" style="font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">Total Portfolio Value</div>
        <div style="font-size:34px;font-weight:800;color:var(--accent)">${money(data.total_value)}</div>
      </div></div>
      <div class="panel" style="margin:0"><div class="panel-body" style="text-align:center;padding:20px 12px">
        <div class="muted" style="font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">Categories</div>
        <div style="font-size:34px;font-weight:800">${data.by_category.length}</div>
      </div></div>
      <div class="panel" style="margin:0"><div class="panel-body" style="text-align:center;padding:20px 12px">
        <div class="muted" style="font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">Valued Assets</div>
        <div style="font-size:34px;font-weight:800">${data.top_assets.length > 0 ? data.by_category.reduce((s,c)=>s+c.count,0) : 0}</div>
      </div></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px">
      <div class="panel" style="margin:0">
        <div class="panel-head"><h3>By Category</h3></div>
        <div class="panel-body" style="padding:0">
          <div class="table-wrap" style="border:none;box-shadow:none">
            <table class="data-table">
              <thead><tr><th>Category</th><th>Assets</th><th>Total</th><th>Avg</th><th>Share</th></tr></thead>
              <tbody>${catRows||'<tr><td colspan="5" class="muted" style="padding:16px">No categorised assets with purchase cost</td></tr>'}</tbody>
            </table>
          </div>
        </div>
      </div>
      <div class="panel" style="margin:0">
        <div class="panel-head"><h3>Top 10 by Value</h3></div>
        <div class="panel-body" style="padding:0">
          <div class="table-wrap" style="border:none;box-shadow:none">
            <table class="data-table">
              <thead><tr><th>#</th><th>Tag</th><th>Name</th>${isMSP()?'<th>Tenant</th>':''}<th>Cost</th></tr></thead>
              <tbody>${topRows||'<tr><td colspan="5" class="muted" style="padding:16px">No valued assets</td></tr>'}</tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
    ${tenantPanel}`;
}

// ── Depreciation Report page ──────────────────────────────────────────────────

async function pageReportDepreciation() {
  const page = document.getElementById('page');
  page.innerHTML = pageHeader('Depreciation Report', null,
    `<button class="btn btn-ghost btn-sm" onclick="_downloadDepreciationReport()">${icon('download',14)} CSV</button>`)
    + _reportsNav('reports-depreciation') + loading();

  let data;
  try { data = await api('/reports/depreciation'); }
  catch(e) { page.innerHTML += `<p style="color:var(--red)">${esc(e.message)}</p>`; return; }

  const s = data.summary;
  const lostPct = s.total_purchase_value > 0
    ? Math.round(s.total_depreciated / s.total_purchase_value * 100) : 0;

  const rows = data.items.map(i => {
    const barColor = i.fully_depreciated ? 'var(--red)' : i.depreciation_pct >= 80 ? 'var(--amber)' : 'var(--accent)';
    return `<tr>
      <td><span class="tag">${esc(i.asset_tag)}</span>
        ${i.fully_depreciated?'<span class="badge retired" style="font-size:11px;margin-left:4px">Fully depreciated</span>':''}</td>
      <td>${esc(i.name)}</td>
      <td class="muted">${esc(i.category_name||'—')}</td>
      <td>${money(i.purchase_cost)}</td>
      <td style="font-weight:600;${i.fully_depreciated?'color:var(--text-muted)':''}">${money(i.current_value)}</td>
      <td>
        <div style="display:flex;align-items:center;gap:8px">
          <div style="width:72px;height:6px;background:var(--border);border-radius:3px;overflow:hidden">
            <div style="width:${Math.min(100,i.depreciation_pct)}%;height:100%;background:${barColor};border-radius:3px"></div>
          </div>
          <span style="font-size:12px;width:34px">${i.depreciation_pct}%</span>
        </div>
      </td>
      <td class="muted" style="font-size:12.5px">${i.end_of_life_date?fmtDate(i.end_of_life_date):'—'}</td>
      <td class="muted" style="font-size:12.5px">${i.days_remaining < 0 ? 'Expired' : i.days_remaining+'d'}</td>
    </tr>`;
  }).join('');

  page.innerHTML = pageHeader('Depreciation Report', null,
    `<button class="btn btn-ghost btn-sm" onclick="_downloadDepreciationReport()">${icon('download',14)} CSV</button>`)
    + _reportsNav('reports-depreciation') + `
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:24px">
      <div class="panel" style="margin:0"><div class="panel-body" style="text-align:center;padding:18px 12px">
        <div class="muted" style="font-size:11px;text-transform:uppercase;margin-bottom:6px">Purchase Value</div>
        <div style="font-size:26px;font-weight:700">${money(s.total_purchase_value)}</div>
      </div></div>
      <div class="panel" style="margin:0"><div class="panel-body" style="text-align:center;padding:18px 12px">
        <div class="muted" style="font-size:11px;text-transform:uppercase;margin-bottom:6px">Current Book Value</div>
        <div style="font-size:26px;font-weight:700;color:var(--emerald)">${money(s.total_current_value)}</div>
      </div></div>
      <div class="panel" style="margin:0"><div class="panel-body" style="text-align:center;padding:18px 12px">
        <div class="muted" style="font-size:11px;text-transform:uppercase;margin-bottom:6px">Total Depreciated</div>
        <div style="font-size:26px;font-weight:700;color:var(--amber)">${money(s.total_depreciated)} <span style="font-size:14px">(${lostPct}%)</span></div>
      </div></div>
      <div class="panel" style="margin:0"><div class="panel-body" style="text-align:center;padding:18px 12px">
        <div class="muted" style="font-size:11px;text-transform:uppercase;margin-bottom:6px">Fully Depreciated</div>
        <div style="font-size:26px;font-weight:700;color:var(--red)">${s.fully_depreciated_count}</div>
      </div></div>
      <div class="panel" style="margin:0"><div class="panel-body" style="text-align:center;padding:18px 12px">
        <div class="muted" style="font-size:11px;text-transform:uppercase;margin-bottom:6px">Tracked Assets</div>
        <div style="font-size:26px;font-weight:700">${s.tracked_asset_count}</div>
      </div></div>
    </div>
    ${data.items.length
      ? `<div class="panel">
          <div class="panel-head"><h3>All Depreciated Assets</h3>
            <span class="muted" style="font-size:12.5px">Sorted by depreciation %</span>
          </div>
          <div class="panel-body" style="padding:0">
            <div class="table-wrap" style="border:none;box-shadow:none">
              <table class="data-table">
                <thead><tr><th>Tag</th><th>Name</th><th>Category</th><th>Purchase</th>
                  <th>Book Value</th><th>Depreciated</th><th>End of Life</th><th>Days Left</th></tr></thead>
                <tbody>${rows}</tbody>
              </table>
            </div>
          </div>
        </div>`
      : `<div class="panel"><div class="panel-body">
          <p class="muted">No assets have depreciation data set yet. Add <b>Useful Life</b> and <b>Purchase Cost</b> to an asset to start tracking.</p>
        </div></div>`}`;
}

// ── Age Report ────────────────────────────────────────────────────────────────

async function pageReportsAge() {
  const page = document.getElementById('page');
  page.innerHTML = pageHeader('Reports') + _reportsNav('reports-age') + loading();
  let data;
  try { data = await api('/reports/age'); }
  catch (e) { page.innerHTML += `<p style="color:var(--red)">${esc(e.message)}</p>`; return; }

  const BRACKET_COLORS = ['#10b981', '#6366f1', '#f59e0b', '#ef4444'];
  const bracketBars = data.brackets.map((b, i) => {
    const pct = data.total > 0 ? Math.round((b.count / data.total) * 100) : 0;
    return `
      <div style="margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:5px">
          <span style="font-weight:600">${esc(b.label)}</span>
          <span style="color:var(--text-muted)">${b.count} asset${b.count !== 1 ? 's' : ''} · ${pct}%</span>
        </div>
        <div class="usage-bar-track">
          <div class="usage-bar-fill" style="width:${pct}%;background:${BRACKET_COLORS[i]};border-radius:4px"></div>
        </div>
        ${b.assets.length ? `<details style="margin-top:8px">
          <summary style="cursor:pointer;font-size:12.5px;color:var(--text-muted)">Show assets</summary>
          <div class="table-wrap" style="border:none;box-shadow:none;margin-top:6px">
            <table class="data-table">
              <thead><tr><th>Tag</th><th>Name</th><th>Purchase Date</th><th>Age</th><th>Status</th><th>Category</th></tr></thead>
              <tbody>${b.assets.map(a => `
                <tr onclick="navigate('asset-detail',${a.id})" style="cursor:pointer">
                  <td><span class="tag">${esc(a.asset_tag)}</span></td>
                  <td>${esc(a.name)}</td>
                  <td>${fmtDate(a.purchase_date)}</td>
                  <td>${a.age_years} yr</td>
                  <td>${statusBadge(a.status)}</td>
                  <td>${esc(a.category||'—')}</td>
                </tr>`).join('')}</tbody>
            </table>
          </div>
        </details>` : ''}
      </div>`;
  }).join('');

  page.innerHTML = pageHeader('Reports') + _reportsNav('reports-age') + `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <div>
        <b>${data.total}</b> assets total
        ${data.no_purchase_date > 0 ? `<span class="muted" style="font-size:12.5px;margin-left:10px">(${data.no_purchase_date} without purchase date, not shown)</span>` : ''}
      </div>
      <button class="btn btn-ghost btn-sm" onclick="_downloadAgeReport()">${icon('download',14)} Export CSV</button>
    </div>
    <div class="panel">
      <div class="panel-head"><h3>${icon('clock',16)} Asset Age Brackets</h3></div>
      <div class="panel-body">
        ${data.brackets.every(b => b.count === 0)
          ? `<p class="muted">No assets with purchase dates found. Add purchase dates to assets to use this report.</p>`
          : bracketBars}
      </div>
    </div>`;
}

async function _downloadDepSchedule(assetId) {
  const url = `/api/reports/depreciation/schedule/${assetId}/export`;
  try {
    const resp = await fetch(url, { headers: { Authorization: 'Bearer ' + State.token } });
    if (!resp.ok) throw new Error('Export failed');
    const blob = await resp.blob();
    const cd = resp.headers.get('content-disposition') || '';
    const fname = (cd.match(/filename=([^;]+)/) || [])[1] || `tether-depreciation-${assetId}.csv`;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = fname;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch(e) { toast(e.message, 'err'); }
}

async function _downloadAgeReport() {
  const url = '/api/reports/age/export';
  try {
    const resp = await fetch(url, { headers: { Authorization: 'Bearer ' + State.token } });
    if (!resp.ok) throw new Error('Export failed');
    const blob = await resp.blob();
    const cd = resp.headers.get('content-disposition') || '';
    const fname = (cd.match(/filename=([^;]+)/) || [])[1] || 'tether-report-age.csv';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = fname;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch(e) { toast(e.message, 'err'); }
}

// ── Depreciation helpers ──────────────────────────────────────────────────────

function _renderDepreciationPanel(dep, assetId) {
  if (!dep) return '';
  const pct        = dep.depreciation_pct;
  const barClass   = dep.fully_depreciated ? 'exceeded' : pct >= 80 ? 'warn' : '';
  const barColor   = dep.fully_depreciated ? 'var(--red)' : pct >= 80 ? 'var(--amber)' : 'var(--accent)';
  const eolFmt     = dep.end_of_life_date ? fmtDate(dep.end_of_life_date) : '—';
  const daysLeft   = dep.days_remaining;
  const daysLabel  = dep.fully_depreciated
    ? `<span style="color:var(--red);font-weight:600">Fully depreciated</span>`
    : `${daysLeft} day${daysLeft !== 1 ? 's' : ''} remaining`;

  const banner = dep.fully_depreciated
    ? `<div style="background:var(--amber)18;border:1px solid var(--amber)44;border-radius:6px;
                   padding:10px 14px;margin-bottom:16px;color:var(--amber);font-size:13.5px;font-weight:500">
         ${icon('alert', 15)} This asset is fully depreciated
       </div>`
    : '';

  return `
    <div class="panel" style="margin-top:18px">
      <div class="panel-head"><h3>${icon('activity', 16)} Depreciation</h3>${assetId ? `<button class="btn btn-ghost btn-sm" onclick="_downloadDepSchedule(${assetId})">${icon('download',14)} Schedule</button>` : ''}</div>
      <div class="panel-body">
        ${banner}
        <div style="margin-bottom:16px">
          <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:6px">
            <span>Book value</span>
            <span style="font-weight:600">${money(dep.current_value)} of ${money(dep.purchase_cost)}</span>
          </div>
          <div class="usage-bar-track">
            <div class="usage-bar-fill ${barClass}"
                 style="width:${Math.min(100, pct)}%;background:${barColor}"></div>
          </div>
          <div style="font-size:12px;color:var(--text-muted);margin-top:4px">${pct}% depreciated</div>
        </div>
        <div class="detail-rows">
          <div class="drow"><div class="k">Annual Depreciation</div>
            <div class="v">${money(dep.annual_depreciation)} / yr</div></div>
          <div class="drow"><div class="k">Total Depreciated</div>
            <div class="v">${money(dep.total_depreciation)}</div></div>
          <div class="drow"><div class="k">End of Life</div>
            <div class="v">${eolFmt}</div></div>
          <div class="drow"><div class="k">Days Remaining</div>
            <div class="v">${daysLabel}</div></div>
          <div class="drow"><div class="k">Salvage Value</div>
            <div class="v">${money(dep.salvage_value)}</div></div>
        </div>
      </div>
    </div>`;
}

function _renderCustomFieldsPanel(cfs, assetId) {
  if (!cfs || !cfs.length) return '';
  const row = (k, v) => `<div class="drow"><div class="k">${k}</div><div class="v">${v}</div></div>`;
  const rows = cfs.map(cf => {
    let display;
    if (cf.field_type === 'url' && cf.value) {
      display = `<a href="${esc(cf.value)}" target="_blank" rel="noopener" style="color:var(--accent)">${esc(cf.value)}</a>`;
    } else if (cf.field_type === 'boolean') {
      display = cf.value === 'true' ? 'Yes' : cf.value === 'false' ? 'No' : '—';
    } else if (cf.field_type === 'date') {
      display = cf.value ? fmtDate(cf.value) : '—';
    } else {
      display = cf.value ? esc(cf.value) : '—';
    }
    return row(esc(cf.label), display);
  }).join('');
  return `
    <div class="panel" style="margin-top:18px">
      <div class="panel-head"><h3>Custom Fields</h3></div>
      <div class="panel-body"><div class="detail-rows">${rows}</div></div>
    </div>`;
}

function _downloadDepreciationReport() {
  window.location.href = '/api/reports/depreciation/export';
}

// ── Software Licences ─────────────────────────────────────────────────────────

const LICENCE_TYPES = ['per-seat', 'site', 'concurrent', 'OEM', 'subscription'];

async function pageLicences() {
  const page = document.getElementById('page');
  page.innerHTML = pageHeader('Software Licences', null,
    `<button class="btn btn-accent" onclick="openLicenceForm()">${icon('plus', 16)}New Licence</button>`) +
    loading();

  let licences, expiring;
  try {
    [licences, expiring] = await Promise.all([
      api('/licences'),
      api('/licences/expiring?days=90'),
    ]);
  } catch(e) { toast(e.message, 'err'); return; }

  const totalSeats = licences.reduce((s, l) => s + (l.total_seats ?? 0), 0);
  const usedSeats  = licences.reduce((s, l) => s + l.seats_used, 0);
  const seatsLabel = totalSeats > 0 ? `${usedSeats} / ${totalSeats}` : `${usedSeats} used`;

  const stats = `
    <div class="stat-grid" style="margin-bottom:18px">
      <div class="stat"><div class="label">${icon('layers',15)}Total Licences</div>
        <div class="value">${licences.length}</div></div>
      <div class="stat"><div class="label">${icon('users',15)}Seats Used</div>
        <div class="value">${seatsLabel}</div></div>
      <div class="stat"><div class="label">${icon('alert',15)}Expiring (90d)</div>
        <div class="value">${expiring.length}</div></div>
    </div>`;

  if (!licences.length) {
    page.innerHTML = pageHeader('Software Licences', null,
      `<button class="btn btn-accent" onclick="openLicenceForm()">${icon('plus',16)}New Licence</button>`) +
      stats +
      `<div class="table-wrap"><div class="empty">${icon('layers',44)}<h3>No licences yet</h3>
        <p>Track your software licences and seat usage.</p></div></div>`;
    return;
  }

  const today = new Date();
  const rows = licences.map(l => {
    const pct = l.total_seats ? Math.round(l.seats_used / l.total_seats * 100) : null;
    const barColor = pct === null ? 'var(--indigo)' : pct >= 100 ? 'var(--red)' : pct >= 80 ? 'var(--amber)' : 'var(--emerald)';
    const seatsHtml = l.total_seats === null
      ? `<span class="muted">${l.seats_used} / ∞</span>`
      : `<div style="display:flex;align-items:center;gap:8px">
           <span style="color:${barColor};font-weight:600;white-space:nowrap">${l.seats_used} / ${l.total_seats}</span>
           <div style="width:60px;height:6px;background:var(--border);border-radius:3px;overflow:hidden">
             <div style="width:${Math.min(100,pct)}%;height:100%;background:${barColor};border-radius:3px"></div>
           </div>
         </div>`;

    let expiryHtml = '<span class="muted">—</span>';
    if (l.expiry_date) {
      const days = Math.ceil((new Date(l.expiry_date) - today) / 86400000);
      const color = days < 0 ? 'var(--red)' : days <= 30 ? 'var(--amber)' : '';
      expiryHtml = color
        ? `<span style="color:${color};font-weight:600">${fmtDate(l.expiry_date)}</span>`
        : fmtDate(l.expiry_date);
    }

    return `<tr>
      <td><b>${esc(l.name)}</b>${l.vendor ? `<div class="cell-sub">${esc(l.vendor)}</div>` : ''}</td>
      <td class="muted">${esc(l.licence_type || '—')}</td>
      <td>${seatsHtml}</td>
      <td>${expiryHtml}</td>
      <td class="muted">${l.purchase_cost != null ? money(l.purchase_cost) : '—'}</td>
      <td>
        <div style="display:flex;gap:6px">
          <button class="btn btn-ghost btn-sm" onclick="viewLicence(${l.id})">${icon('eye',14)} View</button>
          <button class="btn btn-ghost btn-sm" onclick="openLicenceForm(${l.id})">${icon('edit',14)}</button>
          <button class="btn btn-danger btn-sm" onclick="deleteLicence(${l.id})">${icon('trash',14)}</button>
        </div>
      </td>
    </tr>`;
  }).join('');

  page.innerHTML = pageHeader('Software Licences', null,
    `<button class="btn btn-accent" onclick="openLicenceForm()">${icon('plus',16)}New Licence</button>`) +
    stats + `
    <div class="table-wrap"><table>
      <thead><tr>
        <th>Name / Vendor</th><th>Type</th><th>Seats</th>
        <th>Expiry</th><th>Cost</th><th>Actions</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
}

async function openLicenceForm(id = null) {
  let l = { name:'', vendor:'', licence_type:'per-seat', total_seats:'',
             purchase_date:'', expiry_date:'', purchase_cost:'', renewal_cost:'',
             licence_key:'', notes:'' };
  if (id) {
    try { l = await api(`/licences/${id}`); } catch(e) { toast(e.message,'err'); return; }
  }
  const typeOpts = LICENCE_TYPES.map(t =>
    `<option value="${t}" ${l.licence_type===t?'selected':''}>${t[0].toUpperCase()+t.slice(1)}</option>`
  ).join('');

  openModal(`
    <div class="modal-head"><h2>${id ? 'Edit Licence' : 'New Licence'}</h2>
      <button class="x-btn" onclick="closeModal()">✕</button></div>
    <form id="lic-form"><div class="modal-body">
      <div class="field"><label>Name *</label>
        <input name="name" value="${esc(l.name)}" required placeholder="Microsoft 365 Business"></div>
      <div class="field-row">
        <div class="field"><label>Vendor</label>
          <input name="vendor" value="${esc(l.vendor||'')}" placeholder="Microsoft"></div>
        <div class="field"><label>Licence Type</label>
          <select name="licence_type">${typeOpts}</select></div>
      </div>
      <div class="field-row">
        <div class="field"><label>Total Seats</label>
          <input name="total_seats" type="number" min="1" value="${l.total_seats ?? ''}"
            placeholder="blank = unlimited"></div>
        <div class="field"><label>Purchase Cost</label>
          <input name="purchase_cost" type="number" step="0.01" min="0" value="${l.purchase_cost ?? ''}"></div>
      </div>
      <div class="field-row">
        <div class="field"><label>Renewal Cost</label>
          <input name="renewal_cost" type="number" step="0.01" min="0" value="${l.renewal_cost ?? ''}"></div>
        <div class="field"><label>Purchase Date</label>
          <input name="purchase_date" type="date" value="${l.purchase_date || ''}"></div>
      </div>
      <div class="field"><label>Expiry Date</label>
        <input name="expiry_date" type="date" value="${l.expiry_date || ''}"></div>
      <div class="field">
        <label>Licence Key</label>
        <div style="display:flex;gap:6px">
          <input id="lic-key-input" name="licence_key" type="password" value="${esc(l.licence_key||'')}"
            style="flex:1" placeholder="xxxx-xxxx-xxxx-xxxx">
          <button type="button" class="btn btn-ghost btn-sm"
            onclick="document.getElementById('lic-key-input').type=document.getElementById('lic-key-input').type==='password'?'text':'password'">
            ${icon('eye',14)}</button>
        </div>
      </div>
      <div class="field"><label>Notes</label>
        <textarea name="notes" rows="2" style="resize:vertical">${esc(l.notes||'')}</textarea></div>
    </div>
    <div class="modal-foot">
      <button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button type="submit" class="btn btn-primary">${id ? 'Save Changes' : 'Create Licence'}</button>
    </div></form>`);

  document.getElementById('lic-form').onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const body = {
      name:          f.get('name'),
      vendor:        f.get('vendor') || '',
      licence_type:  f.get('licence_type') || '',
      total_seats:   f.get('total_seats') ? parseInt(f.get('total_seats')) : null,
      purchase_date: f.get('purchase_date') || null,
      expiry_date:   f.get('expiry_date') || null,
      purchase_cost: f.get('purchase_cost') ? parseFloat(f.get('purchase_cost')) : null,
      renewal_cost:  f.get('renewal_cost')  ? parseFloat(f.get('renewal_cost'))  : null,
      licence_key:   f.get('licence_key') || '',
      notes:         f.get('notes') || '',
    };
    try {
      if (id) await api(`/licences/${id}`, { method: 'PUT', json: body });
      else    await api('/licences',        { method: 'POST', json: body });
      closeModal();
      toast(id ? 'Licence updated' : 'Licence created');
      pageLicences();
    } catch(err) { toast(err.message, 'err'); }
  };
}

async function viewLicence(id) {
  let lic;
  try { lic = await api(`/licences/${id}`); } catch(e) { toast(e.message,'err'); return; }

  const today = new Date();
  let expiryHtml = '—';
  if (lic.expiry_date) {
    const days = Math.ceil((new Date(lic.expiry_date) - today) / 86400000);
    const color = days < 0 ? 'var(--red)' : days <= 30 ? 'var(--amber)' : '';
    expiryHtml = color
      ? `<span style="color:${color};font-weight:600">${fmtDate(lic.expiry_date)} (${days}d)</span>`
      : fmtDate(lic.expiry_date);
  }

  const assignRows = (lic.assignments || []).map(a => `
    <tr>
      <td>${esc(a.employee_name || '—')}</td>
      <td><code style="font-size:12px">${esc(a.asset_tag || '—')}</code></td>
      <td class="muted" style="font-size:12px">${a.assigned_at ? fmtDate(a.assigned_at) : '—'}</td>
      <td class="muted" style="font-size:12px">${esc(a.notes || '')}</td>
      <td>
        <button class="btn btn-danger btn-sm" onclick="unassignSeat(${id}, ${a.id})">
          ${icon('trash',13)} Unassign</button>
      </td>
    </tr>`).join('');

  const seatsLabel = lic.total_seats === null
    ? `${lic.seats_used} used (unlimited)`
    : `${lic.seats_used} / ${lic.total_seats} (${lic.seats_available} available)`;

  openModal(`
    <div class="modal-head">
      <h2>${esc(lic.name)}</h2>
      <button class="x-btn" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-body">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px 24px;margin-bottom:18px">
        <div><div class="form-label">Vendor</div><div>${esc(lic.vendor||'—')}</div></div>
        <div><div class="form-label">Type</div><div>${esc(lic.licence_type||'—')}</div></div>
        <div><div class="form-label">Seats</div><div>${seatsLabel}</div></div>
        <div><div class="form-label">Expiry</div><div>${expiryHtml}</div></div>
        <div><div class="form-label">Purchase Cost</div><div>${lic.purchase_cost != null ? money(lic.purchase_cost) : '—'}</div></div>
        <div><div class="form-label">Renewal Cost</div><div>${lic.renewal_cost != null ? money(lic.renewal_cost) : '—'}</div></div>
        ${lic.purchase_date ? `<div><div class="form-label">Purchased</div><div>${fmtDate(lic.purchase_date)}</div></div>` : ''}
        ${lic.notes ? `<div style="grid-column:1/-1"><div class="form-label">Notes</div><div class="muted">${esc(lic.notes)}</div></div>` : ''}
      </div>

      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <b>Assigned to (${lic.assignments.length})</b>
        ${lic.total_seats === null || lic.seats_available > 0
          ? `<button class="btn btn-accent btn-sm" onclick="openAssignModal(${id})">
               ${icon('plus',13)} Assign Seat</button>`
          : `<span class="muted" style="font-size:12.5px">No seats available</span>`}
      </div>
      ${assignRows
        ? `<div class="table-wrap" style="border:none;box-shadow:none">
             <table class="data-table" style="font-size:13px">
               <thead><tr><th>Employee</th><th>Asset</th><th>Assigned</th><th>Notes</th><th></th></tr></thead>
               <tbody id="assign-tbody">${assignRows}</tbody>
             </table></div>`
        : '<p class="muted">No seats assigned yet.</p>'}
    </div>
    <div class="modal-foot">
      <button class="btn btn-ghost" onclick="openLicenceForm(${id});closeModal=()=>{}">Edit</button>
      <button class="btn btn-ghost" onclick="closeModal()">Close</button>
    </div>`, true);
}

async function openAssignModal(licId) {
  let employees = [], assets = [];
  try {
    let [empsResp, assetsResp] = await Promise.all([api('/employees'), api('/assets?limit=200')]);
    employees = empsResp.items ?? empsResp;
    assets = assetsResp.items ?? assetsResp;
  } catch(e) { toast(e.message,'err'); return; }

  const empOpts = employees.map(e =>
    `<option value="${e.id}">${esc(e.name)}${e.department ? ' · '+esc(e.department) : ''}</option>`
  ).join('');
  const assetOpts = assets.map(a =>
    `<option value="${a.id}">${esc(a.asset_tag)} — ${esc(a.name)}</option>`
  ).join('');

  openModal(`
    <div class="modal-head"><h2>Assign Seat</h2>
      <button class="x-btn" onclick="closeModal()">✕</button></div>
    <form id="assign-form"><div class="modal-body">
      <div class="field"><label>Employee (optional)</label>
        <select name="employee_id">
          <option value="">— None —</option>${empOpts}
        </select></div>
      <div class="field"><label>Asset (optional)</label>
        <select name="asset_id">
          <option value="">— None —</option>${assetOpts}
        </select></div>
      <div class="field"><label>Notes</label>
        <input name="notes" placeholder="e.g. Primary device"></div>
    </div>
    <div class="modal-foot">
      <button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button type="submit" class="btn btn-primary">Assign</button>
    </div></form>`);

  document.getElementById('assign-form').onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const body = {
      employee_id: f.get('employee_id') ? parseInt(f.get('employee_id')) : null,
      asset_id:    f.get('asset_id')    ? parseInt(f.get('asset_id'))    : null,
      notes:       f.get('notes') || '',
    };
    try {
      await api(`/licences/${licId}/assign`, { method: 'POST', json: body });
      closeModal();
      toast('Seat assigned');
      viewLicence(licId);
    } catch(err) { toast(err.message, 'err'); }
  };
}

async function unassignSeat(licId, assignId) {
  if (!confirm('Remove this seat assignment?')) return;
  try {
    await api(`/licences/${licId}/assign/${assignId}`, { method: 'DELETE' });
    toast('Seat unassigned');
    viewLicence(licId);
  } catch(e) { toast(e.message, 'err'); }
}

async function deleteLicence(id) {
  if (!confirm('Delete this licence and all seat assignments? This cannot be undone.')) return;
  try {
    await api(`/licences/${id}`, { method: 'DELETE' });
    toast('Licence deleted');
    pageLicences();
  } catch(e) { toast(e.message, 'err'); }
}

// ── Activity Feed ─────────────────────────────────────────────────────────────

const _ACT_ICON = {
  checkout: { ic: 'arrowOut', color: '#3b82f6' },
  checkin:  { ic: 'arrowIn',  color: '#10b981' },
  create:   { ic: 'plus',     color: '#d4f034' },
  update:   { ic: 'edit',     color: '#6b7280' },
  delete:   { ic: 'trash',    color: '#ef4444' },
};
const _ACT_LABEL = {
  checkout: 'Checked out', checkin: 'Checked in',
  create: 'Created', update: 'Updated', delete: 'Deleted',
};

let _actOffset   = 0;
let _actFilter   = '';
let _actSearch   = '';
let _actDateFrom = '';
let _actDateTo   = '';
const _ACT_LIMIT = 50;

async function pageActivity() {
  _actOffset = 0;
  _actFilter = '';
  _actSearch = '';
  _actDateFrom = '';
  _actDateTo   = '';

  const page = document.getElementById('page');
  page.innerHTML = pageHeader('Activity Feed') + `
    <div class="toolbar" style="margin-bottom:16px">
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
        <select id="act-action-filter" onchange="_actApplyFilter()"
          style="padding:7px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);
                 background:var(--surface);color:var(--text);font-size:13.5px">
          <option value="">All actions</option>
          <option value="checkout">Check Out</option>
          <option value="checkin">Check In</option>
          <option value="create">Created</option>
          <option value="update">Updated</option>
          <option value="delete">Deleted</option>
        </select>
        <input id="act-search" type="search" placeholder="Filter by asset tag or name…"
          oninput="_actApplyFilter()"
          style="padding:7px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);
                 background:var(--surface);color:var(--text);font-size:13.5px;min-width:220px">
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text-muted)">
          From
          <input id="act-date-from" type="date" onchange="_actApplyFilter()"
            style="padding:6px 8px;border:1px solid var(--border);border-radius:var(--radius-sm);
                   background:var(--surface);color:var(--text);font-size:13px">
        </label>
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text-muted)">
          To
          <input id="act-date-to" type="date" onchange="_actApplyFilter()"
            style="padding:6px 8px;border:1px solid var(--border);border-radius:var(--radius-sm);
                   background:var(--surface);color:var(--text);font-size:13px">
        </label>
      </div>
    </div>
    <div id="act-feed">${loading()}</div>`;

  await _actLoad(true);
}

async function _actLoad(reset = false) {
  if (reset) _actOffset = 0;
  const feed = document.getElementById('act-feed');
  if (!feed) return;

  const qs = new URLSearchParams({ limit: _ACT_LIMIT, offset: _actOffset });
  if (_actFilter)   qs.set('action',    _actFilter);
  if (_actDateFrom) qs.set('date_from', _actDateFrom);
  if (_actDateTo)   qs.set('date_to',   _actDateTo);

  let data;
  try { data = await api('/assets/activity?' + qs); }
  catch(e) { feed.innerHTML = `<p style="color:var(--red)">${esc(e.message)}</p>`; return; }

  // client-side search filter on already-fetched items
  const term = _actSearch.toLowerCase();
  const items = term
    ? data.items.filter(i =>
        (i.asset_tag  || '').toLowerCase().includes(term) ||
        (i.asset_name || '').toLowerCase().includes(term))
    : data.items;

  if (reset) feed.innerHTML = '';

  if (!items.length && _actOffset === 0) {
    feed.innerHTML = `
      <div class="empty" style="padding:60px 0">
        ${icon('activity', 44)}
        <h3>No activity yet</h3>
        <p>Activity appears here when assets are checked out, checked in, or modified.</p>
      </div>`;
    return;
  }

  // Remove old Load More button before appending
  const oldMore = document.getElementById('act-load-more');
  if (oldMore) oldMore.remove();

  const frag = document.createDocumentFragment();
  const list = document.createElement('ul');
  list.className = 'timeline';
  list.style.cssText = 'list-style:none;padding:0;margin:0';

  items.forEach(item => {
    const cfg   = _ACT_ICON[item.action] || { ic: 'activity', color: '#6b7280' };
    const label = _ACT_LABEL[item.action] || item.action;
    const tagEl = item.asset_id
      ? `<b class="act-asset-link" style="cursor:pointer;color:var(--accent)"
           onclick="navigate('asset',${item.asset_id})">${esc(item.asset_tag)}</b>`
      : `<b style="text-decoration:line-through;color:var(--text-muted)">${esc(item.asset_tag)}</b>`;

    const tenantBadge = item.tenant_name
      ? `<span class="tag muted" style="font-size:11px;margin-left:6px">${esc(item.tenant_name)}</span>`
      : '';

    const noteTxt = item.note && item.action !== 'create' && item.action !== 'update' && item.action !== 'delete'
      ? `<div class="muted" style="font-size:12.5px;margin-top:2px">${esc(item.note)}</div>`
      : '';

    const li = document.createElement('li');
    li.style.cssText = 'display:flex;align-items:flex-start;gap:14px;padding:12px 0;border-bottom:1px solid var(--border)';
    li.innerHTML = `
      <div style="flex-shrink:0;width:34px;height:34px;border-radius:50%;
                  background:${cfg.color}18;display:flex;align-items:center;
                  justify-content:center;margin-top:1px">
        <span style="color:${cfg.color}">${icon(cfg.ic, 15)}</span>
      </div>
      <div style="flex:1;min-width:0">
        <div style="font-size:14px;line-height:1.5">
          ${tagEl}
          <span class="muted"> — ${label}</span>
          ${item.actor_name !== '—' ? `<span class="muted"> by ${esc(item.actor_name)}</span>` : ''}
          ${tenantBadge}
        </div>
        ${noteTxt}
      </div>
      <div class="muted" style="font-size:12px;flex-shrink:0;text-align:right;white-space:nowrap"
           title="${esc(item.timestamp || '')}">
        ${item.timestamp ? timeAgo(item.timestamp) : ''}
      </div>`;
    list.appendChild(li);
  });

  frag.appendChild(list);

  // Load More button if there may be more pages
  const hasMore = data.offset + _ACT_LIMIT < data.total;
  if (hasMore) {
    const moreBtn = document.createElement('div');
    moreBtn.id = 'act-load-more';
    moreBtn.style.cssText = 'text-align:center;padding:20px 0';
    moreBtn.innerHTML = `<button class="btn btn-ghost" onclick="_actLoadMore()">Load more</button>
      <div class="muted" style="font-size:12px;margin-top:6px">${data.total - data.offset - _ACT_LIMIT} more events</div>`;
    frag.appendChild(moreBtn);
  }

  feed.appendChild(frag);
}

function _actApplyFilter() {
  _actFilter   = document.getElementById('act-action-filter')?.value || '';
  _actSearch   = document.getElementById('act-search')?.value || '';
  _actDateFrom = document.getElementById('act-date-from')?.value || '';
  _actDateTo   = document.getElementById('act-date-to')?.value || '';
  _actOffset = 0;
  const feed = document.getElementById('act-feed');
  if (feed) feed.innerHTML = loading();
  _actLoad(true);
}

async function _actLoadMore() {
  _actOffset += _ACT_LIMIT;
  await _actLoad(false);
}
