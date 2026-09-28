import { el, clear, mount, charDiff, statusLabel, fmtPct } from './util.js';

const STATUS_CLASS = { MATCH: 'badge-ok', MISMATCH: 'badge-bad', MISSING: 'badge-warn', EXTRA: 'badge-extra', TYPE_MISMATCH: 'badge-type' };
const STATUS_COLOR = { MATCH: 'var(--ok)', MISMATCH: 'var(--bad)', MISSING: 'var(--warn)', EXTRA: 'var(--extra)', TYPE_MISMATCH: 'var(--type)' };

function statusBadge(status) {
  if (!status) return el('span', { class: 'badge badge-muted' }, '—');
  return el('span', { class: `badge ${STATUS_CLASS[status] || 'badge-muted'}` }, statusLabel(status));
}

function diffSpan(goldenVal, val) {
  const parts = charDiff(goldenVal, val);
  return el('span', { class: 'cmp-val' }, parts.map((p) => p.changed ? el('span', { class: 'diff-add' }, p.text) : document.createTextNode(p.text)));
}

function scoreCard(title, score) {
  const card = el('div', { class: 'score-card' });
  if (!score) { mount(card, [el('div', { class: 'sc-head' }, [el('span', { class: 'sc-name' }, title), el('span', { class: 'sc-acc' }, '—')])]); return card; }
  const total = score.total || 0;
  const bar = el('div', { class: 'score-bar' });
  for (const k of ['MATCH', 'MISMATCH', 'MISSING', 'EXTRA', 'TYPE_MISMATCH']) {
    const n = score[k] || 0; if (!n) continue;
    bar.appendChild(el('span', { style: `width:${(n / total) * 100}%;background:${STATUS_COLOR[k]}`, title: `${statusLabel(k)} ${n}` }));
  }
  mount(card, [
    el('div', { class: 'sc-head' }, [el('span', { class: 'sc-name' }, title), el('span', { class: 'sc-acc' }, fmtPct(score.accuracy))]),
    bar,
    el('div', { class: 'hint' }, ['MATCH', 'MISMATCH', 'MISSING', 'EXTRA', 'TYPE_MISMATCH'].map((k) => `${statusLabel(k)} ${score[k] || 0}`).join(' · ')),
  ]);
  return card;
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
      ...[['all', '전체', list.length], ['mismatch', 'Mismatch', c.mismatch], ['missing', 'Missing', c.missing], ['extra', 'Extra', c.extra]]
        .map(([key, label, n]) => el('button', { class: `chip ${state.filter === key ? 'active' : ''}`, onclick: () => { state.filter = key; draw(); } }, [label, el('span', { class: 'n' }, String(n))])),
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
        const label = area === 'field' ? '필드' : area === 'group' ? `그룹 · ${container}` : `표 · ${container}`;
        tbody.appendChild(el('tr', {}, el('td', { colspan: '5', class: 'cmp-container' }, label)));
        for (const e of rows) {
          const tr = el('tr', { dataset: { path: e.path },
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
            el('td', {}, [diffSpan(e.golden, e.ao), ' ', statusBadge(e.ao_status)]),
            el('td', {}, [diffSpan(e.golden, e.harness), ' ', statusBadge(e.harness_status)]),
            el('td', { class: 'cmp-adopt' }, [
              onAdopt && e.ao != null && e.ao !== '' && el('button', { class: 'btn btn-sm', title: 'AO 값 채택', onclick: () => onAdopt(e, e.ao) }, 'AO'),
              onAdopt && e.harness != null && e.harness !== '' && el('button', { class: 'btn btn-sm', title: 'Harness 값 채택', onclick: () => onAdopt(e, e.harness) }, 'H'),
            ]),
          ]);
          tbody.appendChild(tr);
        }
      }
      tableWrap.appendChild(el('table', { class: 'cmp-table' }, [
        el('thead', {}, el('tr', {}, ['Key', 'Golden', 'AO', 'Harness', ''].map((h) => el('th', {}, h)))),
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
