'use strict';
/* Golden Set 검수 뷰어 — API 계약은 API.md 참고 */

const $ = s => document.querySelector(s);
const enc = encodeURIComponent;
const ERR = new Set(['미검출', '보정실패', '악화']);
const STATUSES = ['보정성공', '미검출', '보정실패', '악화', '일치', '제외'];
const RAW_KINDS = ['answer', 'draft', 'ao', 'ao_ui', 'harness', 'grade'];
const REVIEW = { done: '검수 완료', progress: '검수 중', '': '미검수' };

const esc = v => v == null ? '' : String(v).replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = v => v == null ? '–' : (v * 100).toFixed(1);
const store = (k, v) => { try { v === undefined ? (v = localStorage.getItem(k)) : localStorage.setItem(k, v); } catch { v = null; } return v; };

async function api(url, opt) {
  const res = await fetch(url, opt);
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { const b = await res.json(); msg += ' — ' + (b.detail || b.error || JSON.stringify(b)); } catch { /* 본문 없음 */ }
    throw new Error(msg);
  }
  return res;
}
const getJson = async url => (await api(url)).json();

let toastTimer;
function toast(msg, bad) {
  const t = $('#toast');
  t.textContent = msg; t.className = bad ? 'bad' : ''; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, bad ? 5000 : 1800);
}

/* ---------- 상태 ---------- */
const S = {
  docs: [], type: store('gv.type') || '',
  doc: null, edits: new Map(), adds: new Map(), checked: new Set(), status: '', dirty: false,
  filter: 'all', q: '', rows: [], sel: null, hover: null, after: null,
  view: store('gv.view') || 'processed', page: 1, zoom: 'fit', shown: '', fell: false,
};
const cellById = id => S.doc?.cells.find(c => c.id === id);
const gold = c => S.edits.has(c.id) ? S.edits.get(c.id).value : c.answer;
const isEdited = c => S.edits.has(c.id) || !!S.doc.review?.edited?.[c.id];
const docKey = d => d.folder + '/' + d.file;
const docHash = d => `#/${enc(d.folder)}/${enc(d.file)}`;
const docList = () => S.docs.filter(d => !S.type || d.folder === S.type);

const FILTERS = {
  all: ['전체', () => true],
  err: ['오류만', c => ERR.has(c.status)],
  fixed: ['보정됨', c => c.status === '보정성공'],
  todo: ['미검수', c => c.status !== '제외' && !S.checked.has(c.id)],
  edited: ['수정됨', c => isEdited(c)],
};

function markDirty() {
  S.dirty = true;
  $('#dirty').hidden = false; $('#saveBtn').disabled = false;
}

/* ---------- 라우팅 ---------- */
let quietHash = false;
function setHash(h) { if (location.hash !== h) { quietHash = true; location.hash = h; } }

async function route() {
  if (quietHash) { quietHash = false; return; }
  const [head, ...rest] = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  if (head === 'stats') return showStats();
  showPage('review');
  if (head === 'list') { setType(rest[0] || ''); return openPicker(); }
  if (head && rest.length) return openDoc(head, rest.join('/'));
  const d = S.doc || docList()[0];
  if (d) setHash(docHash(d)), openDoc(d.folder, d.file);
}

function showPage(name) {
  $('#review').hidden = name !== 'review';
  $('#stats').hidden = name !== 'stats';
  $('#tabReview').classList.toggle('on', name === 'review');
  $('#tabStats').classList.toggle('on', name === 'stats');
}

async function openDoc(folder, file) {
  if (S.doc && S.doc.folder === folder && S.doc.file === file) { renderAll(); return; }
  if (S.dirty && !confirm('저장하지 않은 수정이 있습니다. 저장하지 않고 이동할까요?')) {
    if (S.doc) setHash(docHash(S.doc));
    return;
  }
  let doc;
  try { doc = await getJson(`/api/doc/${enc(folder)}/${enc(file)}`); }
  catch (e) { toast('문서를 불러오지 못했습니다: ' + e.message, true); return; }
  setDoc(doc);
  S.page = 1; S.zoom = 'fit'; S.sel = null; S.hover = null;
  $('#scroller').scrollTop = 0;
  renderAll();
  if (S.after) { const errs = S.rows.filter(c => ERR.has(c.status)); const c = S.after === 'first' ? errs[0] : errs.at(-1); S.after = null; if (c) select(c.id); }
  await loadImage();
}

function setDoc(doc) {
  S.doc = doc;
  S.edits.clear(); S.adds.clear();
  S.checked = new Set(doc.review?.checked || []);
  S.status = doc.review?.status || '';
  S.dirty = false; $('#dirty').hidden = true; $('#saveBtn').disabled = true;
}

function goDoc(d) {
  if (!d) return;
  location.hash = docHash(d);
}
function stepDoc(delta) {
  const list = docList(), i = S.doc ? list.findIndex(d => docKey(d) === docKey(S.doc)) : -1;
  goDoc(list[i + delta]);
}

/* ---------- 문서 목록·필터 ---------- */
async function loadDocs() {
  try { S.docs = await getJson('/api/docs'); }
  catch (e) { toast('문서 목록을 불러오지 못했습니다: ' + e.message, true); return; }
  const types = [...new Set(S.docs.map(d => d.folder))];
  $('#typeSel').innerHTML = `<option value="">전체 문서 (${S.docs.length})</option>` + types.map(t =>
    `<option value="${esc(t)}">${esc(t)} (${S.docs.filter(d => d.folder === t).length})</option>`).join('');
  setType(types.includes(S.type) ? S.type : '');
  renderTop();
}

