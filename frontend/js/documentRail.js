import { el, clear, mount, debounce, icon, getDocTypeFilter, matchDocType, docTypeSelect } from './util.js';

const STATE = { pending: ['pending', '미검수', 'muted'], progress: ['progress', '검수 중', 'warn'], done: ['done', '검수 완료', 'ok'], error: ['error', '오류', 'bad'] };
const stateOf = (doc) => doc.errors && doc.errors.length ? STATE.error
  : doc.review === 'done' ? STATE.done
    : doc.review === 'progress' ? STATE.progress : STATE.pending;

// 검색어·상태 필터는 문서를 옮겨 다녀도(레일 재생성) 유지한다. 유형 필터는 util 에서 목록 화면과 공유.
// page 가 null 이면 현재 문서가 있는 쪽을 보여 준다. 수천 건을 한 번에 그리지 않도록 PAGE 건씩 끊는다.
const kept = { bundleId: null, query: '', filter: 'all', page: null };
const PAGE = 100;

export function createDocumentRail(host, docs, currentId, onSelect, { onToggleCollapse, bundleId } = {}) {
  if (kept.bundleId !== bundleId) Object.assign(kept, { bundleId, query: '', filter: 'all', page: null });
  const search = el('input', { class: 'doc-rail-search', type: 'search', placeholder: '문서 ID·유형 검색', 'aria-label': '문서 검색', value: kept.query, oninput: debounce((e) => { kept.query = e.target.value; kept.page = null; draw(); }, 150) });
  const select = el('select', { class: 'doc-rail-filter', 'aria-label': '검수 상태 필터', onchange: (e) => { kept.filter = e.target.value; kept.page = null; draw(); } }, [
    el('option', { value: 'all' }, '모든 상태'), el('option', { value: 'pending' }, '미검수'),
    el('option', { value: 'progress' }, '검수 중'), el('option', { value: 'done' }, '검수 완료'),
    el('option', { value: 'error' }, '오류'),
  ]);
  select.value = kept.filter;
  const typeHost = el('div', { class: 'doc-rail-typehost' });
  const drawTypes = () => { clear(typeHost); typeHost.appendChild(docTypeSelect(docs, bundleId, () => { kept.page = null; draw(); }, 'doc-rail-filter')); };
  const titleCount = el('span', { class: 'doc-rail-count' }, String(docs.length));
  const collapseBtn = el('button', { class: 'btn ghost icon', title: '문서 목록 접기', 'aria-label': '문서 목록 접기', onclick: () => onToggleCollapse && onToggleCollapse() }, icon('panel-left-close'));
  const vlabel = el('span', { class: 'doc-rail-vlabel' }, '문서');
  const list = el('nav', { class: 'doc-rail-list', 'aria-label': '번들 문서' });
  const pagerHost = el('div', { class: 'doc-rail-pager', style: 'display:none' });
  host.append(
    el('div', { class: 'doc-rail-head panel-head' }, [el('span', {}, '문서'), el('div', { class: 'grow' }), titleCount, collapseBtn]),
    el('div', { class: 'doc-rail-filters' }, [search, select, typeHost]),
    list,
    pagerHost,
    vlabel,
  );

  function draw() {
    const q = kept.query.trim().toLocaleLowerCase();
    const type = getDocTypeFilter(bundleId);
    const visible = docs.filter((doc) => {
      const [status] = stateOf(doc);
      return (kept.filter === 'all' || kept.filter === status) && matchDocType(doc, type) && (!q || `${doc.id} ${doc.doc_type || ''}`.toLocaleLowerCase().includes(q));
    });
    titleCount.textContent = `${visible.length}/${docs.length}`;
    clear(list);
    const last = Math.max(0, Math.ceil(visible.length / PAGE) - 1);
    const cur = visible.findIndex((doc) => doc.id === currentId);
    const page = Math.min(last, kept.page ?? (cur >= 0 ? Math.floor(cur / PAGE) : 0));
    drawPager(page, last, visible.length);
    if (!visible.length) { list.appendChild(el('div', { class: 'doc-rail-empty' }, '문서가 없습니다.')); return; }
    visible.slice(page * PAGE, (page + 1) * PAGE).forEach((doc) => {
      const [, label, tone] = stateOf(doc);
      const mismatches = doc.mismatch || 0;
      const off = doc.enabled === false;
      const button = el('button', { class: `doc-rail-item ${doc.id === currentId ? 'active' : ''} ${off ? 'is-disabled' : ''}`, 'aria-current': doc.id === currentId ? 'page' : null,
        title: `${doc.id}${doc.doc_type ? ` · ${doc.doc_type}` : ''}${off ? ' (비활성)' : ''}`, onclick: () => onSelect(doc.id) }, [
        el('div', { class: 'dr-row' }, [
          el('span', { class: 'dr-id' }, doc.id),
          el('span', { class: `badge badge-${tone}` }, label),
        ]),
        el('div', { class: 'dr-row' }, [
          el('span', { class: 'dr-type' }, doc.doc_type || '유형 미지정'),
          mismatches ? el('span', { class: 'dr-mismatch', title: 'AO·Harness 중 하나라도 다른 항목 수' }, `불일치 ${mismatches}`) : null,
          off ? el('span', { class: 'dr-off' }, '비활성') : null,
        ]),
      ]);
      list.appendChild(button);
    });
  }
  function drawPager(page, last, total) {
    pagerHost.style.display = last > 0 ? '' : 'none';
    if (!last) return;
    const go = (n) => { kept.page = n; draw(); list.scrollTop = 0; };
    mount(pagerHost, [
      el('button', { class: 'btn ghost sm icon', disabled: page <= 0, 'aria-label': '이전 문서 묶음', onclick: () => go(page - 1) }, icon('chevron-left')),
      el('span', {}, `${page * PAGE + 1}–${Math.min(total, (page + 1) * PAGE)} / ${total}`),
      el('button', { class: 'btn ghost sm icon', disabled: page >= last, 'aria-label': '다음 문서 묶음', onclick: () => go(page + 1) }, icon('chevron-right')),
    ]);
  }

  drawTypes();
  draw();
  return {
    update(nextDocs, nextCurrentId) { docs = nextDocs || []; currentId = nextCurrentId; kept.page = null; drawTypes(); draw(); },
    setCurrent(nextCurrentId) { currentId = nextCurrentId; draw(); },
    setCollapsed(collapsed) {
      collapseBtn.title = collapsed ? '문서 목록 펼치기' : '문서 목록 접기';
      collapseBtn.setAttribute('aria-label', collapseBtn.title);
      clear(collapseBtn);
      collapseBtn.appendChild(icon(collapsed ? 'panel-left-open' : 'panel-left-close'));
    },
    destroy() { clear(host); },
  };
}
