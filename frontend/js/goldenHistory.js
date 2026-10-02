import { el, clear, toast } from './util.js';
import { api } from './api.js';

function dialogShell(className, title, onClose) {
  const previousFocus = document.activeElement;
  const overlay = el('div', { class: `golden-history-overlay ${className}-overlay`, role: 'presentation', onclick: (e) => { if (e.target === overlay) onClose(); } });
  const card = el('section', { class: `golden-history-dialog ${className}`, role: 'dialog', 'aria-modal': 'true', 'aria-label': title });
  overlay.appendChild(card);
  document.body.appendChild(overlay);
  const onKeydown = (e) => {
    if (e.key === 'Escape' && document.body.lastElementChild === overlay) { e.preventDefault(); e.stopImmediatePropagation(); onClose(); }
    if (e.key === 'Tab' && document.body.lastElementChild === overlay) {
      const controls = [...card.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled)')];
      if (!controls.length) { e.preventDefault(); card.focus(); return; }
      const first = controls[0], last = controls[controls.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  };
  document.addEventListener('keydown', onKeydown);
  requestAnimationFrame(() => card.querySelector('button')?.focus());
  return { overlay, card, restoreFocus: () => { document.removeEventListener('keydown', onKeydown); if (previousFocus?.isConnected) previousFocus.focus(); } };
}

export function showGoldenConflictDialog({ onDownload, onReload, onClose = () => {} }) {
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    shell.overlay.remove();
    shell.restoreFocus();
    onClose();
  };
  const shell = dialogShell('golden-conflict-dialog', 'Golden 변경 충돌', close);
  shell.card.appendChild(el('header', {}, [
    el('h2', {}, '다른 저장 내용이 있습니다'),
    el('p', {}, '최신 버전이 열린 뒤 변경되었습니다. 내 변경 JSON을 보관하거나 서버의 최신 내용을 불러오세요.'),
  ]));
  const message = el('p', { class: 'golden-history-message', role: 'status' }, '최신 내용을 불러오면 현재 편집 내용은 버려집니다.');
  const download = el('button', { class: 'btn', onclick: onDownload }, '내 변경 JSON 다운로드');
  const reload = el('button', { class: 'btn primary', onclick: async () => {
    if (!confirm('서버의 최신 Golden으로 바꾸고 현재 편집 내용을 버릴까요? 필요하면 먼저 내 변경 JSON을 다운로드하세요.')) return;
    reload.disabled = true; message.textContent = '최신 내용을 불러오는 중…';
    try { await onReload(); close(); }
    catch (e) { message.textContent = `불러오지 못했습니다: ${e.message}`; reload.disabled = false; }
  } }, '최신 내용 불러오기');
  shell.card.appendChild(el('div', { class: 'golden-history-actions' }, [message, download, reload]));
  shell.card.appendChild(el('button', { class: 'btn ghost', onclick: close }, '닫기'));
  return close;
}

export function openGoldenHistory({ bundleId, docId, isDirty, onRestore }) {
  let items = [], selectedId = null, selectedVersion = null, nextCursor = null, loading = false;
  let closed = false;
  const close = () => { if (closed) return; closed = true; shell.overlay.remove(); shell.restoreFocus(); };
  const shell = dialogShell('golden-history-modal', 'Golden 기록', close);
  const list = el('div', { class: 'golden-history-list', role: 'list', 'aria-label': 'Golden 버전 기록' });
  const preview = el('pre', { class: 'golden-history-preview' }, '기록을 불러오는 중…');
  const message = el('div', { class: 'golden-history-message', role: 'status' });
  const actions = el('div', { class: 'golden-history-actions' });
  const body = el('div', { class: 'golden-history-content' }, [list, preview]);
  const header = el('header', { class: 'golden-history-header' }, [
    el('div', {}, [el('h2', {}, 'Golden 변경 기록'), el('p', {}, '선택한 저장 버전을 미리 보고 복원할 수 있습니다.')]),
    el('button', { class: 'btn ghost', 'aria-label': '닫기', onclick: close }, '닫기'),
  ]);
  const footer = el('footer', {}, [message, actions]);
  shell.card.appendChild(header); shell.card.appendChild(body); shell.card.appendChild(footer);

  function formatItem(item) {
    const time = item.created_at ? new Date(item.created_at).toLocaleString() : '시간 미상';
    const action = ({ baseline: '기존 내용', create: '생성', save: '저장', delete: '삭제', restore: '복원' })[item.action] || '변경';
    const revision = item.revision && item.revision !== 'missing' ? `${item.revision.slice(0, 10)}…` : item.revision || '';
    return `${time} · ${action} · ${revision}`;
  }

  function drawList() {
    clear(list);
    if (!items.length) list.appendChild(el('div', { class: 'golden-history-message' }, '저장 기록이 없습니다.'));
    for (const item of items) {
      list.appendChild(el('button', {
        class: `golden-history-item ${item.id === selectedId ? 'active' : ''}`,
        role: 'listitem', 'aria-current': item.id === selectedId ? 'true' : null,
        onclick: () => loadVersion(item.id),
      }, formatItem(item)));
    }
    if (nextCursor) list.appendChild(el('button', { class: 'btn sm', disabled: loading, onclick: loadMore }, '이전 기록 더 보기'));
  }

  function drawActions() {
    clear(actions);
    if (!selectedVersion || loading) return;
    actions.appendChild(el('button', { class: 'btn primary', onclick: restoreSelected }, '이 버전 복원'));
  }

  async function loadVersion(id) {
    if (loading) return;
    loading = true; selectedId = id; selectedVersion = null;
    preview.textContent = '버전을 불러오는 중…'; message.textContent = ''; drawList(); drawActions();
    try {
      selectedVersion = await api.getGoldenHistoryVersion(bundleId, docId, id);
      preview.textContent = JSON.stringify(selectedVersion.golden, null, 2);
    } catch (e) {
      preview.textContent = `버전을 불러오지 못했습니다: ${e.message}`;
    } finally { loading = false; drawList(); drawActions(); }
  }

  async function loadMore() {
    if (!nextCursor || loading) return;
    loading = true; message.textContent = '이전 기록을 불러오는 중…'; drawList();
    try {
      const result = await api.getGoldenHistory(bundleId, docId, { limit: 100, before: nextCursor });
      items.push(...(result.items || [])); nextCursor = result.next_cursor || null;
      message.textContent = ''; drawList();
    } catch (e) { message.textContent = `이전 기록을 불러오지 못했습니다: ${e.message}`; }
    finally { loading = false; drawList(); }
  }

  async function performRestore(id, disposition) {
    if (loading || !selectedVersion) return;
    loading = true; message.textContent = '복원하는 중…'; drawActions();
    try {
      if (await onRestore(id, disposition)) close();
      else { loading = false; message.textContent = ''; drawActions(); }
    } catch (e) { loading = false; message.textContent = `복원하지 못했습니다: ${e.message}`; drawActions(); }
  }

  async function restoreSelected() {
    if (!selectedVersion || loading) return;
    const id = selectedId;
    if (isDirty()) {
      const startRestore = (disposition) => {
        choice.querySelectorAll('button').forEach((button) => { button.disabled = true; });
        performRestore(id, disposition).finally(() => {
          if (choice.isConnected) choice.querySelectorAll('button').forEach((button) => { button.disabled = false; });
        });
      };
      const choice = el('div', { class: 'golden-history-restore-choice' }, [
        el('p', {}, '저장하지 않은 변경사항이 있습니다. 복원 전에 처리하세요.'),
        el('button', { class: 'btn primary', onclick: () => startRestore('save') }, '저장 후 복원'),
        el('button', { class: 'btn danger', onclick: () => {
          if (confirm('저장하지 않은 변경사항을 버리고 선택한 기록을 복원할까요?')) startRestore('discard');
        } }, '변경 버리고 복원'),
        el('button', { class: 'btn ghost', onclick: () => choice.remove() }, '취소'),
      ]);
      clear(message); message.appendChild(choice);
      return;
    }
    if (!confirm('선택한 Golden 버전을 복원할까요?')) return;
    await performRestore(id, 'discard');
  }

  api.getGoldenHistory(bundleId, docId).then((result) => {
    items = result.items || []; nextCursor = result.next_cursor || null;
    drawList();
    if (items.length) loadVersion(items[0].id);
    else preview.textContent = '저장 기록이 없습니다.';
  }).catch((e) => { list.textContent = `기록을 불러오지 못했습니다: ${e.message}`; preview.textContent = ''; });
  return close;
}
