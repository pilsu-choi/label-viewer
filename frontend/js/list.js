import { startExport } from './exportTask.js';
import { el, mount, debounce, clear, fmtPct, scoreCard, icon, menuButton, mismatchBadge, classBadges, getDocTypeFilter, matchDocType, docTypeSelect, toast } from './util.js';
import { api } from './api.js';
import { navigate } from './router.js';

// 점수 카드 아래 분류 채점 요약과 필드 집계 제외 안내.
function classLine(cls) {
  if (!cls) return null;
  const ex = cls.total - cls.correct;
  return el('div', { class: 'hint' }, [`분류 ${cls.correct}/${cls.total} (${fmtPct(cls.accuracy)})`, ex ? ` · 분류 오답 ${ex}건은 필드 집계 제외` : '']);
}

function docBadges(has) {
  const order = [['original', '원본', '원'], ['preprocessed', '전처리', '전'], ['ao_extract', 'AO 결과', 'AO'], ['harness', 'Harness 결과', 'H'], ['golden', 'Golden', 'G']];
  return el('div', { class: 'doc-badges' }, order.map(([k, full, short]) =>
    el('span', { class: `file-chip ${has[k] ? 'on' : 'off'}`, title: `${full} ${has[k] ? '있음' : '없음'}` }, short)));
}

function accBars(score) {
  if (!score || (!score.ao && !score.harness)) return null;
  const row = (label, s) => el('div', { class: 'acc-bar-row' }, [
    el('span', { class: 'lbl' }, label),
    el('div', { class: 'track' }, el('span', { style: `width:${s ? (s.accuracy || 0) * 100 : 0}%` })),
    el('span', { class: 'pct' }, s ? fmtPct(s.accuracy) : '—'),
  ]);
  return el('div', { class: 'acc-bars' }, [row('AO', score.ao), row('H', score.harness)]);
}

function reviewBadge(review) {
  if (review === 'done') return el('span', { class: 'badge badge-ok' }, [icon('check'), '완료']);
  if (review === 'progress') return el('span', { class: 'badge badge-warn' }, '검수중');
  return el('span', { class: 'badge badge-muted' }, '미검수');
}

const THUMB_W = 480;

function thumbImg(bundleId, doc) {
  const wrap = el('div', { class: 'doc-thumb' });
  if (!doc.has.original && !doc.has.preprocessed) {
    wrap.appendChild(el('span', { class: 'ph' }, 'No Image'));
    return wrap;
  }
  const view = doc.has.preprocessed ? 'preprocessed' : 'original';
  const img = el('img', { loading: 'lazy', decoding: 'async', src: api.imageUrl(bundleId, doc.id, view, 1, THUMB_W), alt: doc.id });
  img.addEventListener('error', () => {
    if (view === 'preprocessed' && doc.has.original) { img.src = api.imageUrl(bundleId, doc.id, 'original', 1, THUMB_W); }
    else { clear(wrap); wrap.appendChild(el('span', { class: 'ph' }, 'No Image')); }
  }, { once: true });
  wrap.appendChild(img);
  return wrap;
}

const PAGE_SIZES = [50, 100, 200];
const SCOPES = [['all', '전체'], ['enabled', '활성'], ['disabled', '비활성']];

function readPageSize() {
  try { const n = Number(localStorage.getItem('lv.pageSize')); return PAGE_SIZES.includes(n) ? n : PAGE_SIZES[0]; } catch (e) { return PAGE_SIZES[0]; }
}

// 번호 목록: 처음·끝과 현재 주변 2쪽, 사이는 '…'.
function pageNumbers(cur, last) {
  const out = [];
  for (let i = 1; i <= last; i += 1) {
    if (i === 1 || i === last || Math.abs(i - cur) <= 2) out.push(i);
    else if (out[out.length - 1] !== '…') out.push('…');
  }
  return out;
}

