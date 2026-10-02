import { el, mount, downloadUrl } from './util.js';
import { api } from './api.js';

let current = null;
const active = (task) => task && !['ready', 'cancelled', 'failed'].includes(task.job?.state);

// 작업 패널은 화면을 이동해도 유지된다. 파일은 브라우저 다운로드로 받아 메모리에 쌓지 않는다.
export function startExport(bundleId, options, label = '내보내기') {
  if (active(current)) {
    current.panel.focus();
    return;
  }
  current?.panel.remove();
  const task = { bundleId, options, label, job: null, cancelling: false, started: Date.now(), timer: null };
  task.panel = el('section', { class: 'export-task', role: 'region', 'aria-label': '내보내기 진행 상태', tabindex: '-1' });
  current = task;
  document.body.appendChild(task.panel);
  draw(task);
  task.timer = setInterval(() => { if (current === task) draw(task); }, 1000);
  api.startExport(bundleId, options).then(async (job) => {
    task.job = job;
    if (task.cancelling) await cancel(task);
    else poll(task);
  }).catch((error) => fail(task, error));
}

function fail(task, error) {
  task.job = { ...task.job, state: 'failed', message: error.message };
  clearInterval(task.timer);
  draw(task);
}

async function poll(task) {
  if (current !== task || task.cancelling) return;
  try {
    task.connectionError = null;
    task.job = await api.getExport(task.bundleId, task.job.id);
    if (task.cancelling) return;
    draw(task);
    if (task.job.state === 'ready') {
      clearInterval(task.timer);
      downloadUrl(api.exportDownloadUrl(task.bundleId, task.job.id), task.job.filename);
    } else if (['failed', 'cancelled'].includes(task.job.state)) {
      clearInterval(task.timer);
    } else {
      setTimeout(() => poll(task), 500);
    }
  } catch (error) {
    if ([404, 410].includes(error.status)) { fail(task, error); return; }
    task.connectionError = error.message;
    clearInterval(task.timer);
    draw(task);
  }
}

async function cancel(task) {
  task.cancelling = true;
  draw(task);
  if (!task.job?.id) return;
  try {
    task.job = await api.cancelExport(task.bundleId, task.job.id);
    task.connectionError = null;
    task.cancelling = false;
    // 실행 중 작업은 취소 확인까지 상태를 계속 받는다.
    if (!['ready', 'failed', 'cancelled'].includes(task.job.state)) poll(task);
    else { clearInterval(task.timer); draw(task); }
  } catch (error) { task.cancelling = false; task.connectionError = error.message; draw(task); }
}

function draw(task) {
  if (current !== task) return;
  const job = task.job;
  const state = task.connectionError ? 'disconnected' : job?.state || 'starting';
  const busy = active(task);
  const completed = job?.completed || 0;
  const total = job?.total || 0;
  const titles = { disconnected: '작업 상태를 확인하지 못했습니다', starting: '내보내기 요청 중…', queued: '순서를 기다리는 중…', running: '파일을 준비하는 중…', ready: '파일 준비 완료 · 다운로드 시작', cancelled: '내보내기를 취소했습니다', failed: '내보내기에 실패했습니다' };
  const percent = total ? Math.min(100, Math.round(completed / total * 100)) : 0;
  const progress = el('progress', { max: 100, 'aria-label': '내보내기 문서 처리 진행률', ...(total ? { value: percent } : {}) });
  const close = () => { clearInterval(task.timer); task.panel.remove(); if (current === task) current = null; };
  const focused = task.panel.contains(document.activeElement) ? document.activeElement.textContent : null;
  mount(task.panel, [
    el('div', { class: 'export-task-title' }, [el('b', {}, task.label), !busy && el('button', { class: 'btn ghost sm', onclick: close, 'aria-label': '내보내기 상태 닫기' }, '닫기')]),
    el('div', { role: 'status', 'aria-live': 'polite' }, task.cancelling ? '취소를 요청하는 중…' : titles[state] || state),
    busy && progress,
    busy && el('div', { class: 'hint' }, `${completed} / ${total || '…'} 문서 · ${Math.floor((Date.now() - task.started) / 1000)}초${job?.phase === 'finalizing' ? ' · 파일 마무리 중' : ''}`),
    task.connectionError && el('div', { class: 'error-block' }, task.connectionError),
    job?.message && el('div', { class: state === 'failed' ? 'error-block' : 'hint' }, job.message),
    el('div', { class: 'export-task-actions' }, [
      task.connectionError && el('button', { class: 'btn sm', onclick: () => { task.connectionError = null; task.timer = setInterval(() => draw(task), 1000); poll(task); } }, '상태 다시 확인'),
      busy && el('button', { class: 'btn sm', disabled: task.cancelling, onclick: () => cancel(task) }, '내보내기 취소'),
      state === 'ready' && el('a', { class: 'btn primary sm', href: api.exportDownloadUrl(task.bundleId, job.id), download: job.filename }, '다시 다운로드'),
      state === 'failed' && el('button', { class: 'btn sm', onclick: () => startExport(task.bundleId, task.options, task.label) }, '다시 시도'),
    ]),
  ]);
  if (focused) [...task.panel.querySelectorAll("button, a")].find((node) => node.textContent === focused)?.focus({ preventScroll: true });
}
