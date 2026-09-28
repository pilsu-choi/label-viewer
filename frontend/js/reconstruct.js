import { el, fmtNumber, isNumericDtype } from './util.js';

// 하네스 최종값 규칙: harness.final_value 있으면 그것, 없으면 value.
export function cellDisplay(cell, source) {
  if (!cell) return '';
  if (source === 'harness' && cell.harness && cell.harness.final_value != null && cell.harness.final_value !== '') {
    return cell.harness.final_value;
  }
  return cell.value;
}

function cellText(cell, source) {
  const v = cellDisplay(cell, source);
  if (v == null) return '';
  if (isNumericDtype(cell.dtype)) return fmtNumber(v);
  return String(v);
}

// 원본 JSON(AO 형식) → 렌더링용 모델. 항상 텍스트만 다루며 HTML 을 해석하지 않는다.
export function buildReconModel(root, source) {
  const docs = (root && Array.isArray(root.documents)) ? root.documents : [];
  return docs.map((doc) => ({
    doc_type: doc.doc_type || '',
    fields: (doc.extracted_fields || []).map((c) => [c.key, cellText(c, source)]),
    groups: (doc.extracted_groups || []).map((g) => ({
      key: g.key, fields: (g.fields || []).map((c) => [c.key, cellText(c, source)]),
    })),
    tables: (doc.extracted_tables || []).map((t) => ({
      key: t.key, headers: t.headers || [],
      rows: (t.rows || []).map((row) => (row || []).map((c) => ({ text: cellText(c, source), numeric: isNumericDtype(c && c.dtype) }))),
    })),
  }));
}

export function renderReconHTML(model) {
  if (!model.length) return el('div', { class: 'rc-empty' }, '표시할 데이터가 없습니다.');
  const wrap = el('div', {});
  model.forEach((doc, i) => {
    if (model.length > 1) wrap.appendChild(el('h3', {}, doc.doc_type || `문서 ${i + 1}`));
    else if (doc.doc_type) wrap.appendChild(el('h3', {}, doc.doc_type));
    if (doc.fields.length) {
      const dl = el('dl', { class: 'rc-dl' });
      for (const [k, v] of doc.fields) { dl.appendChild(el('dt', {}, k)); dl.appendChild(el('dd', {}, v)); }
      wrap.appendChild(el('div', { class: 'rc-section' }, dl));
    }
    for (const g of doc.groups) {
      const dl = el('dl', { class: 'rc-dl' });
      for (const [k, v] of g.fields) { dl.appendChild(el('dt', {}, k)); dl.appendChild(el('dd', {}, v)); }
      wrap.appendChild(el('div', { class: 'rc-section' }, [el('h4', {}, g.key), dl]));
    }
    for (const t of doc.tables) {
      const thead = el('thead', {}, el('tr', {}, t.headers.map((h) => el('th', {}, h))));
      const tbody = el('tbody', {}, t.rows.map((row) => el('tr', {}, row.map((c) => el('td', { class: c.numeric ? 'num' : '' }, c.text)))));
      wrap.appendChild(el('div', { class: 'rc-section' }, [el('h4', {}, t.key), el('table', { class: 'rc-table' }, [thead, tbody])]));
    }
    if (!doc.fields.length && !doc.groups.length && !doc.tables.length) {
      wrap.appendChild(el('div', { class: 'rc-empty' }, '필드가 없습니다.'));
    }
  });
  return wrap;
}

function mdEscapeCell(s) { return String(s).replace(/\|/g, '\\|').replace(/\n/g, ' '); }

export function buildMarkdown(model) {
  const lines = [];
  model.forEach((doc, i) => {
    lines.push(`## ${doc.doc_type || `문서 ${i + 1}`}`, '');
    for (const [k, v] of doc.fields) lines.push(`- ${k}: ${v}`);
    if (doc.fields.length) lines.push('');
    for (const g of doc.groups) {
      lines.push(`### ${g.key}`, '');
      for (const [k, v] of g.fields) lines.push(`- ${k}: ${v}`);
      lines.push('');
    }
    for (const t of doc.tables) {
      lines.push(`### ${t.key}`, '');
      lines.push(`| ${t.headers.map(mdEscapeCell).join(' | ')} |`);
      lines.push(`|${t.headers.map(() => '---').join('|')}|`);
      for (const row of t.rows) lines.push(`| ${row.map((c) => mdEscapeCell(c.text)).join(' | ')} |`);
      lines.push('');
    }
  });
  return lines.join('\n');
}

// 아주 작은 안전한 마크다운 렌더러: heading(#) · list(-) · table(|) 만 지원. innerHTML 사용 안 함.
export function renderMarkdownToDom(text) {
  const root = el('div', { class: 'rc-md' });
  const lines = text.split('\n');
  let i = 0;
  let listEl = null;
  const flushList = () => { listEl = null; };
  while (i < lines.length) {
    const line = lines[i];
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flushList();
      root.appendChild(el(`h${heading[1].length}`, {}, heading[2]));
      i++; continue;
    }
    if (/^\s*-\s+/.test(line)) {
      if (!listEl) { listEl = el('ul'); root.appendChild(listEl); }
      listEl.appendChild(el('li', {}, line.replace(/^\s*-\s+/, '')));
      i++; continue;
    }
    if (/^\|.*\|\s*$/.test(line) && lines[i + 1] && /^\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      flushList();
      const headCells = line.trim().slice(1, -1).split('|').map((s) => s.trim());
      i += 2;
      const rows = [];
      while (i < lines.length && /^\|.*\|\s*$/.test(lines[i])) {
        rows.push(lines[i].trim().slice(1, -1).split('|').map((s) => s.trim()));
        i++;
      }
      const table = el('table', { class: 'rc-table' }, [
        el('thead', {}, el('tr', {}, headCells.map((h) => el('th', {}, h)))),
        el('tbody', {}, rows.map((r) => el('tr', {}, r.map((c) => el('td', { class: /^-?[\d.,]+$/.test(c) ? 'num' : '' }, c))))),
      ]);
      root.appendChild(table);
      continue;
    }
    flushList();
    if (line.trim()) root.appendChild(el('p', {}, line));
    i++;
  }
  return root;
}
