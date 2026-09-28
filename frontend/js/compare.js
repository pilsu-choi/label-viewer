import { el, clear, mount, charDiff, fmtPct, statusBadge, scoreCard, statusDescription } from './util.js';

function diffSpan(goldenVal, val) {
  const parts = charDiff(goldenVal, val);
  return el('span', { class: 'cmp-val' }, parts.map((p) => p.changed ? el('span', { class: 'diff-add' }, p.text) : document.createTextNode(p.text)));
}

function evidencePopover(x, y, entry) {
  const box = el('div', { class: 'evidence-pop', style: `left:${Math.min(x + 14, window.innerWidth - 356)}px;top:${Math.min(y + 14, window.innerHeight - 200)}px` });
  const rows = [];
  rows.push(el('div', { class: 'ev-row' }, [el('span', {}, '경로'), el('span', { class: 'mono' }, entry.path)]));
  if (entry.ao_confidence != null) rows.push(el('div', { class: 'ev-row' }, [el('span', {}, 'AO 신뢰도'), el('span', {}, fmtPct(entry.ao_confidence))]));
  box.appendChild(el('h5', {}, '근거'));
  box.appendChild(el('div', {}, rows));
  const ev = entry.evidence;
  if (!ev) { box.appendChild(el('div', { class: 'hint', style: 'margin-top:8px' }, '하네스 근거 없음')); return box; }
  const meta = [];
  if (ev.tier) meta.push(['Tier', ev.tier]);
  if (ev.correction_basis) meta.push(['보정 근거', ev.correction_basis]);
  if (ev.decision_rule_no) meta.push(['결정 규칙', ev.decision_rule_no]);
  if (ev.final_value != null) meta.push(['최종값', String(ev.final_value)]);
  if (meta.length) box.appendChild(el('div', { style: 'margin-top:8px' }, meta.map(([k, v]) => el('div', { class: 'ev-row' }, [el('span', {}, k), el('span', {}, v)]))));
  const evi = ev.evidence || {};
  if (Array.isArray(evi.rule) && evi.rule.length) {
    box.appendChild(el('h5', { style: 'margin-top:10px' }, '규칙 결과'));
    box.appendChild(el('table', {}, [
      el('thead', {}, el('tr', {}, ['결과', '규칙', '설명'].map((h) => el('th', {}, h)))),
      el('tbody', {}, evi.rule.map((r) => el('tr', {}, [
        el('td', {}, r.result || ''), el('td', {}, r.rule_id || ''), el('td', {}, r.detail || ''),
      ]))),
    ]));
  }
  if (evi.reread) {
    box.appendChild(el('h5', { style: 'margin-top:10px' }, '재판독'));
    box.appendChild(el('div', { class: 'ev-row' }, [el('span', {}, evi.reread.status || ''), el('span', {}, evi.reread.value == null ? '—' : String(evi.reread.value))]));
    if (evi.reread.detail) box.appendChild(el('div', { class: 'hint' }, evi.reread.detail));
  }
  if (evi.master) {
    box.appendChild(el('h5', { style: 'margin-top:10px' }, '마스터 대조'));
    box.appendChild(el('div', { class: 'ev-row' }, [el('span', {}, '상태'), el('span', {}, evi.master.status || '')]));
  }
  return box;
}

let popEl = null;
function hidePop() { if (popEl) { popEl.remove(); popEl = null; } }

