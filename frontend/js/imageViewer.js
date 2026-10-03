import { el, clear } from './util.js';

// 확대/축소·드래그 팬·bbox 오버레이·미니맵을 갖춘 이미지 뷰어. stage 엘리먼트 하나에 마운트한다.
export function createImageViewer(stage, { onZoomChange, onRotationChange, focusMode } = {}) {
  const canvas = el('div', { class: 'viewer-canvas' });
  const rotatedContent = el('div', { class: 'viewer-rotated-content' });
  const bboxLayer = el('div', { class: 'bbox-layer' });
  Object.assign(bboxLayer.style, { position: 'absolute', left: '0', top: '0' });
  rotatedContent.appendChild(bboxLayer);
  canvas.appendChild(rotatedContent);
  stage.appendChild(canvas);

  const minimapContent = el('div', { class: 'mm-rotated-content' });
  const minimapImg = el('img', { alt: '' });
  const minimapBoxes = el('div', { class: 'mm-boxes' });
  const minimapViewport = el('div', { class: 'mm-viewport' });
  minimapContent.append(minimapImg, minimapBoxes);
  const minimapEl = el('div', { class: 'minimap' }, [minimapContent, minimapViewport]);
  stage.appendChild(minimapEl);

  let scale = 1, tx = 0, ty = 0, natW = 0, natH = 0, imgEl = null, rotation = 0;
  let pendingBoxes = [], focusView = null;
  let mode = focusMode === 'locate' ? 'locate' : 'zoom';
  // fitMode: 'page' | 'width' | 'manual' — stage 크기 변화(스플리터 드래그·윈도우 리사이즈·패널 접기/펼치기) 시
  // 어떻게 다시 맞출지 결정한다. page/width 는 다시 맞춤, manual 은 중심점을 유지한 채 비율 조정.
  let fitMode = 'page';
  let prevStageW = 0, prevStageH = 0;

  function viewWidth() { return rotation % 180 ? natH : natW; }
  function viewHeight() { return rotation % 180 ? natW : natH; }
  function layoutRotation() {
    const w = viewWidth(), h = viewHeight();
    canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
    rotatedContent.style.width = `${natW}px`; rotatedContent.style.height = `${natH}px`;
    rotatedContent.style.left = `${w / 2}px`; rotatedContent.style.top = `${h / 2}px`;
    rotatedContent.style.transform = `translate(-50%, -50%) rotate(${rotation}deg)`;
    layoutMinimap();
  }
  function layoutMinimap() {
    if (!natW) return;
    const s = Math.min(160 / viewWidth(), 200 / viewHeight());
    minimapEl.style.width = `${viewWidth() * s}px`; minimapEl.style.height = `${viewHeight() * s}px`;
    minimapContent.style.width = `${natW * s}px`; minimapContent.style.height = `${natH * s}px`;
    minimapContent.style.left = '50%'; minimapContent.style.top = '50%';
    minimapContent.style.transform = `translate(-50%, -50%) rotate(${rotation}deg)`;
  }
  function apply() { canvas.style.transform = `translate(${tx}px,${ty}px) scale(${scale})`; if (onZoomChange) onZoomChange(scale); updateMinimap(); }

  function updateMinimap() {
    if (!natW) { minimapEl.classList.remove('visible'); return; }
    const stageW = stage.clientWidth, stageH = stage.clientHeight;
    const vw = viewWidth(), vh = viewHeight();
    const fullyVisible = tx >= -0.5 && ty >= -0.5 && tx + vw * scale <= stageW + 0.5 && ty + vh * scale <= stageH + 0.5;
    minimapEl.classList.toggle('visible', !fullyVisible);
    const vx0 = Math.max(0, -tx / scale) / vw, vy0 = Math.max(0, -ty / scale) / vh;
    const vx1 = Math.min(vw, (stageW - tx) / scale) / vw, vy1 = Math.min(vh, (stageH - ty) / scale) / vh;
    Object.assign(minimapViewport.style, { left: `${vx0 * 100}%`, top: `${vy0 * 100}%`, width: `${Math.max(0, vx1 - vx0) * 100}%`, height: `${Math.max(0, vy1 - vy0) * 100}%` });
  }

  function minimapPanTo(e) {
    const rect = minimapEl.getBoundingClientRect();
    const fx = (e.clientX - rect.left) / rect.width, fy = (e.clientY - rect.top) / rect.height;
    tx = stage.clientWidth / 2 - fx * viewWidth() * scale;
    ty = stage.clientHeight / 2 - fy * viewHeight() * scale;
    apply();
  }
  let mmDragging = false;
  const onMmDown = (e) => { e.stopPropagation(); mmDragging = true; minimapPanTo(e); };
  const onMmWheel = (e) => e.stopPropagation();
  minimapEl.addEventListener('mousedown', onMmDown);
  minimapEl.addEventListener('wheel', onMmWheel);
  const onMmMove = (e) => { if (mmDragging) minimapPanTo(e); };
  const onMmUp = () => { mmDragging = false; };
  window.addEventListener('mousemove', onMmMove);
  window.addEventListener('mouseup', onMmUp);

  function zoomAt(factor, cx, cy) {
    if (!natW) return;
    fitMode = 'manual';
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

  const PAGE_MARGIN = 24;

  function fitWidth() {
    if (!natW) return;
    fitMode = 'width';
    scale = Math.max(0.02, (stage.clientWidth - PAGE_MARGIN * 2) / viewWidth());
    tx = PAGE_MARGIN; ty = PAGE_MARGIN;
    apply();
  }

  function fitPage() {
    if (!natW) return;
    fitMode = 'page';
    scale = Math.max(0.02, Math.min((stage.clientWidth - PAGE_MARGIN * 2) / viewWidth(), (stage.clientHeight - PAGE_MARGIN * 2) / viewHeight()));
    tx = (stage.clientWidth - viewWidth() * scale) / 2;
    ty = (stage.clientHeight - viewHeight() * scale) / 2;
    apply();
  }

  // stage 크기가 바뀌었을 때(스플리터 드래그, 창 리사이즈, 패널 접기/펼치기) 현재 fitMode 에 맞춰
  // 다시 맞추거나(page/width), 중심점을 유지한 채 비율로 재조정한다(manual). bbox 포커스 중에는 건드리지 않는다.
  function handleStageResize() {
    const newW = stage.clientWidth, newH = stage.clientHeight;
    if (!natW || focusView) { prevStageW = newW; prevStageH = newH; return; }
    if (fitMode === 'page') fitPage();
    else if (fitMode === 'width') fitWidth();
    else if (prevStageW && newW !== prevStageW) {
      const factor = newW / prevStageW;
      if (isFinite(factor) && factor > 0) {
        const imgX = (prevStageW / 2 - tx) / scale, imgY = (prevStageH / 2 - ty) / scale;
        scale = Math.max(0.02, Math.min(8, scale * factor));
        tx = newW / 2 - imgX * scale;
        ty = newH / 2 - imgY * scale;
        apply();
      }
    }
    prevStageW = newW; prevStageH = newH;
  }

  let resizeRAF = null;
  const resizeObserver = new ResizeObserver(() => {
    if (resizeRAF) return;
    resizeRAF = requestAnimationFrame(() => { resizeRAF = null; handleStageResize(); });
  });
  resizeObserver.observe(stage);

  let panning = false, lastX = 0, lastY = 0, panRAF = null, loadSeq = 0, destroyed = false;
  const onMouseDown = (e) => {
    if (e.button !== 0) return;
    panning = true; lastX = e.clientX; lastY = e.clientY;
    stage.classList.add('panning');
  };
  const onMouseMove = (e) => {
    if (!panning) return;
    fitMode = 'manual';
    tx += e.clientX - lastX; ty += e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY;
    if (!panRAF) panRAF = requestAnimationFrame(() => { panRAF = null; apply(); }); // 프레임당 한 번만 그린다
  };
  const onMouseUp = () => { panning = false; stage.classList.remove('panning'); };
  const onWheel = (e) => { e.preventDefault(); zoomAt(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX, e.clientY); };
  stage.addEventListener('mousedown', onMouseDown);
  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mouseup', onMouseUp);
  stage.addEventListener('wheel', onWheel, { passive: false });

  // 빠른 이전/다음 이동 시 늦게 도착한 이전 요청은 무시한다(loadSeq).
  function load(url) {
    const seq = ++loadSeq;
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.alt = '';
      img.onload = () => {
        if (destroyed || seq !== loadSeq) return resolve(null);
        natW = img.naturalWidth; natH = img.naturalHeight;
        layoutRotation();
        bboxLayer.style.width = natW + 'px'; bboxLayer.style.height = natH + 'px';
        if (imgEl) imgEl.remove();
        imgEl = img;
        img.style.position = 'absolute'; img.style.left = '0'; img.style.top = '0';
        rotatedContent.insertBefore(img, bboxLayer);
        minimapImg.src = url;
        layoutMinimap();
        fitPage();
        setBoxes(pendingBoxes);
        resolve({ width: natW, height: natH });
      };
      img.onerror = () => seq === loadSeq ? reject(new Error('이미지를 불러오지 못했습니다.')) : resolve(null);
      img.src = url;
    });
  }

  function setBoxes(boxes) {
    pendingBoxes = boxes || [];
    drawBoxes();
  }

  function drawBoxes() {
    clear(bboxLayer);
    clear(minimapBoxes);
    for (const b of pendingBoxes) {
      const style = `left:${b.x * 100}%;top:${b.y * 100}%;width:${b.w * 100}%;height:${b.h * 100}%`;
      bboxLayer.appendChild(el('div', { class: 'bbox-rect', style }));
      minimapBoxes.appendChild(el('div', { class: 'mm-rect', style }));
    }
  }

  function setFocusMode(m) { mode = m === 'locate' ? 'locate' : 'zoom'; }

  function orientedBox(b) {
    if (rotation === 90) return { x: 1 - b.y - b.h, y: b.x, w: b.h, h: b.w };
    if (rotation === 180) return { x: 1 - b.x - b.w, y: 1 - b.y - b.h, w: b.w, h: b.h };
    if (rotation === 270) return { x: b.y, y: 1 - b.x - b.w, w: b.h, h: b.w };
    return b;
  }

  function rotateBy(degrees) {
    if (!natW) { rotation = (rotation + degrees + 360) % 360; if (onRotationChange) onRotationChange(rotation); return rotation; }
    rotation = (rotation + degrees + 360) % 360;
    focusView = null;
    layoutRotation();
    drawBoxes();
    fitPage();
    if (onRotationChange) onRotationChange(rotation);
    return rotation;
  }

  // 화면 밖으로 벗어난 bbox를 배율 변경 없이 화면 안으로 살짝 옮긴다.
  function panIntoView(bx0, by0, bx1, by1) {
    const stageW = stage.clientWidth, stageH = stage.clientHeight, m = 24;
    const sx0 = tx + bx0 * scale, sy0 = ty + by0 * scale, sx1 = tx + bx1 * scale, sy1 = ty + by1 * scale;
    let dx = 0, dy = 0;
    if (sx1 - sx0 > stageW - 2 * m) dx = stageW / 2 - (sx0 + sx1) / 2;
    else if (sx0 < m) dx = m - sx0;
    else if (sx1 > stageW - m) dx = (stageW - m) - sx1;
    if (sy1 - sy0 > stageH - 2 * m) dy = stageH / 2 - (sy0 + sy1) / 2;
    else if (sy0 < m) dy = m - sy0;
    else if (sy1 > stageH - m) dy = (stageH - m) - sy1;
    if (dx || dy) { tx += dx; ty += dy; apply(); }
  }

  function focusBoxes(boxes) {
    if (!boxes || !boxes.length || !natW) { clearFocus(); return; }
    if (!focusView) focusView = { scale, tx, ty };
    setBoxes(boxes);
    const oriented = boxes.map(orientedBox);
    const x = Math.min(...oriented.map((b) => b.x));
    const y = Math.min(...oriented.map((b) => b.y));
    const right = Math.max(...oriented.map((b) => b.x + b.w));
    const bottom = Math.max(...oriented.map((b) => b.y + b.h));
    if (mode === 'locate') { panIntoView(x * viewWidth(), y * viewHeight(), right * viewWidth(), bottom * viewHeight()); return; }
    const rectW = Math.max((right - x) * viewWidth(), 1);
    const rectH = Math.max((bottom - y) * viewHeight(), 1);
    const stageW = stage.clientWidth, stageH = stage.clientHeight;
    const fitScale = Math.min(stageW / (rectW * 1.5), stageH / (rectH * 1.8));
    scale = Math.min(8, Math.max(focusView.scale, Math.min(focusView.scale * 4, fitScale)));
    tx = stageW / 2 - ((x + right) / 2) * viewWidth() * scale;
    ty = stageH / 2 - ((y + bottom) / 2) * viewHeight() * scale;
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
    loadSeq++;
    natW = 0; natH = 0;
    focusView = null;
    pendingBoxes = [];
    if (imgEl) { imgEl.remove(); imgEl = null; }
    clear(bboxLayer);
    clear(minimapBoxes);
    minimapImg.removeAttribute('src');
    updateMinimap();
    stage.querySelectorAll('.viewer-empty').forEach((n) => n.remove());
    if (message) stage.appendChild(el('div', { class: 'viewer-empty' }, message));
  }

  return {
    load, setBoxes, focusBoxes, clearFocus, empty, setFocusMode,
    rotateLeft: () => rotateBy(-90), rotateRight: () => rotateBy(90),
    resetRotation: () => rotateBy((360 - rotation) % 360),
    setRotation: (angle) => {
      const target = ((Number(angle) % 360) + 360) % 360;
      return rotateBy((target - rotation + 360) % 360);
    },
    getRotation: () => rotation,
    zoomIn: () => zoomAt(1.25), zoomOut: () => zoomAt(0.8), fitWidth, fitPage,
    getScale: () => scale,
    destroy: () => {
      destroyed = true;
      loadSeq++;
      resizeObserver.disconnect();
      if (resizeRAF) cancelAnimationFrame(resizeRAF);
      if (panRAF) cancelAnimationFrame(panRAF);
      window.removeEventListener('mousemove', onMouseMove); window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('mousemove', onMmMove); window.removeEventListener('mouseup', onMmUp);
      minimapEl.removeEventListener('mousedown', onMmDown); minimapEl.removeEventListener('wheel', onMmWheel);
      stage.removeEventListener('mousedown', onMouseDown); stage.removeEventListener('wheel', onWheel);
    },
  };
}
