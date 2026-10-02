import { el, clear, mount, debounce, toast, isEditingTarget, isMismatch, icon, menuButton, mismatchBadge, classBadges } from './util.js';
import { api } from './api.js';
import { navigate, setNavGuard } from './router.js';
import { createImageViewer } from './imageViewer.js';
import { createJsonViewer } from './jsonViewer.js';
import { createGoldenEditor } from './goldenEditor.js';
import { renderCompare } from './compare.js';
import { buildReconModel, renderReconHTML, buildMarkdown, renderMarkdownToDom } from './reconstruct.js';
import { createDocumentRail } from './documentRail.js';

const RAW_KIND = { golden: 'golden', ao: 'ao_extract', harness: 'harness', ao_ui: 'ao_ui' };

function readFocusMode() {
  try { return localStorage.getItem('lv.bboxMode') === 'locate' ? 'locate' : 'zoom'; } catch { return 'zoom'; }
}
function writeFocusMode(mode) { try { localStorage.setItem('lv.bboxMode', mode); } catch {} }

function readFlag(key) { try { return localStorage.getItem(key) === '1'; } catch { return false; } }
function writeFlag(key, val) { try { localStorage.setItem(key, val ? '1' : '0'); } catch {} }
const RECON_RATIO_MIN = 0.15, RECON_RATIO_MAX = 0.7;
const clampRatio = (r, lo, hi) => Math.min(Math.max(r, lo), hi);
function readReconRatio() {
  try { const n = Number(localStorage.getItem('lv.reconRatio')); return n ? clampRatio(n, RECON_RATIO_MIN, RECON_RATIO_MAX) : 0.3; } catch { return 0.3; }
}
function writeReconRatio(r) { try { localStorage.setItem('lv.reconRatio', r.toFixed(3)); } catch {} }

