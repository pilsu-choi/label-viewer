import { el, mount, icon } from './util.js';
import { api } from './api.js';
import { navigate } from './router.js';

const PAGE_SIZES = [25, 50, 100];

function pageNumbers(cur, last) {
  const out = [];
  for (let i = 1; i <= last; i += 1) {
    if (i === 1 || i === last || Math.abs(i - cur) <= 1) out.push(i);
    else if (out[out.length - 1] !== '…') out.push('…');
  }
  return out;
}

function createdLabel(value) {
  if (!value) return '생성일 미상';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ko-KR', { dateStyle: 'medium', timeStyle: 'short' });
}

export function renderBundles(root) {
  const state = { items: [], total: 0, filteredTotal: 0, query: '', sort: 'newest', page: 1, pageSize: 50, loading: true, error: '' };
  let destroyed = false;
  let requestGeneration = 0, searchTimer = null;

  const count = el('span', { class: 'bundles-count', 'aria-live': 'polite' });
  const content = el('div');
  const search = el('input', { type: 'search', placeholder: '이름 또는 ID 검색', 'aria-label': '번들 이름 또는 ID 검색',
    oninput: (e) => {
      state.query = e.target.value; state.page = 1;
      // Invalidate any active response immediately, before the debounce timer fires.
      requestGeneration++;
      state.loading = true; state.error = '';
      drawContent();
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => { searchTimer = null; load(); }, 200);
    } });
  const sort = el('select', { 'aria-label': '정렬', onchange: (e) => { state.sort = e.target.value; state.page = 1; load(); } }, [
    el('option', { value: 'newest' }, '최신순'),
    el('option', { value: 'oldest' }, '오래된순'),
    el('option', { value: 'name' }, '이름순'),
  ]);

  mount(root, el('div', { class: 'bundles-shell' }, [
    el('header', { class: 'bundles-head' }, [
      el('a', { class: 'brand', href: '#/' }, 'Label Viewer'),
      el('a', { class: 'btn ghost sm', href: '#/' }, [icon('upload'), '업로드']),
    ]),
    el('main', { class: 'bundles-main' }, [
      el('div', { class: 'bundles-title-row' }, [
        el('div', {}, [el('h1', {}, '전체 번들'), el('p', {}, '업로드한 번들을 검색하고 정렬합니다.')]),
        count,
      ]),
      el('div', { class: 'bundles-toolbar' }, [
        el('label', { class: 'search-box' }, [icon('search'), search]),
        sort,
      ]),
      content,
    ]),
  ]));

  function drawContent() {
    if (destroyed) return;
    if (state.loading) {
      count.textContent = '';
      mount(content, el('div', { class: 'loading-block' }, '번들 목록을 불러오는 중…'));
      return;
    }
    if (state.error) {
      count.textContent = '';
      mount(content, el('div', { class: 'error-block' }, [
        el('div', {}, `번들 목록을 불러오지 못했습니다: ${state.error}`),
        el('button', { class: 'btn sm', onclick: load }, '다시 시도'),
      ]));
      return;
    }

    const items = state.items;
    count.textContent = `${state.filteredTotal.toLocaleString()}개 / ${state.total.toLocaleString()}개`;
    if (!items.length) {
      mount(content, el('div', { class: 'empty bundles-empty' }, [
        icon('folder'),
        el('div', { class: 'empty-title' }, state.total ? '검색 결과가 없습니다' : '아직 올린 번들이 없습니다'),
        el('div', { class: 'empty-desc' }, state.total ? '검색어를 바꿔 보세요.' : '홈에서 폴더나 ZIP을 올리면 여기에 표시됩니다.'),
      ]));
      return;
    }

    const last = Math.max(1, Math.ceil(state.filteredTotal / state.pageSize));
    state.page = Math.min(Math.max(state.page, 1), last);
    const from = (state.page - 1) * state.pageSize;
    const list = el('div', { class: 'recent-list bundle-directory-list' });
    for (const bundle of items) {
      const counts = bundle.counts || {};
      const open = () => navigate(`#/b/${encodeURIComponent(bundle.id)}`);
      list.appendChild(el('div', { class: 'recent-item bundle-directory-item', role: 'link', tabindex: '0', onclick: open,
        onkeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } } }, [
        el('span', { class: 'name' }, [
          el('b', { title: bundle.name || bundle.id }, bundle.name || bundle.id),
          el('small', {}, [el('span', {}, bundle.id), ' · ', createdLabel(bundle.created_at)]),
        ]),
        el('span', { class: 'cnt' }, [el('b', {}, String(counts.docs || 0)), '문서']),
        el('span', { class: 'cnt' }, [el('b', {}, String(counts.golden || 0)), 'Golden']),
        el('span', { class: 'cnt' }, [el('b', {}, String(counts.reviewed || 0)), '검수 완료']),
        el('span', { class: `cnt ${counts.error ? 'bad' : ''}` }, [el('b', {}, String(counts.error || 0)), '오류']),
      ]));
    }

    const start = from + 1;
    const pager = el('nav', { class: 'pager', 'aria-label': '번들 페이지' }, [
      el('span', { class: 'pager-range' }, `${start.toLocaleString()}–${Math.min(state.filteredTotal, from + items.length).toLocaleString()} / ${state.filteredTotal.toLocaleString()}건`),
      el('div', { class: 'pager-pages' }, [
        el('button', { class: 'btn ghost sm icon', disabled: state.page <= 1, 'aria-label': '이전 페이지', onclick: () => { state.page -= 1; load(); } }, icon('chevron-left')),
        ...pageNumbers(state.page, last).map((n) => n === '…' ? el('span', { class: 'pager-gap' }, '…')
          : el('button', { class: `btn ghost sm ${n === state.page ? 'active' : ''}`, 'aria-current': n === state.page ? 'page' : null,
            onclick: () => { state.page = n; load(); } }, String(n))),
        el('button', { class: 'btn ghost sm icon', disabled: state.page >= last, 'aria-label': '다음 페이지', onclick: () => { state.page += 1; load(); } }, icon('chevron-right')),
      ]),
      el('select', { class: 'pager-size', 'aria-label': '페이지당 번들 수', value: String(state.pageSize), onchange: (e) => { state.pageSize = Number(e.target.value); state.page = 1; load(); } },
        PAGE_SIZES.map((n) => el('option', { value: String(n), selected: n === state.pageSize }, `${n}개씩`))),
    ]);
    mount(content, [list, pager]);
  }

  function load() {
    if (searchTimer) { clearTimeout(searchTimer); searchTimer = null; }
    const generation = ++requestGeneration;
    state.loading = true;
    state.error = '';
    drawContent();
    api.listBundlePage({ query: state.query, sort: state.sort, page: state.page, page_size: state.pageSize }).then((result) => {
      if (destroyed || generation !== requestGeneration) return;
      state.items = Array.isArray(result.items) ? result.items : [];
      state.total = Number(result.total) || 0;
      state.filteredTotal = Number(result.filtered_total) || 0;
      state.page = Number(result.page) || 1;
      state.pageSize = Number(result.page_size) || state.pageSize;
      state.loading = false;
      drawContent();
    }).catch((err) => {
      if (destroyed || generation !== requestGeneration) return;
      state.error = err.message || '네트워크 오류';
      state.loading = false;
      drawContent();
    });
  }

  drawContent();
  load();
  return () => { destroyed = true; requestGeneration++; clearTimeout(searchTimer); };
}
