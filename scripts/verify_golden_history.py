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
              const { createGoldenEditor } = await import('/frontend/js/goldenEditor.js');
              const golden = (value) => ({documents:[{doc_type:'',extracted_fields:[{key:'f',value,dtype:'string'}],extracted_groups:[],extracted_tables:[]}]});
              const detail = (value, revision) => ({doc_types:[],has:{},compare:[],golden_revision:revision,golden:golden(value)});
              const host = document.createElement('div'); document.body.appendChild(host);
              const editor = createGoldenEditor(host, {bundleId:'b',docId:'d',doc:detail('initial','rev-1')});
              window.confirm = () => true;

              let conflictAttempts = 0;
              api.putGolden = async () => { conflictAttempts += 1; const error = new Error('revision conflict'); error.status = 409; throw error; };
              api.getDoc = async () => detail('server latest','rev-2');
              editor.adoptValue({doc:0,area:'field',key:'f'}, 'local edit');
              const saveResult = await editor.save();
              if (!saveResult.conflict || !editor.isDirty() || !editor.hasConflict()) throw new Error('409 did not preserve local edits and conflict state');
              if (!host.ownerDocument.querySelector('.golden-conflict-dialog')) throw new Error('conflict dialog did not open');
              if (!Array.from(document.querySelectorAll('.golden-conflict-dialog button')).some(button => button.textContent.includes('내 변경 JSON 다운로드'))) throw new Error('conflict dialog omitted local JSON backup action');
              await new Promise(r => setTimeout(r, 1600));
              if (conflictAttempts !== 1) throw new Error('autosave retried while conflict was unresolved');
              const reload = Array.from(document.querySelectorAll('.golden-conflict-dialog button')).find(button => button.textContent.includes('최신 내용 불러오기'));
              reload.click();
              await new Promise(r => setTimeout(r, 0));
              if (editor.isDirty() || editor.hasConflict() || editor.getGoldenObject().documents[0].extracted_fields[0].value !== 'server latest') throw new Error('conflict reload did not replace editor with latest server state');
              if (document.querySelector('.golden-conflict-dialog')) throw new Error('conflict dialog remained after reload');

              const calls = [];
              api.getGoldenHistory = async (_b, _d, options={}) => {
                calls.push(options);
                return options.before ? {items:[{id:'v0',created_at:'2026-01-01T00:00:00Z',action:'baseline',revision:'rev-v0'}],next_cursor:null}
                  : {items:[{id:'v1',created_at:'2026-01-02T00:00:00Z',action:'save',revision:'rev-v1'}],next_cursor:'v1'};
              };
              api.getGoldenHistoryVersion = async (_b,_d,id) => ({id,action:'save',golden:golden('version '+id)});
              let restoreArgs;
              api.restoreGolden = async (_b,_d,id,revision) => { restoreArgs={id,revision}; return detail('restored '+id,'rev-restored'); };
              editor.adoptValue({doc:0,area:'field',key:'f'}, 'unsaved local');
              Array.from(host.querySelectorAll('button')).find(button => button.textContent.includes('버전 기록')).click();
              const history = document.querySelector('.golden-history-modal');
              if (!history) throw new Error('history modal did not open');
              await new Promise(r => setTimeout(r, 0));
              if (!history.querySelector('.golden-history-preview').textContent.includes('version v1')) throw new Error('history version preview was not loaded');
              history.querySelector('.golden-history-list button').click();
              await new Promise(r => setTimeout(r, 0));
              Array.from(history.querySelectorAll('.golden-history-list button')).find(button => button.textContent.includes('이전 기록 더 보기')).click();
              await new Promise(r => setTimeout(r, 0));
              if (!calls.some(options => options.before === 'v1')) throw new Error('older history page was not fetched with cursor');
              const restore = Array.from(history.querySelectorAll('button')).find(button => button.textContent === '이 버전 복원');
              restore.click();
              await new Promise(r => setTimeout(r, 0));
              const discard = Array.from(history.querySelectorAll('button')).find(button => button.textContent === '변경 버리고 복원');
              if (!discard) throw new Error('dirty restore did not offer save/discard choices');
              discard.click();
              await new Promise(r => setTimeout(r, 0));
              if (restoreArgs?.id !== 'v1' || restoreArgs.revision !== 'rev-2') throw new Error('restore did not use selected ID and latest revision');
              if (editor.isDirty() || editor.getGoldenObject().documents[0].extracted_fields[0].value !== 'restored v1') throw new Error('restored version did not replace local state');
              if (document.querySelector('.golden-history-modal')) throw new Error('history modal remained open after restore');

              let deleteRevision;
              api.deleteGolden = async (_b,_d,revision) => { deleteRevision=revision; };
              Array.from(host.querySelectorAll('button')).find(button => button.textContent.includes('Golden 삭제')).click();
              await new Promise(r => setTimeout(r, 0));
              if (deleteRevision !== 'rev-restored' || editor.hasGolden()) throw new Error('delete did not use the current revision or clear Golden');
              api.getGoldenHistory = async () => ({items:[
                {id:'v2',created_at:'2026-01-03T00:00:00Z',action:'delete',revision:'missing',has_golden:false},
                {id:'v1',created_at:'2026-01-02T00:00:00Z',action:'save',revision:'rev-v1',has_golden:true},
              ],next_cursor:null});
              api.getGoldenHistoryVersion = async (_b,_d,id) => ({id,action:id === 'v2' ? 'delete' : 'save',golden:id === 'v2' ? null : golden('old saved content')});
              Array.from(host.querySelectorAll('button')).find(button => button.textContent.includes('버전 기록')).click();
              const afterDeleteHistory = document.querySelector('.golden-history-modal');
              await new Promise(r => setTimeout(r, 0));
              const earlier = afterDeleteHistory.querySelectorAll('.golden-history-item')[1];
              earlier.click(); await new Promise(r => setTimeout(r, 0));
              Array.from(afterDeleteHistory.querySelectorAll('button')).find(button => button.textContent === '이 버전 복원').click();
              await new Promise(r => setTimeout(r, 0));
              if (restoreArgs?.id !== 'v1' || restoreArgs.revision !== 'missing') throw new Error('history from the deleted-Golden screen did not restore against missing revision');
              if (!editor.hasGolden() || editor.getGoldenObject().documents[0].extracted_fields[0].value !== 'restored v1') throw new Error('history did not restore Golden after deletion');
              editor.destroy(); host.remove();
              return {ok:true, conflict:'reload latest', historyPages:calls.length, restored:restoreArgs.id, deleteRevision};
            }""")
            print(result)
            await browser.close()
    finally:
        server.shutdown()
        server_thread.join()


asyncio.run(main())
