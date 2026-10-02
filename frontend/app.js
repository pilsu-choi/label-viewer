import { clear } from './js/util.js';
import { onRoute, setNavGuard, startRouter } from './js/router.js';
import { renderUpload } from './js/upload.js';
import { renderBundles } from './js/bundles.js';
import { renderList } from './js/list.js';
import { renderDetail } from './js/detail.js';

const root = document.getElementById('app');
let cleanup = null;

function mountScreen(renderFn, ...args) {
  if (cleanup) { cleanup(); cleanup = null; }
  setNavGuard(null);
  clear(root);
  window.scrollTo(0, 0);
  const result = renderFn(root, ...args);
  cleanup = typeof result === 'function' ? result : null;
}

onRoute('/', () => mountScreen(renderUpload));
onRoute('/bundles', () => mountScreen(renderBundles));
onRoute('/b/{id}', (p) => mountScreen(renderList, p.id));
onRoute('/b/{id}/d/{doc}', (p) => mountScreen(renderDetail, p.id, p.doc));

startRouter();
