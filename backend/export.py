"""번들 내보내기: 전체 묶음 ZIP, Golden Excel."""
from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path
from typing import BinaryIO

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill

from . import bundle as B

_STATUS_FILL = {
    "MATCH": PatternFill("solid", fgColor="C6EFCE"),
    "MISMATCH": PatternFill("solid", fgColor="FFC7CE"),
    "MISSING": PatternFill("solid", fgColor="FFD9A0"),
    "EXTRA": PatternFill("solid", fgColor="E4C7FF"),
    "TYPE_MISMATCH": PatternFill("solid", fgColor="FFF2A8"),
}


_STORED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}  # 이미 압축된 이미지는 다시 deflate 하지 않는다


def export_bundle_zip(data_dir: Path, bundle_id: str, doc_id: str | None = None,
                      scope: str = "enabled") -> BinaryIO:
    """원본·전처리 이미지와 AO·Harness·Golden JSON을 업로드 폴더 구조 그대로 묶는다.
    doc_id가 있으면 그 문서만, 없으면 scope(활성·비활성) 문서만. 수천 건이면 수 GB라 메모리 대신 임시 파일에 쓴다."""
    bdir = B.bundle_dir(data_dir, bundle_id)
    if not bdir.is_dir():
        raise B.ApiError(404, "bundle not found")
    wanted = {doc_id} if doc_id is not None else set(B.scope_doc_ids(data_dir, bundle_id, scope))
    tmp_dir = B.cache_root(data_dir) / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out = tempfile.TemporaryFile(dir=tmp_dir)
    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for kind in (*B.DOC_KINDS, "ao_ui"):
                d = bdir / kind
                if not d.is_dir():
                    continue
                for p in sorted(d.iterdir()):
                    if p.is_file() and not p.name.startswith(".") and p.stem in wanted:
                        ctype = zipfile.ZIP_STORED if p.suffix.lower() in _STORED_EXTS else zipfile.ZIP_DEFLATED
                        zf.write(p, arcname=f"{kind}/{p.name}", compress_type=ctype)
    except BaseException:
        out.close()
        raise
    out.seek(0)
    return out


_OX = {True: "O", False: "X", None: ""}


def _cell_val(v) -> str:
    return "" if v is None else ILLEGAL_CHARACTERS_RE.sub("", str(v))  # OCR 값의 제어문자는 xlsx에 쓸 수 없다


def export_golden_xlsx(data_dir: Path, bundle_id: str, doc_id: str | None = None, scope: str = "enabled") -> bytes:
    doc_ids = B.scope_doc_ids(data_dir, bundle_id, scope) if doc_id is None else [doc_id]

    wb = Workbook()
    ws_summary = wb.active
    ws_summary.title = "요약"
    ws_summary.append(["id", "doc_type", "AO 분류", "H 분류", "검수상태",
                        "AO MATCH", "AO MISMATCH", "AO MISSING", "AO EXTRA", "AO TYPE_MISMATCH", "AO 정확도",
                        "H MATCH", "H MISMATCH", "H MISSING", "H EXTRA", "H TYPE_MISMATCH", "H 정확도"])
    for c in ws_summary[1]:
        c.font = Font(bold=True)

    ws_fields = wb.create_sheet("필드")
    ws_fields.append(["문서", "문서index", "구역", "그룹", "key", "value", "dtype"])
    for c in ws_fields[1]:
        c.font = Font(bold=True)

    ws_tables = wb.create_sheet("표")

    ws_compare = wb.create_sheet("비교")
    ws_compare.append(["문서", "path", "구역", "그룹/표", "행", "key", "Golden", "AO", "AO상태", "Harness", "Harness상태"])
    for c in ws_compare[1]:
        c.font = Font(bold=True)

    totals = {"ao": {"MATCH": 0, "MISMATCH": 0, "MISSING": 0, "EXTRA": 0, "TYPE_MISMATCH": 0},
              "h": {"MATCH": 0, "MISMATCH": 0, "MISSING": 0, "EXTRA": 0, "TYPE_MISMATCH": 0}}

    for did in doc_ids:
        detail = B.doc_detail(data_dir, bundle_id, did)
        ao_sc, h_sc = detail["score"]["ao"], detail["score"]["harness"]
        cls = detail["classification"]
        row = [did, detail["doc_type"], *(_OX[cls[k]] for k in ("ao", "harness")), detail["review"] or "",
               *(ao_sc.get(k) if ao_sc else "" for k in ("MATCH", "MISMATCH", "MISSING", "EXTRA", "TYPE_MISMATCH")),
               ao_sc.get("accuracy") if ao_sc else "",
               *(h_sc.get(k) if h_sc else "" for k in ("MATCH", "MISMATCH", "MISSING", "EXTRA", "TYPE_MISMATCH")),
               h_sc.get("accuracy") if h_sc else ""]
        ws_summary.append(row)
        for side, sc, ok in (("ao", ao_sc, cls["ao"]), ("h", h_sc, cls["harness"])):
            if sc and ok is not False:
                for k in ("MATCH", "MISMATCH", "MISSING", "EXTRA", "TYPE_MISMATCH"):
                    totals[side][k] += sc[k]

        golden = detail["golden"] or {}
        for doc_i, doc in enumerate(golden.get("documents") or []):
            for c in doc.get("extracted_fields") or []:
                ws_fields.append([did, doc_i, "필드", "", c.get("key"), _cell_val(c.get("value")), c.get("dtype", "")])
            for g in doc.get("extracted_groups") or []:
                for c in g.get("fields") or []:
                    ws_fields.append([did, doc_i, "그룹", g.get("key"), c.get("key"), _cell_val(c.get("value")),
                                       c.get("dtype", "")])
            for t in doc.get("extracted_tables") or []:
                headers = t.get("headers") or []
                ws_tables.append([did, t.get("key")] + headers)
                for c in ws_tables[ws_tables.max_row]:
                    c.font = Font(bold=True)
                for r in t.get("rows") or []:
                    cellmap = {c.get("key"): c for c in r}
                    ws_tables.append(["", ""] + [_cell_val((cellmap.get(h) or {}).get("value")) for h in headers])
                ws_tables.append([])

        for r in detail["compare"]:
            ws_compare.append([did, r["path"], r["area"], r["container"], r["row"], r["key"],
                                _cell_val(r["golden"]), _cell_val(r["ao"]), r["ao_status"],
                                _cell_val(r["harness"]), r["harness_status"]])
            row_idx = ws_compare.max_row
            for col_idx, status in ((9, r["ao_status"]), (11, r["harness_status"])):
                fill = _STATUS_FILL.get(status)
                if fill:
                    ws_compare.cell(row=row_idx, column=col_idx).fill = fill

    def _acc(n_match: int, total: dict) -> float | str:
        t = sum(total.values())
        return round(n_match / t, 4) if t else ""

    ws_summary.append(["합계", "", "", "", "",
                        totals["ao"]["MATCH"], totals["ao"]["MISMATCH"], totals["ao"]["MISSING"],
                        totals["ao"]["EXTRA"], totals["ao"]["TYPE_MISMATCH"], _acc(totals["ao"]["MATCH"], totals["ao"]),
                        totals["h"]["MATCH"], totals["h"]["MISMATCH"], totals["h"]["MISSING"],
                        totals["h"]["EXTRA"], totals["h"]["TYPE_MISMATCH"], _acc(totals["h"]["MATCH"], totals["h"])])
    for c in ws_summary[ws_summary.max_row]:
        c.font = Font(bold=True)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
