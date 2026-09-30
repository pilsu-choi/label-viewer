"""업로드 분류 · 저장 구조 · 번들/문서 조회 · Golden Set 생성/저장 · 이미지 변환."""
from __future__ import annotations

import copy
import json
import os
import re
import secrets
import shutil
import time
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Callable

from PIL import Image, ImageSequence

from .compare import compare_bundle, harness_value, score
from .doctype import DOC_TYPES, apply_template, canon, classified, label

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
JSON_KINDS = ("ao_extract", "harness", "golden", "ao_ui")
CORE_JSON_KINDS = ("ao_extract", "harness", "golden")
DOC_KINDS = ("original", "preprocessed", "ao_extract", "harness", "golden")

_FOLDER_KEYS: dict[str, set[str]] = {
    "ao_ui": {"ao_ui", "aiocr_ui"},
    "golden": {"golden", "answer", "answers", "정답", "정답지"},
    "harness": {"harness", "하네스"},
    "ao_extract": {"ao_extract", "ao", "aiocr", "extract"},
    "preprocessed": {"preprocessed", "pre", "processed", "전처리"},
    "original": {"original", "origin", "원본", "images"},
}
_KIND_ORDER = ["golden", "harness", "ao_ui", "ao_extract", "preprocessed", "original"]
_SUFFIX_KEYS: dict[str, tuple[str, ...]] = {
    "ao_ui": (".aiocr.ui.json",),
    "golden": (".answer.json", ".golden.json"),
    "harness": (".harness.json",),
    "ao_extract": (".aiocr.json", ".ao.json"),
}
_STRIP_EXT = IMAGE_EXTS | {".json"}
_STRIP_SUFFIX = {".answer", ".golden", ".harness", ".aiocr", ".ao", ".ui", ".draft"}
_PAGE_RE = re.compile(r"\.p\d+$", re.I)
_ID_RE = re.compile(r"^[^/\\\x00-\x1f]+$")  # 파일명에서 온 ID(한글·공백·괄호 포함). 경로 구분자·제어문자만 막는다


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def classify(relpath: str) -> str | None:
    """상대 경로에서 kind 를 정한다. 분류 안 되면 None(무시)."""
    parts = PurePosixPath(relpath.replace("\\", "/"))
    name = parts.name
    if name.startswith(".") or any(p == "__MACOSX" for p in parts.parts):
        return None
    low = name.lower()
    dirs = [p.lower() for p in parts.parts[:-1]]
    for kind in _KIND_ORDER:
        if any(d in _FOLDER_KEYS[kind] for d in dirs):
            return kind
    for kind, suffixes in _SUFFIX_KEYS.items():
        if any(low.endswith(s) for s in suffixes):
            return kind
    if Path(name).suffix.lower() in IMAGE_EXTS:
        return "original"
    return None


def stem_of(filename: str) -> str:
    """파일명 → 확장자 제거 → 알려진 접미사 제거를 반복해 문서 ID를 얻는다."""
    s = PurePosixPath(filename.replace("\\", "/")).name
    while True:
        base, ext = os.path.splitext(s)
        extl = ext.lower()
        if extl in _STRIP_EXT and base:
            s = base
            continue
        if extl in _STRIP_SUFFIX and base:
            s = base
            continue
        m = _PAGE_RE.search(s)
        if m:
            s = s[:m.start()]
            continue
        break
    return s or filename


def _safe_id(value: str, what: str = "id") -> str:
    if not _ID_RE.fullmatch(value or "") or value in (".", ".."):
        raise ApiError(400, f"invalid {what}: {value!r}")
    return value


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{secrets.token_hex(4)}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _atomic_write_json(path: Path, data: Any) -> None:
    _atomic_write_bytes(path, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))


# ── 캐시 ──────────────────────────────────────────────────────────────────
# 프로세스 내 캐시. 키에 파일 (inode, mtime_ns, size) 시그니처를 넣어 원자적 교체·외부 변경(다른 워커 포함)에도 무효화된다.

