import { el, clear } from './util.js';

// 확대/축소·드래그 팬·bbox 오버레이를 갖춘 이미지 뷰어. stage 엘리먼트 하나에 마운트한다.
export function createImageViewer(stage, { onZoomChange } = {}) {
  const canvas = el('div', { class: 'viewer-canvas' });
  const bboxLayer = el('div', { class: 'bbox-layer' });
  canvas.appendChild(bboxLayer);
  stage.appendChild(canvas);

  let scale = 1, tx = 0, ty = 0, natW = 0, natH = 0, imgEl = null;
  let pendingBoxes = [], focusView = null;

  function apply() { canvas.style.transform = `translate(${tx}px,${ty}px) scale(${scale})`; if (onZoomChange) onZoomChange(scale); }

  function zoomAt(factor, cx, cy) {
    if (!natW) return;
    const rect = stage.getBoundingClientRect();
    const px = cx == null ? rect.width / 2 : cx - rect.left;
    const py = cy == null ? rect.height / 2 : cy - rect.top;
    const before = scale;
    scale = Math.max(0.08, Math.min(8, scale * factor));
    const ratio = scale / before;
    tx = px - (px - tx) * ratio;
    ty = py - (py - ty) * ratio;
    apply();
  }

  function fitWidth() {
    if (!natW) return;
    scale = stage.clientWidth / natW;
    tx = 0; ty = 0;
    apply();
  }

  function fitPage() {
    if (!natW) return;
    scale = Math.min(stage.clientWidth / natW, stage.clientHeight / natH);
    tx = (stage.clientWidth - natW * scale) / 2;
    ty = (stage.clientHeight - natH * scale) / 2;
    apply();
  }

  let panning = false, lastX = 0, lastY = 0;
  const onMouseDown = (e) => {
    if (e.button !== 0) return;
    panning = true; lastX = e.clientX; lastY = e.clientY;
    stage.classList.add('panning');
  };
  const onMouseMove = (e) => {
    if (!panning) return;
    tx += e.clientX - lastX; ty += e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY;
    apply();
  };
  const onMouseUp = () => { panning = false; stage.classList.remove('panning'); };
  const onWheel = (e) => { e.preventDefault(); zoomAt(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX, e.clientY); };
  stage.addEventListener('mousedown', onMouseDown);
  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mouseup', onMouseUp);
  stage.addEventListener('wheel', onWheel, { passive: false });

  function load(url) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.alt = '';
      img.onload = () => {
        natW = img.naturalWidth; natH = img.naturalHeight;
        canvas.style.width = natW + 'px'; canvas.style.height = natH + 'px';
        bboxLayer.style.width = natW + 'px'; bboxLayer.style.height = natH + 'px';
        if (imgEl) imgEl.remove();
        imgEl = img;
        canvas.insertBefore(img, bboxLayer);
        fitPage();
        setBoxes(pendingBoxes);
        resolve({ width: natW, height: natH });
      };
      img.onerror = () => reject(new Error('이미지를 불러오지 못했습니다.'));
      img.src = url;
    });
  }

  function setBoxes(boxes) {
    pendingBoxes = boxes || [];
    drawBoxes();
  }

  function drawBoxes() {
    clear(bboxLayer);
    for (const b of pendingBoxes) {
      bboxLayer.appendChild(el('div', {
        class: 'bbox-rect',
        style: `left:${b.x * 100}%;top:${b.y * 100}%;width:${b.w * 100}%;height:${b.h * 100}%`,
      }));
    }
  }

  function focusBoxes(boxes) {
    if (!boxes || !boxes.length || !natW) { clearFocus(); return; }
    if (!focusView) focusView = { scale, tx, ty };
    setBoxes(boxes);
    const x = Math.min(...boxes.map((b) => b.x));
    const y = Math.min(...boxes.map((b) => b.y));
    const right = Math.max(...boxes.map((b) => b.x + b.w));
    const bottom = Math.max(...boxes.map((b) => b.y + b.h));
    const rectW = Math.max((right - x) * natW, 1);
    const rectH = Math.max((bottom - y) * natH, 1);
    const stageW = stage.clientWidth, stageH = stage.clientHeight;
    const fitScale = Math.min(stageW / (rectW * 1.5), stageH / (rectH * 1.8));
    scale = Math.min(8, Math.max(focusView.scale, Math.min(focusView.scale * 4, fitScale)));
    tx = stageW / 2 - ((x + right) / 2) * natW * scale;
    ty = stageH / 2 - ((y + bottom) / 2) * natH * scale;
    apply();
  }

  function clearFocus() {
    if (focusView) {
      ({ scale, tx, ty } = focusView);
      focusView = null;
      apply();
    }
    pendingBoxes = [];
    drawBoxes();
  }

  function empty(message) {
    natW = 0; natH = 0;
    focusView = null;
    pendingBoxes = [];
    if (imgEl) { imgEl.remove(); imgEl = null; }
    clear(bboxLayer);
    stage.querySelectorAll('.viewer-empty').forEach((n) => n.remove());
    if (message) stage.appendChild(el('div', { class: 'viewer-empty' }, message));
  }

  return {
    load, setBoxes, focusBoxes, clearFocus, empty,
    zoomIn: () => zoomAt(1.25), zoomOut: () => zoomAt(0.8), fitWidth, fitPage,
    getScale: () => scale,
    destroy: () => { window.removeEventListener('mousemove', onMouseMove); window.removeEventListener('mouseup', onMouseUp); },
  };
}
