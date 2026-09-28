import { el, clear, mount, charDiff, fmtPct, statusBadge, scoreCard, statusDescription, isMismatch } from './util.js';

// 필터 키 순서. 'mismatch_all' 은 탭 배지·사이드바·편집 탭 요약과 같은 isMismatch 기준.
const FILTER_KEYS = ['all', 'mismatch_all', 'mismatch', 'missing', 'extra'];
const FILTER_LABEL = { all: '전체', mismatch_all: '불일치 전체', mismatch: '불일치', missing: '누락', extra: '추가' };
const FILTER_STATUS = { mismatch: ['MISMATCH', 'TYPE_MISMATCH'], missing: ['MISSING'], extra: ['EXTRA'] };

// 필터 판정과 칩 개수 집계를 하나로 묶는다: 칩 숫자는 항상 "이 필터를 눌렀을 때 보이는 행 수"와 같다.
function matchesFilter(e, key) {
  if (key === 'all') return true;
  if (key === 'mismatch_all') return isMismatch(e);
  return [e.ao_status, e.harness_status].some((s) => FILTER_STATUS[key].includes(s));
}

function countsByFilter(list) {
  const c = {};
  for (const key of FILTER_KEYS) c[key] = list.filter((e) => matchesFilter(e, key)).length;
  return c;
}

function diffSpan(goldenVal, val) {
  const parts = charDiff(goldenVal, val);
  return el('span', { class: 'cmp-val' }, parts.map((p) => p.changed ? el('span', { class: 'diff-add' }, p.text) : document.createTextNode(p.text)));
}

function evidencePopover(entry) {
  const box = el('div', { class: 'evidence-pop' });
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

// 근거 팝오버 상태: hover-intent(짧은 지연 뒤 숨김, 포인터가 팝오버로 이동하면 취소)와
// 클릭 고정(핀)을 지원한다. 핀 상태에서는 Esc·바깥 클릭·같은 행 재클릭으로만 닫힌다.
let popEl = null;
let pinned = false;
let hideTimer = null;
let anchorRow = null;
let lastBbox = null;
let hoverBboxCb = null;

function clearHideTimer() { if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; } }
function scheduleHide() { clearHideTimer(); hideTimer = setTimeout(hidePop, 200); }
function onEsc(ev) { if (ev.key === 'Escape') hidePop(); }
function onOutsideClick(ev) {
  if (popEl && !popEl.contains(ev.target) && (!anchorRow || !anchorRow.contains(ev.target))) hidePop();
}
function hidePop() {
  clearHideTimer();
  if (popEl) { popEl.remove(); popEl = null; }
  pinned = false; anchorRow = null;
  document.removeEventListener('keydown', onEsc);
  document.removeEventListener('mousedown', onOutsideClick, true);
  if (hoverBboxCb) { hoverBboxCb(null); hoverBboxCb = null; }
}

// 뷰포트 안에 들어오도록 위치를 잡는다: 오른쪽/아래로 넘치면 각각 왼쪽으로 접거나 위로 뒤집는다.
function positionPop(x, y) {
  if (!popEl) return;
  const vw = window.innerWidth, vh = window.innerHeight;
  const r = popEl.getBoundingClientRect();
  let left = Math.min(x + 14, vw - r.width - 8);
  left = Math.max(8, left);
  let top = y + 14;
  if (top + r.height > vh - 8) top = y - r.height - 14;
  top = Math.max(8, top);
  popEl.style.left = `${left}px`;
  popEl.style.top = `${top}px`;
}

function openPop(tr, entry, x, y, onHoverBbox) {
  clearHideTimer();
  if (popEl) popEl.remove();
  popEl = evidencePopover(entry);
  popEl.addEventListener('mouseenter', clearHideTimer);
  popEl.addEventListener('mouseleave', () => { if (!pinned) scheduleHide(); });
  document.body.appendChild(popEl);
  positionPop(x, y);
  anchorRow = tr;
  lastBbox = entry.bbox || null;
  hoverBboxCb = onHoverBbox || null;
  if (lastBbox && onHoverBbox) onHoverBbox(lastBbox);
}

