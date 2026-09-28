import { el, clear, icon } from './util.js';

const STATE = { pending: ['pending', '미검수', 'muted'], progress: ['progress', '검수 중', 'warn'], done: ['done', '검수 완료', 'ok'], error: ['error', '오류', 'bad'] };
const stateOf = (doc) => doc.errors && doc.errors.length ? STATE.error
  : doc.review === 'done' ? STATE.done
    : doc.review === 'progress' ? STATE.progress : STATE.pending;

export function createDocumentRail(host, docs, currentId, onSelect, { onToggleCollapse } = {}) {
  let query = '', filter = 'all';
  const search = el('input', { class: 'doc-rail-search', type: 'search', placeholder: '문서 ID·유형 검색', 'aria-label': '문서 검색', oninput: (e) => { query = e.target.value; draw(); } });
  const select = el('select', { class: 'doc-rail-filter', 'aria-label': '검수 상태 필터', onchange: (e) => { filter = e.target.value; draw(); } }, [
    el('option', { value: 'all' }, '모든 상태'), el('option', { value: 'pending' }, '미검수'),
    el('option', { value: 'progress' }, '검수 중'), el('option', { value: 'done' }, '검수 완료'),
    el('option', { value: 'error' }, '오류'),
  ]);
  const titleCount = el('span', { class: 'doc-rail-count' }, String(docs.length));
  const collapseBtn = el('button', { class: 'btn ghost icon', title: '문서 목록 접기', 'aria-label': '문서 목록 접기', onclick: () => onToggleCollapse && onToggleCollapse() }, icon('panel-left-close'));
  const vlabel = el('span', { class: 'doc-rail-vlabel' }, '문서');
  const list = el('nav', { class: 'doc-rail-list', 'aria-label': '번들 문서' });
  host.append(
    el('div', { class: 'doc-rail-head panel-head' }, [el('span', {}, '문서'), el('div', { class: 'grow' }), titleCount, collapseBtn]),
    el('div', { class: 'doc-rail-filters' }, [search, select]),
    list,
    vlabel,
  );

  function draw() {
    const q = query.trim().toLocaleLowerCase();
    const visible = docs.filter((doc) => {
      const [status] = stateOf(doc);
      return (filter === 'all' || filter === status) && (!q || `${doc.id} ${doc.doc_type || ''}`.toLocaleLowerCase().includes(q));
    });
    titleCount.textContent = `${visible.length}/${docs.length}`;
    clear(list);
    if (!visible.length) { list.appendChild(el('div', { class: 'doc-rail-empty' }, '문서가 없습니다.')); return; }
    visible.forEach((doc) => {
      const [, label, tone] = stateOf(doc);
      const mismatches = ['ao', 'harness'].reduce((n, side) => n + (doc.score?.[side]?.MISMATCH || 0) + (doc.score?.[side]?.TYPE_MISMATCH || 0) + (doc.score?.[side]?.MISSING || 0) + (doc.score?.[side]?.EXTRA || 0), 0);
      const button = el('button', { class: `doc-rail-item ${doc.id === currentId ? 'active' : ''}`, 'aria-current': doc.id === currentId ? 'page' : null,
        title: `${doc.id}${doc.doc_type ? ` · ${doc.doc_type}` : ''}`, onclick: () => onSelect(doc.id) }, [
        el('div', { class: 'dr-row' }, [
          el('span', { class: 'dr-id' }, doc.id),
          el('span', { class: `badge badge-${tone}` }, label),
        ]),
        el('div', { class: 'dr-row' }, [
          el('span', { class: 'dr-type' }, doc.doc_type || '유형 미지정'),
          mismatches ? el('span', { class: 'dr-mismatch' }, `불일치 ${mismatches}`) : null,
        ]),
      ]);
      list.appendChild(button);
    });
  }
  draw();
  return {
    update(nextDocs, nextCurrentId) { docs = nextDocs || []; currentId = nextCurrentId; draw(); },
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