function setType(t) {
  S.type = t; store('gv.type', t);
  $('#typeSel').value = t;
  $('#xlsx').href = '/api/export.xlsx' + (t ? '?folder=' + enc(t) : '');
  renderTop(); if (!$('#picker').hidden) renderPicker();
}

function renderTop() {
  const list = docList(), i = S.doc ? list.findIndex(d => docKey(d) === docKey(S.doc)) : -1;
  $('#docName').textContent = S.doc ? S.doc.file : '문서 선택';
  $('#docPos').textContent = i >= 0 ? `${i + 1} / ${list.length}` : list.length ? `– / ${list.length}` : '';
  $('#prevDoc').disabled = i <= 0;
  $('#nextDoc').disabled = i < 0 || i >= list.length - 1;
}

let pickIdx = 0;
function openPicker() {
  const p = $('#picker'); p.hidden = false;
  renderPicker();
  $('#pickQ').focus(); $('#pickQ').select();
}
function pickerRows() {
  const q = $('#pickQ').value.trim().toLowerCase();
  return docList().filter(d => (!q || (d.file + ' ' + d.doc_type).toLowerCase().includes(q))
    && (!$('#pickErr').checked || d.errors > 0) && (!$('#pickTodo').checked || d.review !== 'done'));
}
function renderPicker() {
  const rows = pickerRows(), cur = S.doc && docKey(S.doc);
  if (pickIdx >= rows.length) pickIdx = Math.max(0, rows.length - 1);
  $('#pickList tbody').innerHTML = rows.map((d, i) => `<tr data-i="${i}" class="${i === pickIdx ? 'act' : ''} ${docKey(d) === cur ? 'cur' : ''}">
    <td class="file" title="${esc(d.file)}">${esc(d.file)}</td><td>${esc(d.doc_type)}</td>
    <td class="num ${d.errors ? 'errn' : 'muted'}">${d.errors}</td>
    <td><span class="rv rv-${d.review || 'none'}">${REVIEW[d.review || '']}</span></td>
    <td class="num">${pct(d.h_acc)}</td></tr>`).join('') || '<tr><td colspan="5" class="empty">조건에 맞는 문서가 없습니다</td></tr>';
  $('#pickList .act')?.scrollIntoView({ block: 'nearest' });
}
function pickOpen(i) {
  const d = pickerRows()[i];
  if (d) { $('#picker').hidden = true; goDoc(d); }
}

/* ---------- 오른쪽: 문서 요약·필터·표 ---------- */
function renderAll() {
  if (!S.doc) return;
  renderTop(); renderHead(); renderChips(); renderGrid(); renderEvidence(); renderImgBar();
}

function renderHead() {
  const d = S.doc, s = d.summary || {}, counts = {};
  d.cells.forEach(c => { counts[c.status] = (counts[c.status] || 0) + 1; });
  const delta = (s.하네스정확도 ?? 0) - (s.AO정확도 ?? 0);
  const unc = d.uncertain?.length ? `<span class="chip warn" title="${esc(d.uncertain.join('\n'))}">판독 불확실 ${d.uncertain.length}</span>` : '';
  $('#docHead').innerHTML = `
    <div class="title"><b>${esc(d.file)}</b><span class="muted">${esc(d.doc_type)}</span>
      ${d.harness_doc?.tier ? `<span class="chip">하네스 ${esc(d.harness_doc.tier)}</span>` : ''}
      <span class="spacer"></span>
      <button id="doneBtn" class="rvbtn rv-${S.status || 'none'}" title="문서 검수 완료 표시 (c)">${S.status === 'done' ? '✓ 검수 완료' : REVIEW[S.status]}</button>
      <button id="rawBtn" title="원본 JSON (r)">JSON</button></div>
    <div class="meta">
      <span class="acc num" title="채점칸 ${s.채점칸 ?? '–'}">AO ${pct(s.AO정확도)} <span class="arrow">→</span> H <b>${pct(s.하네스정확도)}</b>
        <span class="delta ${delta > 0 ? 'up' : delta < 0 ? 'down' : ''}">${delta > 0 ? '+' : ''}${(delta * 100).toFixed(1)}</span></span>
      ${STATUSES.filter(k => counts[k]).map(k => `<span class="chip st" data-st="${k}">${k} <b class="num">${counts[k]}</b></span>`).join('')}
      ${unc}
    </div>
    ${d.notes ? `<div class="notes" title="${esc(d.notes)}">메모: ${esc(d.notes)}</div>` : ''}`;
}

function renderChips() {
  $('#chips').innerHTML = Object.entries(FILTERS).map(([k, [name, fn]]) =>
    `<button data-filter="${k}" class="${S.filter === k ? 'on' : ''}">${name} <span class="num">${S.doc.cells.filter(fn).length}</span></button>`).join('');
}

const matchQ = c => !S.q || [c.key, c.label, c.container, gold(c), c.ao, c.harness].some(v => v != null && String(v).toLowerCase().includes(S.q));

function renderGrid() {
  S.rows = S.doc.cells.filter(c => FILTERS[S.filter][1](c) && matchQ(c));
  let html = '', grp = null, row = null;
  for (const c of S.rows) {
    const g = c.area + '|' + c.container;
    if (g !== grp) { grp = g; row = null; html += `<tr class="grp"><th colspan="6">${esc(c.container || c.area)}<small>${esc(c.area)}</small></th></tr>`; }
    if (c.area === '표' && c.row !== row) { row = c.row; html += rowHead(c); }
    html += cellRow(c);
  }
  $('#rows').innerHTML = html || '<tr><td colspan="6" class="empty">조건에 맞는 칸이 없습니다</td></tr>';
  renderRuler(); drawBoxes();
}

