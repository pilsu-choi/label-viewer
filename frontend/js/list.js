import { el, mount, clear, fmtPct } from './util.js';
import { api } from './api.js';
import { navigate } from './router.js';

const STATUS_KEYS = ['MATCH', 'MISMATCH', 'MISSING', 'EXTRA', 'TYPE_MISMATCH'];
const STATUS_COLOR = { MATCH: 'var(--ok)', MISMATCH: 'var(--bad)', MISSING: 'var(--warn)', EXTRA: 'var(--extra)', TYPE_MISMATCH: 'var(--type)' };

function scoreCard(title, score) {
  if (!score) return el('div', { class: 'score-card' }, [el('div', { class: 'sc-head' }, [el('span', { class: 'sc-name' }, title), el('span', { class: 'sc-acc' }, '—')]), el('div', { class: 'hint' }, 'Golden 필요')]);
  const total = score.total || 0;
  const bar = el('div', { class: 'score-bar' });
  if (total) {
    for (const k of STATUS_KEYS) {
      const n = score[k] || 0;
      if (!n) continue;
      bar.appendChild(el('span', { style: `width:${(n / total) * 100}%;background:${STATUS_COLOR[k]}`, title: `${k} ${n}` }));
    }
  }
  return el('div', { class: 'score-card' }, [
    el('div', { class: 'sc-head' }, [el('span', { class: 'sc-name' }, title), el('span', { class: 'sc-acc' }, fmtPct(score.accuracy))]),
    bar,
  ]);
}

function docBadges(has) {
  const order = [['original', 'O'], ['preprocessed', 'P'], ['ao_extract', 'AO'], ['harness', 'H'], ['golden', 'G']];
  return el('div', { class: 'doc-badges' }, order.map(([k, label]) =>
    el('span', { class: `mini-badge ${has[k] ? 'on' : 'off'}`, title: `${label}: ${has[k] ? '있음' : '없음'}` }, label)));
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
  if (review === 'done') return el('span', { class: 'badge badge-ok doc-review' }, '완료');
  if (review === 'progress') return el('span', { class: 'badge badge-warn doc-review' }, '진행중');
  return null;
}

function thumbImg(bundleId, doc) {
  const wrap = el('div', { class: 'doc-thumb' });
  if (!doc.has.original && !doc.has.preprocessed) {
    wrap.appendChild(el('span', { class: 'ph' }, 'No Image'));
    return wrap;
  }
  const view = doc.has.original ? 'original' : 'preprocessed';
  const img = el('img', { loading: 'lazy', src: api.imageUrl(bundleId, doc.id, view, 1), alt: doc.id });
  img.addEventListener('error', () => {
    if (view === 'original' && doc.has.preprocessed) { img.src = api.imageUrl(bundleId, doc.id, 'preprocessed', 1); }
    else { clear(wrap); wrap.appendChild(el('span', { class: 'ph' }, 'No Image')); }
  }, { once: true });
  wrap.appendChild(img);
  return wrap;
}

