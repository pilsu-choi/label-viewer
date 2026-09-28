import { el, mount, clear, toast } from './util.js';
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

export function renderUpload(root) {
  const state = { uploading: false, progress: 0, error: '', bundles: [] };

  const screen = el('div', { class: 'upload-screen' });
  mount(root, screen);

  function startUpload(fileList) {
    if (!fileList.length) { state.error = '업로드할 파일이 없습니다.'; draw(); return; }
    state.uploading = true; state.progress = 0; state.error = '';
    draw();
    const name = fileList.length === 1 && /\.zip$/i.test(fileList[0].relPath)
      ? fileList[0].relPath.replace(/\.zip$/i, '') : null;
    api.uploadBundle(fileList, name, (p) => { state.progress = p; drawProgressOnly(); })
      .then((bundle) => { navigate(`#/b/${encodeURIComponent(bundle.id)}`); })
      .catch((err) => { state.uploading = false; state.error = err.message || '업로드 실패'; draw(); });
  }

  function drawProgressOnly() {
    const bar = screen.querySelector('.dz-progress > span');
    if (bar) bar.style.width = `${Math.round(state.progress * 100)}%`;
  }

  function loadBundles() {
    api.listBundles().then((list) => { state.bundles = list; drawRecent(); }).catch(() => {});
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
      recentHost.appendChild(el('div', { class: 'recent-empty' }, '아직 업로드한 번들이 없습니다.'));
      return;
    }
    const list = el('div', { class: 'recent-list' });
    for (const b of state.bundles) {
      const c = b.counts || {};
      const meta = `문서 ${c.docs || 0} · Golden ${c.golden || 0} · 검수 ${c.reviewed || 0}${c.error ? ` · 오류 ${c.error}` : ''}`;
      list.appendChild(el('div', { class: 'recent-item' }, [
        el('span', { class: 'name', onclick: () => navigate(`#/b/${encodeURIComponent(b.id)}`) }, b.name || b.id),
        el('span', { class: 'meta' }, meta),
        el('button', { class: 'btn btn-ghost btn-sm', onclick: (e) => deleteBundle(b.id, e) }, '삭제'),
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
      el('div', { class: 'dz-corner-bl' }), el('div', { class: 'dz-corner-br' }),
      state.uploading
        ? el('div', { class: 'dz-title' }, `업로드 중… ${Math.round(state.progress * 100)}%`)
        : el('div', { class: 'dz-title' }, 'Drop Bundle Here'),
      !state.uploading && el('div', { class: 'dz-sub' }, 'Folder / ZIP supported'),
      state.uploading && el('div', { class: 'dz-progress' }, el('span', { style: `width:${Math.round(state.progress * 100)}%` })),
      !state.uploading && el('div', { class: 'dz-actions' }, [
        el('button', { class: 'btn btn-primary', onclick: () => folderInput.click() }, '폴더 선택'),
        el('button', { class: 'btn', onclick: () => zipInput.click() }, 'ZIP 선택'),
      ]),
      state.error && el('div', { class: 'dz-error' }, state.error),
    ]);

    const folderInput = el('input', { type: 'file', webkitdirectory: true, directory: true, multiple: true, style: 'display:none',
      onchange: (e) => startUpload(filesFromInput(e.target)) });
    const zipInput = el('input', { type: 'file', accept: '.zip', style: 'display:none',
      onchange: (e) => startUpload(filesFromInput(e.target)) });

    recentHost = el('div', { class: 'recent-list' });
    const recentPanel = el('div', { class: 'recent-panel' }, [
      el('h2', {}, '최근 번들'),
      recentHost,
    ]);

    mount(screen, [
      el('div', { class: 'upload-brand' }, [
        el('h1', {}, 'Label Viewer'),
        el('p', {}, 'Golden Set Validation Workspace'),
      ]),
      dz, folderInput, zipInput,
      recentPanel,
    ]);
    drawRecent();
  }

  draw();
  loadBundles();
}
