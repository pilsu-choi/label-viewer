import { el, clear, debounce, toast, statusLabel, icon, menuButton, josa } from './util.js';
import { api } from './api.js';
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

function mismatchOf(entry) {
  if (!entry) return false;
  return (entry.ao_status && entry.ao_status !== 'MATCH') || (entry.harness_status && entry.harness_status !== 'MATCH');
}

function findOrPush(arr, key, make) {
  let it = arr.find((x) => x.key === key);
  if (!it) { it = make(); arr.push(it); }
  return it;
}

// compare 엔트리(doc/area/container/row/key)를 이용해 golden 값을 채택한다. 없는 위치면 만든다.
function applyAdopt(golden, entry, value) {
  if (!golden.documents) golden.documents = [];
  while (golden.documents.length <= entry.doc) golden.documents.push({ doc_type: '', extracted_fields: [], extracted_groups: [], extracted_tables: [] });
  const d = golden.documents[entry.doc];
  d.extracted_fields = d.extracted_fields || []; d.extracted_groups = d.extracted_groups || []; d.extracted_tables = d.extracted_tables || [];
  const dtype = entry.dtype || 'string';
  if (entry.area === 'field') {
    const cell = findOrPush(d.extracted_fields, entry.key, () => ({ key: entry.key, value: '', dtype }));
    cell.value = value;
  } else if (entry.area === 'group') {
    const g = findOrPush(d.extracted_groups, entry.container, () => ({ key: entry.container, fields: [] }));
    g.fields = g.fields || [];
    const cell = findOrPush(g.fields, entry.key, () => ({ key: entry.key, value: '', dtype }));
    cell.value = value;
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
    row[colIdx].value = value;
  }
}

