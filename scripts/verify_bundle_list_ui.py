"""Browser regression checks for recent and server-paginated bundle lists."""
import asyncio
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import threading

from playwright.async_api import async_playwright


class QuietHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/static/app.css":
            self.path = "/frontend/app.css"
        super().do_GET()

    def log_message(self, *_args):
        pass


async def main():
    repo_root = Path(__file__).resolve().parents[1]
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(repo_root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    browsers = Path.home().joinpath(".cache/ms-playwright").glob("chromium-*/chrome-linux64/chrome")
    executable = max(browsers, key=lambda p: int(re.search(r"chromium-(\d+)", str(p)).group(1)))
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, executable_path=str(executable))
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            await page.goto(f"http://127.0.0.1:{server.server_port}/frontend/index.html")
            result = await page.evaluate("""async () => {
              const {api} = await import('/frontend/js/api.js');
              const {renderUpload} = await import('/frontend/js/upload.js');
              const {renderBundles} = await import('/frontend/js/bundles.js');
              const assert=(ok,msg)=>{if(!ok)throw new Error(msg)};
              const wait=async(predicate,msg,timeout=3000)=>{const end=Date.now()+timeout;while(Date.now()<end){if(predicate())return;await new Promise(r=>setTimeout(r,20));}throw new Error(msg)};
              const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}};
              const item=(id,name=id)=>({id,name,created_at:'2026-01-01T00:00:00Z',counts:{docs:2,golden:1,reviewed:1,error:0}});
              const response=(page=1,pageSize=50,filtered=125,total=125,items=Array.from({length:Math.min(pageSize,Math.max(0,filtered-(page-1)*pageSize))},(_,i)=>item(`b-${page}-${i}`)))=>({items,total,filtered_total:filtered,page,page_size:pageSize});

              // Verify the API helper retains its legacy unbounded call and formats both new routes.
              const oldFetch=window.fetch, urls=[];
              window.fetch=async url=>{urls.push(String(url));return new Response('[]',{status:200,headers:{'Content-Type':'application/json'}})};
              await api.listBundles(); await api.listBundles({limit:5});
              await api.listBundlePage({query:'a b',sort:'oldest',page:2,page_size:25});
              window.fetch=oldFetch;
              assert(new URL(urls[0],location.href).pathname==='/api/bundles'&&!new URL(urls[0],location.href).search,'legacy listBundles() added a query');
              assert(new URL(urls[1],location.href).searchParams.get('limit')==='5','listBundles limit was not encoded');
              const pageUrl=new URL(urls[2],location.href);
              assert(pageUrl.pathname==='/api/bundles/page'&&pageUrl.searchParams.get('query')==='a b'&&pageUrl.searchParams.get('sort')==='oldest'&&pageUrl.searchParams.get('page')==='2'&&pageUrl.searchParams.get('page_size')==='25','listBundlePage options were not encoded');

              // Home shows a loading state, requests only five, and gives an actionable retry on failure.
              const home=document.createElement('div');document.body.append(home);
              const homeCalls=[];let recent=deferred();
              api.listBundles=options=>{homeCalls.push(options);return recent.promise};
              const cleanHome=renderUpload(home);
              assert(home.querySelector('.recent-host .loading-block')||home.querySelector('.recent-panel .loading-block'),'home did not show recent-list loading');
              assert(!home.textContent.includes('아직 올린 번들이 없습니다'),'home flashed its empty state during loading');
              recent.reject(new Error('temporary outage'));
              await wait(()=>!!home.querySelector('.recent-panel .error-block'),'home error was not shown');
              recent=deferred();
              home.querySelector('.recent-panel .error-block button').click();
              assert(homeCalls.every(options=>options?.limit===5),'home did not request exactly five recent bundles');
              recent.resolve(Array.from({length:5},(_,i)=>item(`recent-${i}`)));
              await wait(()=>home.querySelectorAll('.recent-item').length===5,'home retry did not render recent bundles');
              cleanHome();home.remove();

              // Each full-list action goes to the server and stale out-of-order responses are ignored.
              const root=document.createElement('div');document.body.append(root);
              const calls=[];
              api.listBundlePage=options=>{const d=deferred();calls.push({options:{...options},d});return d.promise};
              const cleanup=renderBundles(root);
              assert(root.querySelector('.loading-block'),'full list did not render initial loading');
              assert(JSON.stringify(calls[0].options)===JSON.stringify({query:'',sort:'newest',page:1,page_size:50}),'initial server page options are wrong');
              calls[0].d.resolve(response());
              await wait(()=>root.querySelectorAll('.bundle-directory-item').length===50,'initial server page was not rendered');
              assert(root.querySelector('.bundles-count').textContent==='125개 / 125개','total counters are wrong');

              root.querySelector('[aria-label="다음 페이지"]').click();
              assert(calls[1].options.page===2,'next page did not request page 2');
              calls[1].d.resolve(response(2,50,125,125,Array.from({length:50},(_,i)=>item(`page2-${i}`))));
              await wait(()=>root.textContent.includes('page2-0'),'page 2 response was not rendered');

              root.querySelector('[aria-label="다음 페이지"]').click();
              const stalePage=calls[2];
              const search=root.querySelector('[aria-label="번들 이름 또는 ID 검색"]');
              const setSearch=value=>{search.value=value;search.dispatchEvent(new Event('input',{bubbles:true}));};
              setSearch('alpha');
              await new Promise(r=>setTimeout(r,80));
              assert(calls.length===3,'search was not debounced');
              stalePage.d.resolve(response(3,50,125,125,[item('stale-page-result')]));
              await new Promise(r=>setTimeout(r,0));
              assert(root.querySelector('.loading-block')&&!root.textContent.includes('stale-page-result'),'stale page response replaced search loading');
              await wait(()=>calls.length===4,'debounced alpha query was not sent');
              assert(calls[3].options.query==='alpha'&&calls[3].options.page===1,'alpha search options are wrong');

              setSearch('beta');
              await wait(()=>calls.length===5,'debounced beta query was not sent');
              assert(calls[4].options.query==='beta','latest search query was not sent');
              calls[4].d.resolve(response(1,50,1,125,[item('beta-latest','beta latest result')]))
              await wait(()=>root.textContent.includes('beta latest result'),'latest search result was not rendered');
              calls[3].d.resolve(response(1,50,1,125,[item('alpha-stale','alpha stale result')]))
              await new Promise(r=>setTimeout(r,0));
              assert(root.textContent.includes('beta latest result')&&!root.textContent.includes('alpha stale result'),'out-of-order search response overwrote the latest result');
              assert(root.querySelector('.bundles-count').textContent==='1개 / 125개','filtered and total counters are not distinct');

              const sort=root.querySelector('[aria-label="정렬"]');
              sort.value='name';sort.dispatchEvent(new Event('change',{bubbles:true}));
              assert(calls[5].options.sort==='name'&&calls[5].options.query==='beta'&&calls[5].options.page===1,'sort did not query the server with current filter');
              calls[5].d.resolve(response(1,50,501,125,[item('sorted','sorted result')]));
              await wait(()=>root.textContent.includes('sorted result'),'sorted response was not rendered');

              const size=root.querySelector('[aria-label="페이지당 번들 수"]');
              size.value='100';size.dispatchEvent(new Event('change',{bubbles:true}));
              assert(calls[6].options.page_size===100&&calls[6].options.page===1,'page size was not sent to the server');
              calls[6].d.resolve(response(1,100,501,125,[item('large-page','large page')]));
              await wait(()=>root.textContent.includes('large page'),'page-size response was not rendered');
              const pageSix=Array.from(root.querySelectorAll('.pager-pages button')).find(button=>button.textContent==='6');
              assert(pageSix,'expected page 6 control');pageSix.click();
              assert(calls[7].options.page===6,'page number click was not sent to server');
              calls[7].d.resolve(response(5,100,501,125,[item('clamped-page','clamped page')]));
              await wait(()=>root.textContent.includes('clamped page'),'clamped page response was not rendered');
              assert(root.querySelector('[aria-current="page"]')?.textContent==='5','server page clamp was not reflected in controls');

              root.querySelector('[aria-label="다음 페이지"]').click();
              const pending=calls[8];
              cleanup();
              pending.d.resolve(response(6,100,501,125,[item('destroyed-result')]));
              await new Promise(r=>setTimeout(r,0));
              assert(root.querySelector('.loading-block')&&!root.textContent.includes('destroyed-result'),'destroyed list accepted a late response');
              root.remove();
              return {homeCalls:homeCalls.length,fullListCalls:calls.length,initialCount:50,latestSearch:'beta',serverClampedPage:5};
            }""")
            print(result)
            await browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    asyncio.run(main())
