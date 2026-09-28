import { el, clear, mount, charDiff, fmtPct, statusBadge, scoreCard, statusDescription, isMismatch, entryState, STATUSES, STATUS_TONE, icon, toast } from './util.js';

// 필터 키 순서. 기본은 불일치 전체이고 '전체'는 마지막. 'mismatch_all' 은 탭 배지·사이드바·편집 탭 요약과 같은 isMismatch 기준.
const FILTER_KEYS = ['mismatch_all', 'mismatch', 'missing', 'extra', 'all'];
const FILTER_LABEL = { all: '전체', mismatch_all: '불일치 전체', mismatch: '불일치', missing: '누락', extra: '추가' };
const FILTER_STATUS = { mismatch: ['MISMATCH', 'TYPE_MISMATCH'], missing: ['MISSING'], extra: ['EXTRA'] };

// 선택한 필터/점수 카드 펼침 상태를 기억한다(세션 간).
function readStr(key, fallback) { try { const v = localStorage.getItem(key); return v == null ? fallback : v; } catch { return fallback; } }
function writeStr(key, val) { try { localStorage.setItem(key, val); } catch {} }
function readFlag(key) { try { return localStorage.getItem(key) === '1'; } catch { return false; } }
function writeFlag(key, val) { try { localStorage.setItem(key, val ? '1' : '0'); } catch {} }

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

// 내부 경로(documents[0].groups[..].fields[..])를 사람이 읽는 위치로 바꾼다.
function entryLocation(entry) {
  const { area, container, row, key } = entry;
  if (area === 'field') return `필드 › ${key}`;
  if (area === 'group') return `${container} › ${key}`;
  const rowLabel = typeof row === 'string' && row.startsWith('+')
    ? `추가 행 ${Number(row.slice(1)) + 1}`
    : `#${Number(row) + 1}`;
  return `${container} › ${rowLabel} › ${key}`;
}

// AO/Harness 값 셀: 값이 있으면 편집 탭 .gs-chip 스타일을 재사용한 채택 버튼, 없으면 일반 칸.
// Golden 이 비어 있으면(EXTRA 성격) 빈 문자열과의 문자 diff 로 전체가 빨갛게 보이지 않도록 diff 없이 중립색으로 보여준다.
function valueCell(kind, label, e, goldenVal, onAdopt) {
  const value = e[kind];
  const status = e[`${kind}_status`];
  const goldenEmpty = goldenVal == null || goldenVal === '';
  const valSpan = goldenEmpty ? el('span', { class: 'cmp-val' }, value == null || value === '' ? '—' : String(value)) : diffSpan(goldenVal, value);
  const body = [valSpan, statusBadge(status)];
  const available = value != null && value !== '';
  if (!onAdopt || !available) return el('td', {}, el('div', { class: 'cmp-cell' }, body));
  return el('td', {}, el('button', {
    class: 'gs-chip cmp-chip', type: 'button', title: `${label} 값을 Golden에 채택`,
    onclick: (ev) => { ev.stopPropagation(); onAdopt(e, value); },
  }, body));
}

// 점수 카드의 압축 한 줄 요약(제목·정확도·작은 상태 막대). scoreCard() 와 같은 톤(STATUS_TONE)을 쓴다.
function scoreMini(label, score) {
  const bar = score ? el('span', { class: 'cmp-score-mini-bar' }, STATUSES.filter((k) => score[k]).map((k) =>
    el('i', { class: `tone-${STATUS_TONE[k]}`, style: `width:${(score[k] / (score.total || 1)) * 100}%`, title: `${k} ${score[k]}` }))) : null;
  return el('span', { class: 'cmp-score-mini' }, [el('b', {}, label), ` ${score ? fmtPct(score.accuracy) : '—'}`, bar]);
}

