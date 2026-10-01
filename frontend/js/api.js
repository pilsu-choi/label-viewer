// API.md 계약을 그대로 감싼 얇은 클라이언트.

async function req(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = '';
    try { const j = await res.json(); detail = j.detail || j.error || JSON.stringify(j); } catch (e) { /* no body */ }
    const err = new Error(detail || `${res.status} ${res.statusText}`);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

// 문서 간 이동마다 번들 목록을 다시 받지 않도록 마지막 번들만 기억한다. fresh 면 새로 받는다.
let bundleCache = null;

export const api = {
  listBundles: () => req('GET', '/api/bundles'),
  getBundle(id, fresh) {
    if (fresh || bundleCache?.id !== id) {
      const p = req('GET', `/api/bundles/${encodeURIComponent(id)}`);
      bundleCache = { id, p };
      p.catch(() => { if (bundleCache?.p === p) bundleCache = null; });
    }
    return bundleCache.p;
  },
  deleteBundle: (id) => { bundleCache = null; return req('DELETE', `/api/bundles/${encodeURIComponent(id)}`); },
  getDoc: (bundleId, docId) => req('GET', `/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}`),
  imageUrl: (bundleId, docId, view, page, w) =>
    `/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}/image?view=${view}&page=${page || 1}${w ? `&w=${w}` : ''}`,
  rawUrl: (bundleId, docId, kind) =>
    `/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}/raw/${kind}`,
  getRaw: (bundleId, docId, kind) => fetch(`/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}/raw/${kind}`)
    .then((res) => { if (!res.ok) throw new Error(`${res.status}`); return res.text(); }),
  createGolden: (bundleId, docId, from, docType) =>
    req('POST', `/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}/golden`, { from, doc_type: docType || undefined }),
  putGolden: (bundleId, docId, golden) =>
    req('PUT', `/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}/golden`, { golden }),
  deleteGolden: (bundleId, docId) =>
    req('DELETE', `/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}/golden`),
  // 여러 문서 활성 여부를 바꾸고 갱신된 번들 화면 데이터를 받는다. 문서 이동용 캐시도 바꿔 둔다.
  setEnabled(bundleId, ids, enabled) {
    const p = req('PUT', `/api/bundles/${encodeURIComponent(bundleId)}/enabled`, { ids, enabled });
    return p.then((b) => { bundleCache = { id: bundleId, p: Promise.resolve(b) }; return b; });
  },
  putReview: (bundleId, docId, review) =>
    req('PUT', `/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}/review`, { review }),
  // docId 가 있으면 그 문서만, 없으면 scope('enabled'|'disabled') 문서만 내보낸다.
  exportBundleZipUrl: (bundleId, docId, scope = 'enabled') =>
    `/api/bundles/${encodeURIComponent(bundleId)}/export/bundle.zip?${docId ? `doc=${encodeURIComponent(docId)}` : `scope=${scope}`}`,
  exportGoldenXlsxUrl: (bundleId, docId, scope = 'enabled') =>
    `/api/bundles/${encodeURIComponent(bundleId)}/export/golden.xlsx?${docId ? `doc=${encodeURIComponent(docId)}` : `scope=${scope}`}`,

  uploadBundle(files, name, onProgress) {
    return new Promise((resolve, reject) => {
      const fd = new FormData();
      for (const f of files) fd.append('files', f.file, f.relPath);
      if (name) fd.append('name', name);
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/bundles');
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
      });
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try { resolve(JSON.parse(xhr.responseText)); } catch (e) { reject(e); }
        } else {
          let detail = xhr.responseText;
          try { detail = JSON.parse(xhr.responseText).detail || detail; } catch (e) { /* ignore */ }
          reject(new Error(detail || `${xhr.status}`));
        }
      };
      xhr.onerror = () => reject(new Error('네트워크 오류'));
      xhr.send(fd);
    });
  },
};
