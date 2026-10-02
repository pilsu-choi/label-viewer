import { el, clear, mount, debounce, toast, statusLabel, icon, menuButton, josa, isMismatch, hasSourceValue, entryState } from './util.js';
import { api } from './api.js';
import { openGoldenHistory, showGoldenConflictDialog } from './goldenHistory.js';
import { cellDisplay } from './reconstruct.js';

const DTYPES = ['string', 'int', 'float', 'number', 'date', 'bool'];

let tooltipEl = null;
function showTip(x, y, entry) {
  hideTip();
  if (!entry) return;
  tooltipEl = el('div', { class: 'tooltip', style: `left:${Math.min(x + 12, window.innerWidth - 300)}px;top:${Math.max(8, y - 68)}px` }, [
    el('div', {}, [el('b', {}, 'AO'), entry.ao === '' || entry.ao == null ? '—' : String(entry.ao), entry.ao_status ? ` (${statusLabel(entry.ao_status)})` : '']),
    el('div', {}, [el('b', {}, 'Harness'), entry.harness === '' || entry.harness == null ? '—' : String(entry.harness), entry.harness_status ? ` (${statusLabel(entry.harness_status)})` : '']),
    entry.evidence && entry.evidence.correction_basis ? el('div', { class: 'gs-tip-evidence' }, `근거 · ${entry.evidence.correction_basis}`) : null,
  ]);
  document.body.appendChild(tooltipEl);
}
function hideTip() { if (tooltipEl) { tooltipEl.remove(); tooltipEl = null; } }

function compareMap(compareList) {
  const m = new Map();
  for (const c of compareList || []) m.set(c.path, c);
  return m;
}

// 행/셀 상태는 비교 탭과 같은 util.entryState(entry, goldenValue) 하나로 판정한다:
// 'bad'(값 불일치) | 'warn'(Golden 이 비어서 생긴 차이) | 'weak'(한쪽 소스만 누락/추가) | ''(일치).

// key 처럼 실수로 바뀌면 안 되는 입력: 기본 readOnly, 더블클릭/Enter 로 편집, blur/Enter 로 종료
function keyInput(value, ariaLabel, onChange, cls = '') {
  const enterEdit = (e) => { e.target.readOnly = false; e.target.focus(); e.target.select(); };
  return el('input', {
    type: 'text', class: cls, value, readOnly: true, 'aria-label': ariaLabel,
    ondblclick: enterEdit,
    onkeydown: (e) => {
      if (e.key !== 'Enter') return;
      if (e.target.readOnly) { e.preventDefault(); enterEdit(e); } else { e.target.blur(); }
    },
    oninput: (e) => onChange(e.target.value),
    onblur: (e) => { e.target.readOnly = true; },
  });
}

function findOrPush(arr, key, make) {
  let it = arr.find((x) => x.key === key);
  if (!it) { it = make(); arr.push(it); }
  return it;
}

// compare 엔트리(doc/area/container/row/key)를 이용해 golden 값을 채택한다. 없는 위치면 만든다. 채택 전 값을 돌려준다(되돌리기용, 새 칸은 '').
function applyAdopt(golden, entry, value) {
  let prev;
  const set = (cell) => { prev = cell.value ?? ''; cell.value = value; };
  if (!golden.documents) golden.documents = [];
  while (golden.documents.length <= entry.doc) golden.documents.push({ doc_type: '', extracted_fields: [], extracted_groups: [], extracted_tables: [] });
  const d = golden.documents[entry.doc];
  d.extracted_fields = d.extracted_fields || []; d.extracted_groups = d.extracted_groups || []; d.extracted_tables = d.extracted_tables || [];
  const dtype = entry.dtype || 'string';
  if (entry.area === 'field') {
    const cell = findOrPush(d.extracted_fields, entry.key, () => ({ key: entry.key, value: '', dtype }));
    set(cell);
  } else if (entry.area === 'group') {
    const g = findOrPush(d.extracted_groups, entry.container, () => ({ key: entry.container, fields: [] }));
    g.fields = g.fields || [];
    const cell = findOrPush(g.fields, entry.key, () => ({ key: entry.key, value: '', dtype }));
    set(cell);
  } else if (entry.area === 'table') {
    const t = findOrPush(d.extracted_tables, entry.container, () => ({ key: entry.container, headers: [], rows: [] }));
    t.headers = t.headers || []; t.rows = t.rows || [];
    let colIdx = t.headers.indexOf(entry.key);
    if (colIdx === -1) { t.headers.push(entry.key); colIdx = t.headers.length - 1; }
    const rowIdx = /^\d+$/.test(String(entry.row)) ? Number(entry.row) : t.rows.length;
    while (t.rows.length <= rowIdx) t.rows.push(t.headers.map((h) => ({ key: h, value: '', dtype: 'string' })));
    const row = t.rows[rowIdx];
    while (row.length < t.headers.length) row.push({ key: t.headers[row.length], value: '', dtype: 'string' });
    if (!row[colIdx]) row[colIdx] = { key: entry.key, value: '', dtype };
    set(row[colIdx]);
  }
  return prev;
}