function evidencePopover(entry) {
  const box = el('div', { class: 'evidence-pop' });
  box.appendChild(el('div', { class: 'ev-loc' }, entryLocation(entry)));
  const rows = [];
  if (entry.ao_confidence != null) rows.push(el('div', { class: 'ev-row' }, [el('span', {}, 'AO 신뢰도'), el('span', {}, fmtPct(entry.ao_confidence))]));
  box.appendChild(el('h5', {}, '근거'));
  if (rows.length) box.appendChild(el('div', {}, rows));
  const ev = entry.evidence;
  if (!ev) {
    box.appendChild(el('div', { class: 'hint', style: 'margin-top:8px' }, '하네스 근거 없음'));
  } else {
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
  }
  box.appendChild(el('details', { class: 'ev-detail' }, [
    el('summary', {}, '상세'),
    el('div', { class: 'ev-row' }, [
      el('span', {}, '경로'),
      el('span', { class: 'ev-path' }, [
        el('span', { class: 'mono' }, entry.path),
        el('button', {
          class: 'btn ghost sm icon', title: '경로 복사', 'aria-label': '경로 복사',
          onclick: () => { navigator.clipboard && navigator.clipboard.writeText(entry.path).then(() => toast('경로를 복사했습니다.')); },
        }, icon('copy')),
      ]),
    ]),
  ]));
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

// 호출 행(anchorRow)을 가리지 않도록 행 바로 위나 아래(가용 공간이 큰 쪽)에 둔다.
// 수평은 커서 x 근처로 두되 뷰포트 안으로 클램프한다.
function positionPop(x, y) {
  if (!popEl) return;
  const vw = window.innerWidth, vh = window.innerHeight;
  const r = popEl.getBoundingClientRect();
  const gap = 8;
  const rowRect = anchorRow && anchorRow.getBoundingClientRect();
  let top;
  if (rowRect) {
    const spaceBelow = vh - rowRect.bottom;
    const spaceAbove = rowRect.top;
    top = spaceBelow >= spaceAbove ? rowRect.bottom + gap : rowRect.top - gap - r.height;
  } else {
    top = y + 14;
  }
  top = Math.max(gap, Math.min(top, vh - r.height - gap));
  let left = Math.min(x + 14, vw - r.width - gap);
  left = Math.max(gap, left);
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
  anchorRow = tr;
  positionPop(x, y);
  lastBbox = entry.bbox || null;
  hoverBboxCb = onHoverBbox || null;
  if (lastBbox && onHoverBbox) onHoverBbox(lastBbox);
}

export function renderCompare(host, doc, { onAdopt, onHoverBbox, onGoToEdit } = {}) {
  const savedFilter = readStr('lv.cmpFilter', '');
  const state = { filter: FILTER_KEYS.includes(savedFilter) ? savedFilter : 'mismatch_all', scoreExpanded: readFlag('lv.cmpScoreExpanded') };
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
      onclick: () => { state.filter = key; writeStr('lv.cmpFilter', key); draw(); },
    }, [FILTER_LABEL[key], el('span', { class: `seg-count ${c[key] && key !== 'all' ? 'bad' : ''}` }, String(c[key]))])));
    // 점수 카드: 기본은 한 줄 요약, 클릭하면 펼침 상태를 기억하며 scoreCard() 상세로 바꾼다.
    const scoreToggle = el('button', {
      class: 'cmp-score-toggle', type: 'button', title: state.scoreExpanded ? '점수 상세 접기' : '점수 상세 펼치기',
      onclick: () => { state.scoreExpanded = !state.scoreExpanded; writeFlag('lv.cmpScoreExpanded', state.scoreExpanded); draw(true); },
    }, [
      el('div', { class: 'cmp-score-line' }, [scoreMini('AO', doc.score && doc.score.ao), scoreMini('Harness', doc.score && doc.score.harness)]),
      icon(state.scoreExpanded ? 'chevrons-down-up' : 'chevrons-up-down'),
    ]);
    const scoreCards = state.scoreExpanded
      ? el('div', { class: 'cmp-score-cards' }, [scoreCard('AO Extract', doc.score && doc.score.ao), scoreCard('Harness', doc.score && doc.score.harness)])
      : null;

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
        tbody.appendChild(el('tr', { class: 'cmp-group' }, el('td', { colspan: '4' }, [el('span', { class: 'kind' }, kind), container || null])));
        for (const e of rows) {
          const isPending = pending.has(e.path);
          const pendingVal = pending.get(e.path);
          const goldenVal = isPending ? pendingVal : e.golden;
          // 행/셀 상태는 편집 탭과 같은 entryState 하나로 정한다: bad(값 불일치) > warn(Golden 빈 값) > weak(한쪽 소스만 누락/추가).
          const rowState = isPending ? '' : entryState(e, goldenVal);
          const tr = el('tr', { class: `${rowState} ${isPending ? 'is-pending' : ''}`.trim(), dataset: { path: e.path }, tabindex: '0',
            onmouseenter: (ev) => { if (!pinned || anchorRow === tr) openPop(tr, e, ev.clientX, ev.clientY, onHoverBbox); },
            onmousemove: (ev) => { if (popEl && anchorRow === tr && !pinned) positionPop(ev.clientX, ev.clientY); },
            onmouseleave: () => { if (!pinned) scheduleHide(); },
            onclick: (ev) => {
              if (ev.target.closest('.cmp-chip')) return;
              if (pinned && anchorRow === tr) { hidePop(); return; }
              // 이미 hover로 열려 있으면(같은 행) 재생성하지 않고 그대로 고정해 스크롤 위치를 보존한다.
              if (!popEl || anchorRow !== tr) openPop(tr, e, ev.clientX, ev.clientY, onHoverBbox);
              pinned = true;
              popEl.classList.add('pinned');
              document.addEventListener('keydown', onEsc);
              document.addEventListener('mousedown', onOutsideClick, true);
            },
          }, [
            el('td', {}, el('div', { class: 'cmp-item' }, [e.area === 'table' ? el('span', { class: 'cmp-row' }, typeof e.row === 'number' ? `#${e.row + 1}` : `#${Number(String(e.row).slice(1)) + 1} 추가`) : null, el('span', { class: 'cmp-key', title: e.key }, e.key)])),
            el('td', { class: rowState === 'warn' ? 'cmp-golden-warn' : '' }, [
              el('span', { class: 'cmp-val' }, goldenVal == null ? '—' : String(goldenVal)),
              isPending ? el('span', { class: 'badge badge-pending', title: '저장되면 실제 비교 결과로 반영됩니다.' }, '채택됨 · 저장 대기') : null,
            ]),
            valueCell('ao', 'AO', e, goldenVal, onAdopt),
            valueCell('harness', 'Harness', e, goldenVal, onAdopt),
          ]);
          tbody.appendChild(tr);
        }
      }
      tableWrap.appendChild(el('table', { class: 'cmp-table' }, [
        el('thead', {}, el('tr', {}, ['항목', 'Golden', 'AO', 'Harness'].map((h) => el('th', {}, h)))),
        tbody,
      ]));
    }
    mount(host, [toolbar, scoreToggle, scoreCards, tableWrap]);

    if (preserveScroll) {
      const anchorRowEl = anchorPath && tableWrap.querySelector(`tr[data-path="${CSS.escape(anchorPath)}"]`);
      tableWrap.scrollTop = anchorRowEl ? anchorRowEl.offsetTop : savedScrollTop;
    }
  }

  return {
    // onAdopt 호출 직후 detail.js 가 불러 저장 대기 상태를 낙관적으로 표시한다.
    markAdopted(path, value) { pending.set(path, value); draw(true); },
    flashPath(path) {
      // 대상 행이 현재 필터에 없을 때만 필터를 '전체'로 바꾼다. 이미 보이는 행이면 필터를 유지한다.
      const entry = (doc.compare || []).find((c) => c.path === path);
      if (!entry || !matchesFilter(entry, state.filter)) { state.filter = 'all'; writeStr('lv.cmpFilter', 'all'); }
      draw();
      const row = host.querySelector(`tr[data-path="${CSS.escape(path)}"]`);
      if (row) { row.scrollIntoView({ block: 'center', behavior: 'smooth' }); row.classList.add('flash'); setTimeout(() => row.classList.remove('flash'), 1400); }
      return row;
    },
    refresh(newDoc) { doc = newDoc; pending.clear(); draw(true); },
    destroy() { hidePop(); },
  };
}
