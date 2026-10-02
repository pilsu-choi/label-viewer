"""FastAPI 앱: 라우트 정의와 uvicorn 진입점."""
from __future__ import annotations

import argparse
import hashlib
import mimetypes
import os
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import bundle as B
from . import export as E

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
NO_CACHE = {"Cache-Control": "no-cache"}  # 배포 뒤 예전 JS 모듈을 쓰지 않도록 매번 재검증
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}  # 버전 경로 정적 파일
IMAGE_CACHE = {"Cache-Control": "private, max-age=86400"}


class HeaderStatic(StaticFiles):
    def __init__(self, *args, headers: dict, **kw):
        super().__init__(*args, **kw)
        self.headers = headers

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers.update(self.headers)
        return resp


class TextGZip(GZipMiddleware):
    """이미지·내보내기(ZIP·XLSX)는 이미 압축돼 있어 건너뛴다."""
    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if path.endswith("/image") or "/export/" in path:
            return await self.app(scope, receive, send)
        await super().__call__(scope, receive, send)


def _static_version() -> str:
    """프론트 파일 경로·mtime·크기 해시. 파일이 바뀌면 /static/{ver} URL 이 바뀐다."""
    h = hashlib.sha1()
    for p in sorted(FRONTEND_DIR.rglob("*")):
        if p.is_file():
            st = p.stat()
            h.update(f"{p.relative_to(FRONTEND_DIR)}{st.st_mtime_ns}{st.st_size}".encode())
    return h.hexdigest()[:10]


