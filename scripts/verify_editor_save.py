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
          const pending = [];
          api.putGolden = (_bundleId, _docId, golden) => new Promise((resolve, reject) => pending.push({golden, resolve, reject}));
          const fixture = () => ({
            doc_types: [], has: {}, compare: [], golden: { documents: [{ doc_type: '', extracted_fields: [{key:'f', value:'initial', dtype:'string'}], extracted_groups: [], extracted_tables: [] }] }
          });
          const response = (golden) => ({ ...fixture(), golden });
          const host = document.createElement('div'); document.body.appendChild(host);
          let editor;
          const callbackDirty = [];
          editor = createGoldenEditor(host, { bundleId:'b', docId:'d', doc:fixture(), onDirtyChange:v=>callbackDirty.push(v), onSaveOk:()=>callbackDirty.push(editor.isDirty()) });
          const entry = { doc:0, area:'field', key:'f' };
          editor.adoptValue(entry, 'A');
          const firstSave = editor.save();
          await Promise.resolve(); await Promise.resolve();
          if (pending.length !== 1) throw new Error('first request did not start');
          editor.adoptValue(entry, 'B');
          pending[0].resolve(response(pending[0].golden));
          await firstSave;
          if (!editor.isDirty()) throw new Error('edit made during request was incorrectly marked clean');
          await new Promise(r => setTimeout(r, 1600));
          if (pending.length !== 2) throw new Error('latest edit was not autosaved');
          if (pending[1].golden.documents[0].extracted_fields[0].value !== 'B') throw new Error('autosave did not contain latest value');
          pending[1].resolve(response(pending[1].golden));
          await new Promise(r => setTimeout(r, 0));
          if (editor.isDirty()) throw new Error('latest successful save remained dirty');
          if (callbackDirty.at(-1) !== false) throw new Error('save status callback did not observe clean state');
          editor.destroy(); host.remove();

          const host2 = document.createElement('div'); document.body.appendChild(host2);
          const calls = []; const started = [];
          api.putGolden = (_b, _d, golden) => new Promise(resolve => calls.push({golden, resolve}));
          const editor2 = createGoldenEditor(host2, { bundleId:'b', docId:'d', doc:fixture(), onSaveStart:()=>started.push('start'), onSaveOk:()=>started.push('ok'), onDirtyChange:()=>started.push('dirty') });
          editor2.adoptValue(entry, 'queued-1');
          const queuedFirst = editor2.save();
          await Promise.resolve(); await Promise.resolve();
          editor2.adoptValue(entry, 'queued-2');
          const queuedSecond = editor2.save();
          editor2.destroy();
          const callbackCountAtDestroy = started.length;
          calls[0].resolve(response(calls[0].golden));
          await queuedFirst;
          await Promise.resolve(); await Promise.resolve();
          if (calls.length !== 2) throw new Error('explicitly queued network save was dropped during destroy');
          calls[1].resolve(response(calls[1].golden));
          await queuedSecond;
          await new Promise(r => setTimeout(r, 1600));
          if (started.length !== callbackCountAtDestroy) throw new Error('callbacks ran after destroy');
          if (calls.length !== 2) throw new Error('destroy scheduled an extra autosave');
          host2.remove();

          const hostError = document.createElement('div'); document.body.appendChild(hostError);
          const failedQueue = []; let saveErrors = 0;
          api.putGolden = (_b, _d, golden) => new Promise((resolve, reject) => failedQueue.push({golden, resolve, reject}));
          const editorError = createGoldenEditor(hostError, { bundleId:'b', docId:'d', doc:fixture(), onSaveErr:()=>saveErrors++ });
          editorError.adoptValue(entry, 'first');
          const failedSave = editorError.save();
          await Promise.resolve(); await Promise.resolve();
          editorError.adoptValue(entry, 'second');
          const nextSave = editorError.save();
          failedQueue[0].reject(new Error('expected test failure'));
          await failedSave;
          await Promise.resolve(); await Promise.resolve();
          if (failedQueue.length !== 2) throw new Error('queued save did not start after prior PUT error');
          if (failedQueue[1].golden.documents[0].extracted_fields[0].value !== 'second') throw new Error('queued save used an outdated snapshot');
          failedQueue[1].resolve(response(failedQueue[1].golden));
          await nextSave;
          if (editorError.isDirty() || saveErrors !== 1) throw new Error('queue did not recover cleanly after PUT error');
          editorError.destroy(); hostError.remove();

          const host3 = document.createElement('div'); document.body.appendChild(host3);
          const deletePending = []; const events = [];
          window.confirm = () => true;
          api.putGolden = (_b, _d, golden) => new Promise(resolve => deletePending.push({golden, resolve}));
          api.deleteGolden = async () => { events.push('delete'); };
          const editor3 = createGoldenEditor(host3, { bundleId:'b', docId:'d', doc:fixture() });
          editor3.adoptValue(entry, 'before-delete');
          const saveBeforeDelete = editor3.save();
          await Promise.resolve(); await Promise.resolve();
          host3.querySelector('button.danger').click();
          await Promise.resolve();
          if (events.length) throw new Error('delete was not serialized behind pending PUT');
          deletePending[0].resolve(response(deletePending[0].golden));
          await saveBeforeDelete;
          await new Promise(r => setTimeout(r, 0));
          if (events.join(',') !== 'delete') throw new Error('delete did not follow the pending PUT');
          await new Promise(r => setTimeout(r, 1600));
          if (deletePending.length !== 1) throw new Error('autosave ran after deletion');
          editor3.destroy(); host3.remove();
          return { ok:true, requests:calls.length + deletePending.length, ordering:events.join(',') };
            }""")
            print(result)
            await browser.close()
    finally:
        server.shutdown()
        server_thread.join()


asyncio.run(main())
