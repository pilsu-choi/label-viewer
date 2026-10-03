import { el, mount, clear, toast, icon } from './util.js';
import { api } from './api.js';
import { navigate } from './router.js';

function readEntry(entry) {
  return new Promise((resolve) => {
    if (entry.isFile) {
      entry.file((file) => resolve([{ file, relPath: entry.fullPath.replace(/^\//, '') }]), () => resolve([]));
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      const all = [];
      const readBatch = () => {
        reader.readEntries(async (entries) => {
          if (!entries.length) { resolve(all); return; }
          for (const e of entries) all.push(...(await readEntry(e)));
          readBatch();
        }, () => resolve(all));
      };
      readBatch();
    } else {
      resolve([]);
    }
  });
}

async function filesFromDataTransfer(dt) {
  const items = Array.from(dt.items || []);
  const out = [];
  const entrySupported = items.length && items[0].webkitGetAsEntry;
  if (entrySupported) {
    for (const it of items) {
      const entry = it.webkitGetAsEntry && it.webkitGetAsEntry();
      if (entry) out.push(...(await readEntry(entry)));
    }
    if (out.length) return out;
  }
  return Array.from(dt.files || []).map((file) => ({ file, relPath: file.name }));
}

function filesFromInput(input) {
  return Array.from(input.files || []).map((file) => ({ file, relPath: file.webkitRelativePath || file.name }));
}

function bundleAnatomy() {
  const cols = ['original', 'preprocessed', 'ao_extract', 'harness', 'golden'];
  const rows = [
    ['doc_001', ['.jpg', '.png', '.json', '.json', '.json']],
    ['doc_002', ['.tif', '.png', '.json', '.json', null]],
    ['doc_003', ['.png', null, '.json', null, null]],
  ];
  return el('details', { class: 'anatomy' }, [
    el('summary', {}, '번들 구조 예시'),
    el('table', {}, [
      el('thead', {}, el('tr', {}, [el('th', {}, ''), ...cols.map((c) => el('th', {}, c))])),
      el('tbody', {}, rows.map(([stem, exts]) => el('tr', {}, [
        el('th', {}, el('span', { class: 'stem' }, stem)),
        ...exts.map((x) => el('td', { class: x ? '' : 'miss' }, x || '없음')),
      ]))),
    ]),
    el('p', { class: 'anatomy-caption' }, '확장자를 뗀 파일명이 같으면 한 문서입니다. 빠진 파일은 그 문서에만 표시되고, 번들 전체는 그대로 열립니다.'),
  ]);
}

export function renderUpload(root) {
  let destroyed = false;
  const state = { uploading: false, progress: 0, error: '', bundles: [] };

  const screen = el('div', { class: 'upload-screen' });
  mount(root, screen);

  function startUpload(fileList) {
    if (state.uploading || destroyed) return;
    if (!fileList.length) { state.error = '업로드할 파일이 없습니다.'; draw(); return; }
    state.uploading = true; state.progress = 0; state.error = '';
    draw();
    const name = fileList.length === 1 && /\.zip$/i.test(fileList[0].relPath)
      ? fileList[0].relPath.replace(/\.zip$/i, '') : null;
    api.uploadBundle(fileList, name, (p) => { state.progress = p; drawProgressOnly(); })
      .then((bundle) => { if (!destroyed) navigate(`#/b/${encodeURIComponent(bundle.id)}`); })
      .catch((err) => { if (destroyed) return; state.uploading = false; state.error = err.message || '업로드 실패'; draw(); });
  }

  function drawProgressOnly() {
    const bar = screen.querySelector('.dz-progress > span');
    if (bar) bar.style.width = `${Math.round(state.progress * 100)}%`;
  }

  function loadBundles() {
    api.listBundles().then((list) => { if (destroyed) return; state.bundles = list; drawRecent(); }).catch(() => {});
  }

  function deleteBundle(id, ev) {
    ev.stopPropagation();
    if (!confirm('이 번들을 삭제할까요? 되돌릴 수 없습니다.')) return;
    api.deleteBundle(id).then(() => { toast('번들을 삭제했습니다.'); loadBundles(); }).catch((e) => toast(e.message, 'error'));
  }

  let recentHost;

  function drawRecent() {
    if (!recentHost) return;
    clear(recentHost);
    if (!state.bundles.length) {
      recentHost.appendChild(el('div', { class: 'empty' }, [
        icon('folder'),
        el('div', { class: 'empty-title' }, '아직 올린 번들이 없습니다'),
        el('div', { class: 'empty-desc' }, '위에서 폴더나 ZIP을 올리면 여기에 쌓입니다.'),
      ]));
      return;
    }
    const list = el('div', { class: 'recent-list' });
    for (const b of state.bundles.slice(0, 5)) {
      const c = b.counts || {};
      const open = () => navigate(`#/b/${encodeURIComponent(b.id)}`);
      list.appendChild(el('div', { class: 'recent-item', tabindex: '0', onclick: open, onkeydown: (e) => { if (e.key === 'Enter') open(); } }, [
        el('span', { class: 'name' }, [el('b', {}, b.name || b.id), el('small', {}, (b.created_at || '').replace('T', ' ').slice(0, 16))]),
        el('span', { class: 'cnt' }, [el('b', {}, String(c.docs || 0)), '문서']),
        el('span', { class: 'cnt' }, [el('b', {}, String(c.golden || 0)), 'Golden']),
        el('span', { class: 'cnt' }, [el('b', {}, String(c.reviewed || 0)), '검수 완료']),
        el('span', { class: `cnt ${c.error ? 'bad' : ''}` }, [el('b', {}, String(c.error || 0)), '오류']),
        el('button', { class: 'btn sm icon danger', title: '번들 삭제', 'aria-label': '번들 삭제', onclick: (e) => deleteBundle(b.id, e) }, icon('trash')),
      ]));
    }
    recentHost.appendChild(list);
  }

  function draw() {
    const dz = el('div', { class: 'dropzone', ondragover: (e) => { e.preventDefault(); dz.classList.add('drag-over'); },
      ondragleave: () => dz.classList.remove('drag-over'),
      ondrop: async (e) => {
        e.preventDefault(); dz.classList.remove('drag-over');
        const files = await filesFromDataTransfer(e.dataTransfer);
        startUpload(files);
      } }, [
      el('div', { class: 'dz-icon' }, icon('upload')),
      state.uploading
        ? el('div', { class: 'dz-title' }, `올리는 중 ${Math.round(state.progress * 100)}%`)
        : el('div', { class: 'dz-title' }, '번들 폴더나 ZIP을 여기에 놓으세요'),
      !state.uploading && el('div', { class: 'dz-sub' }, '같은 파일명끼리 원본·전처리·AO·Harness·Golden을 자동으로 묶습니다.'),
      state.uploading && el('div', { class: 'dz-progress' }, el('span', { style: `width:${Math.round(state.progress * 100)}%` })),
      !state.uploading && el('div', { class: 'dz-actions' }, [
        el('button', { class: 'btn primary', onclick: () => folderInput.click() }, [icon('folder'), '폴더 선택']),
        el('button', { class: 'btn', onclick: () => zipInput.click() }, [icon('file-archive'), 'ZIP 선택']),
      ]),
      state.error && el('div', { class: 'dz-error' }, state.error),
    ]);

    const folderInput = el('input', { type: 'file', webkitdirectory: true, directory: true, multiple: true, style: 'display:none',
      onchange: (e) => startUpload(filesFromInput(e.target)) });
    const zipInput = el('input', { type: 'file', accept: '.zip', style: 'display:none',
      onchange: (e) => startUpload(filesFromInput(e.target)) });

    recentHost = el('div', { class: 'recent-list' });
    const recentPanel = el('div', { class: 'recent-panel' }, [
      el('div', { class: 'recent-head' }, [el('h2', {}, '최근 번들'), el('a', { href: '#/bundles' }, '모든 번들 보기')]),
      recentHost,
    ]);

    mount(screen, [
      el('header', { class: 'upload-head' }, [
        el('a', { class: 'brand', href: '#/' }, 'Label Viewer'),
        el('a', { class: 'btn ghost sm', href: '#/bundles' }, '전체 번들'),
      ]),
      el('div', { class: 'upload-main' }, [
        el('div', { class: 'upload-intro' }, [
          el('h1', {}, '스캔본 옆에서 정답지를 확정하세요'),
          el('p', {}, 'AO와 Harness가 읽은 값을 원본 이미지와 한 화면에 놓고, 칸마다 맞았는지 가립니다. 고친 값은 Golden JSON 파일에 바로 저장됩니다.'),
        ]),
        dz, folderInput, zipInput,
        bundleAnatomy(),
        recentPanel,
      ]),
    ]);
    drawRecent();
  }

  draw();
  loadBundles();
  return () => { destroyed = true; };
}
