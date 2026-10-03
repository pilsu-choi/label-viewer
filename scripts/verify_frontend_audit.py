"""Browser regressions for numeric display, bad routes, request deadlines and upload navigation."""
import asyncio
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.async_api import async_playwright


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


async def main():
    root = Path(__file__).resolve().parents[1]
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
    executable = max(Path.home().joinpath('.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'), key=lambda p: int(re.search(r'chromium-(\d+)',str(p)).group(1)))
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, executable_path=str(executable))
            page = await browser.new_page()
            await page.goto(f'http://127.0.0.1:{server.server_port}/frontend/index.html')
            result = await page.evaluate('''async () => {
              const assert = (value, text) => { if (!value) throw new Error(text); };
              const {fmtNumber} = await import('/frontend/js/util.js');
              assert(fmtNumber('9007199254740993') === '9,007,199,254,740,993', 'large integer display rounded');
              assert(fmtNumber('0.123456789012345678901') === '0.123456789012345678901', 'decimal display rounded');
              assert(fmtNumber('-0000.000') === '0', 'negative zero formatting');
              const router = await import('/frontend/js/router.js');
              let home = 0, bad = 0;
              router.onRoute('/', () => {home++;});
              router.onRoute('/b/{id}', () => {bad++;});
              history.replaceState(null, '', '#/b/%');router.startRouter();
              assert(home === 1 && bad === 0 && location.hash === '#/', 'bad percent route crashed');

              const originalFetch = window.fetch, originalTimeout = window.setTimeout;
              const deadlineApi = (await import('/frontend/js/api.js?deadline-audit')).api;
              window.fetch = (_url, options) => new Promise((_resolve, reject) => {
                options.signal.addEventListener('abort', () => reject(new DOMException('aborted','AbortError')));
              });
              window.setTimeout = (fn, ms, ...args) => originalTimeout(fn, ms === 30000 ? 15 : ms, ...args);
              try {
                await deadlineApi.listBundles();throw new Error('deadline did not abort');
              } catch (error) { assert(error.message.includes('시간이 초과'), 'wrong deadline error'); }
              finally {window.fetch = originalFetch;window.setTimeout = originalTimeout;}

              const {api} = await import('/frontend/js/api.js');
              const {renderUpload} = await import('/frontend/js/upload.js');
              api.listBundles = async () => [];
              let finish, uploads = 0;
              api.uploadBundle = () => { uploads++;return new Promise(resolve => {finish = resolve;});};
              const host = document.createElement('div');document.body.appendChild(host);
              const cleanup = renderUpload(host);
              const input = host.querySelector('input[type=file]');
              const dt = new DataTransfer();dt.items.add(new File(['fixture'],'one.zip'));
              input.files = dt.files;input.dispatchEvent(new Event('change'));
              input.dispatchEvent(new Event('change'));
              assert(uploads === 1, 'double upload accepted while busy');
              cleanup();history.replaceState(null, '', '#/bundles');
              finish({id:'finished-old-upload'});await new Promise(resolve => originalTimeout(resolve,30));
              assert(location.hash === '#/bundles', 'completed old upload stole navigation');host.remove();
              return {ok:true, numericDisplay:true, malformedRoute:true, timeout:true, uploadLifecycle:true};
            }''')
            print(result);await browser.close()
    finally:
        server.shutdown();thread.join()


asyncio.run(main())
