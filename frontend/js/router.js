// 해시 라우터. 라우트: #/  #/b/{id}  #/b/{id}/d/{doc}

const routes = [];
let guard = null; // () => true(이동 허용) | string(경고 메시지)
let current = null;

export function onRoute(pattern, handler) {
  const keys = [];
  const re = new RegExp('^' + pattern.replace(/\{(\w+)\}/g, (_, k) => { keys.push(k); return '([^/]+)'; }) + '$');
  routes.push({ re, keys, handler });
}

export function setNavGuard(fn) { guard = fn; }

export function navigate(hash) {
  if (location.hash === hash) { dispatch(); return; }
  location.hash = hash;
}

function dispatch() {
  const hash = location.hash.replace(/^#/, '') || '/';
  if (guard && current !== hash) {
    const res = guard();
    if (res !== true) {
      if (!confirm(res + '\n\n그래도 이동하시겠습니까?')) {
        if (current != null) history.replaceState(null, '', '#' + current);
        return;
      }
    }
  }
  current = hash;
  for (const r of routes) {
    const m = hash.match(r.re);
    if (m) {
      const params = {};
      try {
        r.keys.forEach((k, i) => { params[k] = decodeURIComponent(m[i + 1]); });
      } catch (error) {
        if (!(error instanceof URIError)) throw error;
        current = '/';
        history.replaceState(null, '', '#/');
        routes[0].handler({});
        return;
      }
      r.handler(params);
      return;
    }
  }
  routes.length && routes[0].handler({});
}

export function startRouter() {
  window.addEventListener('hashchange', dispatch);
  dispatch();
}