export function renderDetail(root, bundleId, docId) {
  const state = { view: null, page: 1, tab: 'edit', reconSource: 'golden', reconRenderer: 'html', mismatchCursor: -1, focusMode: readFocusMode(), railCollapsed: readFlag('lv.railCollapsed'), panelCollapsed: readFlag('lv.panelCollapsed'), reconCollapsed: readFlag('lv.reconCollapsed') };
  let doc = null, bundle = null, editor = null, compareApi = null, imgViewer = null, documentRail = null;
  let saveStateEl, reviewInput, enabledInput, offBadge, reconBody, reconSourceButtons = {}, tabHosts = {}, tabButtons = {}, viewToggleBtns = {}, focusModeBtns = {}, pageLabel, pageNavEl, zoomLabel, helpOverlay = null;
  let leftPanel, rightPanel, closeExportMenus, dragCleanup;
  let railHost, workspace, body, rightCollapseBtn;
  let destroyed = false, compareStale = false, rawBuilt = false;
  const drawReconLater = debounce(() => drawRecon(), 300);

  mount(root, el('div', { class: 'loading-block' }, '불러오는 중…'));

  api.getBundle(bundleId).then((b) => { if (destroyed) return; bundle = b; if (documentRail) documentRail.update(bundle.docs, docId); }).catch(() => {});
  api.getDoc(bundleId, docId).then((d) => {
    if (destroyed) return;
    doc = d; state.view = doc.has.preprocessed ? 'preprocessed' : 'original'; build();
  }).catch((e) => {
    if (destroyed) return;
    mount(root, el('div', { class: 'error-block' }, `문서를 불러오지 못했습니다: ${e.message}`));
  });

  function setSaveState(cls, label) {
    saveStateEl.className = `save-state ${cls}`;
    saveStateEl.textContent = label;
  }

  function onKeydown(e) {
    if (e.key === 'Escape' && helpOverlay) { closeHelp(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); editor && editor.save(); return; }
    if (isEditingTarget(e.target)) return;
    if (e.key === 'ArrowLeft') { if (doc.prev) navigate(`#/b/${encodeURIComponent(bundleId)}/d/${encodeURIComponent(doc.prev)}`); }
    else if (e.key === 'ArrowRight') { if (doc.next) navigate(`#/b/${encodeURIComponent(bundleId)}/d/${encodeURIComponent(doc.next)}`); }
    else if (e.key === '+') { editor && editor.addField(); }
    else if (e.key === 'Delete') { editor && editor.deleteFocused(); }
    else if (e.key === 'm' || e.key === 'M') { jumpNextMismatch(e.shiftKey ? -1 : 1); }
    else if (e.key === 'o' || e.key === 'O') { toggleView(); }
    else if (e.key === 'z' || e.key === 'Z') { setFocusMode(state.focusMode === 'zoom' ? 'locate' : 'zoom'); }
    else if (e.key === '1') { setReconSource('golden'); }
    else if (e.key === '2') { setReconSource('ao'); }
    else if (e.key === '3') { setReconSource('harness'); }
    else if (e.key === '[') { toggleRail(); }
    else if (e.key === ']') { togglePanel(); }
    else if (e.key === '?') { openHelp(); }
  }

  // 편집 탭이면 편집기 안에서 이동(입력칸 포커스 유지), 그 외 탭이면 비교 탭으로 전환해 강조한다.
  function jumpNextMismatch(dir = 1) {
    if (state.tab === 'edit') { editor && editor.focusMismatch(dir); return; }
    const entries = (doc.compare || []).filter(isMismatch);
    if (!entries.length) { toast('불일치 항목이 없습니다.'); return; }
    state.mismatchCursor = (state.mismatchCursor + dir + entries.length) % entries.length;
    setTab('compare');
    compareApi && compareApi.flashPath(entries[state.mismatchCursor].path);
  }

  function toggleView() {
    const other = state.view === 'original' ? 'preprocessed' : 'original';
    if (!doc.has[other]) return;
    state.view = other; state.page = 1; loadImage();
    for (const k in viewToggleBtns) viewToggleBtns[k].classList.toggle('active', k === state.view);
  }

  function setFocusMode(mode) {
    state.focusMode = mode;
    focusModeBtns.zoom && focusModeBtns.zoom.classList.toggle('active', mode === 'zoom');
    focusModeBtns.locate && focusModeBtns.locate.classList.toggle('active', mode === 'locate');
    imgViewer && imgViewer.setFocusMode(mode);
    writeFocusMode(mode);
  }

  function animateWidth(elm) {
    if (!elm) return;
    elm.classList.add('lv-anim-w');
    window.setTimeout(() => elm.classList.remove('lv-anim-w'), 200);
  }

  function setRightCollapseBtn(collapsed) {
    if (!rightCollapseBtn) return;
    rightCollapseBtn.title = collapsed ? '검수 패널 펼치기' : '검수 패널 접기';
    rightCollapseBtn.setAttribute('aria-label', rightCollapseBtn.title);
    clear(rightCollapseBtn);
    rightCollapseBtn.appendChild(icon(collapsed ? 'panel-right-open' : 'panel-right-close'));
  }

  function applyRailState(collapsed) {
    workspace && workspace.classList.toggle('rail-collapsed', collapsed);
    documentRail && documentRail.setCollapsed(collapsed);
  }

  function applyPanelState(collapsed) {
    body && body.classList.toggle('panel-collapsed', collapsed);
    setRightCollapseBtn(collapsed);
  }

  function toggleRail() {
    state.railCollapsed = !state.railCollapsed;
    writeFlag('lv.railCollapsed', state.railCollapsed);
    animateWidth(railHost);
    applyRailState(state.railCollapsed);
  }

  function togglePanel() {
    state.panelCollapsed = !state.panelCollapsed;
    writeFlag('lv.panelCollapsed', state.panelCollapsed);
    animateWidth(rightPanel);
    animateWidth(leftPanel);
    applyPanelState(state.panelCollapsed);
  }

  function openHelp() {
    if (helpOverlay) return;
    const rows = [['← / →', '이전 / 다음 문서'], ['Ctrl+S', '저장'], ['+', '필드 추가'], ['Delete', '필드 삭제'],
      ['M / Shift+M', '다음 / 이전 불일치 (편집 탭에서는 편집기 안에서 이동)'], ['O', '원본/전처리 전환'], ['Z', 'bbox hover 확대/위치표시 전환'], ['1 / 2 / 3', 'Golden / AO / Harness 재구성'],
      ['[', '문서 목록 접기/펼치기'], [']', '검수 패널 접기/펼치기'],
      ['↑ / ↓ (비교 탭)', '행 이동 (접힌 소그룹은 헤더에서 멈춤)'], ['A / H (비교 탭)', 'AO / Harness 값 채택'], ['Enter (비교 탭)', '근거 고정/해제, 소그룹 헤더에서는 접기/펼치기'],
      ['?', '도움말']];
    helpOverlay = el('div', { class: 'help-overlay', onclick: (e) => { if (e.target === helpOverlay) closeHelp(); } },
      el('div', { class: 'help-card' }, [
        el('h3', {}, '단축키'),
        ...rows.map(([k, v]) => el('div', { class: 'help-row' }, [el('span', {}, v), el('span', { class: 'kbd' }, k)])),
      ]));
    document.body.appendChild(helpOverlay);
  }
  function closeHelp() { if (helpOverlay) { helpOverlay.remove(); helpOverlay = null; } }

  function setReconSource(src) {
    state.reconSource = src;
    for (const k in reconSourceButtons) reconSourceButtons[k].classList.toggle('active', k === src);
    drawRecon();
  }

  function drawRecon() {
    if (!reconBody || state.reconCollapsed) return; // 접힌 동안은 그리지 않고 펼칠 때 그린다
    let sourceObj;
    if (state.reconSource === 'golden') sourceObj = (editor && editor.getGoldenObject()) || doc.golden;
    else if (state.reconSource === 'ao') sourceObj = doc.ao;
    else sourceObj = doc.harness;
    const model = buildReconModel(sourceObj || { documents: [] }, state.reconSource);
    clear(reconBody);
    reconBody.appendChild(state.reconRenderer === 'html' ? renderReconHTML(model) : renderMarkdownToDom(buildMarkdown(model)));
  }

  function setTab(tab) {
    state.tab = tab;
    for (const k in tabButtons) tabButtons[k].classList.toggle('active', k === tab);
    for (const k in tabHosts) tabHosts[k].style.display = k === tab ? 'flex' : 'none';
    if (tab === 'compare' && compareStale) { compareStale = false; compareApi.refresh(doc); }
    if (tab === 'raw' && !rawBuilt) { rawBuilt = true; buildRawTab(); }
  }

  function loadImage() {
    imgViewer && imgViewer.clearFocus();
    const pages = (doc.pages && doc.pages[state.view]) || 1;
    state.page = Math.min(Math.max(1, state.page), Math.max(1, pages));
    if (pageLabel) pageLabel.textContent = pages > 1 ? `${state.page} / ${pages}` : '';
    if (pageNavEl) pageNavEl.style.display = pages > 1 ? 'flex' : 'none';
    if (!doc.has[state.view]) { imgViewer.empty('이미지가 없습니다.'); return; }
    imgViewer.empty();
    imgViewer.load(api.imageUrl(bundleId, docId, state.view, state.page)).catch((e) => imgViewer.empty(e.message));
  }

  function onHoverBbox(bboxList) {
    if (!imgViewer) return;
    if (!bboxList) { imgViewer.clearFocus(); return; }
    const boxes = bboxList.filter((b) => (b.page || 1) === state.page).map((b) => ({ x: b.box[0], y: b.box[1], w: b.box[2], h: b.box[3] }));
    imgViewer.focusBoxes(boxes);
  }

  function refreshAfterDocUpdate(updated) {
    doc = updated;
    syncDocumentRail();
    if (state.tab === 'compare') compareApi.refresh(doc); else compareStale = true;
    drawReconLater.cancel();
    drawRecon();
    if (reviewInput) reviewInput.checked = doc.review === 'done';
    updateTabCounts();
  }

  function syncDocumentRail() {
    if (!bundle || !doc) return;
    bundle.docs = bundle.docs.map((item) => item.id === docId ? {
      ...item, has: doc.has, errors: doc.errors, review: doc.review, score: doc.score, enabled: doc.enabled !== false,
      doc_type: doc.golden?.documents?.[0]?.doc_type || item.doc_type,
    } : item);
    documentRail?.update(bundle.docs, docId);
  }

  function updateTabCounts() {
    const mismatchCount = (doc.compare || []).filter(isMismatch).length;
    const btn = tabButtons.compare;
    if (btn) { clear(btn); btn.appendChild(document.createTextNode('비교')); if (mismatchCount) btn.appendChild(el('span', { class: 'count' }, String(mismatchCount))); }
  }

  function exportMenu() {
    const guardUnsaved = (e) => {
      if (editor && editor.isDirty()) { e.preventDefault(); toast('저장하지 않은 Golden 변경이 있습니다. 저장 후 내보내세요.', 'error'); }
    };
    return menuButton('내보내기', [
      el('a', { href: api.exportBundleZipUrl(bundleId, docId), onclick: guardUnsaved }, [el('b', {}, '전체 묶음 ZIP'), el('span', {}, '이 문서의 원본·전처리 이미지, AO·Harness·Golden JSON')]),
      el('a', { href: api.exportGoldenXlsxUrl(bundleId, docId), onclick: guardUnsaved }, [el('b', {}, 'Excel'), el('span', {}, '이 문서의 비교·채점 결과')]),
    ]);
  }

  function build() {
    closeExportMenus = () => root.querySelectorAll('.export-pop').forEach((p) => { p.style.display = 'none'; });
    document.addEventListener('click', closeExportMenus);
    document.addEventListener('keydown', onKeydown);
    setNavGuard(() => (editor && editor.isDirty() && !editor.isAutosaveOn()) ? '저장하지 않은 변경사항이 있습니다.' : true);

    saveStateEl = el('span', { class: 'save-state saved' }, '저장됨');
    reviewInput = el('input', { type: 'checkbox', checked: doc.review === 'done',
      onchange: (e) => { const review = e.target.checked ? 'done' : ''; api.putReview(bundleId, docId, review).then(() => { doc.review = review; syncDocumentRail(); toast('검수 상태를 변경했습니다.'); }).catch((err) => { e.target.checked = doc.review === 'done'; toast(err.message, 'error'); }); } });

    // 활성 여부. 비활성 문서는 목록 화면의 '활성' 집계·내보내기에서 빠진다.
    offBadge = el('span', { class: 'badge badge-muted badge-off', style: doc.enabled === false ? null : 'display:none' }, '비활성');
    enabledInput = el('input', { type: 'checkbox', checked: doc.enabled !== false,
      onchange: (e) => {
        const enabled = e.target.checked;
        e.target.disabled = true;
        api.setEnabled(bundleId, [docId], enabled).then((b) => {
          doc.enabled = enabled; bundle = b; offBadge.style.display = enabled ? 'none' : '';
          documentRail?.update(bundle.docs, docId);
          toast(enabled ? '문서를 활성화했습니다.' : '문서를 비활성화했습니다. 활성 목록 집계·내보내기에서 빠집니다.');
        }).catch((err) => { e.target.checked = doc.enabled !== false; toast(err.message, 'error'); })
          .finally(() => { e.target.disabled = false; });
      } });

    const topbar = el('div', { class: 'topbar detail-topbar' }, [
      el('a', { class: 'brand', href: '#/' }, 'Label Viewer'),
      el('div', { class: 'sep' }),
      el('a', { class: 'btn ghost', href: `#/b/${encodeURIComponent(bundleId)}` }, [icon('chevron-left'), '목록']),
      el('div', { class: 'nav-group' }, [
        el('button', { class: 'btn ghost icon', disabled: !doc.prev, onclick: () => navigate(`#/b/${encodeURIComponent(bundleId)}/d/${encodeURIComponent(doc.prev)}`), title: '이전 문서 (←)', 'aria-label': '이전 문서' }, icon('chevron-left')),
        el('button', { class: 'btn ghost icon', disabled: !doc.next, onclick: () => navigate(`#/b/${encodeURIComponent(bundleId)}/d/${encodeURIComponent(doc.next)}`), title: '다음 문서 (→)', 'aria-label': '다음 문서' }, icon('chevron-right')),
      ]),
      el('div', { class: 'title' }, [doc.id, doc.doc_type ? el('small', {}, doc.doc_type) : null, offBadge, mismatchBadge(doc.doc_type_mismatch), classBadges(doc.classification)]),
      el('div', { class: 'grow' }),
      saveStateEl,
      el('button', { class: 'btn primary sm', title: 'Ctrl+S', onclick: () => editor && editor.save() }, '저장'),
      el('label', { class: 'switch', title: '끄면 활성 목록 집계·내보내기에서 빠집니다' }, [enabledInput, '활성']),
      el('label', { class: 'switch' }, [reviewInput, '검수 완료']),
      exportMenu(),
      el('button', { class: 'btn ghost icon', title: '단축키 (?)', 'aria-label': '단축키', onclick: openHelp }, icon('help-circle')),
    ]);

    // --- 좌측: 이미지 뷰어 ---
    const viewToggle = el('div', { class: 'seg' }, [
      (viewToggleBtns.original = el('button', { class: state.view === 'original' ? 'active' : '', disabled: !doc.has.original, onclick: () => { state.view = 'original'; state.page = 1; loadImage(); refreshToggle(); } }, '원본')),
      (viewToggleBtns.preprocessed = el('button', { class: state.view === 'preprocessed' ? 'active' : '', disabled: !doc.has.preprocessed, onclick: () => { state.view = 'preprocessed'; state.page = 1; loadImage(); refreshToggle(); } }, '전처리')),
    ]);
    function refreshToggle() { viewToggleBtns.original.classList.toggle('active', state.view === 'original'); viewToggleBtns.preprocessed.classList.toggle('active', state.view === 'preprocessed'); }

    const focusModeSeg = el('div', { class: 'seg focus-mode-seg' }, [
      (focusModeBtns.zoom = el('button', { class: state.focusMode === 'zoom' ? 'active' : '', title: '행에 마우스를 올리면 bbox 위치로 자동 확대합니다. (Z)', onclick: () => setFocusMode('zoom') }, '자동 확대')),
      (focusModeBtns.locate = el('button', { class: state.focusMode === 'locate' ? 'active' : '', title: '확대하지 않고 bbox 위치만 표시합니다. 화면 밖이면 살짝 이동합니다. (Z)', onclick: () => setFocusMode('locate') }, '위치만 표시')),
    ]);

    pageLabel = el('span', {}, '');
    zoomLabel = el('span', { class: 'zoom-pct' }, '100%');
    const stage = el('div', { class: 'viewer-stage' });
    pageNavEl = el('div', { class: 'page-nav', style: 'display:none' }, [
      el('button', { class: 'btn sm icon', onclick: () => { state.page--; loadImage(); } }, icon('chevron-left')),
      pageLabel,
      el('button', { class: 'btn sm icon', onclick: () => { state.page++; loadImage(); } }, icon('chevron-right')),
    ]);
    const viewerToolbar = el('div', { class: 'panel-head viewer-toolbar' }, [
      viewToggle,
      focusModeSeg,
      pageNavEl,
      el('div', { class: 'zoom-group' }, [
        el('button', { class: 'btn sm icon', onclick: () => imgViewer.zoomOut(), title: '축소' }, icon('zoom-out')),
        el('button', { class: 'btn sm icon', onclick: () => imgViewer.zoomIn(), title: '확대' }, icon('zoom-in')),
        zoomLabel,
        el('button', { class: 'btn ghost sm', onclick: () => imgViewer.fitWidth(), title: '너비 맞춤' }, [icon('columns'), el('span', { class: 'lbl' }, '너비 맞춤')]),
        el('button', { class: 'btn ghost sm', onclick: () => imgViewer.fitPage(), title: '전체 보기' }, [icon('maximize'), el('span', { class: 'lbl' }, '전체 보기')]),
      ]),
    ]);
    leftPanel = el('div', { class: 'detail-left' }, [viewerToolbar, stage]);
    imgViewer = createImageViewer(stage, { onZoomChange: (s) => { zoomLabel.textContent = `${Math.round(s * 100)}%`; }, focusMode: state.focusMode });

    // --- 우측: 탭 + 재구성 ---
    tabButtons.edit = el('button', { class: 'tab-btn active' }, '편집');
    tabButtons.compare = el('button', { class: 'tab-btn' }, '비교');
    tabButtons.raw = el('button', { class: 'tab-btn' }, 'JSON');
    tabButtons.edit.addEventListener('click', () => setTab('edit'));
    tabButtons.compare.addEventListener('click', () => setTab('compare'));
    tabButtons.raw.addEventListener('click', () => setTab('raw'));
    rightCollapseBtn = el('button', { class: 'btn ghost icon', onclick: () => togglePanel() }, icon('panel-right-close'));
    setRightCollapseBtn(state.panelCollapsed);
    const tabs = el('div', { class: 'tabs panel-head' }, [tabButtons.edit, tabButtons.compare, tabButtons.raw, el('div', { class: 'grow' }), rightCollapseBtn]);

    tabHosts.edit = el('div', { class: 'tab-panel-host' });
    tabHosts.compare = el('div', { class: 'tab-panel-host', style: 'display:none' });
    tabHosts.raw = el('div', { class: 'tab-panel-host', style: 'display:none' });

    editor = createGoldenEditor(tabHosts.edit, {
      bundleId, docId, doc,
      onDirtyChange: (isDirty) => { setSaveState(isDirty ? 'dirty' : 'saved', isDirty ? '변경사항 있음' : '저장됨'); if (isDirty && state.reconSource === 'golden') drawReconLater(); },
      onSaveStart: () => setSaveState('saving', '저장 중…'),
      onSaveOk: (updated) => {
        const stillDirty = editor.isDirty();
        setSaveState(stillDirty ? 'dirty' : 'saved', stillDirty ? '변경사항 있음' : '저장됨');
        refreshAfterDocUpdate(updated);
        if (!stillDirty) toast('저장했습니다.');
      },
      onSaveErr: () => setSaveState('dirty', '변경사항 있음'),
      onGoldenCreated: (updated) => { refreshAfterDocUpdate(updated); },
      onHoverBbox,
    });

    compareApi = renderCompare(tabHosts.compare, doc, {
      onAdopt: (entry, value) => {
        const prev = editor.adoptValue(entry, value);
        if (prev === undefined) return;
        compareApi.markAdopted(entry.path, value);
        toast(`${value === '' ? '빈 값을' : '값을'} Golden에 채택했습니다.`, 'info', { label: '되돌리기', onClick: () => { editor.adoptValue(entry, prev); compareApi.markAdopted(entry.path, prev); } });
      },
      onHoverBbox,
      onGoToEdit: () => setTab('edit'),
    });

    const vsplit = el('div', { class: 'splitter v', style: state.reconCollapsed ? 'display:none' : '' });
    reconBody = el('div', { class: 'recon-body' });
    reconSourceButtons.golden = el('button', { class: 'active', onclick: () => setReconSource('golden') }, 'Golden');
    reconSourceButtons.ao = el('button', { onclick: () => setReconSource('ao'), disabled: !doc.has.ao_extract }, 'AO');
    reconSourceButtons.harness = el('button', { onclick: () => setReconSource('harness'), disabled: !doc.has.harness }, 'Harness');
    const rendererButtons = {
      html: el('button', { class: 'active', onclick: () => { state.reconRenderer = 'html'; rendererButtons.html.classList.add('active'); rendererButtons.md.classList.remove('active'); drawRecon(); } }, 'HTML'),
      md: el('button', { onclick: () => { state.reconRenderer = 'md'; rendererButtons.md.classList.add('active'); rendererButtons.html.classList.remove('active'); drawRecon(); } }, 'Markdown'),
    };
    const reconCollapseBtn = el('button', {
      class: 'btn ghost icon sm', title: state.reconCollapsed ? '펼치기' : '접기', 'aria-label': '재구성 패널 접기/펼치기',
      onclick: toggleReconCollapse,
    }, icon(state.reconCollapsed ? 'chevron-right' : 'chevron-down'));
    const reconPanel = el('div', { class: `recon-panel ${state.reconCollapsed ? 'collapsed' : ''}`, style: `--recon-ratio:${readReconRatio()}` }, [
      el('div', { class: 'panel-head recon-toolbar' }, [
        reconCollapseBtn,
        el('span', { class: 'label' }, '재구성 보기'),
        el('div', { class: 'seg' }, [reconSourceButtons.golden, reconSourceButtons.ao, reconSourceButtons.harness]),
        el('div', { class: 'seg' }, [rendererButtons.html, rendererButtons.md]),
      ]),
      reconBody,
    ]);
    function toggleReconCollapse() {
      state.reconCollapsed = !state.reconCollapsed;
      writeFlag('lv.reconCollapsed', state.reconCollapsed);
      reconPanel.classList.toggle('collapsed', state.reconCollapsed);
      vsplit.style.display = state.reconCollapsed ? 'none' : '';
      reconCollapseBtn.title = state.reconCollapsed ? '펼치기' : '접기';
      clear(reconCollapseBtn); reconCollapseBtn.appendChild(icon(state.reconCollapsed ? 'chevron-right' : 'chevron-down'));
      drawRecon();
    }

    let dragging = false, startY = 0, startH = 0;
    const onVMove = (e) => { if (dragging) reconPanel.style.setProperty('--recon-ratio', clampRatio((startH - (e.clientY - startY)) / rightPanel.clientHeight, RECON_RATIO_MIN, RECON_RATIO_MAX)); };
    const onVUp = () => { if (dragging) writeReconRatio(Number(reconPanel.style.getPropertyValue('--recon-ratio'))); dragging = false; vsplit.classList.remove('active'); };
    vsplit.addEventListener('mousedown', (e) => { e.preventDefault(); dragging = true; startY = e.clientY; startH = reconPanel.getBoundingClientRect().height; vsplit.classList.add('active'); });
    window.addEventListener('mousemove', onVMove);
    window.addEventListener('mouseup', onVUp);

    rightPanel = el('div', { class: 'detail-right' }, [tabs, tabHosts.edit, tabHosts.compare, tabHosts.raw, vsplit, reconPanel, el('div', { class: 'panel-vlabel' }, '검수')]);

    const resizer = el('div', { class: 'splitter h detail-resizer' });
    let rdrag = false, rStartX = 0, rStartW = 0;
    const onRMove = (e) => {
      if (!rdrag) return;
      const total = leftPanel.parentElement.clientWidth;
      const w = clampRatio(rStartW + (e.clientX - rStartX), 280, total - 470);
      leftPanel.style.width = `${(w / total * 100).toFixed(2)}%`;
    };
    const onRUp = () => { rdrag = false; resizer.classList.remove('active'); };
    resizer.addEventListener('mousedown', (e) => { e.preventDefault(); rdrag = true; rStartX = e.clientX; rStartW = leftPanel.getBoundingClientRect().width; resizer.classList.add('active'); });
    window.addEventListener('mousemove', onRMove);
    window.addEventListener('mouseup', onRUp);
    dragCleanup = () => {
      window.removeEventListener('mousemove', onVMove); window.removeEventListener('mouseup', onVUp);
      window.removeEventListener('mousemove', onRMove); window.removeEventListener('mouseup', onRUp);
    };

    body = el('div', { class: 'detail-body' }, [leftPanel, resizer, rightPanel]);
    railHost = el('aside', { class: 'doc-rail', 'aria-label': '문서 목록' });
    const railResizer = el('div', { class: 'splitter h doc-rail-resizer', role: 'separator', 'aria-label': '문서 목록 너비 조절' });
    let railDragging = false;
    const onRailMove = (e) => { if (railDragging) railHost.style.width = `${Math.max(180, Math.min(360, e.clientX - railHost.getBoundingClientRect().left))}px`; };
    const onRailUp = () => { railDragging = false; railResizer.classList.remove('active'); };
    railResizer.addEventListener('mousedown', (e) => { e.preventDefault(); railDragging = true; railResizer.classList.add('active'); });
    window.addEventListener('mousemove', onRailMove);
    window.addEventListener('mouseup', onRailUp);
    const cleanupPanelDrags = dragCleanup;
    dragCleanup = () => { cleanupPanelDrags(); window.removeEventListener('mousemove', onRailMove); window.removeEventListener('mouseup', onRailUp); };
    documentRail = createDocumentRail(railHost, bundle?.docs || [], docId,
      (nextId) => nextId !== docId && navigate(`#/b/${encodeURIComponent(bundleId)}/d/${encodeURIComponent(nextId)}`),
      { onToggleCollapse: toggleRail, bundleId });
    workspace = el('div', { class: 'detail-main' }, [railHost, railResizer, body]);

    const screen = el('div', { class: 'detail-screen' }, [
      topbar,
      doc.errors && doc.errors.length ? el('div', { class: 'error-block' }, [
        `이 문서에서 오류가 발견되었습니다:`,
        el('ul', { class: 'error-list' }, doc.errors.map((msg) => el('li', {}, msg))),
      ]) : null,
      workspace,
    ]);
    mount(root, screen);

    applyRailState(state.railCollapsed);
    applyPanelState(state.panelCollapsed);

    loadImage();
    drawRecon();
    updateTabCounts();
    for (const id of [doc.prev, doc.next]) if (id && doc.has[state.view]) new Image().src = api.imageUrl(bundleId, id, state.view); // 이웃 문서 이미지 미리 받기
  }

  function buildRawTab() {
    const viewerHost = el('div', { class: 'json-viewer' });
    const jsonViewer = createJsonViewer(viewerHost);
    const sourceLabels = { golden: 'Golden', ao: 'AO Extract', harness: 'Harness', ao_ui: 'AO UI' };
    const sel = Object.fromEntries(Object.entries(sourceLabels)
      .filter(([key]) => key !== 'ao_ui' || doc.has.ao_ui)
      .map(([key, label]) => [key, el('button', { disabled: !doc.has[RAW_KIND[key]] }, label)]));
    let current = Object.keys(sel).find((key) => doc.has[RAW_KIND[key]]) || 'golden';
    function load(kind) {
      current = kind;
      for (const k in sel) sel[k].classList.toggle('active', k === kind);
      if (!doc.has[RAW_KIND[kind]]) { jsonViewer.showMessage(`${sourceLabels[kind]} 파일 없음`, '이 소스에는 원본 JSON이 없습니다.', 'folder'); return; }
      jsonViewer.showMessage('불러오는 중…');
      api.getRaw(bundleId, docId, RAW_KIND[kind]).then((text) => {
        if (kind !== current) return;
        jsonViewer.show(text);
      }).catch(() => { if (kind === current) jsonViewer.showMessage(`${sourceLabels[kind]} 파일을 불러오지 못했습니다.`, '', 'alert-triangle'); });
    }
    for (const [key, button] of Object.entries(sel)) button.addEventListener('click', () => load(key));
    mount(tabHosts.raw, el('div', { class: 'raw-json-panel' }, [
      el('div', { class: 'raw-json-toolbar' }, [el('div', { class: 'seg' }, Object.values(sel))]),
      viewerHost,
    ]));
    load(current);
  }

  return () => {
    destroyed = true;
    document.removeEventListener('keydown', onKeydown);
    drawReconLater.cancel();
    if (closeExportMenus) document.removeEventListener('click', closeExportMenus);
    if (dragCleanup) dragCleanup();
    if (documentRail) documentRail.destroy();
    setNavGuard(null);
    editor && editor.destroy();
    imgViewer && imgViewer.destroy();
    compareApi && compareApi.destroy();
    closeHelp();
  };
}