_MEMO: dict = {}
_MEMO_MAX = 4096
_RACY_NS = 20_000_000  # mtime 이 방금 전이면 같은 tick 의 재기록을 못 알아볼 수 있어 키를 매번 다르게 한다


def _sig(p: Path) -> tuple | None:
    try:
        st = p.stat()
    except OSError:
        return None
    racy = (time.monotonic_ns(),) if time.time_ns() - st.st_mtime_ns < _RACY_NS else ()
    return (st.st_ino, st.st_mtime_ns, st.st_size, *racy)


def _memo(key: tuple, fn: Callable[[], Any]) -> Any:
    try:
        return _MEMO[key]
    except KeyError:
        if len(_MEMO) >= _MEMO_MAX:
            _MEMO.clear()
        val = _MEMO[key] = fn()
        return val


# ── 경로 ──────────────────────────────────────────────────────────────────

def bundles_root(data_dir: Path) -> Path:
    return data_dir / "bundles"


def cache_root(data_dir: Path) -> Path:
    return data_dir / ".cache"


def bundle_dir(data_dir: Path, bundle_id: str) -> Path:
    _safe_id(bundle_id, "bundle_id")
    d = bundles_root(data_dir) / bundle_id
    return d


def new_bundle_id() -> str:
    now = datetime.now()
    return f"{now:%Y%m%d-%H%M}-{secrets.token_hex(2)}"


# ── 상태 ──────────────────────────────────────────────────────────────────

def load_state(bdir: Path) -> dict:
    p = bdir / "_state.json"
    if not p.exists():
        return {"name": bdir.name, "created_at": "", "review": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"name": bdir.name, "created_at": "", "review": {}}


def save_state(bdir: Path, state: dict) -> None:
    _atomic_write_json(bdir / "_state.json", state)


# ── 업로드 ────────────────────────────────────────────────────────────────

