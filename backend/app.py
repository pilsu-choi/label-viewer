"""FastAPI 앱: 라우트 정의와 uvicorn 진입점."""
from __future__ import annotations

import argparse
import mimetypes
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import bundle as B
from . import export as E

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def create_app(data_dir: Path, max_upload_mb: Optional[int] = None) -> FastAPI:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    max_mb = max_upload_mb or int(os.environ.get("LABEL_VIEWER_MAX_UPLOAD_MB", "2048"))

    app = FastAPI(title="Label Viewer")
    app.state.data_dir = data_dir
    app.state.max_upload_bytes = max_mb * 1024 * 1024

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except B.ApiError as e:
            raise HTTPException(status_code=e.status, detail=e.message)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.post("/api/bundles", status_code=201)
    async def upload_bundle(request: Request, files: list[UploadFile] = File(...),
                             name: Optional[str] = Form(None)):
        collected = [(f.filename, await f.read()) for f in files]
        bid = call(B.process_upload, data_dir, collected, name, request.app.state.max_upload_bytes)
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
    def get_image(bundle_id: str, doc_id: str, view: str = "original", page: int = 1):
        path, n_pages = call(B.get_image, data_dir, bundle_id, doc_id, view, page)
        media = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        return FileResponse(path, media_type=media, headers={"X-Pages": str(n_pages)})

    @app.get("/api/bundles/{bundle_id}/docs/{doc_id}/raw/{kind}")
    def get_raw(bundle_id: str, doc_id: str, kind: str):
        if kind not in B.JSON_KINDS:
            raise HTTPException(404, "unknown kind")
        bdir = call(B.bundle_dir, data_dir, bundle_id)
        path = B.find_kind_file(bdir, kind, doc_id)
        if path is None:
            raise HTTPException(404, "not found")
        return Response(content=path.read_text(encoding="utf-8"), media_type="application/json")

    @app.post("/api/bundles/{bundle_id}/docs/{doc_id}/golden")
    async def post_golden(bundle_id: str, doc_id: str, request: Request):
        body = await request.json()
        return call(B.create_golden, data_dir, bundle_id, doc_id, body.get("from", "empty"), body.get("doc_type"))

    @app.put("/api/bundles/{bundle_id}/docs/{doc_id}/golden")
    async def put_golden(bundle_id: str, doc_id: str, request: Request):
        body = await request.json()
        return call(B.save_golden, data_dir, bundle_id, doc_id, body.get("golden"))

    @app.delete("/api/bundles/{bundle_id}/docs/{doc_id}/golden", status_code=204)
    def delete_golden(bundle_id: str, doc_id: str):
        call(B.delete_golden, data_dir, bundle_id, doc_id)
        return Response(status_code=204)

    @app.put("/api/bundles/{bundle_id}/docs/{doc_id}/review", status_code=204)
    async def put_review(bundle_id: str, doc_id: str, request: Request):
        body = await request.json()
        call(B.set_review, data_dir, bundle_id, doc_id, body.get("review", ""))
        return Response(status_code=204)

    @app.get("/api/bundles/{bundle_id}/export/golden.zip")
    def export_zip(bundle_id: str):
        data = call(E.export_golden_zip, data_dir, bundle_id)
        return Response(content=data, media_type="application/zip",
                         headers={"Content-Disposition": f'attachment; filename="{bundle_id}-golden.zip"'})

    @app.get("/api/bundles/{bundle_id}/export/golden.xlsx")
    def export_xlsx(bundle_id: str, doc: Optional[str] = None):
        data = call(E.export_golden_xlsx, data_dir, bundle_id, doc)
        return Response(content=data,
                         media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         headers={"Content-Disposition": f'attachment; filename="{bundle_id}-golden.xlsx"'})

    if FRONTEND_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def index():
        idx = FRONTEND_DIR / "index.html"
        if idx.exists():
            return FileResponse(idx)
        raise HTTPException(404, "frontend not built")

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Label Viewer backend")
    parser.add_argument("--data", default=os.environ.get("LABEL_VIEWER_DATA", "./storage"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    import uvicorn
    app = create_app(Path(args.data))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
