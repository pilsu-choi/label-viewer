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