function rowHead(c) {
  const extra = c.row.startsWith('결과');
  const key = c.container + '|' + c.row, add = S.adds.get(key);
  const act = !extra ? '' : add
    ? `<span class="addon">행 추가 예정 (${add.by === 'ao' ? 'AO' : 'H'})</span><button data-add="" data-key="${esc(key)}" title="취소">×</button>`
    : `<button data-add="ao" data-key="${esc(key)}">행 추가 AO</button><button data-add="harness" data-key="${esc(key)}">행 추가 H</button>`;
  return `<tr class="rowh${extra ? ' extra' : ''}"><td colspan="6"><span class="rn">${esc(c.row)}</span><span class="lbl">${esc(c.label)}</span>${act}</td></tr>`;
}

const same = (a, b) => (a ?? null) === (b ?? null) || (a != null && b != null && String(a) === String(b));
const val = v => v === null || v === undefined ? '<span class="nil" title="칸 없음">∅</span>' : v === '' ? '<span class="nil">빈 값</span>' : esc(v);

function cellRow(c) {
  const g = gold(c), chk = S.checked.has(c.id), ed = isEdited(c), pend = S.edits.has(c.id);
  const low = c.confidence != null && c.confidence < 0.8 && c.ao != null && c.ao !== '' && c.status !== '제외';
  const changed = String(c.ao ?? '') !== String(c.harness ?? '');
  const dis = c.editable ? '' : ' disabled';
  return `<tr class="c${c.id === S.sel ? ' sel' : ''}${chk ? ' chk' : ''}" data-id="${esc(c.id)}" data-st="${c.status}">
    <td class="f" title="${esc(c.path || c.key)}">${esc(c.key)}${c.kind ? `<i class="kind">${c.kind}</i>` : ''}${c.uncertain ? '<i class="unc" title="판독 불확실">?</i>' : ''}</td>
    <td class="g${pend ? ' pend' : ''}">${val(g)}${ed ? `<i class="ed" title="${pend ? '저장 전 수정' : '수정됨'}">${pend ? '●' : '✎'}</i>` : ''}</td>
    <td class="a">${diffVal(c.ao, g, c)}${low ? `<i class="lowc" title="AO 신뢰도 ${c.confidence.toFixed(2)}">${Math.round(c.confidence * 100)}</i>` : ''}</td>
    <td class="h">${changed ? '<i class="chg" title="하네스가 AO 값을 바꿈">Δ</i>' : ''}${diffVal(c.harness, g, c)}</td>
    <td class="s"><span class="st">${c.status}</span></td>
    <td class="x"><button data-act="ao" title="AO 채택 (1)"${dis}>A</button><button data-act="harness" title="H 채택 (2)"${dis}>H</button><button data-act="null" title="칸 없음 (0)"${dis}>∅</button><button data-act="check" class="ck" title="검수 확인 (Space)" aria-pressed="${chk}">✓</button></td>
  </tr>`;
}

