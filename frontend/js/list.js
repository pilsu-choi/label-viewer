import { el, mount, clear, fmtPct, scoreCard, icon, menuButton } from './util.js';
import { api } from './api.js';
import { navigate } from './router.js';

function docBadges(has) {
  const order = [['original', '원본'], ['preprocessed', '전처리'], ['ao_extract', 'AO'], ['harness', 'Harness'], ['golden', 'Golden']];
  return el('div', { class: 'doc-badges' }, order.map(([k, label]) =>
    el('span', { class: `mini-badge ${has[k] ? 'on' : 'off'}`, title: `${label} ${has[k] ? '있음' : '없음'}` }, label)));
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
  if (review === 'done') return el('span', { class: 'doc-review done' }, [icon('check'), '검수 완료']);
  if (review === 'progress') return el('span', { class: 'doc-review' }, '검수 중');
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
        el('button', { class: state.view === 'grid' ? 'active' : '', onclick: () => { state.view = 'grid'; draw(); }, title: '썸네일', 'aria-label': '썸네일 보기' }, icon('grid')),
        el('button', { class: state.view === 'list' ? 'active' : '', onclick: () => { state.view = 'list'; draw(); }, title: '목록', 'aria-label': '목록 보기' }, icon('list')),
      ]),
    ]);
  }

  function exportMenu() {
    return menuButton('내보내기', [
      el('a', { href: api.exportGoldenXlsxUrl(bundleId) }, [el('b', {}, 'Excel'), el('span', {}, '요약·필드·표·비교 시트')]),
      el('a', { href: api.exportGoldenZipUrl(bundleId) }, [el('b', {}, 'Golden ZIP'), el('span', {}, '정답지 JSON 전체')]),
    ]);
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
      el('label', { class: 'search-box' }, [
        icon('search'),
        el('input', { type: 'search', placeholder: '문서 ID나 유형으로 찾기', value: state.q,
          oninput: (e) => { state.q = e.target.value; drawGrid(); } }),
      ]),
      exportMenu(),
    ]);

    const summary = b.summary;
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
        scoreCard('AO Extract', sc.ao),
        el('div', { class: `ov-delta ${delta == null ? '' : delta >= 0 ? 'up' : 'down'}` }, delta == null ? '—'
          : [el('b', {}, `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}p`), el('span', {}, 'Harness 보정')]),
        scoreCard('Harness', sc.harness),
      ]),
    ]);

    const gridHost = el('div');
    mount(screen, [topbar, el('div', { class: 'list-body' }, [overview, chips(summary), gridHost])]);
    drawGrid();

    function drawGrid() {
      const docs = filteredDocs();
      if (!docs.length) { mount(gridHost, el('div', { class: 'empty-state' }, '조건에 맞는 문서가 없습니다. 필터나 검색어를 바꿔 보세요.')); return; }
      if (state.view === 'grid') {
        mount(gridHost, el('div', { class: 'doc-grid' }, docs.map((d) => {
          const card = el('div', { class: 'doc-card', onclick: () => navigate(`#/b/${encodeURIComponent(bundleId)}/d/${encodeURIComponent(d.id)}`) }, [
            thumbImg(bundleId, d),
            reviewBadge(d.review),
            el('div', { class: 'doc-info' }, [
              el('div', { class: 'doc-id' }, d.id),
              el('div', { class: 'doc-type' }, d.doc_type || '문서 유형 없음'),
              docBadges(d.has),
              d.errors && d.errors.length ? el('div', { class: 'doc-err', title: d.errors.join('\n') }, `읽지 못한 파일 ${d.errors.length}개`) : null,
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
