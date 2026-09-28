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
  return el('span', { class: `badge badge-${STATUS_TONE[status] || 'muted'}` }, status ? statusLabel(status) : '—');
}

// 정확도 + 상태 분포 막대 + 범례. score 가 없으면 hint 를 보여 준다.
export function scoreCard(title, score, hint = 'Golden이 있어야 채점됩니다') {
  const head = el('div', { class: 'sc-head' }, [el('span', { class: 'sc-name' }, title), el('span', { class: 'sc-acc' }, score ? fmtPct(score.accuracy) : '—')]);
  if (!score) return el('div', { class: 'score-card' }, [head, el('div', { class: 'hint' }, hint)]);
  const total = score.total || 1;
  return el('div', { class: 'score-card' }, [
    head,
    el('div', { class: 'score-bar' }, STATUSES.filter((k) => score[k]).map((k) =>
      el('span', { class: `tone-${STATUS_TONE[k]}`, style: `width:${(score[k] / total) * 100}%`, title: `${statusLabel(k)} ${score[k]}` }))),
    el('div', { class: 'sc-legend' }, STATUSES.map((k) =>
      el('span', { class: score[k] ? '' : 'zero' }, [el('i', { class: `tone-${STATUS_TONE[k]}` }), statusLabel(k), el('b', {}, String(score[k] || 0))]))),
  ]);
}

// 고정 아이콘(SVG path). 데이터 문자열은 들어가지 않는다.
const ICONS = {
  search: 'M11 4a7 7 0 1 0 4.2 12.6l4.1 4.1 1.4-1.4-4.1-4.1A7 7 0 0 0 11 4zm0 2a5 5 0 1 1 0 10 5 5 0 0 1 0-10z',
  grid: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  list: 'M4 5h16v2H4zM4 11h16v2H4zM4 17h16v2H4z',
  left: 'M14.7 5.3 8 12l6.7 6.7 1.4-1.4L10.8 12l5.3-5.3z',
  right: 'M9.3 5.3 16 12l-6.7 6.7-1.4-1.4 5.3-5.3-5.3-5.3z',
  down: 'M5.3 8.7 12 15.4l6.7-6.7-1.4-1.4-5.3 5.3-5.3-5.3z',
  x: 'M6.4 5 5 6.4 10.6 12 5 17.6 6.4 19l5.6-5.6 5.6 5.6 1.4-1.4-5.6-5.6L19 6.4 17.6 5 12 10.6z',
  upload: 'M12 3 6.3 8.7l1.4 1.4L11 6.8V16h2V6.8l3.3 3.3 1.4-1.4zM4 18h16v2H4z',
  download: 'M11 4v9.2l-3.3-3.3-1.4 1.4L12 17l5.7-5.7-1.4-1.4-3.3 3.3V4zM4 18h16v2H4z',
  check: 'M9.5 16.2 5.3 12l-1.4 1.4 5.6 5.6L20.1 8.4l-1.4-1.4z',
};
export function icon(name) {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('class', 'ic'); svg.setAttribute('aria-hidden', 'true');
  const p = document.createElementNS(NS, 'path'); p.setAttribute('d', ICONS[name]); svg.appendChild(p);
  return svg;
}

// 내보내기 같은 드롭다운. 팝업은 상단 바 스크롤에 잘리지 않게 fixed 로 버튼 아래에 붙인다.
// 바깥 클릭으로 닫기는 각 화면이 '.export-pop' 을 숨겨 처리한다.
export function menuButton(label, items) {
  const pop = el('div', { class: 'export-pop', style: 'display:none' }, items);
  return el('div', { class: 'btn menu-btn', onclick: (e) => {
    e.stopPropagation();
    const open = pop.style.display !== 'block';
    pop.style.display = open ? 'block' : 'none';
    if (open) {
      const r = e.currentTarget.getBoundingClientRect();
      Object.assign(pop.style, { top: `${r.bottom}px`, right: `${window.innerWidth - r.right}px` });
    }
  } }, [icon('download'), label, pop]);
}
