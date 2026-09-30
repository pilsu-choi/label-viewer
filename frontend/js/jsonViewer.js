import { el, clear, debounce, toast, icon } from './util.js';

// 테마 인식 트리 뷰의 읽기 전용 JSON 뷰어. 큰 배열은 펼칠 때만 자식을 렌더한다.
export function createJsonViewer(host) {
  let data = null, raw = '', mode = 'message', query = '', selectedPath = null;
  const openState = new Map();
  let forceAll = null;
  let hitCache = new WeakMap(), hitQuery = null; // 객체별 하위 일치 수(검색어가 바뀔 때만 비운다)

  const search = el('input', { class: 'json-search', type: 'search', placeholder: '키 또는 값 검색', 'aria-label': 'JSON 검색', oninput: debounce(onSearch, 120) });
  const count = el('span', { class: 'json-count' });
  const btn = (name, title, onclick) => el('button', { class: 'btn ghost sm icon', title, 'aria-label': title, onclick }, icon(name));
  const btnExpand = btn('chevrons-up-down', '모두 펼치기', () => { forceAll = true; openState.clear(); drawTree(); });
  const btnCollapse = btn('chevrons-down-up', '모두 접기', () => { forceAll = false; openState.clear(); drawTree(); });
  const btnCopy = btn('copy', '복사', () => { navigator.clipboard && navigator.clipboard.writeText(raw).then(() => toast('복사했습니다.')).catch(() => toast('복사 실패', 'error')); });
  const toolbar = el('div', { class: 'panel-head' }, [
    el('div', { class: 'json-search-wrap' }, [icon('search'), search]), count, el('div', { class: 'grow' }), btnExpand, btnCollapse, btnCopy,
  ]);
  const tree = el('div', { class: 'json-tree' });
  const pathText = el('span', { class: 'json-path' });
  const statusBar = el('div', { class: 'json-status', style: 'display:none' }, [pathText,
    el('button', { class: 'btn ghost sm icon', title: '경로 복사', 'aria-label': '경로 복사', onclick: () => { navigator.clipboard && navigator.clipboard.writeText(pathText.textContent).then(() => toast('경로를 복사했습니다.')); } }, icon('copy'))]);
  host.append(toolbar, tree, statusBar);

  function onSearch() { query = search.value.trim().toLowerCase(); if (mode === 'tree') drawTree(); }

  function matchCount(value, key, q) {
    const isObj = value && typeof value === 'object';
    if (q !== hitQuery) { hitCache = new WeakMap(); hitQuery = q; }
    let n = String(key).toLowerCase().includes(q) ? 1 : 0;
    if (isObj) {
      if (!hitCache.has(value)) hitCache.set(value, Object.entries(value).reduce((s, [k, v]) => s + matchCount(v, k, q), 0));
      n += hitCache.get(value);
    } else if (!n && String(value).toLowerCase().includes(q)) n = 1;
    return n;
  }

  function markHits(text, q) {
    if (!q) return [text];
    const i = text.toLowerCase().indexOf(q);
    return i < 0 ? [text] : [text.slice(0, i), el('mark', { class: 'json-hit' }, text.slice(i, i + q.length)), text.slice(i + q.length)].filter((s) => s !== '');
  }

  function primitive(value) {
    if (typeof value === 'string') {
      const node = el('span', { class: 'json-string' }, ['"', ...markHits(value, query), '"']);
      if (value.length > 60) node.title = value;
      return node;
    }
    return el('span', { class: `json-${value === null ? 'null' : typeof value}` }, String(value));
  }

  function preview(value, isArr) {
    const parts = isArr ? value.slice(0, 6).map(pv) : Object.entries(value).slice(0, 4).map(([k, v]) => `${k}: ${pv(v)}`);
    const more = (isArr ? value.length > 6 : Object.keys(value).length > 4) ? ', …' : '';
    return parts.join(', ') + more;
  }
  function pv(v) {
    if (v === null) return 'null';
    if (typeof v === 'string') return JSON.stringify(v.length > 20 ? `${v.slice(0, 20)}…` : v);
    if (typeof v === 'object') return Array.isArray(v) ? '[…]' : '{…}';
    return String(v);
  }

  function isOpen(path, depth) {
    if (openState.has(path)) return openState.get(path);
    if (forceAll != null) return forceAll;
    if (query) return true;
    return depth < 2;
  }

  function select(path, e) {
    e.stopPropagation();
    selectedPath = path;
    pathText.textContent = path;
    statusBar.style.display = 'flex';
    drawTree();
  }

  function renderNode(value, key, path, depth, isArrIndex) {
    const isObj = value !== null && typeof value === 'object';
    const entries = isObj ? Object.entries(value) : null;
    const isArr = Array.isArray(value);
    const hasKids = isObj && entries.length > 0;
    const open = hasKids && isOpen(path, depth);
    const row = el('div', { class: `json-row${selectedPath === path ? ' selected' : ''}`, style: `padding-left:${depth * 16}px`, onclick: (e) => select(path, e) });
    row.appendChild(hasKids
      ? el('span', { class: `json-toggle${open ? ' open' : ''}`, onclick: (e) => { e.stopPropagation(); openState.set(path, !open); forceAll = null; drawTree(); } }, icon('chevron-right'))
      : el('span', { class: 'json-toggle' }));
    if (key !== null) row.append(el('span', { class: isArrIndex ? 'json-index' : 'json-key' }, markHits(String(key), query)), el('span', { class: 'json-punct' }, ':'));
    if (!isObj) row.appendChild(primitive(value));
    else if (!hasKids) row.appendChild(el('span', { class: 'json-punct' }, isArr ? '[]' : '{}'));
    else {
      row.appendChild(el('span', { class: 'json-pill' }, isArr ? `[ ${entries.length} ]` : `{ ${entries.length} }`));
      if (!open) row.appendChild(el('span', { class: 'json-preview' }, preview(value, isArr)));
    }
    const wrap = el('div', {}, [row]);
    if (hasKids && open) {
      const visible = query ? entries.filter(([k, v]) => matchCount(v, k, query)) : entries;
      const kids = el('div', { class: 'json-children' }, visible.map(([k, v]) => renderNode(v, k, isArr ? `${path}[${k}]` : `${path}.${k}`, depth + 1, isArr)));
      wrap.appendChild(kids);
    }
    return wrap;
  }

  function drawTree() {
    mode = 'tree';
    clear(tree);
    search.disabled = false;
    const isObj = data !== null && typeof data === 'object';
    const entries = isObj ? Object.entries(data) : null;
    const total = isObj ? entries.reduce((s, [k, v]) => s + matchCount(v, k, query), 0) : (query ? matchCount(data, '', query) : 0);
    count.textContent = query ? (total ? `${total}개 일치` : '일치 없음') : '';
    if (isObj) {
      const visible = query ? entries.filter(([k, v]) => matchCount(v, k, query)) : entries;
      for (const [k, v] of visible) tree.appendChild(renderNode(v, k, Array.isArray(data) ? `$[${k}]` : `$.${k}`, 0, Array.isArray(data)));
    } else {
      tree.appendChild(renderNode(data, null, '$', 0, false));
    }
  }

  function renderEmpty(iconName, title, desc, rawText) {
    mode = rawText ? 'invalid' : 'message';
    clear(tree);
    search.disabled = true;
    count.textContent = '';
    statusBar.style.display = 'none';
    const parts = [iconName ? icon(iconName) : null, el('div', { class: 'empty-title' }, title), desc ? el('div', { class: 'empty-desc' }, desc) : null];
    tree.appendChild(el('div', { class: 'empty' }, parts));
    if (rawText) tree.appendChild(el('pre', { class: 'json-raw' }, rawText));
  }

  return {
    show(text) {
      search.value = ''; query = ''; selectedPath = null; openState.clear(); forceAll = null; hitQuery = null;
      try { data = JSON.parse(text); raw = JSON.stringify(data, null, 2); drawTree(); }
      catch (e) { data = null; raw = text; renderEmpty('alert-triangle', 'JSON 형식 오류', e.message, text); }
    },
    showMessage(title, desc, iconName = null) {
      search.value = ''; query = ''; selectedPath = null; data = null; raw = '';
      renderEmpty(iconName, title, desc);
    },
    getText: () => raw,
  };
}