export function renderList(root, bundleId) {
  const state = { bundle: null, filter: 'all', q: '', view: 'grid', loading: true, error: null };

  const screen = el('div', { class: 'list-screen' });
  mount(root, screen);
  const closeExportMenus = () => screen.querySelectorAll('.export-pop').forEach((p) => { p.style.display = 'none'; });
  document.addEventListener('click', closeExportMenus);
  draw();
  load();

  function load() {
    api.getBundle(bundleId).then((b) => { state.bundle = b; state.loading = false; draw(); })
      .catch((e) => { state.error = e.message; state.loading = false; draw(); });
  }

  function filteredDocs() {
    if (!state.bundle) return [];
    let docs = state.bundle.docs;
    if (state.filter === 'golden') docs = docs.filter((d) => d.has.golden);
    else if (state.filter === 'nogolden') docs = docs.filter((d) => !d.has.golden);
    else if (state.filter === 'done') docs = docs.filter((d) => d.review === 'done');
    else if (state.filter === 'pending') docs = docs.filter((d) => d.review !== 'done');
    else if (state.filter === 'missing') docs = docs.filter((d) => !d.has.original || !d.has.preprocessed || !d.has.ao_extract || !d.has.harness || !d.has.golden);
    else if (state.filter === 'error') docs = docs.filter((d) => d.errors && d.errors.length);
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
        onclick: () => { state.filter = key; draw(); } }, [label, el('span', { class: 'n' }, String(n))])),
      el('div', { class: 'view-toggle' }, [
        el('button', { class: state.view === 'grid' ? 'active' : '', onclick: () => { state.view = 'grid'; draw(); }, title: 'Grid' }, '▦'),
        el('button', { class: state.view === 'list' ? 'active' : '', onclick: () => { state.view = 'list'; draw(); }, title: 'List' }, '☰'),
      ]),
    ]);
  }

  function exportMenu() {
    const menu = el('div', { class: 'chip', style: 'position:relative;cursor:pointer', onclick: (e) => {
      e.stopPropagation();
      const pop = e.currentTarget.querySelector('.export-pop');
      pop.style.display = pop.style.display === 'block' ? 'none' : 'block';
    } }, [
      'Export ▾',
      el('div', { class: 'export-pop', style: 'display:none;position:absolute;right:0;top:100%;margin-top:4px;background:var(--surface);border:1px solid var(--line-strong);border-radius:6px;box-shadow:var(--shadow-pop);z-index:50;min-width:160px' }, [
        el('a', { href: api.exportGoldenZipUrl(bundleId), class: 'btn btn-ghost', style: 'display:flex;width:100%;border-radius:0;justify-content:flex-start' }, 'Golden ZIP'),
        el('a', { href: api.exportGoldenXlsxUrl(bundleId), class: 'btn btn-ghost', style: 'display:flex;width:100%;border-radius:0;justify-content:flex-start' }, 'Excel'),
      ]),
    ]);
    return menu;
  }

  function draw() {
    if (state.loading) { mount(screen, el('div', { class: 'loading-block' }, '불러오는 중…')); return; }
    if (state.error) { mount(screen, el('div', { class: 'error-block' }, `번들을 불러오지 못했습니다: ${state.error}`)); return; }
    const b = state.bundle;
    const topbar = el('div', { class: 'topbar' }, [
      el('a', { class: 'brand', href: '#/' }, 'Label Viewer'),
      el('div', { class: 'sep' }),
      el('div', { class: 'title' }, b.name || b.id),
      el('div', { class: 'grow' }),
      el('div', { class: 'search-box' }, [
        '🔍',
        el('input', { type: 'search', placeholder: '문서 ID·유형 검색', value: state.q,
          oninput: (e) => { state.q = e.target.value; drawGrid(); } }),
      ]),
      exportMenu(),
    ]);

    const summary = b.summary;
    const summaryBar = el('div', { class: 'summary-bar' }, [
      el('div', { class: 'summary-stat' }, [el('span', { class: 'v' }, String(summary.docs)), el('span', { class: 'l' }, '전체 문서')]),
      el('div', { class: 'summary-stat' }, [el('span', { class: 'v' }, String(summary.golden)), el('span', { class: 'l' }, 'Golden 있음')]),
      el('div', { class: 'summary-stat' }, [el('span', { class: 'v' }, String(summary.reviewed)), el('span', { class: 'l' }, '검수 완료')]),
      el('div', { class: 'summary-stat' }, [el('span', { class: 'v' }, String(summary.missing)), el('span', { class: 'l' }, '데이터 누락')]),
      el('div', { class: 'summary-stat' }, [el('span', { class: 'v' }, String(summary.error)), el('span', { class: 'l' }, '오류')]),
    ]);
    const scoreCards = el('div', { class: 'score-cards' }, [scoreCard('AO Extract', summary.score && summary.score.ao), scoreCard('Harness', summary.score && summary.score.harness)]);

    const gridHost = el('div');
    mount(screen, [topbar, summaryBar, scoreCards, chips(summary), gridHost]);
    drawGrid();

    function drawGrid() {
      const docs = filteredDocs();
      if (!docs.length) { mount(gridHost, el('div', { class: 'empty-state' }, '조건에 맞는 문서가 없습니다.')); return; }
      if (state.view === 'grid') {
        mount(gridHost, el('div', { class: 'doc-grid' }, docs.map((d) => {
          const card = el('div', { class: 'doc-card', onclick: () => navigate(`#/b/${encodeURIComponent(bundleId)}/d/${encodeURIComponent(d.id)}`) }, [
            thumbImg(bundleId, d),
            reviewBadge(d.review),
            el('div', { class: 'doc-info' }, [
              el('div', { class: 'doc-id' }, d.id),
              docBadges(d.has),
              accBars(d.score),
            ]),
          ]);
          return card;
        })));
      } else {
        mount(gridHost, el('div', {}, docs.map((d) => el('div', { class: 'doc-list-row', onclick: () => navigate(`#/b/${encodeURIComponent(bundleId)}/d/${encodeURIComponent(d.id)}`) }, [
          el('span', { class: 'doc-id' }, d.id),
          docBadges(d.has),
          el('span', { class: 'doc-type' }, d.doc_type || '—'),
          reviewBadge(d.review) || el('span'),
        ]))));
      }
    }
  }

  return () => document.removeEventListener('click', closeExportMenus);
}
