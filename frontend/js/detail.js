import { el, clear, mount, toast, isEditingTarget, icon, menuButton } from './util.js';
import { api } from './api.js';
import { navigate, setNavGuard } from './router.js';
import { createImageViewer } from './imageViewer.js';
import { createJsonViewer } from './jsonViewer.js';
import { createGoldenEditor } from './goldenEditor.js';
import { renderCompare } from './compare.js';
import { buildReconModel, renderReconHTML, buildMarkdown, renderMarkdownToDom } from './reconstruct.js';
import { createDocumentRail } from './documentRail.js';

const RAW_KIND = { golden: 'golden', ao: 'ao_extract', harness: 'harness' };

export function renderDetail(root, bundleId, docId) {
  const state = { view: null, page: 1, tab: 'edit', reconSource: 'golden', reconRenderer: 'html', mismatchCursor: -1 };
  let doc = null, bundle = null, editor = null, compareApi = null, imgViewer = null, documentRail = null;
  let saveStateEl, reviewInput, reconBody, reconSourceButtons = {}, tabHosts = {}, tabButtons = {}, viewToggleBtns = {}, pageLabel, pageNavEl, zoomLabel, helpOverlay = null;
  let leftPanel, rightPanel, closeExportMenus, dragCleanup;
  let destroyed = false;

  mount(root, el('div', { class: 'loading-block' }, '불러오는 중…'));

  api.getBundle(bundleId).then((b) => { if (destroyed) return; bundle = b; if (documentRail) documentRail.update(bundle.docs, docId); }).catch(() => {});
  api.getDoc(bundleId, docId).then((d) => {
    if (destroyed) return;
    doc = d; state.view = doc.has.original ? 'original' : 'preprocessed'; build();
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
    else if (e.key === 'm' || e.key === 'M') { jumpNextMismatch(); }
    else if (e.key === 'o' || e.key === 'O') { toggleView(); }
    else if (e.key === '1') { setReconSource('golden'); }
    else if (e.key === '2') { setReconSource('ao'); }
    else if (e.key === '3') { setReconSource('harness'); }
    else if (e.key === '?') { openHelp(); }
  }

  function jumpNextMismatch() {
    const entries = (doc.compare || []).filter((e) => (e.ao_status && e.ao_status !== 'MATCH') || (e.harness_status && e.harness_status !== 'MATCH'));
    if (!entries.length) { toast('불일치 항목이 없습니다.'); return; }
    state.mismatchCursor = (state.mismatchCursor + 1) % entries.length;
    setTab('compare');
    compareApi && compareApi.flashPath(entries[state.mismatchCursor].path);
  }

  function toggleView() {
    const other = state.view === 'original' ? 'preprocessed' : 'original';
    if (!doc.has[other]) return;
    state.view = other; state.page = 1; loadImage();
    for (const k in viewToggleBtns) viewToggleBtns[k].classList.toggle('active', k === state.view);
  }

  function openHelp() {
    if (helpOverlay) return;
    const rows = [['← / →', '이전 / 다음 문서'], ['Ctrl+S', '저장'], ['+', 'Field 추가'], ['Delete', 'Field 삭제'],
      ['M', '다음 Mismatch'], ['O', '원본/전처리 전환'], ['1 / 2 / 3', 'Golden / AO / Harness 재구성'], ['?', '도움말']];
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
    if (!reconBody) return;
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
    compareApi && compareApi.refresh(doc);
    drawRecon();
    if (reviewInput) reviewInput.checked = doc.review === 'done';
    updateTabCounts();
  }

  function syncDocumentRail() {
    if (!bundle || !doc) return;
    bundle.docs = bundle.docs.map((item) => item.id === docId ? {
      ...item, has: doc.has, errors: doc.errors, review: doc.review, score: doc.score,
      doc_type: doc.golden?.documents?.[0]?.doc_type || item.doc_type,
    } : item);
    documentRail?.update(bundle.docs, docId);
  }

  function updateTabCounts() {
    const mismatchCount = (doc.compare || []).filter((e) => (e.ao_status && e.ao_status !== 'MATCH') || (e.harness_status && e.harness_status !== 'MATCH')).length;
    const btn = tabButtons.compare;
    if (btn) { clear(btn); btn.appendChild(document.createTextNode('비교')); if (mismatchCount) btn.appendChild(el('span', { class: 'count' }, String(mismatchCount))); }
  }

  function exportMenu() {
    return menuButton('내보내기', [
      el('button', { onclick: () => {
        const g = (editor && editor.getGoldenObject()) || doc.golden;
        if (!g) { toast('Golden Set이 없습니다.', 'error'); return; }
        const blob = new Blob([JSON.stringify(g, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = el('a', { href: url, download: `${docId}.json` });
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
      } }, [el('b', {}, 'Golden JSON'), el('span', {}, '이 문서의 정답지')]),
      el('a', { href: api.exportGoldenXlsxUrl(bundleId, docId) }, [el('b', {}, 'Excel'), el('span', {}, '이 문서의 비교·채점 결과')]),
    ]);
  }

  function build() {
    closeExportMenus = () => root.querySelectorAll('.export-pop').forEach((p) => { p.style.display = 'none'; });
    document.addEventListener('click', closeExportMenus);
    document.addEventListener('keydown', onKeydown);
    setNavGuard(() => (editor && editor.isDirty() && !editor.isAutosaveOn()) ? '저장하지 않은 변경사항이 있습니다.' : true);

    saveStateEl = el('span', { class: 'save-state' }, 'Saved');
    reviewInput = el('input', { type: 'checkbox', checked: doc.review === 'done',
      onchange: (e) => { const review = e.target.checked ? 'done' : ''; api.putReview(bundleId, docId, review).then(() => { doc.review = review; syncDocumentRail(); toast('검수 상태를 변경했습니다.'); }).catch((err) => { e.target.checked = doc.review === 'done'; toast(err.message, 'error'); }); } });

    const topbar = el('div', { class: 'topbar detail-topbar' }, [
      el('a', { class: 'brand', href: '#/' }, 'Label Viewer'),
      el('div', { class: 'sep' }),
      el('a', { class: 'back', href: `#/b/${encodeURIComponent(bundleId)}` }, [icon('left'), '목록']),
      el('div', { class: 'nav-group' }, [
        el('button', { class: 'btn btn-icon', disabled: !doc.prev, onclick: () => navigate(`#/b/${encodeURIComponent(bundleId)}/d/${encodeURIComponent(doc.prev)}`), title: '이전 문서 (←)', 'aria-label': '이전 문서' }, icon('left')),
        el('button', { class: 'btn btn-icon', disabled: !doc.next, onclick: () => navigate(`#/b/${encodeURIComponent(bundleId)}/d/${encodeURIComponent(doc.next)}`), title: '다음 문서 (→)', 'aria-label': '다음 문서' }, icon('right')),
      ]),
      el('div', { class: 'title' }, [doc.id, doc.golden && doc.golden.documents && doc.golden.documents[0] && doc.golden.documents[0].doc_type ? el('small', {}, doc.golden.documents[0].doc_type) : null]),
      el('div', { class: 'grow' }),
      saveStateEl,
      el('button', { class: 'btn btn-primary btn-sm', title: 'Ctrl+S', onclick: () => editor && editor.save() }, '저장'),
      el('label', { class: 'review-toggle' }, [reviewInput, '검수 완료']),
      exportMenu(),
      el('button', { class: 'btn btn-ghost btn-icon', title: '단축키 (?)', onclick: openHelp }, '?'),
    ]);

    // --- 좌측: 이미지 뷰어 ---
    const viewToggle = el('div', { class: 'toggle-group' }, [
      (viewToggleBtns.original = el('button', { class: state.view === 'original' ? 'active' : '', disabled: !doc.has.original, onclick: () => { state.view = 'original'; state.page = 1; loadImage(); refreshToggle(); } }, '원본')),
      (viewToggleBtns.preprocessed = el('button', { class: state.view === 'preprocessed' ? 'active' : '', disabled: !doc.has.preprocessed, onclick: () => { state.view = 'preprocessed'; state.page = 1; loadImage(); refreshToggle(); } }, '전처리')),
    ]);
    function refreshToggle() { viewToggleBtns.original.classList.toggle('active', state.view === 'original'); viewToggleBtns.preprocessed.classList.toggle('active', state.view === 'preprocessed'); }

    pageLabel = el('span', {}, '');
    zoomLabel = el('span', { class: 'zoom-pct' }, '100%');
    const stage = el('div', { class: 'viewer-stage' });
    pageNavEl = el('div', { class: 'page-nav', style: 'display:none' }, [
      el('button', { class: 'btn btn-sm btn-icon', onclick: () => { state.page--; loadImage(); } }, '‹'),
      pageLabel,
      el('button', { class: 'btn btn-sm btn-icon', onclick: () => { state.page++; loadImage(); } }, '›'),
    ]);
    const viewerToolbar = el('div', { class: 'viewer-toolbar' }, [
      viewToggle,
      pageNavEl,
      el('div', { class: 'zoom-group' }, [
        el('button', { class: 'btn btn-sm btn-icon', onclick: () => imgViewer.zoomOut(), title: 'Zoom out' }, '−'),
        el('button', { class: 'btn btn-sm btn-icon', onclick: () => imgViewer.zoomIn(), title: 'Zoom in' }, '+'),
        zoomLabel,
        el('button', { class: 'btn btn-sm', onclick: () => imgViewer.fitWidth() }, 'Fit Width'),
        el('button', { class: 'btn btn-sm', onclick: () => imgViewer.fitPage() }, 'Fit Page'),
      ]),
    ]);
    leftPanel = el('div', { class: 'detail-left' }, [viewerToolbar, stage]);
    imgViewer = createImageViewer(stage, { onZoomChange: (s) => { zoomLabel.textContent = `${Math.round(s * 100)}%`; } });

    // --- 우측: 탭 + 재구성 ---
    tabButtons.edit = el('button', { class: 'tab-btn active' }, 'Golden Set 편집');
    tabButtons.compare = el('button', { class: 'tab-btn' }, '비교');
    tabButtons.raw = el('button', { class: 'tab-btn' }, 'Raw JSON');
    tabButtons.edit.addEventListener('click', () => setTab('edit'));
    tabButtons.compare.addEventListener('click', () => setTab('compare'));
    tabButtons.raw.addEventListener('click', () => setTab('raw'));
    const tabs = el('div', { class: 'tabs' }, [tabButtons.edit, tabButtons.compare, tabButtons.raw]);

    tabHosts.edit = el('div', { class: 'tab-panel-host' });
    tabHosts.compare = el('div', { class: 'tab-panel-host', style: 'display:none' });
    tabHosts.raw = el('div', { class: 'tab-panel-host', style: 'display:none' });

    editor = createGoldenEditor(tabHosts.edit, {
      bundleId, docId, doc,
      onDirtyChange: (isDirty) => { setSaveState(isDirty ? 'dirty' : 'saved', isDirty ? 'Unsaved changes' : 'Saved'); if (state.reconSource === 'golden') drawRecon(); },
      onSaveStart: () => setSaveState('saving', 'Saving…'),
      onSaveOk: (updated) => { setSaveState('saved', 'Saved'); refreshAfterDocUpdate(updated); toast('저장했습니다.'); },
      onSaveErr: () => setSaveState('dirty', 'Unsaved changes'),
      onGoldenCreated: (updated) => { refreshAfterDocUpdate(updated); },
      onHoverBbox,
    });

    compareApi = renderCompare(tabHosts.compare, doc, {
      onAdopt: (entry, value) => editor.adoptValue(entry, value),
      onHoverBbox,
    });

    buildRawTab();

    const vsplit = el('div', { class: 'vsplit-handle' });
    reconBody = el('div', { class: 'recon-body' });
    reconSourceButtons.golden = el('button', { class: 'active', onclick: () => setReconSource('golden') }, 'Golden');
    reconSourceButtons.ao = el('button', { onclick: () => setReconSource('ao'), disabled: !doc.has.ao_extract }, 'AO');
    reconSourceButtons.harness = el('button', { onclick: () => setReconSource('harness'), disabled: !doc.has.harness }, 'Harness');
    const rendererButtons = {
      html: el('button', { class: 'active', onclick: () => { state.reconRenderer = 'html'; rendererButtons.html.classList.add('active'); rendererButtons.md.classList.remove('active'); drawRecon(); } }, 'HTML'),
      md: el('button', { onclick: () => { state.reconRenderer = 'md'; rendererButtons.md.classList.add('active'); rendererButtons.html.classList.remove('active'); drawRecon(); } }, 'Markdown'),
    };
    const reconPanel = el('div', { class: 'recon-panel', style: 'height:280px' }, [
      el('div', { class: 'recon-toolbar' }, [
        el('span', { class: 'label' }, 'Reconstructed View'),
        el('div', { class: 'toggle-group' }, [reconSourceButtons.golden, reconSourceButtons.ao, reconSourceButtons.harness]),
        el('div', { class: 'toggle-group' }, [rendererButtons.html, rendererButtons.md]),
      ]),
      reconBody,
    ]);

    let dragging = false, startY = 0, startH = 0;
    const onVMove = (e) => { if (!dragging) return; const h = Math.min(Math.max(90, startH - (e.clientY - startY)), rightPanel.clientHeight - 120); reconPanel.style.height = `${h}px`; };
    const onVUp = () => { dragging = false; vsplit.classList.remove('active'); };
    vsplit.addEventListener('mousedown', (e) => { dragging = true; startY = e.clientY; startH = reconPanel.getBoundingClientRect().height; vsplit.classList.add('active'); });
    window.addEventListener('mousemove', onVMove);
    window.addEventListener('mouseup', onVUp);

    rightPanel = el('div', { class: 'detail-right' }, [tabs, tabHosts.edit, tabHosts.compare, tabHosts.raw, vsplit, reconPanel]);

    const resizer = el('div', { class: 'detail-resizer' });
    let rdrag = false, rStartX = 0, rStartW = 0;
    const onRMove = (e) => {
      if (!rdrag) return;
      const total = leftPanel.parentElement.clientWidth;
      const w = Math.min(Math.max(280, rStartW + (e.clientX - rStartX)), total - 320);
      leftPanel.style.width = `${w}px`;
    };
    const onRUp = () => { rdrag = false; resizer.classList.remove('active'); };
    resizer.addEventListener('mousedown', (e) => { rdrag = true; rStartX = e.clientX; rStartW = leftPanel.getBoundingClientRect().width; resizer.classList.add('active'); });
    window.addEventListener('mousemove', onRMove);
    window.addEventListener('mouseup', onRUp);
    dragCleanup = () => {
      window.removeEventListener('mousemove', onVMove); window.removeEventListener('mouseup', onVUp);
      window.removeEventListener('mousemove', onRMove); window.removeEventListener('mouseup', onRUp);
    };

    const body = el('div', { class: 'detail-body' }, [leftPanel, resizer, rightPanel]);
    const railHost = el('aside', { class: 'doc-rail', 'aria-label': '문서 목록' });
    const railResizer = el('div', { class: 'doc-rail-resizer', role: 'separator', 'aria-label': '문서 목록 너비 조절' });
    let railDragging = false;
    const onRailMove = (e) => { if (railDragging) railHost.style.width = `${Math.max(180, Math.min(360, e.clientX - railHost.getBoundingClientRect().left))}px`; };
    const onRailUp = () => { railDragging = false; railResizer.classList.remove('active'); };
    railResizer.addEventListener('mousedown', (e) => { e.preventDefault(); railDragging = true; railResizer.classList.add('active'); });
    window.addEventListener('mousemove', onRailMove);
    window.addEventListener('mouseup', onRailUp);
    const cleanupPanelDrags = dragCleanup;
    dragCleanup = () => { cleanupPanelDrags(); window.removeEventListener('mousemove', onRailMove); window.removeEventListener('mouseup', onRailUp); };
    documentRail = createDocumentRail(railHost, bundle?.docs || [], docId,
      (nextId) => nextId !== docId && navigate(`#/b/${encodeURIComponent(bundleId)}/d/${encodeURIComponent(nextId)}`));
    const workspace = el('div', { class: 'detail-main' }, [railHost, railResizer, body]);

    const screen = el('div', { class: 'detail-screen' }, [
      topbar,
      doc.errors && doc.errors.length ? el('div', { class: 'error-block' }, [
        `이 문서에서 오류가 발견되었습니다:`,
        el('ul', { class: 'error-list' }, doc.errors.map((msg) => el('li', {}, msg))),
      ]) : null,
      workspace,
    ]);
    mount(root, screen);

    loadImage();
    drawRecon();
    updateTabCounts();
  }

  function buildRawTab() {
    const viewerHost = el('div', { class: 'json-viewer' });
    const jsonViewer = createJsonViewer(viewerHost);
    const sel = { golden: el('button', { class: 'active' }, 'Golden'), ao: el('button', {}, 'AO Extract'), harness: el('button', {}, 'Harness') };
    let current = 'golden';
    function load(kind) {
      current = kind;
      for (const k in sel) sel[k].classList.toggle('active', k === kind);
      if (!doc.has[RAW_KIND[kind]]) { jsonViewer.show(JSON.stringify('(파일 없음)')); return; }
      jsonViewer.show(JSON.stringify('불러오는 중…'));
      api.getRaw(bundleId, docId, RAW_KIND[kind]).then((text) => {
        if (kind !== current) return;
        try { jsonViewer.show(JSON.stringify(JSON.parse(text), null, 2)); } catch (e) { jsonViewer.show(text); }
      }).catch(() => { if (kind === current) jsonViewer.show(JSON.stringify('(파일 없음)')); });
    }
    sel.golden.addEventListener('click', () => load('golden'));
    sel.ao.addEventListener('click', () => load('ao'));
    sel.harness.addEventListener('click', () => load('harness'));
    const copyBtn = el('button', { class: 'btn btn-sm', onclick: () => {
      navigator.clipboard && navigator.clipboard.writeText(jsonViewer.getText()).then(() => toast('복사했습니다.')).catch(() => toast('복사 실패', 'error'));
    } }, '복사');
    mount(tabHosts.raw, el('div', { class: 'raw-json-panel' }, [
      el('div', { class: 'raw-json-toolbar' }, [el('div', { class: 'toggle-group' }, [sel.golden, sel.ao, sel.harness]), el('div', { class: 'grow' }), copyBtn]),
      viewerHost,
    ]));
    load('golden');
  }

  return () => {
    destroyed = true;
    document.removeEventListener('keydown', onKeydown);
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
