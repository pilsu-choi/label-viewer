import asyncio
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import threading

from playwright.async_api import async_playwright


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


async def main():
    repo_root = Path(__file__).resolve().parents[1]
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(repo_root)))
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    browsers = Path.home().joinpath(".cache/ms-playwright").glob("chromium-*/chrome-linux64/chrome")
    executable = max(browsers, key=lambda p: int(re.search(r"chromium-(\d+)", str(p)).group(1)))
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, executable_path=str(executable))
            page = await browser.new_page()
            await page.goto(f"http://127.0.0.1:{server.server_port}/frontend/index.html")
            result = await page.evaluate("""async () => {
          const { api } = await import('/frontend/js/api.js');
          const { startExport } = await import('/frontend/js/exportTask.js');
          const wait = async (predicate, message, timeout = 4000) => {
            const end = Date.now() + timeout;
            while (Date.now() < end) {
              if (predicate()) return;
              await new Promise(r => setTimeout(r, 20));
            }
            throw new Error(message);
          };
          const panel = () => document.querySelector('.export-task');
          const statusText = () => panel()?.querySelector('[role="status"]')?.textContent || '';
          const clickText = (selector, text) => {
            const node = Array.from(document.querySelectorAll(selector)).find(x => x.textContent.includes(text));
            if (!node) throw new Error(`missing clickable ${text}`);
            node.click();
            return node;
          };
          const originalAnchorClick = HTMLAnchorElement.prototype.click;
          const downloads = [];
          HTMLAnchorElement.prototype.click = function() {
            if (this.download) { downloads.push({href:this.href, filename:this.download}); return; }
            return originalAnchorClick.call(this);
          };
          const closeTask = () => { if (panel()) clickText('.export-task button', '닫기'); };

          // Starting request remains active; duplicate start is ignored. Poll queued/running to ready and auto-download once.
          let startCalls = 0, resolveStart;
          api.startExport = () => { startCalls++; return new Promise(resolve => { resolveStart = resolve; }); };
          const progression = [
            {id:'task-ready', state:'running', completed:0, total:2, phase:'writing', message:'문서를 내보내고 있습니다.'},
            {id:'task-ready', state:'running', completed:2, total:2, phase:'finalizing', message:'파일을 마무리하고 있습니다.'},
            {id:'task-ready', state:'ready', completed:2, total:2, phase:'ready', filename:'sample.zip'},
          ];
          api.getExport = async () => progression.shift() || {id:'task-ready', state:'ready', completed:2, total:2, filename:'sample.zip'};
          api.exportDownloadUrl = (_b, id) => `/mock-download/${id}`;
          startExport('b', {format:'zip'}, '테스트 내보내기');
          startExport('b', {format:'xlsx'}, '중복 요청');
          if (startCalls !== 1) throw new Error('duplicate start was not ignored');
          if (!statusText().includes('요청 중')) throw new Error('pending task state was not rendered');
          resolveStart({id:'task-ready', state:'queued', completed:0, total:2, filename:'sample.zip'});
          await wait(() => statusText().includes('파일 준비 완료'), 'ready state was not rendered');
          if (downloads.length !== 1 || downloads[0].filename !== 'sample.zip') throw new Error('ready job did not auto-download exactly once');
          if (!panel().textContent.includes('다시 다운로드')) throw new Error('ready job has no manual download retry');
          closeTask();

          // Cancel pressed before POST resolves is sent once the job id arrives.
          let resolveBeforeCancel, cancelCalls = 0;
          api.startExport = () => new Promise(resolve => { resolveBeforeCancel = resolve; });
          api.cancelExport = async (_b, id) => { cancelCalls++; return {id, state:'cancelled', completed:0, total:1}; };
          startExport('b', {format:'xlsx'}, '취소 전 요청');
          clickText('.export-task button', '내보내기 취소');
          if (!panel().textContent.includes('취소를 요청하는 중')) throw new Error('pre-start cancel was not shown');
          resolveBeforeCancel({id:'task-pre-cancel', state:'running', completed:0, total:1});
          await wait(() => statusText().includes('취소했습니다'), 'pre-start cancellation did not settle');
          if (cancelCalls !== 1 || downloads.length !== 1) throw new Error('pre-start cancel downloaded or missed the server cancel');
          closeTask();

          // Running cancellation blocks the scheduled poll from completing a download.
          let runningCancelCalls = 0;
          api.startExport = async () => ({id:'task-running-cancel', state:'queued', completed:0, total:1});
          api.getExport = async () => ({id:'task-running-cancel', state:'running', completed:0, total:1, phase:'writing'});
          api.cancelExport = async (_b, id) => { runningCancelCalls++; return {id, state:'cancelled', completed:0, total:1}; };
          startExport('b', {format:'zip'}, '실행 중 취소');
          await wait(() => statusText().includes('파일을 준비하는 중'), 'running state was not rendered');
          clickText('.export-task button', '내보내기 취소');
          await wait(() => statusText().includes('취소했습니다'), 'running cancellation did not settle');
          if (runningCancelCalls !== 1 || downloads.length !== 1) throw new Error('running cancel allowed auto-download');
          closeTask();

          // A failed start can be retried and a failed status connection can be resumed without another start.
          let failedStarts = 0;
          api.startExport = async () => {
            failedStarts++;
            if (failedStarts === 1) throw new Error('temporary start failure');
            return {id:'task-retry', state:'queued', completed:0, total:1};
          };
          api.getExport = async () => ({id:'task-retry', state:'ready', completed:1, total:1, filename:'retry.xlsx'});
          startExport('b', {format:'xlsx'}, '재시도');
          await wait(() => panel()?.textContent.includes('다시 시도'), 'failed job did not offer retry');
          clickText('.export-task button', '다시 시도');
          await wait(() => statusText().includes('파일 준비 완료'), 'retry did not complete');
          if (failedStarts !== 2 || downloads.at(-1)?.filename !== 'retry.xlsx') throw new Error('retry did not start a new job');
          closeTask();

          let reconnectStarts = 0, reads = 0;
          api.startExport = async () => { reconnectStarts++; return {id:'task-reconnect', state:'queued', completed:0, total:1}; };
          api.getExport = async () => {
            reads++;
            if (reads === 1) throw new Error('connection interrupted');
            return {id:'task-reconnect', state:'ready', completed:1, total:1, filename:'reconnected.zip'};
          };
          startExport('b', {format:'zip'}, '연결 복구');
          await wait(() => panel()?.textContent.includes('상태 다시 확인'), 'disconnected state did not offer status retry');
          clickText('.export-task button', '상태 다시 확인');
          await wait(() => statusText().includes('파일 준비 완료'), 'status recheck did not recover the job');
          if (reconnectStarts !== 1 || downloads.at(-1)?.filename !== 'reconnected.zip') throw new Error('status recheck created a new job');
          closeTask();

          // An old ready response must not overwrite a completed cancellation.
          let lateReady, oldReads = 0;
          const beforeLate = downloads.length;
          api.startExport = async () => ({id:'late-ready', state:'queued', completed:0, total:1});
          api.getExport = () => { oldReads++; return new Promise(resolve => { lateReady = resolve; }); };
          api.cancelExport = async () => ({id:'late-ready', state:'cancelled', completed:0, total:1});
          startExport('b', {format:'zip'}, '늦은 응답 취소');
          await wait(() => lateReady, 'late status request did not start');
          clickText('.export-task button', '내보내기 취소');
          await wait(() => statusText().includes('취소했습니다'), 'cancel response did not settle');
          lateReady({id:'late-ready',state:'ready',completed:1,total:1,filename:'late.zip'});
          await new Promise(resolve => setTimeout(resolve, 80));
          if (!statusText().includes('취소했습니다') || downloads.length !== beforeLate) throw new Error('late ready response undid cancellation');
          closeTask();

          // Repeated reconnect clicks must share one pending status request/download.
          let retryReads = 0, retryReady;
          const beforeReconnect = downloads.length;
          api.startExport = async () => ({id:'double-reconnect',state:'queued',completed:0,total:1});
          api.getExport = async () => {
            retryReads++;
            if (retryReads === 1) throw new Error('disconnect');
            return new Promise(resolve => { retryReady = resolve; });
          };
          startExport('b', {format:'zip'}, '중복 상태 확인');
          await wait(() => panel()?.textContent.includes('상태 다시 확인'), 'no reconnect button');
          const retryButton = clickText('.export-task button', '상태 다시 확인');
          retryButton.click();
          if (retryReads !== 2) throw new Error('reconnect launched concurrent status requests');
          retryReady({id:'double-reconnect',state:'ready',completed:1,total:1,filename:'once.zip'});
          await wait(() => statusText().includes('파일 준비 완료'), 'reconnect did not finish');
          if (downloads.length !== beforeReconnect + 1) throw new Error('reconnect downloaded twice');
          closeTask();

          // Reconnecting after a failed cancel must survive a still-pending old poll.
          let pendingOldPoll, cancelRetryReads = 0;
          api.startExport = async () => ({id:'cancel-reconnect',state:'running',completed:0,total:1});
          api.getExport = async () => {
            cancelRetryReads++;
            if (cancelRetryReads === 1) return new Promise(resolve => { pendingOldPoll = resolve; });
            return {id:'cancel-reconnect',state:'ready',completed:1,total:1,filename:'cancel-reconnect.zip'};
          };
          api.cancelExport = async () => { throw new Error('cancel disconnected'); };
          startExport('b', {format:'zip'}, '취소 연결 복구');
          await wait(() => pendingOldPoll, 'old status poll did not start');
          clickText('.export-task button', '내보내기 취소');
          await wait(() => panel()?.textContent.includes('상태 다시 확인'), 'failed cancel missing reconnect');
          clickText('.export-task button', '상태 다시 확인');
          pendingOldPoll({id:'cancel-reconnect',state:'running',completed:0,total:1});
          await wait(() => statusText().includes('파일 준비 완료'), 'reconnect was lost behind stale poll');
          if (cancelRetryReads !== 2) throw new Error('failed cancel reconnect did not resume one poll');
          closeTask();

          // Select across the first and second page, then export exactly those IDs.
          const { renderList } = await import('/frontend/js/list.js');
          localStorage.setItem('lv.pageSize', '50');
          const docs = Array.from({length:51}, (_, i) => {
            const id = `D${String(i + 1).padStart(3, '0')}`;
            return {id, doc_type:'', has:{original:false,preprocessed:false,ao_extract:true,harness:true,golden:false}, errors:[], review:'', enabled:true,
              score:{ao:null,harness:null}, classification:{ao:null,harness:null}};
          });
          const summary = {docs:docs.length, golden:0, reviewed:0, pending:docs.length, missing:0, error:0,
            score:{ao:null,harness:null}, classification:{ao:null,harness:null}};
          api.getBundle = async () => ({id:'bundle-selection', name:'Selection fixture', docs, summary,
            summary_by_scope:{enabled:summary,disabled:{...summary,docs:0,pending:0},all:summary}});
          let selectionRequest;
          api.startExport = async (_bundle, options) => {
            selectionRequest = options;
            return {id:'selection-job', state:'cancelled', completed:0, total:2};
          };
          api.getExport = async () => ({id:'selection-job', state:'cancelled', completed:0, total:2});
          const host = document.createElement('div'); document.body.appendChild(host);
          const cleanup = renderList(host, 'bundle-selection');
          await wait(() => host.querySelector('input[aria-label="D001 선택"]'), 'bundle document list did not load');
          host.querySelector('input[aria-label="D001 선택"]').click();
          const pageNav = host.querySelector('nav[aria-label="페이지"]');
          const pageTwo = Array.from(pageNav.querySelectorAll('button')).find(button => button.textContent.trim() === '2');
          if (!pageTwo) throw new Error('second document page was not rendered');
          pageTwo.click();
          await wait(() => host.querySelector('input[aria-label="D051 선택"]'), 'second page did not load');
          host.querySelector('input[aria-label="D051 선택"]').click();
          host.querySelector('[aria-label="내보내기"]').click();
          clickText('.export-pop button', '선택 문서 ZIP');
          await wait(() => selectionRequest, 'selection export was not requested');
          await wait(() => statusText().includes('취소했습니다'), 'selection mock export did not settle');
          if (JSON.stringify(selectionRequest) !== JSON.stringify({format:'zip', ids:['D001','D051']})) {
            throw new Error(`wrong selected document IDs: ${JSON.stringify(selectionRequest)}`);
          }
          cleanup(); host.remove(); closeTask();
          HTMLAnchorElement.prototype.click = originalAnchorClick;
          return {ok:true, downloads, duplicateStartCalls:startCalls, cancelCalls, runningCancelCalls, failedStarts,
            reconnectStarts, selectionRequest};
            }""")
            print(result)
            await browser.close()
    finally:
        server.shutdown()
        server_thread.join()


asyncio.run(main())
