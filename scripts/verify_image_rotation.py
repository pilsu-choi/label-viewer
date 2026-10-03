"""Browser geometry and control checks for image rotation. Run with Playwright installed."""
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
            page = await browser.new_page(viewport={"width": 1200, "height": 900})
            page.on("pageerror", lambda error: print(f"browser pageerror: {error}"))
            await page.goto(f"http://127.0.0.1:{server.server_port}/frontend/index.html")
            result = await page.evaluate("""async () => {
              const { createImageViewer } = await import('/frontend/js/imageViewer.js');
              const stage = document.createElement('div');
              Object.assign(stage.style, {position:'relative', width:'500px', height:'360px', overflow:'hidden'});
              document.body.append(stage);
              let angle = 0;
              const viewer = createImageViewer(stage, {onRotationChange: value => angle = value});
              const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="#ddd"/><path d="M0 0h320v180H0z" fill="none" stroke="#111"/><text x="12" y="28">TOP LEFT</text><circle cx="240" cy="120" r="15" fill="red"/></svg>`;
              const src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
              await viewer.load(src);
              const box = {x:.1,y:.2,w:.25,h:.3};
              viewer.setBoxes([box]);
              const waitFrame = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
              const dimensions = () => ({w:parseFloat(stage.querySelector('.viewer-canvas').style.width), h:parseFloat(stage.querySelector('.viewer-canvas').style.height)});
              const rect = selector => { const node=stage.querySelector(selector); if (!node) throw new Error(`missing rect selector ${selector}`); const r=node.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; };
              const close = (a,b,tol=2) => Math.abs(a-b) <= tol;
              const assert = (ok,msg) => { if (!ok) throw new Error(msg); };
              const check = async (deg) => {
                assert(viewer.getRotation() === deg && angle === deg, `rotation angle did not report ${deg}`);
                viewer.setBoxes([box]);
                await waitFrame();
                const expected = deg % 180 ? {w:180,h:320} : {w:320,h:180};
                const d = dimensions();
                assert(d.w===expected.w && d.h===expected.h, `wrong rotated canvas size at ${deg}: ${JSON.stringify(d)}`);
                const content = rect('.viewer-rotated-content');
                const layer = rect('.bbox-layer');
                const boxNode=stage.querySelector('.bbox-rect');
                const drawnBox = {...rect('.bbox-rect'), css:boxNode.style.cssText, computed: getComputedStyle(boxNode).left,position:getComputedStyle(boxNode).position,offset:boxNode.offsetLeft,parent:boxNode.offsetParent?.className,parentRect:boxNode.offsetParent?.getBoundingClientRect().toJSON()};
                const p = deg===90 ? {x:1-box.y-box.h,y:box.x,w:box.h,h:box.w}
                  : deg===180 ? {x:1-box.x-box.w,y:1-box.y-box.h,w:box.w,h:box.h}
                  : deg===270 ? {x:box.y,y:1-box.x-box.w,w:box.h,h:box.w} : box;
                const expectedBox = {x:layer.x+p.x*layer.w,y:layer.y+p.y*layer.h,w:p.w*layer.w,h:p.h*layer.h};
                assert(close(layer.x,content.x) && close(layer.y,content.y) && close(layer.w,content.w) && close(layer.h,content.h) && close(drawnBox.x,expectedBox.x) && close(drawnBox.y,expectedBox.y) && close(drawnBox.w,expectedBox.w) && close(drawnBox.h,expectedBox.h), `bbox misaligned at ${deg}: ${JSON.stringify({content,layer,drawnBox,expectedBox})}`);
                const mm = stage.querySelector('.minimap');
                const mmContent = stage.querySelector('.mm-rotated-content').getBoundingClientRect();
                const mmBox = stage.querySelector('.mm-rect').getBoundingClientRect();
                assert(mm.offsetWidth>0 && mm.offsetHeight>0 && mmContent.width>0 && mmBox.width>0, `minimap missing at ${deg}`);
                return {d,mm:{w:mm.offsetWidth,h:mm.offsetHeight}};
              };
              const results = [];
              results.push(await check(0));
              viewer.rotateRight(); results.push(await check(90));
              viewer.zoomIn();
              const minimap=stage.querySelector('.minimap'), viewport=stage.querySelector('.mm-viewport');
              assert(minimap.classList.contains('visible') && parseFloat(viewport.style.width)>0 && parseFloat(viewport.style.height)>0, 'minimap viewport did not reflect zoomed rotated image');
              const transformBefore=stage.querySelector('.viewer-canvas').style.transform;
              const mapRect=minimap.getBoundingClientRect();
              minimap.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,clientX:mapRect.left+mapRect.width*.8,clientY:mapRect.top+mapRect.height*.2}));
              window.dispatchEvent(new MouseEvent('mouseup'));
              assert(stage.querySelector('.viewer-canvas').style.transform!==transformBefore, 'minimap pan did not move the rotated image');
              viewer.fitWidth(); assert(viewer.getScale()>0, 'fit width failed after rotation');
              viewer.setFocusMode('zoom'); viewer.focusBoxes([box]); assert(viewer.getScale()>0, 'bbox focus failed after rotation');
              viewer.clearFocus(); viewer.rotateRight(); results.push(await check(180));
              viewer.rotateRight(); results.push(await check(270));
              viewer.rotateLeft(); assert(viewer.getRotation()===180, 'left rotation failed');
              viewer.resetRotation(); results.push(await check(0));
              const beforeResize = viewer.getScale(); stage.style.width='430px'; window.dispatchEvent(new Event('resize')); await waitFrame();
              assert(viewer.getScale()>0 && beforeResize>0, 'resize after rotation failed');

              // A pending old load followed by empty/new load must never overwrite the current image.
              let releaseOld;
              const oldImage = new Promise(resolve => { releaseOld=resolve; });
              const originalImage = window.Image;
              let constructions=0;
              window.Image = class extends originalImage {
                set src(value) { constructions++; if (constructions===1) oldImage.then(() => { Object.defineProperty(this,'naturalWidth',{value:77}); Object.defineProperty(this,'naturalHeight',{value:44}); this.onload?.(); }); else super.src=value; }
              };
              const pending = viewer.load(src);
              viewer.empty();
              await viewer.load(src);
              releaseOld(); await pending;
              window.Image = originalImage;
              assert(dimensions().w===320 && dimensions().h===180, 'stale image load replaced current image');

              const controls = Array.from(document.querySelectorAll('button[aria-label]')).map(b=>b.getAttribute('aria-label'));
              viewer.destroy(); stage.remove();
              const {api} = await import('/frontend/js/api.js');
              const {renderDetail} = await import('/frontend/js/detail.js');
              api.getBundle = async () => ({docs:[{id:'rot-doc',has:{original:true,preprocessed:false},enabled:true}]});
              api.getDoc = async () => ({id:'rot-doc',prev:null,next:null,doc_type:'sample',doc_types:['sample'],has:{original:true,preprocessed:true,ao_extract:false,harness:false,ao_ui:false},pages:{original:2,preprocessed:1},golden:{documents:[{doc_type:'sample',extracted_fields:[],extracted_groups:[],extracted_tables:[]}]},ao:{documents:[]},harness:{documents:[]},compare:[],enabled:true,review:''});
              api.imageUrl = () => src;
              const host=document.createElement('div'); document.body.append(host);
              const cleanup=renderDetail(host,'rot-bundle','rot-doc');
              const waitToolbar=async()=>{ const end=Date.now()+3000; while(Date.now()<end){ if(host.querySelector('.viewer-toolbar .zoom-group')) return; await new Promise(r=>setTimeout(r,20)); } throw new Error('detail viewer toolbar did not render: '+host.textContent.slice(0,500)); };
              await waitToolbar(); await waitFrame();
              const toolbar=host.querySelector('.viewer-toolbar');
              const findButton=label=>Array.from(toolbar.querySelectorAll('button')).find(button=>button.getAttribute('aria-label')===label);
              const right=findButton('오른쪽으로 90도 회전'), left=findButton('왼쪽으로 90도 회전'), reset=findButton('회전 초기화');
              assert(right&&left&&reset,'rotation toolbar controls lack accessible labels');
              Array.from(toolbar.querySelectorAll('.seg button')).find(button=>button.textContent==='원본').click(); await waitFrame();
              right.click(); await waitFrame();
              assert(toolbar.querySelector('.rotation-angle').textContent==='90°','toolbar angle did not update');
              toolbar.querySelector('.page-nav button:last-child').click(); await waitFrame();
              assert(toolbar.querySelector('.rotation-angle').textContent==='0°','new page did not start with a zero rotation: '+toolbar.querySelector('.page-nav').textContent+' angle '+toolbar.querySelector('.rotation-angle').textContent);
              left.click(); await waitFrame();
              toolbar.querySelector('.page-nav button:first-child').click(); await waitFrame();
              assert(toolbar.querySelector('.rotation-angle').textContent==='90°','returning to a page did not preserve its rotation');
              Array.from(toolbar.querySelectorAll('.seg button')).find(button=>button.textContent==='전처리').click(); await waitFrame();
              assert(toolbar.querySelector('.rotation-angle').textContent==='0°','view toggle did not use its own rotation');
              Array.from(toolbar.querySelectorAll('.seg button')).find(button=>button.textContent==='원본').click(); await waitFrame();
              assert(toolbar.querySelector('.rotation-angle').textContent==='90°','view toggle did not restore the original view rotation');
              reset.click(); await waitFrame();
              assert(toolbar.querySelector('.rotation-angle').textContent==='0°','toolbar reset did not update angle');
              cleanup(); host.remove();
              return {results, controls, toolbar:'rotation buttons and angle/reset verified'};
            }""")
            print(result)
            await browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    asyncio.run(main())