/* Golden과 다른 글자를 표시: 최장 공통 부분열 밖의 글자에 mark */
function diffVal(v, ref, c) {
  if (v == null || v === '' || ref == null || c.status === '제외' || same(v, ref)) return val(v);
  const a = String(v), b = String(ref), n = a.length, m = b.length;
  if (n * m > 40000) return `<mark>${esc(a)}</mark>`;
  const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    L[i][j] = a[i] === b[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  if (L[0][0] * 2 < n) return `<mark>${esc(a)}</mark>`;  /* 절반 넘게 다르면 통째로 */
  const keep = new Array(n).fill(false);
  for (let i = 0, j = 0; i < n && j < m;) {
    if (a[i] === b[j]) { keep[i++] = true; j++; } else if (L[i + 1][j] >= L[i][j + 1]) i++; else j++;
  }
  let html = '', run = '', k0 = keep[0];
  const flush = () => { if (run) html += k0 ? esc(run) : `<mark>${esc(run)}</mark>`; run = ''; };
  keep.forEach((k, i) => { if (k !== k0) { flush(); k0 = k; } run += a[i]; });
  flush();
  return html + (L[0][0] === n ? '<i class="short" title="Golden보다 글자가 빠짐">…</i>' : '');
}

function refreshRow(c) {
  const tr = $(`#rows tr.c[data-id="${CSS.escape(c.id)}"]`);
  if (tr) tr.outerHTML = cellRow(c);
  renderChips();
}

function renderRuler() {
  const sc = $('#scroller'), total = sc.scrollHeight || 1, h = $('#ruler').clientHeight;
  $('#ruler').innerHTML = [...$('#rows').querySelectorAll('tr.c')].filter(tr => ERR.has(tr.dataset.st) || tr.dataset.st === '보정성공')
    .map(tr => `<i data-id="${esc(tr.dataset.id)}" data-st="${tr.dataset.st}" style="top:${Math.min(h - 3, tr.offsetTop / total * h)}px"></i>`).join('');
}

/* ---------- 근거 패널 ---------- */
const SEV = { fail: 0, warn: 1 };
function renderEvidence() {
  const id = S.hover || S.sel, c = id && cellById(id), box = $('#evidence');
  if (!c) { box.innerHTML = '<p class="empty">칸에 마우스를 올리면 근거가 보입니다. 누르면 고정됩니다.</p>'; return; }
  const e = c.evidence || {}, rules = [...(e.rule || [])].sort((x, y) => (SEV[x.result] ?? 2) - (SEV[y.result] ?? 2));
  const hot = rules.filter(r => r.result in SEV), rest = rules.filter(r => !(r.result in SEV));
  const rule = r => `<li class="r-${esc(r.result)}"><b>${esc(r.result)}</b> <code>${esc(r.rule_id)}</code> <span class="muted">${esc(r.category)}${r.severity ? ' ' + esc(r.severity) : ''}</span> ${esc(r.detail)}</li>`;
  const kv = (k, v) => v == null || v === '' ? '' : `<dt>${k}</dt><dd>${v}</dd>`;
  const rr = e.reread && (e.reread.status || e.reread.value)
    ? `${esc(e.reread.status)} ${e.reread.value != null ? `“${esc(e.reread.value)}”` : ''} <span class="muted">${esc(e.reread.engine_id)}</span> ${esc(e.reread.detail)}` : '';
  box.innerHTML = `
    <div class="ev-head"><span class="st" data-st="${c.status}">${c.status}</span>${c.kind ? `<i class="kind">${c.kind}</i>` : ''}
      <b>${esc(c.container)}${c.row ? ' ' + esc(c.row) + '행' : ''} / ${esc(c.key)}</b>
      <span class="muted path">${esc(c.path)}</span><span class="spacer"></span>
      ${id === S.sel && !S.hover ? '<span class="pin">고정</span>' : ''}</div>
    <div class="ev-body">
      <dl class="vals">
        <dt>Golden</dt><dd class="g">${val(gold(c))}</dd>
        <dt>AO</dt><dd>${diffVal(c.ao, gold(c), c)} <span class="muted">${esc(c.ao_verdict)}${c.confidence != null ? ' 신뢰도 ' + c.confidence.toFixed(2) : ''}</span></dd>
        <dt>Harness</dt><dd>${diffVal(c.harness, gold(c), c)} <span class="muted">${esc(c.h_verdict)}</span></dd>
      </dl>
      <dl class="facts">
        ${kv('tier', esc(e.tier || c.tier))}
        ${kv('보정 근거', esc(e.correction_basis))}
        ${kv('결정 규칙', esc(e.decision_rule_no))}
        ${e.ao_value != null || e.final_value != null ? kv('값 변화', `${val(e.ao_value)} <span class="arrow">→</span> ${val(e.final_value)}`) : ''}
        ${kv('재판독', rr)}
        ${kv('마스터', esc(e.master?.status))}
        ${kv('출처', esc(c.source))}
        ${kv('효과', esc(c.effect))}
      </dl>
      ${rules.length ? `<ul class="rules">${hot.map(rule).join('')}</ul>${rest.length ? `<details><summary>통과·해당 없음 ${rest.length}건</summary><ul class="rules">${rest.map(rule).join('')}</ul></details>` : ''}`
        : c.evidence ? '' : '<p class="muted">하네스 근거 없음</p>'}
    </div>`;
}

/* ---------- 선택·수정 ---------- */
function select(id, { scroll = true } = {}) {
  S.sel = id;
  $('#rows tr.sel')?.classList.remove('sel');
  const tr = id && $(`#rows tr.c[data-id="${CSS.escape(id)}"]`);
  if (tr) { tr.classList.add('sel'); if (scroll) tr.scrollIntoView({ block: 'nearest' }); }
  renderEvidence(); focusBox(id);
}

function move(delta) {
  if (!S.rows.length) return;
  const i = S.rows.findIndex(c => c.id === S.sel);
  select(S.rows[i < 0 ? 0 : Math.max(0, Math.min(S.rows.length - 1, i + delta))].id);
}

function nextError(delta) {
  const i = S.rows.findIndex(c => c.id === S.sel);
  const order = delta > 0 ? S.rows.slice(i + 1) : S.rows.slice(0, Math.max(i, 0)).reverse();
  const hit = order.find(c => ERR.has(c.status));
  if (hit) return select(hit.id);
  const list = docList(), di = list.findIndex(d => docKey(d) === docKey(S.doc));
  for (let k = 1; k < list.length; k++) {
    const d = list[(di + delta * k + list.length * k) % list.length];
    if (d.errors > 0 && docKey(d) !== docKey(S.doc)) { S.after = delta > 0 ? 'first' : 'last'; toast(`다음 오류 문서: ${d.file}`); return goDoc(d); }
  }
  const errs = S.rows.filter(c => ERR.has(c.status));
  if (errs.length) select((delta > 0 ? errs[0] : errs.at(-1)).id); else toast('남은 오류가 없습니다');
}

function setGold(c, value, by) {
  if (!c) return;
  if (!c.editable) return toast('정답지에 없는 칸입니다. 행 추가를 사용하세요', true);
  if (same(value, c.answer) && !S.doc.review?.edited?.[c.id]) S.edits.delete(c.id);
  else S.edits.set(c.id, { id: c.id, value, by });
  S.checked.add(c.id); markDirty(); refreshRow(c); renderEvidence();
}

function act(c, what) {
  if (!c) return;
  if (what === 'ao') setGold(c, c.ao, 'ao');
  else if (what === 'harness') setGold(c, c.harness, 'harness');
  else if (what === 'null') setGold(c, null, 'manual');
  else if (what === 'undo') { if (S.edits.delete(c.id)) { markDirty(); refreshRow(c); renderEvidence(); } }
  else if (what === 'check') { S.checked.has(c.id) ? S.checked.delete(c.id) : S.checked.add(c.id); markDirty(); refreshRow(c); }
}

function editCell(c) {
  if (!c) return;
  if (!c.editable) return toast('정답지에 없는 칸입니다. 행 추가를 사용하세요', true);
  const td = $(`#rows tr.c[data-id="${CSS.escape(c.id)}"] td.g`);
  if (!td) return;
  const cur = gold(c);
  td.innerHTML = `<input class="edit" value="${esc(cur ?? '')}">`;
  const inp = td.firstChild; inp.focus(); inp.select();
  let done = false;
  const finish = ok => {
    if (done) return; done = true;
    if (ok && inp.value !== String(cur ?? '')) setGold(c, inp.value, 'manual'); else refreshRow(c);
    select(c.id, { scroll: false });
  };
  inp.addEventListener('keydown', e => {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    else if (e.key === 'Escape') finish(false);
  });
  inp.addEventListener('blur', () => finish(true));
}

async function save() {
  if (!S.doc || !S.dirty) return;
  const body = {
    edits: [...S.edits.values()],
    add_rows: [...S.adds.values()],
    review: { status: S.status || 'progress', checked: [...S.checked] },
  };
  $('#saveBtn').disabled = true;
  try {
    const res = await api(`/api/doc/${enc(S.doc.folder)}/${enc(S.doc.file)}`,
      { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const sel = S.sel;
    setDoc(await res.json());
    renderAll(); if (sel) select(sel, { scroll: false });
    toast('저장했습니다');
    loadDocs();
  } catch (e) { $('#saveBtn').disabled = false; toast('저장하지 못했습니다: ' + e.message, true); }
}

/* ---------- 이미지 ---------- */
const img = $('#img'), stage = $('#stage'), canvas = $('#canvas'), boxes = $('#boxes');
const imgCache = new Map();
let imgToken = 0;

async function loadImage() {
  if (!S.doc) return;
  const token = ++imgToken, view = S.doc.processed ? S.view : 'original';
  const url = `/api/image/${enc(S.doc.folder)}/${enc(S.doc.file)}?view=${view}&page=${S.page}`;
  let hit = imgCache.get(url);
  if (!hit) {
    try {
      const res = await api(url);
      hit = { src: URL.createObjectURL(await res.blob()), fell: res.headers.get('X-Image-Fell-Back') === 'true', view: res.headers.get('X-Image-View') || view };
    } catch (e) { if (token === imgToken) toast('이미지를 불러오지 못했습니다: ' + e.message, true); return; }
    imgCache.set(url, hit);
    if (imgCache.size > 30) { const [k, v] = imgCache.entries().next().value; URL.revokeObjectURL(v.src); imgCache.delete(k); }
  }
  if (token !== imgToken) return;
  img.src = hit.src;
  await img.decode().catch(() => {});
  if (token !== imgToken) return;
  S.shown = hit.view; S.fell = hit.fell;
  applyZoom(); drawBoxes(); renderImgBar(); focusBox(S.hover || S.sel);
}

function renderImgBar() {
  const d = S.doc; if (!d) return;
  document.querySelectorAll('#viewSeg button').forEach(b => {
    b.classList.toggle('on', b.dataset.view === (d.processed ? S.view : 'original'));
    b.disabled = !d.processed;
    b.title = d.processed ? '원본·전처리 전환 (o)' : '전처리 이미지 없음';
  });
  $('#fell').hidden = !S.fell;
  $('#pageNo').textContent = `${S.page} / ${d.pages || 1}`;
  $('#pageNav').hidden = (d.pages || 1) < 2;
  $('#approx').hidden = S.shown !== 'original' || !d.cells.some(c => c.bbox?.length);
}

const scale = () => S.zoom === 'fit' ? Math.max(0.05, (stage.clientWidth - 24) / (img.naturalWidth || 1)) : S.zoom;
function applyZoom() {
  if (!img.naturalWidth) return;
  const z = scale();
  canvas.style.width = Math.round(img.naturalWidth * z) + 'px';
  $('#zoomPct').textContent = Math.round(z * 100) + '%';
}
function zoomAt(z, cx = stage.clientWidth / 2, cy = stage.clientHeight / 2) {
  const old = scale();
  const px = (stage.scrollLeft + cx - canvas.offsetLeft) / old, py = (stage.scrollTop + cy - canvas.offsetTop) / old;
  S.zoom = Math.max(0.05, Math.min(8, z));
  applyZoom();
  const now = scale();
  stage.scrollLeft = px * now + canvas.offsetLeft - cx;
  stage.scrollTop = py * now + canvas.offsetTop - cy;
}
function setPage(p) {
  const n = S.doc?.pages || 1;
  if (p < 1 || p > n || p === S.page) return false;
  S.page = p; loadImage(); return true;
}

function drawBoxes() {
  if (!S.doc) return;
  const all = $('#boxAll').checked, shown = new Set(S.rows.map(c => c.id));
  let h = '';
  for (const c of S.doc.cells) for (const b of c.bbox || []) {
    if ((b.page || 1) !== S.page) continue;
    const faint = shown.has(c.id) && (all || ERR.has(c.status));
    const [x, y, w, hh] = b.box;
    h += `<div class="bx${faint ? '' : ' hid'}" data-id="${esc(c.id)}" data-st="${c.status}" style="left:${x * 100}%;top:${y * 100}%;width:${w * 100}%;height:${hh * 100}%"></div>`;
  }
  boxes.innerHTML = h; markBoxes();
}
function markBoxes() {
  boxes.querySelectorAll('.bx').forEach(el => {
    el.classList.toggle('on', el.dataset.id === S.hover || el.dataset.id === S.sel);
    el.classList.toggle('hov', el.dataset.id === S.hover);
  });
}
function focusBox(id) {
  markBoxes();
  const c = id && cellById(id), b = c?.bbox?.[0];
  if (!b) return;
  if ((b.page || 1) !== S.page) { setPage(b.page || 1); return; }  /* 로드 후 다시 호출된다 */
  if (!img.naturalWidth) return;
  const W = canvas.clientWidth, H = canvas.clientHeight;
  const bx = canvas.offsetLeft + b.box[0] * W, by = canvas.offsetTop + b.box[1] * H, bw = b.box[2] * W, bh = b.box[3] * H;
  const pad = 40, vx = stage.scrollLeft, vy = stage.scrollTop, vw = stage.clientWidth, vh = stage.clientHeight;
  if (bx < vx + pad || bx + bw > vx + vw - pad) stage.scrollTo({ left: bx + bw / 2 - vw / 2, behavior: 'smooth' });
  if (by < vy + pad || by + bh > vy + vh - pad) stage.scrollTo({ top: by + bh / 2 - vh / 2, behavior: 'smooth' });
}

/* 끌어서 이동, 휠 확대, 박스 클릭 */
let drag = null;
stage.addEventListener('mousedown', e => {
  if (e.button !== 0) return;
  drag = { x: e.clientX, y: e.clientY, l: stage.scrollLeft, t: stage.scrollTop, moved: false };
  stage.classList.add('grab'); e.preventDefault();
});
window.addEventListener('mousemove', e => {
  if (!drag) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
  stage.scrollLeft = drag.l - dx; stage.scrollTop = drag.t - dy;
});
window.addEventListener('mouseup', e => {
  if (!drag) return;
  const bx = !drag.moved && e.target.closest?.('.bx');
  drag = null; stage.classList.remove('grab');
  if (bx) { if (!S.rows.some(c => c.id === bx.dataset.id)) { S.filter = 'all'; S.q = ''; $('#q').value = ''; renderChips(); renderGrid(); } select(bx.dataset.id); }
});
stage.addEventListener('wheel', e => {
  e.preventDefault();
  const r = stage.getBoundingClientRect();
  zoomAt(scale() * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX - r.left, e.clientY - r.top);
}, { passive: false });
stage.addEventListener('mouseover', e => { const bx = e.target.closest('.bx'); if (bx) bx.title = cellById(bx.dataset.id)?.key || ''; });

document.querySelectorAll('[data-zoom]').forEach(b => b.addEventListener('click', () => {
  const z = b.dataset.zoom;
  if (z === 'fit') { S.zoom = 'fit'; applyZoom(); } else zoomAt(z === 'in' ? scale() * 1.25 : z === 'out' ? scale() / 1.25 : 1);
}));
document.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => setView(b.dataset.view)));
document.querySelectorAll('[data-page]').forEach(b => b.addEventListener('click', () => setPage(S.page + Number(b.dataset.page))));
$('#boxAll').addEventListener('change', drawBoxes);
window.addEventListener('resize', () => { if (S.zoom === 'fit') applyZoom(); renderRuler(); });

function setView(v) {
  if (!S.doc?.processed) return toast('전처리 이미지 없음');
  S.view = v; store('gv.view', v); loadImage();
}

/* ---------- 원본 JSON ---------- */
let rawKind = 'harness', rawText = '';
$('#rawTabs').innerHTML = RAW_KINDS.map(k => `<button data-raw="${k}">${k}</button>`).join('');

function colorJson(s) {
  const re = /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g;
  let out = '', last = 0, m;
  while ((m = re.exec(s))) {
    out += esc(s.slice(last, m.index));
    out += m[1] ? `<span class="${m[2] ? 'jk' : 'js'}">${esc(m[1])}</span>${m[2] || ''}` : `<span class="${m[3] ? 'jb' : 'jn'}">${m[0]}</span>`;
    last = re.lastIndex;
  }
  return out + esc(s.slice(last));
}

async function openRaw(kind = rawKind) {
  if (!S.doc) return;
  rawKind = kind;
  $('#raw').hidden = false;
  document.querySelectorAll('#rawTabs button').forEach(b => b.classList.toggle('on', b.dataset.raw === kind));
  const body = $('#rawBody'); body.textContent = '불러오는 중…'; $('#rawHits').textContent = '';
  try {
    rawText = JSON.stringify(await getJson(`/api/raw/${enc(S.doc.folder)}/${enc(S.doc.file)}/${kind}`), null, 2);
    body.innerHTML = rawText.length < 2e6 ? colorJson(rawText) : esc(rawText);
    body.scrollTop = 0;
    if ($('#rawQ').value) rawFind(true);
  } catch (e) { rawText = ''; body.textContent = e.message.startsWith('404') ? `${kind} 파일이 없습니다` : e.message; }
}

let rawHit = -1;
function rawFind(reset) {
  const q = $('#rawQ').value, body = $('#rawBody');
  if (!CSS.highlights) { $('#rawHits').textContent = ''; return; }
  CSS.highlights.delete('raw'); CSS.highlights.delete('rawcur');
  if (!q) { $('#rawHits').textContent = ''; return; }
  const ranges = [], walk = document.createTreeWalker(body, NodeFilter.SHOW_TEXT), ql = q.toLowerCase();
  for (let n; (n = walk.nextNode());) {
    const t = n.data.toLowerCase();
    for (let i = t.indexOf(ql); i >= 0 && ranges.length < 5000; i = t.indexOf(ql, i + ql.length)) {
      const r = new Range(); r.setStart(n, i); r.setEnd(n, i + ql.length); ranges.push(r);
    }
  }
  $('#rawHits').textContent = ranges.length ? `${ranges.length}건` : '없음';
  if (!ranges.length) return;
  rawHit = reset ? 0 : (rawHit + 1) % ranges.length;
  CSS.highlights.set('raw', new Highlight(...ranges));
  CSS.highlights.set('rawcur', new Highlight(ranges[rawHit]));
  $('#rawHits').textContent = `${rawHit + 1} / ${ranges.length}`;
  const rr = ranges[rawHit].getBoundingClientRect(), br = body.getBoundingClientRect();
  body.scrollTop += rr.top - br.top - br.height / 2;
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); }
  catch {
    const ta = Object.assign(document.createElement('textarea'), { value: text });
    document.body.append(ta); ta.select(); document.execCommand('copy'); ta.remove();
  }
  toast('복사했습니다');
}