export function createGoldenEditor(host, opts) {
  const { bundleId, docId } = opts;
  let doc = opts.doc; // GET docs/{doc} 응답
  let golden = null;
  let dirty = false;
  let autosave = true;
  let advanced = false;
  let collapsedGroups = new Set();
  let cmap = compareMap(doc.compare);
  let saveTimer = null;
  const listeners = { dirty: opts.onDirtyChange || (() => {}), start: opts.onSaveStart || (() => {}), ok: opts.onSaveOk || (() => {}), err: opts.onSaveErr || (() => {}) };

  const debouncedSave = debounce(() => { if (autosave) doSave(); }, 1500);

  function markDirty() { dirty = true; listeners.dirty(true); debouncedSave(); }

  function doSave() {
    if (!golden) return Promise.resolve();
    listeners.start();
    return api.putGolden(bundleId, docId, golden).then((res) => {
      doc = res; cmap = compareMap(doc.compare);
      dirty = false; listeners.dirty(false); listeners.ok(res);
      if (!host.contains(document.activeElement) || !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) render();
    }).catch((e) => { listeners.err(e); toast(`저장 실패: ${e.message}`, 'error'); });
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
    hideTip(); // 다시 그리기 전에 이전 마우스 위치의 tooltip/bbox 하이라이트를 제거(mouseleave 가 못 나므로)
    if (opts.onHoverBbox) opts.onHoverBbox(null);
    clear(host);
    if (!doc.golden) { host.appendChild(renderCreateCard()); return; }
    if (golden == null) golden = JSON.parse(JSON.stringify(doc.golden));
    const extraDocs = (golden.documents || []).length - 1;
    host.appendChild(el('div', { class: 'gs-subtoolbar' }, [
      el('label', { class: 'switch' }, [
        el('input', { type: 'checkbox', checked: autosave, onchange: (e) => { autosave = e.target.checked; if (autosave && dirty) debouncedSave(); } }),
        '자동 저장',
      ]),
      el('span', { class: 'hint' }, '1.5초 뒤 저장'),
      el('div', { class: 'grow' }),
      menuButton('', [
        el('button', { onclick: () => { advanced = !advanced; render(); } }, advanced ? '폼으로 돌아가기' : 'JSON 보기'),
        el('button', { class: 'danger', onclick: onDeleteGolden }, 'Golden 삭제'),
      ], 'more-horizontal', 'ghost icon sm'),
    ]));

    if (advanced) { host.appendChild(renderAdvanced()); return; }

    const d0 = ensureDoc0();
    host.appendChild(el('div', { class: 'doctype-row' }, [
      el('label', {}, '문서 유형'),
      el('input', { type: 'text', value: d0.doc_type || '', oninput: (e) => { d0.doc_type = e.target.value; markDirty(); } }),
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
      target.focus({ preventScroll: true });
      if (target.select) target.select();
    }
  }

  function renderCreateCard() {
    const sources = [
      ['ao', 'AO 결과에서', doc.has.ao_extract],
      ['harness', 'Harness 결과에서', doc.has.harness],
      ['empty', '빈 Golden', true],
    ];
    let chosen = sources.find((s) => s[2])[0];
    const card = el('div', { class: 'gs-create-card' }, [
      el('h3', {}, 'Golden Set이 없습니다'),
      el('p', {}, '아래 소스로 초안을 만든 뒤 검수를 시작하세요.'),
    ]);
    const optsHost = el('div', {});
    sources.forEach(([key, label, enabled]) => {
      const row = el('label', { class: `gs-source-opt ${enabled ? '' : 'disabled'}` }, [
        el('input', { type: 'radio', name: 'gs-src', value: key, checked: key === chosen, disabled: !enabled,
          onchange: () => { chosen = key; } }),
        el('div', { class: 'grow' }, [el('div', { class: 'opt-label' }, label)]),
        enabled ? null : el('span', { class: 'badge badge-muted' }, '파일 없음'),
      ]);
      optsHost.appendChild(row);
    });
    card.appendChild(optsHost);
    card.appendChild(el('button', { class: 'btn primary', onclick: () => {
      api.createGolden(bundleId, docId, chosen).then((res) => {
        doc = res; golden = null; cmap = compareMap(doc.compare);
        render(); toast('Golden Set을 생성했습니다.');
        opts.onGoldenCreated && opts.onGoldenCreated(res);
      }).catch((e) => toast(`생성 실패: ${e.message}`, 'error'));
    } }, 'Golden 만들기'));
    return card;
  }

  function onDeleteGolden() {
    if (!confirm('Golden Set을 삭제할까요?')) return;
    api.deleteGolden(bundleId, docId).then(() => {
      doc = { ...doc, golden: null }; golden = null; render();
      toast('Golden Set을 삭제했습니다.');
      opts.onGoldenCreated && opts.onGoldenCreated(doc);
    }).catch((e) => toast(e.message, 'error'));
  }

  function tipHandlers(path) {
    return {
      onmouseenter: (e) => { const entry = cmap.get(path); showTip(e.clientX, e.clientY, entry); if (entry && entry.bbox && opts.onHoverBbox) opts.onHoverBbox(entry.bbox); },
      onmousemove: (e) => { if (tooltipEl) { tooltipEl.style.left = `${Math.min(e.clientX + 12, window.innerWidth - 300)}px`; tooltipEl.style.top = `${Math.max(8, e.clientY - 68)}px`; } },
      onmouseleave: () => { hideTip(); if (opts.onHoverBbox) opts.onHoverBbox(null); },
    };
  }

  function cellRow(cell, path, onDelete) {
    if (!cell.dtype) cell.dtype = 'string';
    const entry = cmap.get(path);
    const row = el('div', { class: `field-row ${mismatchOf(entry) ? 'mismatch' : ''}`, tabindex: '0', dataset: { path } }, [
      el('input', { type: 'text', value: cell.key, 'aria-label': 'key', oninput: (e) => { cell.key = e.target.value; markDirty(); } }),
      el('div', { class: 'cell-wrap', ...tipHandlers(path) },
        el('input', { type: 'text', value: cell.value == null ? '' : cell.value, oninput: (e) => { cell.value = e.target.value; markDirty(); } })),
      el('select', { onchange: (e) => { cell.dtype = e.target.value; markDirty(); } },
        DTYPES.map((t) => el('option', { value: t, selected: t === cell.dtype }, t))),
      el('button', { class: 'field-row-del', title: '삭제', 'aria-label': '삭제', onclick: () => onDelete() }, icon('x')),
    ]);
    if (entry) {
      const sources = [['AO', entry.ao, entry.ao_status], ['Harness', entry.harness, entry.harness_status]];
      row.classList.add('has-sources');
      row.appendChild(el('div', { class: 'gs-compare', ...tipHandlers(path) }, sources.map(([label, value, status]) => {
        const available = value != null && value !== '';
        const off = status && status !== 'MATCH';
        return el('button', {
          class: `gs-chip ${off ? 'is-off' : ''}`,
          type: 'button', disabled: !available,
          title: available ? `${label} 값을 Golden에 채택` : `${label} 값 없음`,
          onclick: () => {
            applyAdopt(golden, entry, value); markDirty();
            rerenderAt((h) => Array.from(h.querySelectorAll('.field-row')).find((r) => r.dataset.path === path), null, false);
          },
        }, [
          el('span', { class: 'cap' }, label),
          el('span', { class: 'val' }, available ? String(value) : '—'),
          off ? el('span', { class: 'stat' }, statusLabel(status)) : null,
        ]);
      })));
    }
    return row;
  }

  // 섹션 헤더: fs-xs 라벨 + 개수 + 우측 ghost sm 추가 버튼. 빈 섹션은 한 줄로 축소한다.
  function sectionShell(label, count, addLabel, onAdd, body) {
    if (!count) return el('div', { class: 'section-block' }, el('div', { class: 'section-empty' }, [
      `${label}${josa(label, '이', '가')} 없습니다`, el('button', { class: 'btn ghost sm', onclick: onAdd }, [icon('plus'), addLabel]),
    ]));
    return el('div', { class: 'section-block' }, [
      el('div', { class: 'section-head' }, [
        el('span', { class: 'section-label' }, label), el('span', { class: 'section-count' }, String(count)),
        el('div', { class: 'grow' }),
        el('button', { class: 'btn ghost sm', onclick: onAdd }, [icon('plus'), addLabel]),
      ]),
      body,
    ]);
  }

  function renderFieldsSection(d0) {
    const body = el('div', { class: 'section-body' });
    d0.extracted_fields.forEach((cell, idx) => {
      body.appendChild(cellRow(cell, `documents[0].fields[${cell.key}]`, () => { d0.extracted_fields.splice(idx, 1); markDirty(); rerenderAt(); }));
    });
    const addField = () => { d0.extracted_fields.push({ key: '새 필드', value: '', dtype: 'string' }); markDirty(); rerenderAt(); };
    return sectionShell('필드', d0.extracted_fields.length, '필드 추가', addField, body);
  }

  function renderGroupsSection(d0) {
    const body = el('div', { class: 'section-body' });
    d0.extracted_groups.forEach((g, gi) => {
      if (!g.fields) g.fields = [];
      const collapsed = collapsedGroups.has(gi);
      const fieldsHost = el('div', { class: `group-fields ${collapsed ? 'collapsed' : ''}` });
      g.fields.forEach((cell, fi) => {
        fieldsHost.appendChild(cellRow(cell, `documents[0].groups[${g.key}].fields[${cell.key}]`, () => { g.fields.splice(fi, 1); markDirty(); rerenderAt(); }));
      });
      fieldsHost.appendChild(el('button', { class: 'btn ghost sm', onclick: () => { g.fields.push({ key: '새 필드', value: '', dtype: 'string' }); markDirty(); rerenderAt(); } }, [icon('plus'), '필드 추가']));
      body.appendChild(el('div', { class: 'group-block' }, [
        el('div', { class: 'group-head' }, [
          el('button', { class: 'chev', onclick: () => { collapsed ? collapsedGroups.delete(gi) : collapsedGroups.add(gi); rerenderAt(); } }, icon(collapsed ? 'chevron-right' : 'chevron-down')),
          el('input', { type: 'text', value: g.key, oninput: (e) => { g.key = e.target.value; markDirty(); } }),
          el('button', { class: 'field-row-del', title: '그룹 삭제', onclick: () => { d0.extracted_groups.splice(gi, 1); markDirty(); rerenderAt(); } }, icon('x')),
        ]),
        fieldsHost,
      ]));
    });
    const addGroup = () => { d0.extracted_groups.push({ key: '새 그룹', fields: [] }); markDirty(); rerenderAt(); };
    return sectionShell('그룹', d0.extracted_groups.length, '그룹 추가', addGroup, body);
  }

  function renderTablesSection(d0) {
    const body = el('div', { class: 'section-body' });
    d0.extracted_tables.forEach((t, ti) => {
      if (!t.headers) t.headers = [];
      if (!t.rows) t.rows = [];
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
          return el('td', tipHandlers(path), el('input', { type: 'text', value: cell.value == null ? '' : cell.value,
            oninput: (e) => { cell.value = e.target.value; markDirty(); } }));
        }),
        el('td', {}, el('button', { class: 'field-row-del', title: '행 삭제', onclick: () => { t.rows.splice(ri, 1); markDirty(); rerenderAt(); } }, icon('x'))),
      ])));
      body.appendChild(el('div', { class: 'table-block' }, [
        el('div', { class: 'table-head-row' }, [
          el('input', { type: 'text', value: t.key, oninput: (e) => { t.key = e.target.value; markDirty(); } }),
          el('button', { class: 'field-row-del', title: '표 삭제', onclick: () => { d0.extracted_tables.splice(ti, 1); markDirty(); rerenderAt(); } }, icon('x')),
        ]),
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
    const addTable = () => { d0.extracted_tables.push({ key: '새 표', headers: ['열1'], rows: [] }); markDirty(); rerenderAt(); };
    return sectionShell('표', d0.extracted_tables.length, '표 추가', addTable, body);
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
    isAutosaveOn: () => autosave,
    save: () => { debouncedSave.cancel(); return doSave(); },
    addField: () => { if (!doc.golden) return; const d0 = ensureDoc0(); d0.extracted_fields.push({ key: '새 필드', value: '', dtype: 'string' }); markDirty(); rerenderAt(); },
    deleteFocused: () => {
      const active = host.querySelector('.field-row:focus-within, .field-row:hover');
      if (active) { const del = active.querySelector('.field-row-del'); if (del) del.click(); }
    },
    getGoldenObject: () => golden,
    setDoc: (newDoc) => { doc = newDoc; if (!dirty) golden = doc.golden ? JSON.parse(JSON.stringify(doc.golden)) : null; cmap = compareMap(doc.compare); render(); },
    hasGolden: () => !!doc.golden,
    adoptValue: (entry, value) => {
      if (!doc.golden) { toast('먼저 Golden Set을 생성하세요.', 'error'); return; }
      if (golden == null) golden = JSON.parse(JSON.stringify(doc.golden));
      applyAdopt(golden, entry, value);
      markDirty();
      if (!advanced) render();
    },
    destroy: () => { debouncedSave.cancel(); hideTip(); },
  };
}

export { cellDisplay };
