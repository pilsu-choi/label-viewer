import { el, clear } from './util.js';

// 읽기 전용 JSON 트리. 큰 배열은 펼칠 때만 자식 노드를 만든다.
export function createJsonViewer(host) {
  let raw = '', data = null, invalid = false, loaded = false;
  const search = el('input', { class: 'json-search', type: 'search', placeholder: '키 또는 값 검색', 'aria-label': 'JSON 검색', oninput: draw });
  const count = el('span', { class: 'json-count' });
  const tree = el('div', { class: 'json-tree' });
  host.append(el('div', { class: 'json-viewer-tools' }, [search, count]), tree);

  function primitive(value) {
    const kind = value === null ? 'null' : typeof value;
    return el('span', { class: `json-${kind}` }, JSON.stringify(value));
  }

  function matches(value, key, query) {
    if (!query || String(key).toLowerCase().includes(query)) return true;
    if (value && typeof value === 'object') return Object.entries(value).some(([k, v]) => matches(v, k, query));
    return String(value).toLowerCase().includes(query);
  }

  function renderNode(value, key, path, depth, query) {
    const label = el('span', { class: 'json-key', title: path }, String(key));
    if (!value || typeof value !== 'object') {
      return el('div', { class: 'json-node json-primitive' }, [label, el('span', { class: 'json-colon' }, ': '), primitive(value)]);
    }
    const entries = Object.entries(value);
    if (!entries.length) return el('div', { class: 'json-node json-primitive' }, [label, el('span', { class: 'json-colon' }, ': '), el('span', { class: 'json-empty' }, Array.isArray(value) ? '[]' : '{}')]);
    const selfMatch = query && String(key).toLowerCase().includes(query);
    const childQuery = selfMatch ? '' : query;
    const visible = childQuery ? entries.filter(([k, v]) => matches(v, k, childQuery)) : entries;
    const details = el('details', { class: 'json-node' });
    const summary = el('summary', { class: 'json-summary' }, [label, el('span', { class: 'json-colon' }, ': '),
      el('span', { class: 'json-meta' }, `${Array.isArray(value) ? '[' : '{'}${entries.length}${Array.isArray(value) ? ']' : '}'}`)]);
    const children = el('div', { class: 'json-children' });
    let populated = false;
    const populate = () => {
      if (populated) return;
      populated = true;
      for (const [k, v] of visible) children.appendChild(renderNode(v, k, `${path}${Array.isArray(value) ? `[${k}]` : `.${k}`}`, depth + 1, childQuery));
    };
    details.append(summary, children);
    details.addEventListener('toggle', () => { if (details.open) populate(); });
    if (depth === 0 || (query && !selfMatch)) { details.open = true; populate(); }
    return details;
  }

  function draw() {
    clear(tree);
    if (invalid) { tree.appendChild(el('pre', { class: 'json-error' }, raw)); count.textContent = '유효하지 않은 JSON'; return; }
    if (!loaded) { count.textContent = ''; return; }
    const query = search.value.trim().toLowerCase();
    if (query && !matches(data, '$', query)) { count.textContent = '결과 없음'; return; }
    tree.appendChild(renderNode(data, '$', '$', 0, query));
    count.textContent = query ? '일치 항목 표시' : '접어서 탐색';
  }

  return {
    show(text) {
      raw = text;
      try { data = JSON.parse(text); invalid = false; } catch { data = null; invalid = true; }
      loaded = true;
      draw();
    },
    getText: () => raw,
  };
}