$('#rawTabs').addEventListener('click', e => { const b = e.target.closest('[data-raw]'); if (b) openRaw(b.dataset.raw); });
$('#rawClose').addEventListener('click', () => { $('#raw').hidden = true; });
$('#rawCopy').addEventListener('click', () => rawText && copyText(rawText));
$('#rawQ').addEventListener('keydown', e => { if (e.key === 'Enter') rawFind(false); });
$('#rawQ').addEventListener('input', () => rawFind(true));

/* ---------- 통계 ---------- */
/* [머리글, 응답 키, 표시 방식] */
const STAT_COLS = [
  ['문서', '문서수'], ['채점칸', '채점칸'], ['AO정확도', 'AO정확도', 'acc'], ['하네스정확도', '하네스정확도', 'acc'], ['Δ', '', 'delta'],
  ['보정성공', '보정성공'], ['보정실패', '보정실패'], ['악화', '악화'], ['미검출', '미검출'],
  ['누락', '누락'], ['오탐', '오탐'], ['하네스 수정 칸', '하네스수정칸'], ['검수완료', '검수완료문서'],
];

async function showStats() {
  showPage('stats');
  const box = $('#stats');
  box.innerHTML = '<p class="empty">집계 중…</p>';
  let st;
  try { st = await getJson('/api/stats'); } catch (e) { box.innerHTML = `<p class="empty">통계를 불러오지 못했습니다: ${esc(e.message)}</p>`; return; }
  const { 전체: total, ...types } = st;
  const cell = (r, [name, key, kind]) => {
    if (kind === 'delta') { const d = (r.하네스정확도 ?? 0) - (r.AO정확도 ?? 0); return `<td class="num delta ${d > 0 ? 'up' : d < 0 ? 'down' : ''}">${d > 0 ? '+' : ''}${(d * 100).toFixed(1)}</td>`; }
    const v = r[key];
    if (kind === 'acc') return `<td class="num acc"><span class="meter"><i style="width:${(v ?? 0) * 100}%"></i></span>${pct(v)}</td>`;
    return `<td class="num ${v ? 'col-' + esc(name) : 'muted'}">${v ?? '–'}</td>`;
  };
  const tr = (t, r) => `<tr${t ? ` data-type="${esc(t)}"` : ''}><th>${esc(t || '전체')}</th>${STAT_COLS.map(c => cell(r, c)).join('')}</tr>`;
  box.innerHTML = `<div class="stats-wrap"><h1>문서 종류별 결과</h1>
    <p class="muted">종류를 누르면 해당 문서 목록이 열립니다. 정확도는 채점칸 기준입니다.</p>
    <table class="stat"><thead><tr><th>문서 종류</th>${STAT_COLS.map(([n]) => `<th class="num">${n}</th>`).join('')}</tr></thead>
    <tbody>${Object.entries(types).map(([t, r]) => tr(t, r)).join('')}</tbody>${total ? `<tfoot>${tr('', total)}</tfoot>` : ''}</table></div>`;
}
$('#stats').addEventListener('click', e => { const t = e.target.closest('tr[data-type]'); if (t) location.hash = '#/list/' + enc(t.dataset.type); });