def _zip_name(info: zipfile.ZipInfo) -> str:
    """UTF-8 플래그 없는 항목은 cp437로 읽히므로 원래 바이트를 UTF-8, 안 되면 CP949(Windows 압축)로 다시 읽는다."""
    if info.flag_bits & 0x800:
        return info.filename
    raw = info.filename.encode("cp437")
    for enc in ("utf-8", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return info.filename


def _iter_zip(fp: BinaryIO) -> list[tuple[str, bytes]]:
    out = []
    try:
        zf = zipfile.ZipFile(fp)
    except zipfile.BadZipFile:
        raise ApiError(400, "ZIP 파일을 열 수 없습니다.")
    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = _zip_name(info)
            norm = PurePosixPath(name)
            if norm.is_absolute() or ".." in norm.parts:
                continue  # zip slip 방지
            try:
                out.append((name, zf.read(info)))
            except (RuntimeError, zipfile.BadZipFile) as e:  # 암호·손상 항목
                raise ApiError(400, f"ZIP 항목을 읽을 수 없습니다: {name} ({e})")
    return out


def process_upload(data_dir: Path, files: list[tuple[str, bytes]], name: str | None,
                    max_upload_bytes: int) -> str:
    """업로드 파일 목록(zip 1개 또는 폴더식 다중 파일)을 분류해 번들을 만든다."""
    total = sum(len(b) for _, b in files)
    if total > max_upload_bytes:
        raise ApiError(413, f"upload too large: {total} > {max_upload_bytes} bytes")
    if len(files) == 1 and files[0][0].lower().endswith(".zip"):
        import io
        entries = _iter_zip(io.BytesIO(files[0][1]))
        bundle_name = name or Path(files[0][0]).stem
    else:
        entries = files
        bundle_name = name or (PurePosixPath(files[0][0]).parts[0] if files and len(files[0][0].split("/")) > 1
                                else "bundle")

    # macOS NFD 파일명을 NFC로 맞춰 폴더 키 인식과 다른 출처 파일과의 문서 매칭을 보장한다
    entries = [(unicodedata.normalize("NFC", relpath), data) for relpath, data in entries]
    kinds = {classify(relpath) for relpath, _ in entries}
    if not kinds.intersection(DOC_KINDS):
        if "ao_ui" in kinds:
            raise ApiError(400, "AO UI sidecar만으로는 문서를 만들 수 없습니다. 원본 이미지 또는 AO 추출 JSON을 함께 업로드하세요.")
        raise ApiError(400, "업로드에서 인식 가능한 문서 파일을 찾지 못했습니다.")

    bid = new_bundle_id()
    bdir = bundle_dir(data_dir, bid)
    bdir.mkdir(parents=True, exist_ok=True)
    try:
        _write_entries(bdir, entries)
    except OSError as e:
        shutil.rmtree(bdir, ignore_errors=True)
        raise ApiError(400, f"파일을 저장하지 못했습니다(파일명이 너무 길 수 있음): {e.filename or e}")

    save_state(bdir, {"name": bundle_name, "created_at": datetime.now(timezone.utc).isoformat(), "review": {}})
    return bid


def _write_entries(bdir: Path, entries: list[tuple[str, bytes]]) -> None:
    used: dict[tuple[str, str], int] = {}
    for relpath, data in entries:
        kind = classify(relpath)
        if kind is None:
            continue
        doc_id = stem_of(relpath)
        key = (kind, doc_id)
        n = used.get(key, 0)
        used[key] = n + 1
        final_id = doc_id if n == 0 else f"{doc_id}~{n + 1}"
        ext = Path(relpath).suffix.lower()
        if ext not in ({".json"} if kind in JSON_KINDS else IMAGE_EXTS):
            continue
        dest = bdir / kind / f"{final_id}{ext}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)


# ── 문서 조회 ─────────────────────────────────────────────────────────────

def _natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _names(d: Path) -> frozenset[str]:
    """디렉터리 파일명 집합(디렉터리 mtime 기준 캐시)."""
    sig = _sig(d)
    if sig is None:
        return frozenset()
    return _memo(("names", str(d), sig), lambda: frozenset(e.name for e in os.scandir(d) if not e.name.startswith(".")))


def find_kind_file(bdir: Path, kind: str, doc_id: str) -> Path | None:
    names = _names(bdir / kind)
    for ext in ((".json",) if kind in JSON_KINDS else IMAGE_EXTS):
        if f"{doc_id}{ext}" in names:
            return bdir / kind / f"{doc_id}{ext}"
    return None


def doc_ids(bdir: Path) -> list[str]:
    kdirs = [bdir / k for k in DOC_KINDS]
    return _memo(("ids", str(bdir), tuple(map(_sig, kdirs))),
                 lambda: sorted({Path(n).stem for d in kdirs for n in _names(d)}, key=_natural_key))


def load_json_safe(path: Path | None, canonical: bool = False) -> tuple[dict | None, str | None]:
    """JSON 로드(+검증, canonical 이면 AO/Harness 응답 변환). 결과는 캐시되므로 호출자는 수정하지 않는다."""
    sig = _sig(path) if path else None
    if sig is None:
        return None, None
    return _memo(("json", str(path), sig, canonical), lambda: _load_json(path, canonical))


def _load_json(path: Path, canonical: bool) -> tuple[dict | None, str | None]:
    try:
        data = json.loads(read_json_text(path))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, f"JSON parse error: {e}"
    except OSError as e:
        return None, f"read error: {e}"
    docs = data.get("documents", []) if isinstance(data, dict) else None
    if not isinstance(docs, list) or not all(isinstance(d, dict) for d in docs):
        return None, "JSON 형식 오류: 최상위 객체와 documents 객체 목록이 필요합니다"
    return (canonical_doc(data) if canonical else data), None


def read_json_text(path: Path) -> str:
    """UTF-8(BOM 허용), 안 되면 CP949(Windows 메모장 ANSI)로 읽는다."""
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp949")


def _ao_cell(cell: dict, prefix: str = "") -> dict:
    out = {k: v for k, v in cell.items() if k != "token_bbox"}
    key = out.get("key", "")
    if prefix and isinstance(key, str) and key.startswith(prefix):
        key = key[len(prefix):]
        if key.startswith("."):
            key = key[1:]
        out["key"] = key
    boxes = []
    for region in cell.get("token_bbox") or []:
        if not isinstance(region, dict):
            continue
        for box in region.get("token_bbox") or []:
            if isinstance(box, list) and len(box) == 4:
                boxes.append({"page": region.get("page", 1), "box": box})
    if boxes:
        out["bbox"] = boxes
    return out


def canonical_doc(data: dict | None) -> dict | None:
    """AO/Harness 실행 응답(result.fields/groups/tables) → canonical extracted_* 스키마; 업로드 파일은 그대로 둔다."""
    if isinstance(data, dict) and "documents" not in data and isinstance(data.get("result"), dict):
        data = {k: v for k, v in data.items() if k != "result"} | {"documents": [{"result": data["result"]}]}
    if not isinstance(data, dict) or not isinstance(data.get("documents"), list):
        return data
    docs = []
    converted = False
    for source in data["documents"]:
        result = source.get("result") if isinstance(source, dict) else None
        if not isinstance(result, dict) or not any(k in result for k in ("fields", "groups", "tables")):
            docs.append(source)
            continue
        converted = True
        groups = []
        for group in result.get("groups") or []:
            key = group.get("key", "")
            prefix = f"{key}." if key else ""
            groups.append({**group, "fields": [_ao_cell(c, prefix) for c in group.get("fields") or []]})
        tables = []
        for table in result.get("tables") or []:
            key = table.get("key", "")
            rows = []
            for row in table.get("rows") or []:
                cells = []
                for cell in row:
                    prefix = f"{key}["
                    normalized = _ao_cell(cell, prefix)
                    cell_key = normalized.get("key", "")
                    if isinstance(cell_key, str) and "]." in cell_key:
                        normalized["key"] = cell_key.split("].", 1)[1]
                    cells.append(normalized)
                rows.append(cells)
            tables.append({**table, "rows": rows})
        docs.append({
            **({"harness": result["harness"]} if "harness" in result else {}),
            "doc_type": result.get("doc_type") or result.get("document_type") or source.get("doc_type", ""),
            "extracted_fields": [_ao_cell(c) for c in result.get("fields") or []],
            "extracted_groups": groups,
            "extracted_tables": tables,
        })
    return {**data, "documents": docs} if converted else data


def load_doc_json(path: Path | None) -> tuple[dict | None, str | None]:
    return load_json_safe(path, True)


def _count_pages(path: Path) -> int:
    try:
        with Image.open(path) as im:
            return sum(1 for _ in ImageSequence.Iterator(im))
    except Exception:
        return 1


def page_count(path: Path) -> int:
    if path.suffix.lower() not in (".tif", ".tiff"):
        return 1
    return _memo(("pages", str(path), _sig(path)), lambda: _count_pages(path))


def _doc_type_of(*jsons: dict | None) -> str:
    for j in jsons:
        docs = (j or {}).get("documents") or []
        if docs and docs[0].get("doc_type"):
            return docs[0]["doc_type"]
    return ""


def doc_type_mismatch(harness: dict | None) -> dict | None:
    """Harness 재분류 결과 AO 양식과 제목 양식이 달라진 첫 문서를 반환한다."""
    for d in (((harness or {}).get("harness") or {}).get("reclassification") or {}).get("documents") or []:
        ao, title = d.get("ao_doc_type"), d.get("title_doc_type")
        if d.get("action") in ("reextracted", "detected") and ao and title and ao != title:
            return {"ao": ao, "title": title, "title_line": d.get("title_line") or "", "reason": d.get("reason") or ""}
    return None


def _classification(parsed: dict) -> dict:
    """Golden 대비 AO/Harness 문서 분류 일치 여부(True/False/None)."""
    return {"ao": classified(parsed["golden"], parsed["ao_extract"]),
            "harness": classified(parsed["golden"], parsed["harness"])}


def _doc_type_suggest(parsed: dict) -> str:
    """Golden 생성 기본 문서 종류: 하네스 재분류 제목 → AO → 하네스."""
    mm = doc_type_mismatch(parsed["harness"])
    for v in (mm and mm["title"], _doc_type_of(parsed["ao_extract"]), _doc_type_of(parsed["harness"])):
        if canon(v):
            return canon(v)
    return ""


def doc_detail(data_dir: Path, bundle_id: str, doc_id: str) -> dict:
    _safe_id(doc_id, "doc_id")
    bdir = bundle_dir(data_dir, bundle_id)
    if not bdir.is_dir():
        raise ApiError(404, "bundle not found")
    ids = doc_ids(bdir)
    if doc_id not in ids:
        raise ApiError(404, "document not found")
    state = load_state(bdir)
    paths = {k: find_kind_file(bdir, k, doc_id) for k in DOC_KINDS}
    has = {k: paths[k] is not None for k in DOC_KINDS}
    has["ao_ui"] = find_kind_file(bdir, "ao_ui", doc_id) is not None

    errors = []
    parsed: dict[str, dict | None] = {}
    for k in CORE_JSON_KINDS:
        data, err = load_doc_json(paths[k])
        parsed[k] = data
        if err:
            errors.append(f"{k}: {err}")
    parsed["ao_ui"], ao_ui_err = load_json_safe(find_kind_file(bdir, "ao_ui", doc_id))
    if ao_ui_err:
        errors.append(f"ao_ui: {ao_ui_err}")

    golden_doc = parsed["golden"]
    rows = compare_bundle(golden_doc, parsed["ao_extract"], parsed["harness"], parsed["ao_ui"]) if golden_doc else []
    ids_sorted = ids
    idx = ids_sorted.index(doc_id)
    return {
        "id": doc_id,
        "has": has,
        "errors": errors,
        "review": (state.get("review") or {}).get(doc_id, ""),
        "doc_type": label(_doc_type_of(parsed["golden"], parsed["ao_extract"], parsed["harness"])),
        "doc_type_mismatch": doc_type_mismatch(parsed["harness"]),
        "doc_type_suggest": _doc_type_suggest(parsed),
        "doc_types": DOC_TYPES,
        "classification": _classification(parsed),
        "doc_type_by_source": {k: label(_doc_type_of(parsed[j])) for k, j in
                               (("golden", "golden"), ("ao", "ao_extract"), ("harness", "harness"))},
        "pages": {
            "original": page_count(paths["original"]) if paths["original"] else 0,
            "preprocessed": page_count(paths["preprocessed"]) if paths["preprocessed"] else 0,
        },
        "golden": parsed["golden"], "ao": parsed["ao_extract"], "harness": parsed["harness"],
        "compare": rows,
        "score": {"ao": score(rows, "ao") if golden_doc else None,
                  "harness": score(rows, "harness") if golden_doc else None},
        "prev": ids_sorted[idx - 1] if idx > 0 else None,
        "next": ids_sorted[idx + 1] if idx < len(ids_sorted) - 1 else None,
    }


def _doc_summary(bdir: Path, doc_id: str, rv: str) -> dict:
    """bundle_view 의 문서 한 줄 요약. 문서 파일 시그니처+검수 상태가 같으면 캐시를 쓴다."""
    paths = {k: find_kind_file(bdir, k, doc_id) for k in (*DOC_KINDS, "ao_ui")}
    return _memo(("sum", str(bdir), doc_id, rv, tuple(_sig(p) if p else None for p in paths.values())),
                 lambda: _compute_summary(paths, doc_id, rv))


def _compute_summary(paths: dict, doc_id: str, rv: str) -> dict:
    has = {k: paths[k] is not None for k in DOC_KINDS}
    errors = []
    parsed: dict[str, dict | None] = {}
    for k in CORE_JSON_KINDS:
        data, err = load_doc_json(paths[k])
        parsed[k] = data
        if err:
            errors.append(f"{k}: {err}")
    parsed["ao_ui"], ao_ui_err = load_json_safe(paths["ao_ui"])
    if ao_ui_err:
        errors.append(f"ao_ui: {ao_ui_err}")
    try:
        rows = compare_bundle(parsed["golden"], parsed["ao_extract"], parsed["harness"], parsed["ao_ui"]) if parsed["golden"] else []
    except Exception as e:  # 형식이 어긋난 JSON 하나가 번들 전체 조회를 막지 않게 한다
        rows, errors = [], [*errors, f"compare: {e}"]
    sc = {"ao": score(rows, "ao") if parsed["golden"] else None,
          "harness": score(rows, "harness") if parsed["golden"] else None}
    mismatch = sum(1 for r in rows if r.get("ao_status") not in ("", "MATCH") or r.get("harness_status") not in ("", "MATCH"))
    return {
        "id": doc_id, "has": has, "errors": errors, "review": rv,
        "doc_type": label(_doc_type_of(parsed["golden"], parsed["ao_extract"], parsed["harness"])),
        "doc_type_mismatch": doc_type_mismatch(parsed["harness"]),
        "classification": _classification(parsed), "score": sc, "mismatch": mismatch,
    }


def bundle_view(data_dir: Path, bundle_id: str) -> dict:
    bdir = bundle_dir(data_dir, bundle_id)
    if not bdir.is_dir():
        raise ApiError(404, "bundle not found")
    state = load_state(bdir)
    review = state.get("review") or {}
    agg = {"ao": {"MATCH": 0, "MISMATCH": 0, "MISSING": 0, "EXTRA": 0, "TYPE_MISMATCH": 0, "total": 0},
           "harness": {"MATCH": 0, "MISMATCH": 0, "MISSING": 0, "EXTRA": 0, "TYPE_MISMATCH": 0, "total": 0}}
    cls_sum = {"ao": [0, 0], "harness": [0, 0]}  # [정답 수, 판정 문서 수]
    n_golden = n_reviewed = n_missing = n_error = 0
    docs = [_doc_summary(bdir, doc_id, review.get(doc_id, "")) for doc_id in doc_ids(bdir)]
    for d in docs:
        has, cls, sc = d["has"], d["classification"], d["score"]
        for side in ("ao", "harness"):
            if cls[side] is not None:
                cls_sum[side][0] += cls[side]
                cls_sum[side][1] += 1
            if sc[side] and cls[side] is not False:
                for k in ("MATCH", "MISMATCH", "MISSING", "EXTRA", "TYPE_MISMATCH", "total"):
                    agg[side][k] += sc[side][k]
        n_golden += has["golden"]
        n_reviewed += d["review"] == "done"
        n_missing += not (has["original"] and has["ao_extract"] and has["harness"] and has["golden"])
        n_error += bool(d["errors"])

    def _finish(a: dict) -> dict | None:
        if a["total"] == 0:
            return None
        return {**a, "accuracy": round(a["MATCH"] / a["total"], 4)}

    total_docs = len(docs)
    return {
        "id": bundle_id, "name": state.get("name", bundle_id), "created_at": state.get("created_at", ""),
        "docs": docs,
        "summary": {
            "docs": total_docs, "golden": n_golden, "reviewed": n_reviewed,
            "pending": total_docs - n_reviewed, "missing": n_missing, "error": n_error,
            "score": {"ao": _finish(agg["ao"]), "harness": _finish(agg["harness"])},
            "classification": {s: {"correct": c, "total": t, "accuracy": round(c / t, 4)} if t else None
                               for s, (c, t) in cls_sum.items()},
        },
    }


def _bundle_counts(bdir: Path, review: dict) -> dict:
    ids = doc_ids(bdir)
    n_golden = n_reviewed = n_error = 0
    for doc_id in ids:
        n_golden += find_kind_file(bdir, "golden", doc_id) is not None
        n_reviewed += review.get(doc_id) == "done"
        kinds = (*CORE_JSON_KINDS, "ao_ui")
        n_error += any(load_json_safe(find_kind_file(bdir, k, doc_id))[1] for k in kinds)
    return {"docs": len(ids), "golden": n_golden, "reviewed": n_reviewed, "error": n_error}


def list_bundles(data_dir: Path) -> list[dict]:
    root = bundles_root(data_dir)
    if not root.is_dir():
        return []
    out = []
    for bdir in root.iterdir():
        if not bdir.is_dir():
            continue
        state = load_state(bdir)
        # 문서 파일 추가·삭제·교체는 kind 디렉터리 mtime 에, 검수 상태는 _state.json 에 나타난다
        sig = (*(_sig(bdir / k) for k in (*DOC_KINDS, "ao_ui")), _sig(bdir / "_state.json"))
        out.append({
            "id": bdir.name, "name": state.get("name", bdir.name), "created_at": state.get("created_at", ""),
            "counts": _memo(("counts", str(bdir), sig), lambda: _bundle_counts(bdir, state.get("review") or {})),
        })
    out.sort(key=lambda b: b["created_at"], reverse=True)
    return out


def delete_bundle(data_dir: Path, bundle_id: str) -> None:
    bdir = bundle_dir(data_dir, bundle_id)
    if not bdir.is_dir():
        raise ApiError(404, "bundle not found")
    shutil.rmtree(bdir)
    cdir = cache_root(data_dir) / bundle_id
    if cdir.is_dir():
        shutil.rmtree(cdir, ignore_errors=True)


# ── Golden Set ────────────────────────────────────────────────────────────

EMPTY_GOLDEN = {"documents": [{"doc_type": "", "extracted_fields": [], "extracted_groups": [], "extracted_tables": []}]}


def _strip_harness_blocks(cell: dict) -> None:
    if "harness" in cell:
        cell["value"] = harness_value(cell)
        del cell["harness"]


def _from_harness(hjson: dict) -> dict:
    data = copy.deepcopy(hjson)
    data.pop("harness", None)
    data.pop("meta", None)
    for doc in data.get("documents") or []:
        doc.pop("harness", None)
        for c in doc.get("extracted_fields") or []:
            _strip_harness_blocks(c)
        for g in doc.get("extracted_groups") or []:
            g.pop("harness", None)
            for c in g.get("fields") or []:
                _strip_harness_blocks(c)
        for t in doc.get("extracted_tables") or []:
            t.pop("harness", None)
            for row in t.get("rows") or []:
                for c in row:
                    _strip_harness_blocks(c)
    return data


def golden_path(bdir: Path, doc_id: str) -> Path:
    _safe_id(doc_id, "doc_id")
    return bdir / "golden" / f"{doc_id}.json"


def create_golden(data_dir: Path, bundle_id: str, doc_id: str, source: str, doc_type: str | None = None) -> dict:
    bdir = bundle_dir(data_dir, bundle_id)
    gpath = golden_path(bdir, doc_id)
    if gpath.exists():
        raise ApiError(409, "golden already exists")
    if source == "empty":
        data = copy.deepcopy(EMPTY_GOLDEN)
    elif source == "ao":
        apath = find_kind_file(bdir, "ao_extract", doc_id)
        data, err = load_doc_json(apath)
        if data is None:
            raise ApiError(404, f"ao_extract not available: {err or 'missing'}")
        data = copy.deepcopy(data)
    elif source == "harness":
        hpath = find_kind_file(bdir, "harness", doc_id)
        hdata, err = load_doc_json(hpath)
        if hdata is None:
            raise ApiError(404, f"harness not available: {err or 'missing'}")
        data = _from_harness(hdata)
    else:
        raise ApiError(422, f"invalid source: {source}")
    name = canon(doc_type)
    if name:
        docs = data.setdefault("documents", [copy.deepcopy(EMPTY_GOLDEN["documents"][0])])
        if canon(docs[0].get("doc_type")) != name:
            docs[0] = apply_template(docs[0], name)
        else:
            docs[0]["doc_type"] = name
    _atomic_write_json(gpath, data)
    return doc_detail(data_dir, bundle_id, doc_id)


def _validate_golden(data: Any) -> None:
    if not isinstance(data, dict) or not isinstance(data.get("documents"), list):
        raise ApiError(422, "golden must have a 'documents' list")
    for doc in data["documents"]:
        if not isinstance(doc, dict):
            raise ApiError(422, "each document must be an object")
        cells = [*(doc.get("extracted_fields") or []),
                 *(c for g in doc.get("extracted_groups") or [] if isinstance(g, dict) for c in g.get("fields") or []),
                 *(c for t in doc.get("extracted_tables") or [] if isinstance(t, dict)
                   for row in t.get("rows") or [] if isinstance(row, list) for c in row)]
        for c in cells:
            if not isinstance(c, dict) or "key" not in c:
                raise ApiError(422, "cell must be an object with 'key'")
            c.setdefault("dtype", "string")


def save_golden(data_dir: Path, bundle_id: str, doc_id: str, data: Any) -> dict:
    _validate_golden(data)
    bdir = bundle_dir(data_dir, bundle_id)
    _atomic_write_json(golden_path(bdir, doc_id), data)
    return doc_detail(data_dir, bundle_id, doc_id)


def delete_golden(data_dir: Path, bundle_id: str, doc_id: str) -> None:
    bdir = bundle_dir(data_dir, bundle_id)
    p = golden_path(bdir, doc_id)
    if p.exists():
        p.unlink()


def set_review(data_dir: Path, bundle_id: str, doc_id: str, review: str) -> None:
    if review not in ("done", "progress", ""):
        raise ApiError(422, "invalid review status")
    bdir = bundle_dir(data_dir, bundle_id)
    if doc_id not in doc_ids(bdir):
        raise ApiError(404, "document not found")
    state = load_state(bdir)
    state.setdefault("review", {})
    if review:
        state["review"][doc_id] = review
    else:
        state["review"].pop(doc_id, None)
    save_state(bdir, state)


# ── 이미지 ────────────────────────────────────────────────────────────────

def get_image(data_dir: Path, bundle_id: str, doc_id: str, view: str, page: int,
              w: int | None = None) -> tuple[Path, int]:
    """(반환할 파일 경로, 전체 페이지 수). w 가 있으면 폭 w(64~1600) 이하 JPEG 썸네일. 없으면 ApiError(404)."""
    if view not in ("original", "preprocessed"):
        raise ApiError(422, "invalid view")
    bdir = bundle_dir(data_dir, bundle_id)
    src = find_kind_file(bdir, view, doc_id)
    if src is None:
        raise ApiError(404, "image not found")
    n_pages = page_count(src)
    page = max(1, min(page, n_pages))
    ext = src.suffix.lower()
    if w is None and ext not in (".tif", ".tiff", ".bmp"):
        return src, n_pages

    cdir = cache_root(data_dir) / bundle_id / view
    cdir.mkdir(parents=True, exist_ok=True)
    if w is None:
        cached = cdir / f"{doc_id}.p{page}.png"
    else:
        w = max(64, min(w, 1600))
        cached = cdir / f"{doc_id}.p{page}.{src.stat().st_mtime_ns}.w{w}.jpg"
    if not cached.exists():
        tmp = cached.with_name(f".{secrets.token_hex(4)}{cached.name}")  # 워커 간 동시 생성에도 반쪽 파일이 보이지 않게
        try:
            with Image.open(src) as im:
                if ext in (".tif", ".tiff"):
                    im.seek(page - 1)
                im = im.convert("RGB")
            if w is None:
                im.save(tmp, "PNG", compress_level=1)
            else:
                im.thumbnail((w, 1 << 16))
                im.save(tmp, "JPEG", quality=80)
            os.replace(tmp, cached)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            raise ApiError(422, f"이미지를 열 수 없습니다: {e}")
    return cached, n_pages