export function renderCompare(host, doc, { onAdopt, onHoverBbox, onGoToEdit } = {}) {
  const state = { filter: 'all' };
  // 채택했지만 아직 저장되지 않은 항목: path → 낙관적으로 보여줄 값. refresh() 에서 비운다.
  const pending = new Map();
  draw();

  // draw() 전에 스크롤 위치(및 그 위치에 있던 행의 path)를 기억해 두었다가, 다시 그린 뒤 복원한다.
  // preserveScroll=false(필터 전환 등)면 맨 위에서 시작한다.
  function draw(preserveScroll = false) {
    if (!doc.golden) {
      clear(host);
      mount(host, el('div', { class: 'empty-state' }, [
        el('div', {}, 'Golden이 없어 비교할 수 없습니다.'),
        onGoToEdit ? el('button', { class: 'btn primary sm', style: 'margin-top:8px', onclick: onGoToEdit }, '편집 탭에서 Golden 만들기') : null,
      ]));
      return;
    }
    const prevWrap = host.querySelector('.cmp-table-wrap');
    const savedScrollTop = prevWrap ? prevWrap.scrollTop : 0;
    let anchorPath = null;
    if (prevWrap) {
      for (const row of prevWrap.querySelectorAll('tr[data-path]')) {
        if (row.offsetTop >= prevWrap.scrollTop) { anchorPath = row.dataset.path; break; }
      }
    }

    clear(host);
    const list = doc.compare || [];
    const c = countsByFilter(list);
    const toolbar = el('div', { class: 'cmp-toolbar seg' }, FILTER_KEYS.map((key) => el('button', {
      class: state.filter === key ? 'active' : '',
      title: key === 'all' ? '모든 비교 항목을 표시합니다.'
        : key === 'mismatch_all' ? '편집 탭·탭 배지와 같은 기준(Golden 대비 AO 또는 Harness 값이 하나라도 다름)입니다.'
        : key === 'mismatch' ? `${statusDescription('MISMATCH')} 형식오류도 포함합니다.` : statusDescription(key.toUpperCase()),
      onclick: () => { state.filter = key; draw(); },
    }, [FILTER_LABEL[key], el('span', { class: `seg-count ${c[key] && key !== 'all' ? 'bad' : ''}` }, String(c[key]))])));
    const scoreCards = el('div', { class: 'cmp-score-cards' }, [scoreCard('AO Extract', doc.score && doc.score.ao), scoreCard('Harness', doc.score && doc.score.harness)]);

    const filtered = list.filter((e) => matchesFilter(e, state.filter));
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
          const isPending = pending.has(e.path);
          const pendingVal = pending.get(e.path);
          const goldenVal = isPending ? pendingVal : e.golden;
          const off = !isPending && [e.ao_status, e.harness_status].some((st) => st && st !== 'MATCH');
          const tr = el('tr', { class: `${off ? 'is-off' : ''} ${isPending ? 'is-pending' : ''}`.trim(), dataset: { path: e.path }, tabindex: '0',
            onmouseenter: (ev) => { if (!pinned || anchorRow === tr) openPop(tr, e, ev.clientX, ev.clientY, onHoverBbox); },
            onmousemove: (ev) => { if (popEl && anchorRow === tr && !pinned) positionPop(ev.clientX, ev.clientY); },
            onmouseleave: () => { if (!pinned) scheduleHide(); },
            onclick: (ev) => {
              if (ev.target.closest('.cmp-adopt')) return;
              if (pinned && anchorRow === tr) { hidePop(); return; }
              // 이미 hover로 열려 있으면(같은 행) 재생성하지 않고 그대로 고정해 스크롤 위치를 보존한다.
              if (!popEl || anchorRow !== tr) openPop(tr, e, ev.clientX, ev.clientY, onHoverBbox);
              pinned = true;
              popEl.classList.add('pinned');
              document.addEventListener('keydown', onEsc);
              document.addEventListener('mousedown', onOutsideClick, true);
            },
          }, [
            el('td', {}, [e.area === 'table' ? el('span', { class: 'cmp-row' }, typeof e.row === 'number' ? `#${e.row + 1}` : `#${Number(String(e.row).slice(1)) + 1} 추가`) : null, el('span', { class: 'cmp-key' }, e.key)]),
            el('td', {}, [
              el('span', { class: 'cmp-val' }, goldenVal == null ? '—' : String(goldenVal)),
              isPending ? el('span', { class: 'badge badge-pending', title: '저장되면 실제 비교 결과로 반영됩니다.' }, '채택됨 · 저장 대기') : null,
            ]),
            el('td', {}, el('div', { class: 'cmp-cell' }, [diffSpan(goldenVal, e.ao), statusBadge(e.ao_status)])),
            el('td', {}, el('div', { class: 'cmp-cell' }, [diffSpan(goldenVal, e.harness), statusBadge(e.harness_status)])),
            el('td', { class: 'cmp-adopt' }, [
              onAdopt && e.ao != null && e.ao !== '' && el('button', { class: 'btn sm', title: 'AO 값을 정답으로', onclick: () => onAdopt(e, e.ao) }, 'AO 채택'),
              onAdopt && e.harness != null && e.harness !== '' && el('button', { class: 'btn sm', title: 'Harness 값을 정답으로', onclick: () => onAdopt(e, e.harness) }, 'H 채택'),
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

    if (preserveScroll) {
      const anchorRowEl = anchorPath && tableWrap.querySelector(`tr[data-path="${CSS.escape(anchorPath)}"]`);
      tableWrap.scrollTop = anchorRowEl ? anchorRowEl.offsetTop : savedScrollTop;
    }
  }

  return {
    // onAdopt 호출 직후 detail.js 가 불러 저장 대기 상태를 낙관적으로 표시한다.
    markAdopted(path, value) { pending.set(path, value); draw(true); },
    flashPath(path) {
      state.filter = 'all'; draw();
      const row = host.querySelector(`tr[data-path="${CSS.escape(path)}"]`);
      if (row) { row.scrollIntoView({ block: 'center', behavior: 'smooth' }); row.classList.add('flash'); setTimeout(() => row.classList.remove('flash'), 1400); }
      return row;
    },
    refresh(newDoc) { doc = newDoc; pending.clear(); draw(true); },
    destroy() { hidePop(); },
  };
}