export function renderList(root, bundleId) {
  // scope: 집계·목록 범위(전체/활성/비활성). selected 는 페이지·필터를 넘어 유지한다.
  const state = { bundle: null, filter: 'all', q: '', view: 'grid', scope: 'all', page: 1, pageSize: readPageSize(),
    selected: new Set(), anchor: null, busy: false, loading: true, error: null };

  const screen = el('div', { class: 'list-screen' });
  mount(root, screen);
  const closeExportMenus = () => screen.querySelectorAll('.export-pop').forEach((p) => { p.style.display = 'none'; });
  document.addEventListener('click', closeExportMenus);
  draw();
  load();

  function load() {
    api.getBundle(bundleId, true).then((b) => { state.bundle = b; state.loading = false; draw(); })
      .catch((e) => { state.error = e.message; state.loading = false; draw(); });
  }

  const scopeSummary = () => (state.scope === 'all' ? state.bundle.summary : state.bundle.summary_by_scope[state.scope]);

  function filteredDocs() {
    if (!state.bundle) return [];
    let docs = state.bundle.docs;
    if (state.scope === 'enabled') docs = docs.filter((d) => d.enabled);
    else if (state.scope === 'disabled') docs = docs.filter((d) => !d.enabled);
    if (state.filter === 'golden') docs = docs.filter((d) => d.has.golden);
    else if (state.filter === 'nogolden') docs = docs.filter((d) => !d.has.golden);
    else if (state.filter === 'done') docs = docs.filter((d) => d.review === 'done');
    else if (state.filter === 'pending') docs = docs.filter((d) => d.review !== 'done');
    else if (state.filter === 'missing') docs = docs.filter((d) => !d.has.original || !d.has.ao_extract || !d.has.harness || !d.has.golden);
    else if (state.filter === 'error') docs = docs.filter((d) => d.errors && d.errors.length);
    const type = getDocTypeFilter(bundleId);
    docs = docs.filter((d) => matchDocType(d, type));
    if (state.q.trim()) {
      const q = state.q.trim().toLowerCase();
      docs = docs.filter((d) => d.id.toLowerCase().includes(q) || (d.doc_type || '').toLowerCase().includes(q));
    }
    return docs;
  }

  function chips(summary) {
    const nogolden = summary.docs - summary.golden;
    const defs = [
      ['all', '전체', summary.docs],
      ['golden', 'Golden 있음', summary.golden],
      ['nogolden', 'Golden 없음', nogolden],
      ['done', '검수 완료', summary.reviewed],
      ['pending', '미검수', summary.pending],
      ['missing', '데이터 누락', summary.missing],
      ['error', '오류', summary.error],
    ];
    return el('div', { class: 'filter-row' }, [
      ...defs.map(([key, label, n]) => el('button', { class: `chip ${state.filter === key ? 'active' : ''}`,
        onclick: () => { state.filter = key; state.page = 1; draw(); } }, [label, el('span', { class: 'n' }, String(n))])),
      docTypeSelect(state.bundle.docs, bundleId, () => { state.page = 1; draw(); }, 'doctype-filter'),
      el('div', { class: 'seg view-seg' }, [
        el('button', { class: state.view === 'grid' ? 'active' : '', onclick: () => { state.view = 'grid'; draw(); }, title: '썸네일', 'aria-label': '썸네일 보기' }, icon('grid')),
        el('button', { class: state.view === 'list' ? 'active' : '', onclick: () => { state.view = 'list'; draw(); }, title: '목록', 'aria-label': '목록 보기' }, icon('list')),
      ]),
    ]);
  }

  function scopeSeg() {
    const by = state.bundle.summary_by_scope;
    const n = { all: state.bundle.summary.docs, enabled: by.enabled.docs, disabled: by.disabled.docs };
    return el('div', { class: 'scope-row' }, [
      el('span', { class: 'scope-label' }, '집계 범위'),
      el('div', { class: 'seg' }, SCOPES.map(([key, label]) => el('button', { class: state.scope === key ? 'active' : '',
        onclick: () => { state.scope = key; state.page = 1; draw(); } }, [label, el('span', { class: 'n' }, ` ${n[key]}`)]))),
      el('span', { class: 'hint' }, '내보내기는 활성·비활성 목록을 따로 받습니다.'),
    ]);
  }

  function exportMenu() {
    const by = state.bundle.summary_by_scope;
    const item = (options, n, title, desc) => (n
      ? el('button', { type: 'button', onclick: (event) => {
          event.stopPropagation(); closeExportMenus();
          const latest = options.ids ? { ...options, ids: [...state.selected] } : options;
          startExport(bundleId, latest, `${title} · ${latest.ids?.length ?? n}건`);
        } }, [el('b', {}, title), el('span', {}, desc)])
      : el('div', { class: 'export-item disabled', title: '해당 문서가 없습니다' }, [el('b', {}, title), el('span', {}, '문서 없음')]));
    const group = (scope, label) => {
      const n = by[scope].docs;
      return [
        el('div', { class: 'export-group' }, `${label} 목록 · ${n}건`),
        item({ format: 'xlsx', scope }, n, 'Excel', '요약·필드·표·비교 시트'),
        item({ format: 'zip', scope }, n, '전체 묶음 ZIP', '원본·전처리 이미지, AO·Harness·Golden JSON'),
      ];
    };
    const ids = [...state.selected];
    const selection = [el('div', { class: 'export-group' }, `선택 문서 · ${ids.length}건`),
      item({ format: 'xlsx', ids }, ids.length, '선택 문서 Excel', '페이지·필터를 넘어 선택한 문서만'),
      item({ format: 'zip', ids }, ids.length, '선택 문서 ZIP', '선택한 문서의 전체 묶음')];
    return menuButton('내보내기', [...selection, ...group('enabled', '활성'), ...group('disabled', '비활성')]);
  }

  function applyEnabled(enabled) {
    const ids = [...state.selected];
    if (!ids.length || state.busy) return;
    state.busy = true; draw();
    api.setEnabled(bundleId, ids, enabled).then((b) => {
      state.bundle = b; state.selected.clear(); state.anchor = null;
      toast(`${ids.length}건을 ${enabled ? '활성화' : '비활성화'}했습니다.`);
    }).catch((e) => toast(e.message, 'error'))
      .finally(() => { state.busy = false; draw(); });
  }

  function draw() {
    if (state.loading) { mount(screen, el('div', { class: 'loading-block' }, '불러오는 중…')); return; }
    if (state.error) { mount(screen, el('div', { class: 'error-block' }, `번들을 불러오지 못했습니다: ${state.error}`)); return; }
    const b = state.bundle;
    const exportHost = el("div", {}, exportMenu());
    const topbar = el('div', { class: 'topbar' }, [
      el('a', { class: 'brand', href: '#/' }, 'Label Viewer'),
      el('div', { class: 'sep' }),
      el('div', { class: 'title' }, b.name || b.id),
      el('a', { class: 'btn ghost sm bundle-directory-link', href: '#/bundles' }, '전체 번들'),
      el('div', { class: 'grow' }),
      el('label', { class: 'search-box' }, [
        icon('search'),
        el('input', { type: 'search', placeholder: '문서 ID나 유형으로 찾기', value: state.q,
          oninput: debounce((e) => { state.q = e.target.value; state.page = 1; drawGrid(); }, 150) }),
      ]),
      exportHost,
    ]);

    const summary = scopeSummary();
    const sc = summary.score || {};
    const delta = sc.ao && sc.harness && sc.ao.accuracy != null && sc.harness.accuracy != null
      ? (sc.harness.accuracy - sc.ao.accuracy) * 100 : null;
    const stat = (v, l) => el('div', { class: 'ov-stat' }, [el('b', {}, String(v)), el('span', {}, l)]);
    const overview = el('section', { class: 'overview' }, [
      el('div', { class: 'ov-progress' }, [
        el('h1', {}, [String(summary.reviewed), el('small', {}, ` / ${summary.docs} 검수 완료`)]),
        el('div', { class: 'ov-track' }, el('span', { style: `width:${summary.docs ? (summary.reviewed / summary.docs) * 100 : 0}%` })),
        el('div', { class: 'ov-stats' }, [stat(summary.golden, 'Golden 있음'), stat(summary.missing, '데이터 누락'), stat(summary.error, '오류')]),
      ]),
      el('div', { class: 'ov-scores' }, [
        el('div', {}, [scoreCard('AO Extract', sc.ao), classLine(summary.classification.ao)]),
        el('div', { class: `ov-delta ${delta == null ? '' : delta >= 0 ? 'up' : 'down'}` }, delta == null ? '—'
          : [el('b', {}, `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}p`), el('span', {}, 'Harness 보정')]),
        el('div', {}, [scoreCard('Harness', sc.harness), classLine(summary.classification.harness)]),
      ]),
    ]);

    const gridHost = el('div');
    mount(screen, [topbar, el('div', { class: 'list-body' }, [scopeSeg(), overview, chips(summary), gridHost])]);
    drawGrid();

    function drawGrid() {
      mount(exportHost, exportMenu());
      const docs = filteredDocs();
      const last = Math.max(1, Math.ceil(docs.length / state.pageSize));
      state.page = Math.min(Math.max(1, state.page), last);
      const from = (state.page - 1) * state.pageSize;
      const pageDocs = docs.slice(from, from + state.pageSize);
      const open = (d) => navigate(`#/b/${encodeURIComponent(bundleId)}/d/${encodeURIComponent(d.id)}`);

      // Shift+클릭은 마지막으로 누른 문서부터 현재 필터 결과 순서대로 범위를 같은 상태로 맞춘다.
      const toggle = (d, e) => {
        e.stopPropagation();
        const on = !state.selected.has(d.id);
        const ids = docs.map((x) => x.id);
        const a = e.shiftKey && state.anchor ? ids.indexOf(state.anchor) : -1;
        const z = ids.indexOf(d.id);
        const range = a >= 0 ? ids.slice(Math.min(a, z), Math.max(a, z) + 1) : [d.id];
        range.forEach((id) => (on ? state.selected.add(id) : state.selected.delete(id)));
        state.anchor = d.id;
        drawGrid();
      };
      const check = (d) => el('label', { class: 'doc-check', title: '선택 (Shift: 범위)', onclick: (e) => e.stopPropagation() },
        el('input', { type: 'checkbox', checked: state.selected.has(d.id), 'aria-label': `${d.id} 선택`, onclick: (e) => toggle(d, e) }));
      const offBadge = (d) => (d.enabled ? null : el('span', { class: 'badge badge-muted badge-off' }, '비활성'));

      const pageAll = pageDocs.length > 0 && pageDocs.every((d) => state.selected.has(d.id));
      const nSel = state.selected.size;
      const toolbar = el('div', { class: 'select-bar' }, [
        el('label', { class: 'sel-page' }, [
          el('input', { type: 'checkbox', checked: pageAll, disabled: !pageDocs.length, onchange: (e) => {
            pageDocs.forEach((d) => (e.target.checked ? state.selected.add(d.id) : state.selected.delete(d.id))); drawGrid();
          } }), '이 페이지 선택']),
        el('button', { class: 'btn ghost sm', disabled: !docs.length, onclick: () => { docs.forEach((d) => state.selected.add(d.id)); drawGrid(); } }, `결과 전체 선택 (${docs.length})`),
        nSel ? el('button', { class: 'btn ghost sm', onclick: () => { state.selected.clear(); state.anchor = null; drawGrid(); } }, '선택 해제') : null,
        el('div', { class: 'grow' }),
        el('span', { class: 'sel-count' }, nSel ? `${nSel}건 선택됨` : '문서를 선택하세요'),
        el('button', { class: 'btn sm', disabled: !nSel || state.busy, onclick: () => applyEnabled(true) }, '활성화'),
        el('button', { class: 'btn sm', disabled: !nSel || state.busy, onclick: () => applyEnabled(false) }, '비활성화'),
      ]);

      if (!docs.length) {
        mount(gridHost, [toolbar, el('div', { class: 'empty' }, [
          icon('search'),
          el('div', { class: 'empty-title' }, '조건에 맞는 문서가 없습니다'),
          el('div', { class: 'empty-desc' }, '필터나 검색어를 바꿔 보세요.'),
        ])]);
        return;
      }
      let body;
      if (state.view === 'grid') {
        body = el('div', { class: 'doc-grid' }, pageDocs.map((d) => el('div', { class: `doc-card ${d.enabled ? '' : 'is-disabled'} ${state.selected.has(d.id) ? 'is-selected' : ''}`, onclick: () => open(d) }, [
          check(d),
          thumbImg(bundleId, d),
          el('div', { class: 'doc-info' }, [
            el('div', { class: 'doc-info-head' }, [el('span', { class: 'doc-id' }, d.id), offBadge(d), reviewBadge(d.review)]),
            el('div', { class: 'doc-type' }, d.doc_type || '문서 유형 없음'),
            mismatchBadge(d.doc_type_mismatch),
            classBadges(d.classification),
            docBadges(d.has),
            d.errors && d.errors.length ? el('span', { class: 'badge badge-bad', title: d.errors.join('\n') }, `오류 ${d.errors.length}`) : null,
            accBars(d.score),
          ]),
        ])));
      } else {
        body = el('div', {}, pageDocs.map((d) => el('div', { class: `doc-list-row ${d.enabled ? '' : 'is-disabled'} ${state.selected.has(d.id) ? 'is-selected' : ''}`, onclick: () => open(d) }, [
          check(d),
          el('span', { class: 'doc-id' }, d.id),
          docBadges(d.has),
          el('span', { class: 'doc-type' }, d.doc_type || '—'),
          mismatchBadge(d.doc_type_mismatch),
          classBadges(d.classification),
          el('span', { class: 'row-badges' }, [offBadge(d), reviewBadge(d.review)]),
        ])));
      }
      mount(gridHost, [toolbar, body, pager(docs.length, last)]);
    }

    function pager(total, last) {
      const go = (n) => { state.page = n; drawGrid(); gridHost.scrollIntoView({ block: 'start' }); };
      const from = (state.page - 1) * state.pageSize + 1;
      return el('nav', { class: 'pager', 'aria-label': '페이지' }, [
        el('span', { class: 'pager-range' }, `${from.toLocaleString()}–${Math.min(total, from + state.pageSize - 1).toLocaleString()} / ${total.toLocaleString()}건`),
        el('div', { class: 'pager-pages' }, [
          el('button', { class: 'btn ghost sm icon', disabled: state.page <= 1, 'aria-label': '이전 페이지', onclick: () => go(state.page - 1) }, icon('chevron-left')),
          ...pageNumbers(state.page, last).map((n) => (n === '…' ? el('span', { class: 'pager-gap' }, '…')
            : el('button', { class: `btn ghost sm ${n === state.page ? 'active' : ''}`, 'aria-current': n === state.page ? 'page' : null, onclick: () => go(n) }, String(n)))),
          el('button', { class: 'btn ghost sm icon', disabled: state.page >= last, 'aria-label': '다음 페이지', onclick: () => go(state.page + 1) }, icon('chevron-right')),
        ]),
        el('select', { class: 'pager-size', 'aria-label': '페이지당 문서 수', onchange: (e) => {
          state.pageSize = Number(e.target.value); state.page = 1;
          try { localStorage.setItem('lv.pageSize', String(state.pageSize)); } catch (err) { /* 저장 불가 환경 */ }
          drawGrid();
        } }, PAGE_SIZES.map((n) => el('option', { value: String(n), selected: n === state.pageSize }, `${n}개씩`))),
      ]);
    }
  }

  return () => document.removeEventListener('click', closeExportMenus);
}