def create_app(data_dir: Path, max_upload_mb: Optional[int] = None) -> FastAPI:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    max_mb = max_upload_mb or int(os.environ.get("LABEL_VIEWER_MAX_UPLOAD_MB", "2048"))

    app = FastAPI(title="Label Viewer")
    app.add_middleware(TextGZip, minimum_size=1024, compresslevel=6)
    app.state.data_dir = data_dir
    app.state.max_upload_bytes = max_mb * 1024 * 1024

    async def json_body(request: Request) -> dict:
        try:
            body = await request.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise HTTPException(422, "JSON object body required")
        return body

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except B.ApiError as e:
            raise HTTPException(status_code=e.status, detail=e.message)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.post("/api/bundles", status_code=201)
    async def upload_bundle(request: Request):
        limit = request.app.state.max_upload_bytes
        length = request.headers.get("content-length", "")
        call(B.check_upload_size, int(length) if length.isdigit() else 0, limit)  # 본문 파싱 전 조기 거절
        # Starlette 기본 한도(파일 1000개)로는 200건 넘는 폴더 업로드가 막힌다
        form = await request.form(max_files=100_000, max_fields=100_000)
        try:
            files = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
            if not files:
                raise HTTPException(422, "files required")
            name = form.get("name") or None
            # 업로드는 임시 파일로 스풀링되므로 내용을 읽지 않고 파일째 넘기고, 복사는 이벤트 루프 밖 스레드에서 한다
            bid = await run_in_threadpool(call, B.process_upload, data_dir, [(f.filename, f.file) for f in files], name, limit)
        finally:
            await form.close()
        return call(B.bundle_view, data_dir, bid)

    @app.get("/api/bundles")
    def list_bundles():
        return call(B.list_bundles, data_dir)

    @app.delete("/api/bundles/{bundle_id}", status_code=204)
    def delete_bundle(bundle_id: str):
        call(B.delete_bundle, data_dir, bundle_id)
        return Response(status_code=204)

    @app.get("/api/bundles/{bundle_id}")
    def get_bundle(bundle_id: str):
        return call(B.bundle_view, data_dir, bundle_id)

    @app.get("/api/bundles/{bundle_id}/docs/{doc_id}")
    def get_doc(bundle_id: str, doc_id: str):
        return call(B.doc_detail, data_dir, bundle_id, doc_id)

    @app.get("/api/bundles/{bundle_id}/docs/{doc_id}/image")
    def get_image(bundle_id: str, doc_id: str, view: str = "original", page: int = 1,
                  w: Optional[int] = None):
        path, n_pages = call(B.get_image, data_dir, bundle_id, doc_id, view, page, w)
        media = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        return FileResponse(path, media_type=media, headers={"X-Pages": str(n_pages), **IMAGE_CACHE})

    @app.get("/api/bundles/{bundle_id}/docs/{doc_id}/raw/{kind}")
    def get_raw(bundle_id: str, doc_id: str, kind: str):
        if kind not in B.JSON_KINDS:
            raise HTTPException(404, "unknown kind")
        bdir = call(B.bundle_dir, data_dir, bundle_id)
        path = B.find_kind_file(bdir, kind, doc_id)
        if path is None:
            raise HTTPException(404, "not found")
        return Response(content=B.read_json_text(path), media_type="application/json")

    @app.post("/api/bundles/{bundle_id}/docs/{doc_id}/golden")
    async def post_golden(bundle_id: str, doc_id: str, request: Request):
        body = await json_body(request)
        return await run_in_threadpool(call, B.create_golden, data_dir, bundle_id, doc_id, body.get("from", "empty"), body.get("doc_type"))

    @app.put("/api/bundles/{bundle_id}/docs/{doc_id}/golden")
    async def put_golden(bundle_id: str, doc_id: str, request: Request):
        body = await json_body(request)
        return await run_in_threadpool(call, B.save_golden, data_dir, bundle_id, doc_id, body.get("golden"))

    @app.delete("/api/bundles/{bundle_id}/docs/{doc_id}/golden", status_code=204)
    def delete_golden(bundle_id: str, doc_id: str):
        call(B.delete_golden, data_dir, bundle_id, doc_id)
        return Response(status_code=204)

    @app.put("/api/bundles/{bundle_id}/docs/{doc_id}/review", status_code=204)
    async def put_review(bundle_id: str, doc_id: str, request: Request):
        body = await json_body(request)
        await run_in_threadpool(call, B.set_review, data_dir, bundle_id, doc_id, body.get("review", ""))
        return Response(status_code=204)

    @app.put("/api/bundles/{bundle_id}/enabled")
    async def put_enabled(bundle_id: str, request: Request):
        body = await json_body(request)
        await run_in_threadpool(call, B.set_enabled, data_dir, bundle_id, body.get("ids"), body.get("enabled"))
        return await run_in_threadpool(call, B.bundle_view, data_dir, bundle_id)

    def _export_name(bundle_id: str, doc: Optional[str], scope: str, ext: str) -> str:
        suffix = f"-{doc}" if doc else ("-disabled" if scope == "disabled" else "")
        return quote(f"{bundle_id}{suffix}{ext}")

    @app.get("/api/bundles/{bundle_id}/export/bundle.zip")
    def export_zip(bundle_id: str, doc: Optional[str] = None, scope: str = "enabled"):
        fp = call(E.export_bundle_zip, data_dir, bundle_id, doc, scope)
        size = fp.seek(0, os.SEEK_END)
        fp.seek(0)

        def chunks():
            with fp:
                while block := fp.read(1 << 20):
                    yield block

        return StreamingResponse(chunks(), media_type="application/zip", headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{_export_name(bundle_id, doc, scope, '.zip')}",
            "Content-Length": str(size)})

    @app.get("/api/bundles/{bundle_id}/export/golden.xlsx")
    def export_xlsx(bundle_id: str, doc: Optional[str] = None, scope: str = "enabled"):
        data = call(E.export_golden_xlsx, data_dir, bundle_id, doc, scope)
        return Response(content=data,
                         media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_export_name(bundle_id, doc, scope, '-golden.xlsx')}"})

    if FRONTEND_DIR.is_dir():
        ver = _static_version()
        for prefix, headers in ((f"/static/{ver}", IMMUTABLE), ("/static", NO_CACHE)):  # 구버전 탭용 /static 도 유지
            app.mount(prefix, HeaderStatic(directory=str(FRONTEND_DIR), headers=headers), name=prefix)
        idx = FRONTEND_DIR / "index.html"
        html = idx.read_text(encoding="utf-8").replace('"/static/', f'"/static/{ver}/') if idx.exists() else None

        @app.get("/")
        def index():
            if html is None:
                raise HTTPException(404, "frontend not built")
            return HTMLResponse(html, headers=NO_CACHE)

    return app


def app_from_env() -> FastAPI:
    """다중 워커용 uvicorn 팩토리(import string)."""
    return create_app(Path(os.environ["LABEL_VIEWER_DATA"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Label Viewer backend")
    parser.add_argument("--data", default=os.environ.get("LABEL_VIEWER_DATA", "./storage"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--workers", type=int, default=int(os.environ.get("LABEL_VIEWER_WORKERS", "2")))
    args = parser.parse_args()

    import uvicorn
    os.environ["LABEL_VIEWER_DATA"] = args.data
    uvicorn.run("backend.app:app_from_env", factory=True, host=args.host, port=args.port, workers=args.workers)


if __name__ == "__main__":
    main()