/* ---------- 이벤트 ---------- */
const rowsEl = $('#rows');
let hoverTimer;
rowsEl.addEventListener('mouseover', e => {
  const tr = e.target.closest('tr.c');
  if (!tr || tr.dataset.id === S.hover) return;
  S.hover = tr.dataset.id; renderEvidence(); markBoxes();
  clearTimeout(hoverTimer); hoverTimer = setTimeout(() => focusBox(S.hover), 120);
});
$('#tableWrap').addEventListener('mouseleave', () => { clearTimeout(hoverTimer); S.hover = null; renderEvidence(); markBoxes(); });
rowsEl.addEventListener('click', e => {
  const add = e.target.closest('[data-add]');
  if (add) {
    const [container, row] = add.dataset.key.split('|');
    add.dataset.add ? S.adds.set(add.dataset.key, { container, row, by: add.dataset.add }) : S.adds.delete(add.dataset.key);
    markDirty(); renderGrid(); return;
  }
  const tr = e.target.closest('tr.c'); if (!tr) return;
  const b = e.target.closest('button[data-act]');
  if (b) { b.blur(); act(cellById(tr.dataset.id), b.dataset.act); }
  select(tr.dataset.id, { scroll: false });
});
rowsEl.addEventListener('dblclick', e => { const tr = e.target.closest('tr.c'); if (tr && !e.target.closest('button')) editCell(cellById(tr.dataset.id)); });
$('#ruler').addEventListener('click', e => { const i = e.target.closest('i[data-id]'); if (i) select(i.dataset.id); });
$('#chips').addEventListener('click', e => { const b = e.target.closest('[data-filter]'); if (b) setFilter(b.dataset.filter); });
$('#docHead').addEventListener('click', e => {
  if (e.target.closest('#doneBtn')) toggleDone();
  else if (e.target.closest('#rawBtn')) openRaw();
  else { const st = e.target.closest('.chip.st'); if (st) setFilter(ERR.has(st.dataset.st) ? 'err' : st.dataset.st === '보정성공' ? 'fixed' : 'all'); }
});
$('#q').addEventListener('input', e => { S.q = e.target.value.trim().toLowerCase(); renderGrid(); });
$('#q').addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === 'Escape') { e.target.blur(); if (S.rows[0] && e.key === 'Enter') select(S.rows[0].id); } });
$('#typeSel').addEventListener('change', e => setType(e.target.value));
$('#pickBtn').addEventListener('click', openPicker);
$('#prevDoc').addEventListener('click', () => stepDoc(-1));
$('#nextDoc').addEventListener('click', () => stepDoc(1));
$('#saveBtn').addEventListener('click', save);
$('#helpBtn').addEventListener('click', () => $('#help').showModal());
['#pickQ', '#pickErr', '#pickTodo'].forEach(s => $(s).addEventListener('input', () => { pickIdx = 0; renderPicker(); }));
$('#pickQ').addEventListener('keydown', e => {
  const n = pickerRows().length;
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); pickIdx = Math.max(0, Math.min(n - 1, pickIdx + (e.key === 'ArrowDown' ? 1 : -1))); renderPicker(); }
  else if (e.key === 'Enter') pickOpen(pickIdx);
});
$('#pickList').addEventListener('click', e => { const tr = e.target.closest('tr[data-i]'); if (tr) pickOpen(Number(tr.dataset.i)); });
document.addEventListener('mousedown', e => { if (!$('#picker').hidden && !e.target.closest('#picker, #pickBtn')) $('#picker').hidden = true; });

