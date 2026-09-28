import { el, clear } from './util.js';

const stateOf = (doc) => doc.errors && doc.errors.length ? ['error', '오류']
  : doc.review === 'done' ? ['done', '검수 완료']
    : doc.review === 'progress' ? ['progress', '검수 중'] : ['pending', '미검수'];

export function createDocumentRail(host, docs, currentId, onSelect) {
  let query = '', filter = 'all';
  const search = el('input', { class: 'doc-rail-search', type: 'search', placeholder: '문서 ID·유형 검색', 'aria-label': '문서 검색', oninput: (e) => { query = e.target.value; draw(); } });
  const select = el('select', { class: 'doc-rail-filter', 'aria-label': '검수 상태 필터', onchange: (e) => { filter = e.target.value; draw(); } }, [
    el('option', { value: 'all' }, '모든 상태'), el('option', { value: 'pending' }, '미검수'),
    el('option', { value: 'progress' }, '검수 중'), el('option', { value: 'done' }, '검수 완료'),
    el('option', { value: 'error' }, '오류'),
  ]);
  const titleCount = el('span', { class: 'doc-rail-count' }, String(docs.length));
  const list = el('nav', { class: 'doc-rail-list', 'aria-label': '번들 문서' });
  host.append(el('div', { class: 'doc-rail-head' }, [el('div', { class: 'doc-rail-title' }, ['Documents', titleCount]), search, select]), list);

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
      const [status, label] = stateOf(doc);
      const mismatches = ['ao', 'harness'].reduce((n, side) => n + (doc.score?.[side]?.MISMATCH || 0) + (doc.score?.[side]?.TYPE_MISMATCH || 0) + (doc.score?.[side]?.MISSING || 0) + (doc.score?.[side]?.EXTRA || 0), 0);
      const button = el('button', { class: `doc-rail-item ${doc.id === currentId ? 'active' : ''}`, 'aria-current': doc.id === currentId ? 'page' : null,
        title: `${doc.id}${doc.doc_type ? ` · ${doc.doc_type}` : ''}`, onclick: () => onSelect(doc.id) }, [
        el('span', { class: 'doc-rail-id' }, doc.id),
        el('span', { class: 'doc-rail-type' }, doc.doc_type || '유형 미지정'),
        el('span', { class: 'doc-rail-meta' }, [
          el('span', { class: `doc-rail-state ${status}` }, label),
          mismatches ? el('span', { class: 'doc-rail-mismatch' }, `${mismatches} mismatch`) : null,
        ]),
      ]);
      list.appendChild(button);
    });
  }
  draw();
  return {
    update(nextDocs, nextCurrentId) { docs = nextDocs || []; currentId = nextCurrentId; draw(); },
    setCurrent(nextCurrentId) { currentId = nextCurrentId; draw(); },
    destroy() { clear(host); },
  };
}