export function createGoldenEditor(host, opts) {
  const { bundleId, docId } = opts;
  let doc = opts.doc; // GET docs/{doc} 응답
  let golden = null;
  let dirty = false;
  let editRevision = 0;
  let saveQueue = Promise.resolve();
  let destroyed = false;
  let deleting = false;
  let restoring = false;
  let conflictPaused = false;
  let closeConflictDialog = null;
  let closeHistoryDialog = null;
  let conflictButton = null;
  let autosave = true;
  let advanced = false;
  let collapsedGroups = new Set();
  let cmap = compareMap(doc.compare);
  let saveTimer = null;
  let summaryEl = null;
  let shownPaths = null; // renderedPaths 캐시(render/markDirty 에서 무효화)
  let mismatchCursor = -1; // focusMismatch 가 마지막으로 이동한 위치(버튼 클릭 시 포커스가 버튼으로 옮겨가므로 activeElement 로는 추적 불가)
  const listeners = { dirty: opts.onDirtyChange || (() => {}), start: opts.onSaveStart || (() => {}), ok: opts.onSaveOk || (() => {}), err: opts.onSaveErr || (() => {}) };

  const debouncedSave = debounce(() => { if (!destroyed && !deleting && !restoring && !conflictPaused && autosave) doSave(); }, 1500);

  const updateSummaryLater = debounce(() => updateSummary(), 150);
  function markDirty() {
    if (destroyed) return;
    shownPaths = null; editRevision += 1; dirty = true; listeners.dirty(true); debouncedSave(); updateSummaryLater();
  }

  // 필드+그룹+표 셀 전체에서 "Golden 값이 비었는데 소스(AO/Harness)에는 값이 있는" 항목 수.
  function countEmptyWithSource() {
    if (!golden || !golden.documents || !golden.documents[0]) return 0;
    const d0 = golden.documents[0];
    let n = 0;
    const check = (value, path) => { if ((value == null || value === '') && hasSourceValue(cmap.get(path))) n++; };
    (d0.extracted_fields || []).forEach((c) => check(c.value, `documents[0].fields[${c.key}]`));
    (d0.extracted_groups || []).forEach((g) => (g.fields || []).forEach((c) => check(c.value, `documents[0].groups[${g.key}].fields[${c.key}]`)));
    (d0.extracted_tables || []).forEach((t) => (t.rows || []).forEach((row, ri) => (t.headers || []).forEach((h, ci) => {
      const cell = row[ci];
      if (cell) check(cell.value, `documents[0].tables[${t.key}].rows[${ri}].cells[${cell.key}]`);
    })));
    return n;
  }

  // 불일치 N(저장된 compare 기준) · 빈 값 M(현재 편집 중인 값 기준) 을 요약 바에 반영한다.
  function updateSummary() {
    if (!summaryEl) return;
    const n = (doc.compare || []).filter(isMismatch).length;
    const k = ghostEntries().length;
    summaryEl.textContent = `불일치 ${n} · 빈 값 ${countEmptyWithSource()}${k ? ` · Golden에 없음 ${k}` : ''}`;
  }

  // 현재 golden 에 그려지는 경로 집합 (경로 형식은 각 렌더러와 동일)
  function renderedPaths() {
    if (shownPaths) return shownPaths;
    const d0 = golden && golden.documents && golden.documents[0];
    const s = shownPaths = new Set();
    if (!d0) return s;
    (d0.extracted_fields || []).forEach((c) => s.add(`documents[0].fields[${c.key}]`));
    (d0.extracted_groups || []).forEach((g) => (g.fields || []).forEach((c) => s.add(`documents[0].groups[${g.key}].fields[${c.key}]`)));
    (d0.extracted_tables || []).forEach((t) => (t.rows || []).forEach((row, ri) => row.forEach((c) => c && s.add(`documents[0].tables[${t.key}].rows[${ri}].cells[${c.key}]`))));
    return s;
  }

  // compare 에는 있고 소스 값도 있는데 golden 에는 없는 위치(문서 0). area/container 로 거를 수 있다.
  function ghostEntries(area, container) {
    const shown = renderedPaths();
    return (doc.compare || []).filter((c) => c.doc === 0 && !shown.has(c.path) && hasSourceValue(c)
      && (!area || c.area === area) && (container === undefined || c.container === container));
  }

  function doSave() {
    if (destroyed || deleting || restoring || conflictPaused || !golden) return Promise.resolve({ ok: false });
    const revision = editRevision;
    const snapshot = structuredClone(golden);
    const task = saveQueue.catch(() => {}).then(() => {
      if (conflictPaused) return { ok: false, conflict: true };
      if (!destroyed) listeners.start();
      return api.putGolden(bundleId, docId, snapshot, doc.golden_revision).then((res) => {
        doc = res; cmap = compareMap(doc.compare);
        dirty = editRevision !== revision;
        if (destroyed) return;
        listeners.dirty(dirty);
        listeners.ok(res);
        if (!host.contains(document.activeElement) || !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) render();
        if (dirty && autosave && !conflictPaused && !restoring) debouncedSave();
        return { ok: true, dirty };
      });
    }).catch((e) => {
      if (destroyed) return { ok: false, error: e };
      if (e.status === 409) {
        conflictPaused = true;
        listeners.err(e);
        openConflictDialog();
        return { ok: false, conflict: true };
      }
      listeners.err(e); toast(`저장 실패: ${e.message}`, 'error');
      return { ok: false, error: e };
    });
    saveQueue = task;
    return task;
  }

  function downloadLocalGolden() {
    const blob = new Blob([JSON.stringify(golden, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = el('a', { href: url, download: `${docId}.golden.local.json` });
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function openConflictDialog() {
    if (destroyed || closeConflictDialog) return;
    if (conflictButton) conflictButton.style.display = '';
    closeConflictDialog = showGoldenConflictDialog({
      onDownload: downloadLocalGolden,
      onReload: async () => {
        const latest = await api.getDoc(bundleId, docId);
        if (destroyed) return;
        doc = latest; golden = latest.golden ? structuredClone(latest.golden) : null;
        cmap = compareMap(doc.compare); dirty = false; editRevision += 1; conflictPaused = false;
        listeners.dirty(false); render(); opts.onGoldenRemoteChange?.(latest);
      },
      onClose: () => { closeConflictDialog = null; },
    });
  }

  function openHistory() {
    closeHistoryDialog?.();
    closeHistoryDialog = openGoldenHistory({
      bundleId, docId, isDirty: () => dirty,
      onRestore: async (historyId, disposition) => {
        if (restoring || deleting || destroyed) return false;
        if (disposition === 'save') {
          const result = await doSave();
          if (!result?.ok || dirty || conflictPaused) return false;
        }
        restoring = true; debouncedSave.cancel(); host.inert = true;
        const task = saveQueue.catch(() => {}).then(() => api.restoreGolden(bundleId, docId, historyId, doc.golden_revision));
        saveQueue = task;
        try {
          const updated = await task;
          if (destroyed) return true;
          doc = { ...doc, ...updated, has: { ...doc.has, ...updated.has } };
          golden = doc.golden ? structuredClone(doc.golden) : null;
          cmap = compareMap(doc.compare); dirty = false; editRevision += 1; conflictPaused = false;
          listeners.dirty(false); render(); opts.onGoldenRemoteChange?.(doc); toast('선택한 Golden 버전을 복원했습니다.');
          return true;
        } catch (e) {
          if (!destroyed && e.status === 409) { conflictPaused = true; openConflictDialog(); }
          else if (!destroyed) toast(`복원 실패: ${e.message}`, 'error');
          return false;
        } finally { restoring = false; host.inert = false; }
      },
    });
  }

  function ensureDoc0() {
    if (!golden.documents) golden.documents = [];
    if (!golden.documents.length) golden.documents.push({ doc_type: '', extracted_fields: [], extracted_groups: [], extracted_tables: [] });
    const d = golden.documents[0];
    if (!d.extracted_fields) d.extracted_fields = [];
    if (!d.extracted_groups) d.extracted_groups = [];
    if (!d.extracted_tables) d.extracted_tables = [];
    return d;
  }

  function render() {
    shownPaths = null;
    hideTip(); // 다시 그리기 전에 이전 마우스 위치의 tooltip/bbox 하이라이트를 제거(mouseleave 가 못 나므로)
    if (opts.onHoverBbox) opts.onHoverBbox(null);
    clear(host);
    if (!doc.golden) { host.appendChild(renderCreateCard()); return; }
    if (golden == null) golden = structuredClone(doc.golden);
    const extraDocs = (golden.documents || []).length - 1;
    summaryEl = el('span', { class: 'gs-summary hint' });
    host.appendChild(el('div', { class: 'gs-subtoolbar' }, [
      el('label', { class: 'switch' }, [
        el('input', { type: 'checkbox', checked: autosave, onchange: (e) => { autosave = e.target.checked; if (autosave && dirty) debouncedSave(); } }),
        '자동 저장',
      ]),
      el('span', { class: 'hint' }, '1.5초 뒤 저장'),
      el('div', { class: 'grow' }),
      summaryEl,
      (conflictButton = el('button', { class: 'btn sm danger', style: conflictPaused ? '' : 'display:none', onclick: openConflictDialog }, '저장 충돌 해결')),
      el('button', { class: 'btn sm', onclick: openHistory }, '버전 기록'),
      el('button', { class: 'btn ghost icon sm', title: '이전 불일치', 'aria-label': '이전 불일치', onclick: () => focusMismatch(-1) }, icon('chevron-left')),
      el('button', { class: 'btn ghost icon sm', title: '다음 불일치 (M)', 'aria-label': '다음 불일치', onclick: () => focusMismatch(1) }, icon('chevron-right')),
      menuButton('', [
        el('button', { onclick: () => { advanced = !advanced; render(); } }, advanced ? '폼으로 돌아가기' : 'JSON 보기'),
        el('button', { class: 'danger', onclick: onDeleteGolden }, 'Golden 삭제'),
      ], 'more-horizontal', 'ghost icon sm'),
    ]));
    updateSummary();

    if (advanced) { host.appendChild(renderAdvanced()); return; }

    const d0 = ensureDoc0();
    host.appendChild(el('div', { class: 'doctype-row' }, [
      el('label', {}, '문서 유형'),
      docTypeSelect(d0.doc_type || '', '미지정', (v) => { d0.doc_type = v; markDirty(); }),
    ]));
    host.appendChild(renderFieldsSection(d0));
    host.appendChild(renderGroupsSection(d0));
    host.appendChild(renderTablesSection(d0));
    if (extraDocs > 0) host.appendChild(el('div', { class: 'hint' }, `이 번들 항목에는 문서가 ${extraDocs}개 더 있습니다 (Raw JSON 모드에서 확인).`));
  }

  // render() 후 스크롤 위치를 유지한다. find 는 CSS 선택자 또는 (host) => Element 함수.
  // 찾은 대상이 있으면 화면에 보이도록 스크롤하고(focus 는 기본 on) 지정 시 focus/select 도 한다.
  function rerenderAt(find, fallback, focus = true) {
    const scrollTop = host.scrollTop;
    render();
    host.scrollTop = scrollTop;
    // 마우스가 그대로 있으면 브라우저가 같은 위치의 새 요소로 hover 를 재발생시켜 tooltip 이 다시 뜰 수 있다.
    // 다음 프레임에 한 번 더 정리한다(실제 마우스 이동으로 인한 정상 hover 는 그 다음에 다시 발생).
    requestAnimationFrame(() => { hideTip(); if (opts.onHoverBbox) opts.onHoverBbox(null); });
    if (!find) return;
    const target = (typeof find === 'function' ? find(host) : host.querySelector(find)) || (fallback && host.querySelector(fallback));
    if (!target) return;
    target.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    if (focus && target.focus) {
      target.readOnly = false; // 새로 추가한 key 입력은 바로 편집 가능하게
      target.focus({ preventScroll: true });
      if (target.select) target.select();
    }
  }

  // 문서 순서(필드 → 그룹 → 표)로 불일치 입력을 찾아 이동한다. dir: 1=다음, -1=이전.
  // 접힌 그룹 안에 있으면 펼치고, 이동한 칸은 잠깐 flash 로 강조하며 bbox 도 함께 표시한다.
  function focusMismatch(dir) {
    if (!doc.golden || golden == null) { toast('불일치 항목이 없습니다.'); return; }
    const all = () => Array.from(host.querySelectorAll('.field-row[data-path], .gs-table td[data-path], .ghost-cell[data-path]'));
    const targets = all().filter((n) => isMismatch(cmap.get(n.dataset.path)));
    if (!targets.length) { toast('불일치 항목이 없습니다.'); return; }
    mismatchCursor = mismatchCursor < 0 ? (dir > 0 ? 0 : targets.length - 1) : (mismatchCursor + dir + targets.length) % targets.length;
    const idx = mismatchCursor;
    const path = targets[idx].dataset.path;
    const groupBlock = targets[idx].closest('.group-block');
    if (groupBlock) collapsedGroups.delete(Number(groupBlock.dataset.groupIndex));
    render();
    const node = all().find((n) => n.dataset.path === path);
    if (!node) return;
    const input = node.matches('.field-row') ? node.querySelector('.fr-value input') : node.querySelector('input');
    node.scrollIntoView({ block: 'center' });
    if (input) { input.focus({ preventScroll: true }); if (input.select) input.select(); }
    node.classList.add('flash');
    setTimeout(() => node.classList.remove('flash'), 1400);
    const entry = cmap.get(path);
    if (opts.onHoverBbox) opts.onHoverBbox(entry && entry.bbox ? entry.bbox : null);
  }

  // 표준 문서 종류 select. 표준에 없는 현재 값은 추가 옵션으로 유지한다.
  function docTypeSelect(value, blankLabel, onchange) {
    const types = value && !doc.doc_types.includes(value) ? [...doc.doc_types, value] : doc.doc_types;
    return el('select', { onchange: (e) => onchange(e.target.value) },
      [['', blankLabel], ...types.map((t) => [t, t])].map(([v, l]) => el('option', { value: v, selected: v === value }, l)));
  }

  function renderCreateCard() {
    const sources = [
      ['ao', 'AO 결과에서', doc.has.ao_extract],
      ['harness', 'Harness 결과에서', doc.has.harness],
      ['empty', '빈 Golden', true],
    ];
    let chosen = sources.find((s) => s[2])[0];
    let docType = doc.doc_type_suggest;
    const card = el('div', { class: 'gs-create-card' }, [
      el('h3', {}, 'Golden Set이 없습니다'),
      el('p', {}, '아래 소스로 초안을 만든 뒤 검수를 시작하세요.'),
      el('button', { class: 'btn sm', onclick: openHistory }, '버전 기록'),
    ]);
    if (conflictPaused) {
      conflictButton = el('button', { class: 'btn sm danger', onclick: openConflictDialog }, '저장 충돌 해결');
      card.appendChild(conflictButton);
    }
    const optsHost = el('div', {});
    sources.forEach(([key, label, enabled]) => {
      const row = el('label', { class: `gs-source-opt ${enabled ? '' : 'disabled'}` }, [
        el('input', { type: 'radio', name: 'gs-src', value: key, checked: key === chosen, disabled: !enabled,
          onchange: () => { chosen = key; } }),
        el('div', { class: 'grow' }, [el('div', { class: 'opt-label' }, label)]),
        enabled ? null : el('span', { class: 'badge badge-muted' }, '파일 없음'),
        enabled && key === 'harness' && doc.doc_type_mismatch ? el('span', { class: 'badge badge-ok' }, '권장') : null,
      ]);
      optsHost.appendChild(row);
    });
    card.appendChild(optsHost);
    card.appendChild(el('div', { class: 'doctype-row' }, [
      el('label', {}, '문서 종류'),
      docTypeSelect(docType, '선택 안 함', (v) => { docType = v; }),
    ]));
    card.appendChild(el('div', { class: 'hint' }, 'AO 분류와 다르면 해당 양식 템플릿으로 뼈대를 바꾸고 같은 key 값은 유지합니다.'));
    const m = doc.doc_type_mismatch;
    card.appendChild(el('button', { class: 'btn primary', onclick: () => {
      if (m && chosen === 'ao' && !docType && !confirm(`AO가 '${m.ao}' 양식으로 추출해 키가 실제 문서('${m.title}')와 다릅니다. Harness로 생성하길 권장합니다. 그래도 AO로 만들까요?`)) return;
      api.createGolden(bundleId, docId, chosen, docType, doc.golden_revision).then((res) => {
        if (destroyed) return;
        doc = res; golden = null; cmap = compareMap(doc.compare);
        render(); toast('Golden Set을 생성했습니다.');
        opts.onGoldenCreated && opts.onGoldenCreated(res);
      }).catch((e) => {
        if (destroyed) return;
        if (e.status === 409) { conflictPaused = true; openConflictDialog(); }
        else toast(`생성 실패: ${e.message}`, 'error');
      });
    } }, 'Golden 만들기'));
    return card;
  }

  function onDeleteGolden() {
    if (deleting || !confirm('Golden Set을 삭제할까요?')) return;
    deleting = true;
    debouncedSave.cancel();
    saveQueue = saveQueue.catch(() => {}).then(() => api.deleteGolden(bundleId, docId, doc.golden_revision)).then((updated) => {
      doc = updated || { ...doc, golden: null, golden_revision: 'missing', has: { ...doc.has, golden: false } };
      golden = null; dirty = false; editRevision += 1;
      if (destroyed) return;
      listeners.dirty(false); render();
      toast('Golden Set을 삭제했습니다.');
      opts.onGoldenCreated && opts.onGoldenCreated(doc);
    }).catch((e) => {
      if (!destroyed && e.status === 409) { conflictPaused = true; openConflictDialog(); }
      else if (!destroyed) toast(e.message, 'error');
    }).finally(() => {
      deleting = false;
      if (!destroyed && dirty && autosave) debouncedSave();
    });
  }

  function tipHandlers(path) {
    return {
      onmouseenter: (e) => { const entry = cmap.get(path); showTip(e.clientX, e.clientY, entry); if (entry && entry.bbox && opts.onHoverBbox) opts.onHoverBbox(entry.bbox); },
      onmousemove: (e) => { if (tooltipEl) { tooltipEl.style.left = `${Math.min(e.clientX + 12, window.innerWidth - 300)}px`; tooltipEl.style.top = `${Math.max(8, e.clientY - 68)}px`; } },
      onmouseleave: () => { hideTip(); if (opts.onHoverBbox) opts.onHoverBbox(null); },
    };
  }

  // AO/Harness 비교 칸: 자체 컬럼(넓은 화면)이거나 값 아래 칩 줄(좁은 화면, 컨테이너 쿼리)로 표시된다.
  // refocus: 채택 후 포커스를 되돌릴 대상을 찾는 함수(host => Element). 없으면 필드 행(.field-row)을 찾는 기본 동작.
  function compareCell(kind, label, entry, path, refocus) {
    const value = entry ? entry[kind] : null;
    const status = entry ? entry[`${kind}_status`] : null;
    const available = value != null && value !== '';
    // 이 소스 자체의 상태(행 전체를 아우르는 entryState 와 달리 kind 하나만 본다): 값이 실제로 다르면 bad,
    // 이 소스에만 값이 없으면(MISSING) 약하게(weak), Golden 이 비어서 생긴 EXTRA 는 중립(소스 값 색은 그대로).
    const kindState = status === 'MISMATCH' || status === 'TYPE_MISMATCH' ? 'bad' : status === 'MISSING' ? 'weak' : '';
    const showStat = !!(status && status !== 'MATCH');
    const content = entry
      ? el('button', {
          class: `gs-chip ${kindState ? `st-${kindState}` : ''}`.trim(), type: 'button',
          title: available ? `${label} 값을 Golden에 채택` : `${label} 빈 값을 Golden에 채택`,
          onclick: () => {
            applyAdopt(golden, entry, value ?? ''); markDirty();
            const find = refocus || ((h) => Array.from(h.querySelectorAll('.field-row')).find((r) => r.dataset.path === path));
            rerenderAt(find, null, !!refocus);
          },
        }, [
          el('span', { class: 'cap' }, label),
          el('span', { class: 'val' }, available ? String(value) : '—'),
          showStat ? el('span', { class: 'stat' }, statusLabel(status)) : null,
        ])
      : el('span', { class: 'fr-dash' }, '—');
    return el('div', { class: `fr-${kind} ${kindState === 'bad' ? 'is-bad' : ''}`.trim(), ...tipHandlers(path) }, content);
  }

  // 표 셀(td) 입력을 찾는 refocus 함수
  const tdInput = (path) => (h) => {
    const td = Array.from(h.querySelectorAll('.gs-table td[data-path]')).find((x) => x.dataset.path === path);
    return td && td.querySelector('input');
  };

  // golden 에 없는 위치: 라벨 + "Golden에 없음" 배지 + AO/Harness 채택 칩(채택하면 위치를 만든다)
  function ghostRow(entry) {
    const path = entry.path;
    return el('div', { class: 'field-row ghost', tabindex: '0', dataset: { path } }, [
      el('span', { class: 'fr-label' }, entry.key),
      el('div', { class: 'fr-value', ...tipHandlers(path) }, el('span', { class: 'badge badge-bad' }, 'Golden에 없음')),
      el('div', { class: 'fr-compare' }, [compareCell('ao', 'AO', entry, path), compareCell('harness', 'Harness', entry, path)]),
      el('span', { class: 'fr-dtype' }), el('span', { class: 'fr-del' }),
    ]);
  }

  // 필드/그룹 그리드(헤더 + 실제 행 + ghost 행)
  function fieldsGrid(rows, ghosts) {
    ghosts.forEach((e) => rows.appendChild(ghostRow(e)));
    return el('div', { class: 'gs-grid-wrap' }, [fieldsGridHead(), rows]);
  }

  // 표에서 없는 셀 목록: "행 N · key" + AO/Harness 칩
  function ghostStrip(ghosts) {
    return el('div', { class: 'table-ghosts' }, ghosts.map((e) => el('div', { class: 'table-adopt-bar ghost-cell', dataset: { path: e.path } }, [
      el('span', { class: 'adopt-label' }, `행 ${Number(e.row) + 1} · ${e.key}`),
      el('span', { class: 'badge badge-bad' }, 'Golden에 없음'),
      compareCell('ao', 'AO', e, e.path, tdInput(e.path)),
      compareCell('harness', 'Harness', e, e.path, tdInput(e.path)),
    ])));
  }

  const mismatchBadge = (n) => (n ? el('span', { class: 'badge badge-bad', title: `불일치 ${n}건` }, `불일치 ${n}`) : null);

  function cellRow(cell, path, onDelete) {
    if (!cell.dtype) cell.dtype = 'string';
    const entry = cmap.get(path);
    const row = el('div', { class: `field-row ${entryState(entry, cell.value)}`.trim(), tabindex: '0', dataset: { path } }, [
      keyInput(cell.key, 'key', (v) => { cell.key = v; markDirty(); }, 'fr-label'),
      el('div', { class: 'fr-value cell-wrap', ...tipHandlers(path) },
        el('input', { type: 'text', value: cell.value == null ? '' : cell.value, placeholder: '값 없음',
          oninput: (e) => { cell.value = e.target.value; markDirty(); } })),
      el('div', { class: 'fr-compare' }, [compareCell('ao', 'AO', entry, path), compareCell('harness', 'Harness', entry, path)]),
      el('select', { class: 'fr-dtype', onchange: (e) => { cell.dtype = e.target.value; markDirty(); } },
        DTYPES.map((t) => el('option', { value: t, selected: t === cell.dtype }, t))),
      el('button', { class: 'fr-del field-row-del', title: '삭제', 'aria-label': '삭제', onclick: () => onDelete() }, icon('x')),
    ]);
    return row;
  }

  // 섹션 헤더: fs-xs 라벨 + 개수 + 우측 ghost sm 추가 버튼. 빈 섹션은 한 줄로 축소한다.
  function sectionShell(label, count, addLabel, onAdd, body, extraClass = '') {
    const cls = `section-block ${extraClass}`.trim();
    if (!count) return el('div', { class: cls }, el('div', { class: 'section-empty' }, [
      `${label}${josa(label, '이', '가')} 없습니다`, el('button', { class: 'btn ghost sm', onclick: onAdd }, [icon('plus'), addLabel]),
    ]));
    return el('div', { class: cls }, [
      el('div', { class: 'section-head' }, [
        el('span', { class: 'section-label' }, label), el('span', { class: 'section-count' }, String(count)),
        el('div', { class: 'grow' }),
        el('button', { class: 'btn ghost sm', onclick: onAdd }, [icon('plus'), addLabel]),
      ]),
      body,
    ]);
  }

  // 필드 그리드 헤더(항목/값/AO/Harness/타입/삭제) — Fields 섹션과 각 그룹 카드가 공유한다.
  function fieldsGridHead() {
    return el('div', { class: 'gs-grid-head' }, [
      el('span', { class: 'fr-label' }, '항목'),
      el('span', { class: 'fr-value' }, '값'),
      el('span', { class: 'fr-ao' }, 'AO'),
      el('span', { class: 'fr-harness' }, 'Harness'),
      el('span', { class: 'fr-dtype' }, '타입'),
      el('span', { class: 'fr-del' }),
    ]);
  }

  // 새 필드를 문서 최상위에 추가하고, 스크롤 위치를 유지한 채 새 행의 라벨에 포커스한다.
  function addFieldTop() {
    if (!doc.golden) return;
    const d0 = ensureDoc0();
    d0.extracted_fields.push({ key: '새 필드', value: '', dtype: 'string' });
    markDirty();
    rerenderAt('.section-fields .field-row:last-child .fr-label');
  }

  function renderFieldsSection(d0) {
    const rows = el('div', { class: 'gs-grid-body' });
    d0.extracted_fields.forEach((cell, idx) => {
      rows.appendChild(cellRow(cell, `documents[0].fields[${cell.key}]`, () => {
        d0.extracted_fields.splice(idx, 1); markDirty();
        rerenderAt(`.section-fields .field-row:nth-child(${idx + 1}) .fr-label`, `.section-fields .field-row:nth-child(${idx}) .fr-label`);
      }));
    });
    const ghosts = ghostEntries('field');
    const count = d0.extracted_fields.length + ghosts.length;
    return sectionShell('필드', count, '필드 추가', addFieldTop, count ? fieldsGrid(rows, ghosts) : null, 'section-fields');
  }

  function renderGroupsSection(d0) {
    const body = el('div', { class: 'section-body' });
    d0.extracted_groups.forEach((g, gi) => {
      if (!g.fields) g.fields = [];
      const collapsed = collapsedGroups.has(gi);
      const ghosts = ghostEntries('group', g.key);
      const mismatchCount = ghosts.length + g.fields.reduce((n, cell) => n + (isMismatch(cmap.get(`documents[0].groups[${g.key}].fields[${cell.key}]`)) ? 1 : 0), 0);
      const rows = el('div', { class: 'gs-grid-body' });
      g.fields.forEach((cell, fi) => {
        rows.appendChild(cellRow(cell, `documents[0].groups[${g.key}].fields[${cell.key}]`, () => {
          g.fields.splice(fi, 1); markDirty();
          rerenderAt(`.group-block[data-group-index="${gi}"] .field-row:nth-child(${fi + 1}) .fr-label`, `.group-block[data-group-index="${gi}"] .field-row:nth-child(${fi}) .fr-label`);
        }));
      });
      const grid = g.fields.length || ghosts.length ? fieldsGrid(rows, ghosts) : el('div', { class: 'section-empty sm' }, '필드가 없습니다');
      const fieldsHost = el('div', { class: `group-fields ${collapsed ? 'collapsed' : ''}` }, [
        grid,
        el('button', { class: 'btn ghost sm', onclick: () => {
          g.fields.push({ key: '새 필드', value: '', dtype: 'string' }); markDirty();
          rerenderAt(`.group-block[data-group-index="${gi}"] .field-row:last-child .fr-label`);
        } }, [icon('plus'), '필드 추가']),
      ]);
      body.appendChild(el('div', { class: 'group-block', dataset: { groupIndex: gi } }, [
        el('div', { class: 'group-head' }, [
          el('button', { class: 'chev', onclick: () => { collapsed ? collapsedGroups.delete(gi) : collapsedGroups.add(gi); rerenderAt(); } }, icon(collapsed ? 'chevron-right' : 'chevron-down')),
          keyInput(g.key, '그룹 이름', (v) => { g.key = v; markDirty(); }),
          el('span', { class: 'group-count' }, String(g.fields.length)),
          mismatchBadge(mismatchCount),
          el('button', { class: 'field-row-del', title: '그룹 삭제', onclick: () => { d0.extracted_groups.splice(gi, 1); markDirty(); rerenderAt(); } }, icon('x')),
        ]),
        fieldsHost,
      ]));
    });
    // golden 에 그룹 자체가 없는 경우: ghost 그룹 블록
    const known = new Set(d0.extracted_groups.map((g) => g.key));
    const missing = ghostEntries('group').filter((e) => !known.has(e.container));
    [...new Set(missing.map((e) => e.container))].forEach((name) => {
      const list = missing.filter((e) => e.container === name);
      body.appendChild(el('div', { class: 'group-block ghost' }, [
        el('div', { class: 'group-head' }, [
          el('span', { class: 'ghost-name' }, name), el('span', { class: 'badge badge-bad' }, 'Golden에 없음'), el('div', { class: 'grow' }), mismatchBadge(list.length),
        ]),
        el('div', { class: 'group-fields' }, fieldsGrid(el('div', { class: 'gs-grid-body' }), list)),
      ]));
    });
    const addGroup = () => {
      d0.extracted_groups.push({ key: '새 그룹', fields: [] }); markDirty();
      rerenderAt('.section-groups .group-block:last-child .group-head input[type="text"]');
    };
    return sectionShell('그룹', d0.extracted_groups.length + new Set(missing.map((e) => e.container)).size, '그룹 추가', addGroup, body, 'section-groups');
  }

  function renderTablesSection(d0) {
    const body = el('div', { class: 'section-body' });
    d0.extracted_tables.forEach((t, ti) => {
      if (!t.headers) t.headers = [];
      if (!t.rows) t.rows = [];
      // 셀 채택 바: 셀에 포커스가 오면 그 셀의 compare 항목(AO/Harness 칩)을 보여준다. 표마다 하나.
      // 표가 밀리지 않도록 바는 항상 자리를 차지하고, 내용만 기본 안내 ↔ 셀 비교 ↔ 다중 선택 안내로 바꾼다.
      const adoptBar = el('div', { class: 'table-adopt-bar' });
      const idleBar = () => mount(adoptBar, el('span', { class: 'hint' }, '칸을 선택하면 AO/Harness 값이 보입니다 · 드래그나 Shift+클릭으로 여러 칸을 골라 같은 값 입력'));
      // 드래그/Shift+클릭으로 고른 직사각형 셀 범위. 선택 칸 중 하나에 입력하면 선택 칸 모두 같은 값이 된다.
      let anchor = null, sel = null;
      const inSel = (ri, ci) => sel && ri >= Math.min(sel.r0, sel.r1) && ri <= Math.max(sel.r0, sel.r1) && ci >= Math.min(sel.c0, sel.c1) && ci <= Math.max(sel.c0, sel.c1);
      const selCount = () => (sel ? (Math.abs(sel.r1 - sel.r0) + 1) * (Math.abs(sel.c1 - sel.c0) + 1) : 0);
      function setSel(ri, ci) {
        sel = ri == null ? null : { r0: anchor.ri, c0: anchor.ci, r1: ri, c1: ci };
        tbody.querySelectorAll('td[data-ci]').forEach((td) => td.classList.toggle('sel', selCount() > 1 && inSel(+td.dataset.ri, +td.dataset.ci)));
      }
      // 선택 확정(드래그 종료·Shift+클릭) 시 안내 바를 띄우고 기준 칸에 포커스. 드래그 중에 띄우면 표가 밀려 선택이 어긋난다.
      function commitSel() {
        if (selCount() < 2) return;
        mount(adoptBar, [el('span', { class: 'adopt-label' }, `${selCount()}칸 선택`), el('span', { class: 'hint' }, '입력하면 선택한 칸이 모두 같은 값으로 바뀝니다 · Esc 해제')]);
        const inp = tdInput(cellPath(anchor.ri, anchor.ci))(host);
        inp.focus(); inp.select();
      }
      function clearSel() { if (selCount() < 2) return; setSel(null); idleBar(); }
      const cellMouse = (ri, ci) => ({
        onmousedown: (e) => {
          if (e.button !== 0) return;
          if (e.shiftKey && anchor) { e.preventDefault(); setSel(ri, ci); commitSel(); return; }
          clearSel();
          anchor = { ri, ci };
          document.addEventListener('mouseup', commitSel, { once: true });
        },
        onmouseenter: (e) => {
          if (!(e.buttons & 1) || !anchor || (anchor.ri === ri && anchor.ci === ci && !sel)) return;
          window.getSelection().removeAllRanges();
          setSel(ri, ci);
        },
      });
      const cellPath = (ri, ci) => `documents[0].tables[${t.key}].rows[${ri}].cells[${t.rows[ri][ci].key}]`;
      function fillSel(value) {
        tbody.querySelectorAll('td.sel').forEach((td) => {
          t.rows[+td.dataset.ri][+td.dataset.ci].value = value;
          td.querySelector('input').value = value;
        });
      }
      function showAdoptBar(ri, header, path) {
        if (selCount() > 1) return;
        const entry = cmap.get(path);
        if (!entry) { idleBar(); return; }
        const refocus = tdInput(path);
        clear(adoptBar);
        adoptBar.appendChild(el('span', { class: 'adopt-label' }, `행 ${ri + 1} · ${header}`));
        adoptBar.appendChild(compareCell('ao', 'AO', entry, path, refocus));
        adoptBar.appendChild(compareCell('harness', 'Harness', entry, path, refocus));
      }
      idleBar();
      const ghosts = ghostEntries('table', t.key);
      let mismatchCount = ghosts.length;
      const headRow = el('tr', { class: 'rowhandle-row' }, [
        el('th', { class: 'rowhandle' }, '#'),
        ...t.headers.map((h, ci) => el('th', {}, el('div', { class: 'gs-col-head' }, [
          el('input', { type: 'text', value: h, dataset: { colIndex: ci }, 'aria-label': `${h} 열 이름`, oninput: (e) => {
            t.headers[ci] = e.target.value;
            t.rows.forEach((row) => { if (row[ci]) row[ci].key = e.target.value; });
            markDirty();
          } }),
          el('button', { class: 'gs-col-delete', type: 'button', title: `${h} 열 삭제`, 'aria-label': `${h} 열 삭제`, onclick: () => {
            t.headers.splice(ci, 1);
            t.rows.forEach((row) => row.splice(ci, 1));
            markDirty();
            rerenderAt(`.gs-table[data-table-index="${ti}"] thead input[data-col-index="${Math.min(ci, t.headers.length - 1)}"]`, `.table-block:nth-child(${ti + 1}) .gs-table-actions button:last-child`);
          } }, icon('x')),
        ]))),
        el('th', {}),
      ]);
      const tbody = el('tbody', {}, t.rows.map((row, ri) => el('tr', {}, [
        el('td', { class: 'rowhandle' }, String(ri)),
        ...t.headers.map((h, ci) => {
          const cell = row[ci] || (row[ci] = { key: h, value: '', dtype: 'string' });
          const path = `documents[0].tables[${t.key}].rows[${ri}].cells[${cell.key}]`;
          const cls = entryState(cmap.get(path), cell.value);
          if (cls === 'bad') mismatchCount++;
          return el('td', { class: cls, dataset: { path, ri, ci }, ...tipHandlers(path), ...cellMouse(ri, ci) }, el('input', { type: 'text', value: cell.value == null ? '' : cell.value,
            onfocus: () => showAdoptBar(ri, h, path),
            onkeydown: (e) => { if (e.key === 'Escape') clearSel(); },
            oninput: (e) => { cell.value = e.target.value; if (inSel(ri, ci)) fillSel(e.target.value); markDirty(); } }));
        }),
        el('td', {}, el('button', { class: 'field-row-del', title: '행 삭제', onclick: () => { t.rows.splice(ri, 1); markDirty(); rerenderAt(); } }, icon('x'))),
      ])));
      body.appendChild(el('div', { class: 'table-block' }, [
        el('div', { class: 'table-head-row' }, [
          el('input', { type: 'text', value: t.key, oninput: (e) => { t.key = e.target.value; markDirty(); } }),
          mismatchBadge(mismatchCount),
          el('button', { class: 'field-row-del', title: '표 삭제', onclick: () => { d0.extracted_tables.splice(ti, 1); markDirty(); rerenderAt(); } }, icon('x')),
        ]),
        adoptBar,
        ghosts.length ? ghostStrip(ghosts) : null,
        el('div', { class: 'gs-table-wrap' }, el('table', { class: 'gs-table', dataset: { tableIndex: ti } }, [el('thead', {}, headRow), tbody])),
        el('div', { class: 'gs-table-actions' }, [
          el('button', { class: 'btn ghost sm', onclick: () => {
            t.rows.push(t.headers.map((h) => ({ key: h, value: '', dtype: 'string' })));
            markDirty();
            rerenderAt(`.gs-table[data-table-index="${ti}"] tbody tr:last-child input`, `.table-block:nth-child(${ti + 1}) .gs-table-actions button:last-child`);
          } }, [icon('plus'), '행 추가']),
          el('button', { class: 'btn ghost sm', onclick: () => {
            t.headers.push('새 열');
            t.rows.forEach((row) => row.push({ key: t.headers[t.headers.length - 1], value: '', dtype: 'string' }));
            markDirty();
            rerenderAt(`.gs-table[data-table-index="${ti}"] thead input[data-col-index="${t.headers.length - 1}"]`);
          } }, [icon('plus'), '열 추가']),
        ]),
      ]));
    });
    // golden 에 표 자체가 없는 경우: ghost 표 블록
    const knownT = new Set(d0.extracted_tables.map((t) => t.key));
    const missingT = ghostEntries('table').filter((e) => !knownT.has(e.container));
    [...new Set(missingT.map((e) => e.container))].forEach((name) => {
      const list = missingT.filter((e) => e.container === name);
      body.appendChild(el('div', { class: 'table-block ghost' }, [
        el('div', { class: 'table-head-row' }, [el('span', { class: 'ghost-name' }, name), el('span', { class: 'badge badge-bad' }, 'Golden에 없음'), mismatchBadge(list.length)]),
        ghostStrip(list),
      ]));
    });
    const addTable = () => {
      d0.extracted_tables.push({ key: '새 표', headers: ['열1'], rows: [] }); markDirty();
      rerenderAt('.section-tables .table-block:last-child .table-head-row input[type="text"]');
    };
    return sectionShell('표', d0.extracted_tables.length + new Set(missingT.map((e) => e.container)).size, '표 추가', addTable, body, 'section-tables');
  }

  function renderAdvanced() {
    let text = JSON.stringify(golden, null, 2);
    const errBox = el('div', { class: 'json-error' });
    const ta = el('textarea', { value: text });
    return el('div', { class: 'advanced-json' }, [
      ta,
      errBox,
      el('div', { style: 'display:flex;gap:8px;margin-top:8px' }, [
        el('button', { class: 'btn primary sm', onclick: () => {
          try {
            const parsed = JSON.parse(ta.value);
            if (!parsed || !Array.isArray(parsed.documents)) throw new Error('documents 배열이 필요합니다.');
            golden = parsed; markDirty(); toast('적용했습니다. 저장하려면 Save를 누르세요.');
            clear(errBox);
          } catch (e) { clear(errBox); errBox.appendChild(document.createTextNode('JSON 오류: ' + e.message)); }
        } }, '적용'),
        el('button', { class: 'btn sm', onclick: () => { advanced = false; render(); } }, '폼으로 돌아가기'),
      ]),
    ]);
  }

  render();

  return {
    isDirty: () => dirty,
    hasConflict: () => conflictPaused,
    isAutosaveOn: () => autosave,
    save: () => { debouncedSave.cancel(); return doSave(); },
    addField: () => addFieldTop(),
    deleteFocused: () => {
      const active = host.querySelector('.field-row:focus-within, .field-row:hover');
      if (active) { const del = active.querySelector('.field-row-del'); if (del) del.click(); }
    },
    getGoldenObject: () => golden,
    setDoc: (newDoc) => { doc = newDoc; if (!dirty) golden = doc.golden ? structuredClone(doc.golden) : null; cmap = compareMap(doc.compare); render(); },
    hasGolden: () => !!doc.golden,
    focusMismatch: (dir) => focusMismatch(dir),
    adoptValue: (entry, value) => {
      if (!doc.golden) { toast('먼저 Golden Set을 생성하세요.', 'error'); return; }
      if (golden == null) golden = structuredClone(doc.golden);
      const prev = applyAdopt(golden, entry, value);
      markDirty();
      if (!advanced) render();
      return prev;
    },
    destroy: () => {
      destroyed = true; debouncedSave.cancel(); updateSummaryLater.cancel(); hideTip();
      closeConflictDialog?.(); closeHistoryDialog?.();
    },
  };
}

export { cellDisplay };