function setFilter(f) { S.filter = f; renderChips(); renderGrid(); if (S.sel && S.rows.some(c => c.id === S.sel)) select(S.sel); }
function toggleDone() { if (!S.doc) return; S.status = S.status === 'done' ? 'progress' : 'done'; markDirty(); renderHead(); }

/* 가운데 경계 끌기 */
const setLeft = w => document.documentElement.style.setProperty('--left', w + 'px');
if (store('gv.left')) setLeft(store('gv.left'));
$('#divider').addEventListener('mousedown', e => {
  e.preventDefault();
  const move = ev => setLeft(Math.max(280, Math.min(window.innerWidth - 480, ev.clientX)));
  const up = ev => {
    window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up);
    store('gv.left', Math.max(280, Math.min(window.innerWidth - 480, ev.clientX)));
    if (S.zoom === 'fit') applyZoom();
    renderRuler();
  };
  window.addEventListener('mousemove', move); window.addEventListener('mouseup', up);
});

const KEYS = {
  j: () => move(1), ArrowDown: () => move(1), k: () => move(-1), ArrowUp: () => move(-1),
  n: () => nextError(1), p: () => nextError(-1),
  1: () => act(cellById(S.sel), 'ao'), 2: () => act(cellById(S.sel), 'harness'), 0: () => act(cellById(S.sel), 'null'),
  u: () => act(cellById(S.sel), 'undo'), ' ': () => act(cellById(S.sel), 'check'),
  e: () => editCell(cellById(S.sel)), Enter: () => editCell(cellById(S.sel)),
  s: save, c: toggleDone, '[': () => stepDoc(-1), ']': () => stepDoc(1),
  d: openPicker, '/': () => $('#q').focus(),
  o: () => setView(S.view === 'processed' ? 'original' : 'processed'),
  f: () => { S.zoom = 'fit'; applyZoom(); }, b: () => { $('#boxAll').checked = !$('#boxAll').checked; drawBoxes(); },
  r: () => ($('#raw').hidden ? openRaw() : ($('#raw').hidden = true)), '?': () => $('#help').showModal(),
};
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); save(); return; }
  if (e.key === 'Escape') {
    if (!$('#picker').hidden) $('#picker').hidden = true;
    else if (!$('#raw').hidden) $('#raw').hidden = true;
    else if (S.sel) { S.sel = null; $('#rows tr.sel')?.classList.remove('sel'); renderEvidence(); markBoxes(); }
    return;
  }
  if (e.ctrlKey || e.metaKey || e.altKey || e.target.closest('input, textarea, select, dialog')) return;
  if (!$('#stats').hidden && !'[]?d'.includes(e.key)) return;
  const fn = KEYS[e.key];
  if (fn) { e.preventDefault(); fn(); }
});
window.addEventListener('beforeunload', e => { if (S.dirty) { e.preventDefault(); e.returnValue = ''; } });
window.addEventListener('hashchange', route);

loadDocs().then(route);
