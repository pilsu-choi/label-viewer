// 공용 DOM/포맷 헬퍼. innerHTML 은 절대 쓰지 않는다 — 항상 textContent/createElement.

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else if (k === 'text') node.textContent = v;
    else if (v === true) node.setAttribute(k, '');
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null || c === false) continue;
    node.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
  }
  return node;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

export function mount(node, children) {
  clear(node);
  for (const c of [].concat(children)) {
    if (c == null || c === false) continue;
    node.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
  }
  return node;
}

export function debounce(fn, ms) {
  let t = null;
  const wrapped = (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
  wrapped.cancel = () => clearTimeout(t);
  wrapped.flush = (...args) => { clearTimeout(t); fn(...args); };
  return wrapped;
}

export function fmtNumber(v) {
  if (v === '' || v == null) return '';
  const n = Number(String(v).replace(/,/g, ''));
  if (Number.isNaN(n)) return String(v);
  return n.toLocaleString('ko-KR', { maximumFractionDigits: 6 });
}

export function isNumericDtype(dtype) {
  return dtype === 'int' || dtype === 'float' || dtype === 'number';
}

export function fmtPct(v) {
  if (v == null) return '—';
  return (v * 100).toFixed(1) + '%';
}

export function toast(msg, kind = 'info') {
  const host = document.getElementById('toast-host');
  if (!host) return;
  const node = el('div', { class: `toast toast-${kind}` }, msg);
  host.appendChild(node);
  requestAnimationFrame(() => node.classList.add('show'));
  setTimeout(() => {
    node.classList.remove('show');
    setTimeout(() => node.remove(), 200);
  }, 3200);
}

export function downloadUrl(url, filename) {
  const a = el('a', { href: url, download: filename || '' });
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// 화면 요소가 입력 중인지 (단축키 무력화 판단용)
export function isEditingTarget(target) {
  if (!target) return false;
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (target.isContentEditable) return true;
  return false;
}

// 문자열이 마크업처럼 보이는지 (Reconstructed HTML 뷰에서 text-only 폴백 판단)
export function looksLikeMarkup(s) {
  return typeof s === 'string' && /<\s*\/?\s*[a-zA-Z][^>]*>/.test(s);
}

export function statusLabel(status) {
  return { MATCH: '일치', MISMATCH: '불일치', MISSING: '누락', EXTRA: '추가', TYPE_MISMATCH: '형식오류' }[status] || status || '';
}

export function statusDescription(status) {
  return {
    MATCH: 'Golden과 비교값이 정규화 후 일치합니다.',
    MISMATCH: 'Golden에 값이 있지만 비교값이 다릅니다.',
    MISSING: 'Golden에는 값이 있지만 비교 결과에는 없습니다.',
    EXTRA: 'Golden에는 없는 값이 비교 결과에 있습니다.',
    TYPE_MISMATCH: '비교값이 필요한 숫자 또는 표 형식과 다릅니다.',
  }[status] || '';
}

// 정답(golden) 문자열 대비 비교값의 문자 단위 diff. [{text, changed}] 배열 반환.
export function charDiff(golden, other) {
  const a = golden == null ? '' : String(golden);
  const b = other == null ? '' : String(other);
  if (a === b) return [{ text: b, changed: false }];
  const n = a.length, m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  const out = [];
  let i = n, j = m;
  const rev = [];
  while (i > 0 && j > 0) {
    if (a[i - 1] === b[j - 1]) { rev.push({ ch: b[j - 1], changed: false }); i--; j--; }
    else if (dp[i - 1][j] >= dp[i][j - 1]) { i--; }
    else { rev.push({ ch: b[j - 1], changed: true }); j--; }
  }
  while (j > 0) { rev.push({ ch: b[j - 1], changed: true }); j--; }
  rev.reverse();
  let cur = null;
  for (const { ch, changed } of rev) {
    if (!cur || cur.changed !== changed) { cur = { text: ch, changed }; out.push(cur); }
    else cur.text += ch;
  }
  return out.length ? out : [{ text: '', changed: false }];
}

export function pathKey(docIdx, area, container, key) {
  if (area === 'field') return `documents[${docIdx}].fields[${key}]`;
  if (area === 'group') return `documents[${docIdx}].groups[${container}].fields[${key}]`;
  return `documents[${docIdx}].tables[${container}]`;
}

// ── 공용 UI 조각 ─────────────────────────────────────────────
export const STATUSES = ['MATCH', 'MISMATCH', 'MISSING', 'EXTRA', 'TYPE_MISMATCH'];
const STATUS_TONE = { MATCH: 'ok', MISMATCH: 'bad', MISSING: 'warn', EXTRA: 'extra', TYPE_MISMATCH: 'type' };

export function statusBadge(status) {
  return el('span', { class: `badge badge-${STATUS_TONE[status] || 'muted'}`, title: statusDescription(status) }, status ? statusLabel(status) : '—');
}

// 정확도 + 상태 분포 막대 + 범례. score 가 없으면 hint 를 보여 준다.
export function scoreCard(title, score, hint = 'Golden이 있어야 채점됩니다') {
  const head = el('div', { class: 'sc-head' }, [el('span', { class: 'sc-name' }, title), el('span', { class: 'sc-acc' }, score ? fmtPct(score.accuracy) : '—')]);
  if (!score) return el('div', { class: 'score-card' }, [head, el('div', { class: 'hint' }, hint)]);
  const total = score.total || 1;
  return el('div', { class: 'score-card' }, [
    head,
    el('div', { class: 'score-bar' }, STATUSES.filter((k) => score[k]).map((k) =>
      el('span', { class: `tone-${STATUS_TONE[k]}`, style: `width:${(score[k] / total) * 100}%`, title: `${statusLabel(k)} ${score[k]}건 · ${statusDescription(k)}` }))),
    el('div', { class: 'sc-legend' }, STATUSES.map((k) =>
      el('span', { class: score[k] ? '' : 'zero', title: statusDescription(k) }, [el('i', { class: `tone-${STATUS_TONE[k]}` }), statusLabel(k), el('b', {}, String(score[k] || 0))]))),
  ]);
}

// Lucide 스타일 stroke 아이콘(24 viewBox, stroke-width 1.75, fill none). 각 항목은 <path> d 문자열 하나
// 또는 [tag, attrs][] 배열(여러 path/circle/line 조합)이다. 데이터 문자열은 들어가지 않는다.
const ICONS = {
  search: [['circle', { cx: 11, cy: 11, r: 8 }], ['path', { d: 'M21 21l-4.35-4.35' }]],
  grid: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  list: 'M4 5h16v2H4zM4 11h16v2H4zM4 17h16v2H4z',
  'chevron-left': 'M15 18l-6-6 6-6',
  'chevron-right': 'M9 18l6-6-6-6',
  'chevron-down': 'M6 9l6 6 6-6',
  plus: 'M12 5v14M5 12h14',
  x: 'M18 6L6 18M6 6l12 12',
  trash: [['path', { d: 'M3 6h18' }], ['path', { d: 'M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2' }], ['path', { d: 'M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6' }], ['path', { d: 'M10 11v6M14 11v6' }]],
  download: [['path', { d: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4' }], ['path', { d: 'M7 10l5 5 5-5' }], ['path', { d: 'M12 15V3' }]],
  upload: [['path', { d: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4' }], ['path', { d: 'M17 8l-5-5-5 5' }], ['path', { d: 'M12 3v12' }]],
  folder: 'M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z',
  'file-archive': [['path', { d: 'M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z' }], ['path', { d: 'M14 2v4a2 2 0 0 0 2 2h4' }], ['path', { d: 'M10 8h1M10 11h1M10 14h1' }], ['path', { d: 'M9 17h3v3h-3z' }]],
  'zoom-in': [['circle', { cx: 11, cy: 11, r: 8 }], ['path', { d: 'M21 21l-4.35-4.35' }], ['path', { d: 'M11 8v6M8 11h6' }]],
  'zoom-out': [['circle', { cx: 11, cy: 11, r: 8 }], ['path', { d: 'M21 21l-4.35-4.35' }], ['path', { d: 'M8 11h6' }]],
  maximize: 'M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M21 16v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3',
  'help-circle': [['circle', { cx: 12, cy: 12, r: 10 }], ['path', { d: 'M9.09 9a3 3 0 0 1 5.83 1c0 2-3 2-3 4' }], ['path', { d: 'M12 17h.01' }]],
  check: 'M20 6 9 17l-5-5',
  'check-circle': [['circle', { cx: 12, cy: 12, r: 10 }], ['path', { d: 'M9 12l2 2 4-4' }]],
  'alert-triangle': [['path', { d: 'M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z' }], ['path', { d: 'M12 9v4' }], ['path', { d: 'M12 17h.01' }]],
  eye: [['path', { d: 'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z' }], ['circle', { cx: 12, cy: 12, r: 3 }]],
  columns: [['rect', { x: 3, y: 3, width: 18, height: 18, rx: 2 }], ['path', { d: 'M12 3v18' }]],
  image: [['rect', { x: 3, y: 3, width: 18, height: 18, rx: 2 }], ['circle', { cx: 8.5, cy: 8.5, r: 1.5 }], ['path', { d: 'M21 15l-5-5L5 21' }]],
  'more-horizontal': [['circle', { cx: 5, cy: 12, r: 1 }], ['circle', { cx: 12, cy: 12, r: 1 }], ['circle', { cx: 19, cy: 12, r: 1 }]],
  'chevrons-up-down': [['path', { d: 'M7 15l5 5 5-5' }], ['path', { d: 'M7 9l5-5 5 5' }]],
  'chevrons-down-up': [['path', { d: 'M7 20l5-5 5 5' }], ['path', { d: 'M7 4l5 5 5-5' }]],
  copy: [['rect', { x: 9, y: 9, width: 13, height: 13, rx: 2 }], ['path', { d: 'M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1' }]],
};
export function icon(name) {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('class', 'ic'); svg.setAttribute('aria-hidden', 'true');
  const def = ICONS[name];
  const parts = typeof def === 'string' ? [['path', { d: def }]] : (def || []);
  for (const [tag, attrs] of parts) {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    svg.appendChild(node);
  }
  return svg;
}

// 내보내기 같은 드롭다운. 팝업은 상단 바 스크롤에 잘리지 않게 fixed 로 버튼 아래에 붙인다.
// 바깥 클릭으로 닫기는 각 화면이 '.export-pop' 을 숨겨 처리한다.
export function menuButton(label, items, iconName = 'download', extraClass = '') {
  const pop = el('div', { class: 'export-pop', style: 'display:none' }, items);
  return el('div', { class: `btn menu-btn ${extraClass}`.trim(), 'aria-label': label || '더 보기', onclick: (e) => {
    e.stopPropagation();
    const open = pop.style.display !== 'block';
    pop.style.display = open ? 'block' : 'none';
    if (open) {
      const r = e.currentTarget.getBoundingClientRect();
      Object.assign(pop.style, { top: `${r.bottom}px`, right: `${window.innerWidth - r.right}px` });
    }
  } }, [icon(iconName), label || null, pop]);
}