export function renderCompare(host, doc, { onAdopt, onHoverBbox } = {}) {
  const state = { filter: 'all' };
  draw();

  function counts(list) {
    const c = { mismatch: 0, missing: 0, extra: 0 };
    for (const e of list) {
      for (const s of [e.ao_status, e.harness_status]) {
        if (s === 'MISMATCH' || s === 'TYPE_MISMATCH') c.mismatch++;
        else if (s === 'MISSING') c.missing++;
        else if (s === 'EXTRA') c.extra++;
      }
    }
    return c;
  }

  function matchesFilter(e) {
    if (state.filter === 'all') return true;
    const target = { mismatch: ['MISMATCH', 'TYPE_MISMATCH'], missing: ['MISSING'], extra: ['EXTRA'] }[state.filter];
    return target.includes(e.ao_status) || target.includes(e.harness_status);
  }

  function draw() {
    clear(host);
    const list = doc.compare || [];
    const c = counts(list);
    const toolbar = el('div', { class: 'cmp-toolbar' }, [
      ...[['all', '전체', list.length], ['mismatch', '불일치', c.mismatch], ['missing', '누락', c.missing], ['extra', '추가', c.extra]]
        .map(([key, label, n]) => el('button', {
          class: `chip ${state.filter === key ? 'active' : ''}`,
          title: key === 'all' ? '모든 비교 항목을 표시합니다.' : key === 'mismatch'
            ? `${statusDescription('MISMATCH')} 형식오류도 포함합니다.` : statusDescription(key.toUpperCase()),
          onclick: () => { state.filter = key; draw(); },
        }, [label, el('span', { class: 'n' }, String(n))])),
    ]);
    const scoreCards = el('div', { class: 'cmp-score-cards' }, [scoreCard('AO Extract', doc.score && doc.score.ao), scoreCard('Harness', doc.score && doc.score.harness)]);

    const filtered = list.filter(matchesFilter);
    const groups = new Map();
    for (const e of filtered) {
      const gk = `${e.area}::${e.container || ''}`;
      if (!groups.has(gk)) groups.set(gk, []);
      groups.get(gk).push(e);
    }

    const tableWrap = el('div', { class: 'cmp-table-wrap' });
    if (!filtered.length) {
      tableWrap.appendChild(el('div', { class: 'empty-state' }, '표시할 항목이 없습니다.'));
    } else {
      const tbody = el('tbody');
      for (const [gk, rows] of groups) {
        const [area, container] = gk.split('::');
        const kind = { field: '필드', group: '그룹', table: '표' }[area];
        tbody.appendChild(el('tr', { class: 'cmp-group' }, el('td', { colspan: '5' }, [el('span', { class: 'kind' }, kind), container || null])));
        for (const e of rows) {
          const off = [e.ao_status, e.harness_status].some((st) => st && st !== 'MATCH');
          const tr = el('tr', { class: off ? 'is-off' : '', dataset: { path: e.path },
            onmouseenter: (ev) => {
              if (e.bbox && onHoverBbox) onHoverBbox(e.bbox);
              popEl = evidencePopover(ev.clientX, ev.clientY, e);
              document.body.appendChild(popEl);
            },
            onmousemove: (ev) => { if (popEl) { popEl.style.left = `${Math.min(ev.clientX + 14, window.innerWidth - 356)}px`; popEl.style.top = `${Math.min(ev.clientY + 14, window.innerHeight - 200)}px`; } },
            onmouseleave: () => { hidePop(); if (onHoverBbox) onHoverBbox(null); },
          }, [
            el('td', {}, [e.area === 'table' ? el('span', { class: 'cmp-row' }, typeof e.row === 'number' ? `#${e.row + 1}` : `#${Number(String(e.row).slice(1)) + 1} 추가`) : null, el('span', { class: 'cmp-key' }, e.key)]),
            el('td', {}, el('span', { class: 'cmp-val' }, e.golden == null ? '—' : String(e.golden))),
            el('td', {}, el('div', { class: 'cmp-cell' }, [diffSpan(e.golden, e.ao), statusBadge(e.ao_status)])),
            el('td', {}, el('div', { class: 'cmp-cell' }, [diffSpan(e.golden, e.harness), statusBadge(e.harness_status)])),
            el('td', { class: 'cmp-adopt' }, [
              onAdopt && e.ao != null && e.ao !== '' && el('button', { class: 'btn btn-sm', title: 'AO 값을 정답으로', onclick: () => onAdopt(e, e.ao) }, 'AO 채택'),
              onAdopt && e.harness != null && e.harness !== '' && el('button', { class: 'btn btn-sm', title: 'Harness 값을 정답으로', onclick: () => onAdopt(e, e.harness) }, 'H 채택'),
            ]),
          ]);
          tbody.appendChild(tr);
        }
      }
      tableWrap.appendChild(el('table', { class: 'cmp-table' }, [
        el('thead', {}, el('tr', {}, ['항목', 'Golden', 'AO', 'Harness', ''].map((h) => el('th', {}, h)))),
        tbody,
      ]));
    }
    mount(host, [toolbar, scoreCards, tableWrap]);
  }

  return {
    flashPath(path) {
      state.filter = 'all'; draw();
      const row = host.querySelector(`tr[data-path="${CSS.escape(path)}"]`);
      if (row) { row.scrollIntoView({ block: 'center', behavior: 'smooth' }); row.classList.add('flash'); setTimeout(() => row.classList.remove('flash'), 1400); }
      return row;
    },
    refresh(newDoc) { doc = newDoc; draw(); },
    destroy() { hidePop(); },
  };
}
