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

export const api = {
  listBundles: () => req('GET', '/api/bundles'),
  getBundle: (id) => req('GET', `/api/bundles/${encodeURIComponent(id)}`),
  deleteBundle: (id) => req('DELETE', `/api/bundles/${encodeURIComponent(id)}`),
  getDoc: (bundleId, docId) => req('GET', `/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}`),
  imageUrl: (bundleId, docId, view, page) =>
    `/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}/image?view=${view}&page=${page || 1}`,
  rawUrl: (bundleId, docId, kind) =>
    `/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}/raw/${kind}`,
  getRaw: (bundleId, docId, kind) => fetch(`/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}/raw/${kind}`)
    .then((res) => { if (!res.ok) throw new Error(`${res.status}`); return res.text(); }),
  createGolden: (bundleId, docId, from) =>
    req('POST', `/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}/golden`, { from }),
  putGolden: (bundleId, docId, golden) =>
    req('PUT', `/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}/golden`, { golden }),
  deleteGolden: (bundleId, docId) =>
    req('DELETE', `/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}/golden`),
  putReview: (bundleId, docId, review) =>
    req('PUT', `/api/bundles/${encodeURIComponent(bundleId)}/docs/${encodeURIComponent(docId)}/review`, { review }),
  exportGoldenZipUrl: (bundleId) => `/api/bundles/${encodeURIComponent(bundleId)}/export/golden.zip`,
  exportGoldenXlsxUrl: (bundleId, docId) =>
    `/api/bundles/${encodeURIComponent(bundleId)}/export/golden.xlsx${docId ? `?doc=${encodeURIComponent(docId)}` : ''}`,

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
