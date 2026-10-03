"""업로드 분류 · 저장 구조 · 번들/문서 조회 · Golden Set 생성/저장 · 이미지 변환."""
from __future__ import annotations

import copy
import contextvars
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import time
import unicodedata
import zipfile
import zlib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, BinaryIO, Callable

from PIL import Image, ImageOps, ImageSequence

from .compare import compare_bundle, harness_value, score
from . import db as DB
from .doctype import DOC_TYPES, apply_template, canon, classified, label
from .golden_history import archive_snapshot, golden_revision, list_snapshots, read_snapshot

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

_HELD_LIFECYCLE_LOCKS: contextvars.ContextVar[dict[tuple[str, str], str]] = contextvars.ContextVar(
    "label_viewer_lifecycle_locks", default={}
)


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


def _safe_upload_doc_id(relpath: str) -> str:
    doc_id = _safe_id(stem_of(relpath), "doc_id")
    # ZIP entries can contain Windows drive-prefixed names even on POSIX.
    if PureWindowsPath(doc_id).drive:
        raise ApiError(400, f"invalid doc_id: {doc_id!r}")
    return doc_id


def _storable_kind(relpath: str) -> str | None:
    kind = classify(relpath)
    if kind is None:
        return None
    ext = Path(relpath).suffix.lower()
    if ext not in ({".json"} if kind in JSON_KINDS else IMAGE_EXTS):
        return None
    _safe_upload_doc_id(relpath)
    return kind


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
# 문서 요약은 작고 번들 화면마다 전부 쓰인다. 파싱 JSON 캐시와 나눠야 수천 건 번들에서 서로 밀어내지 않는다
_SUM_MEMO: dict = {}
_SUM_MEMO_MAX = 50_000
_BUNDLE_SUMMARY_MEMO: dict[str, dict] = {}
_BUNDLE_SUMMARY_MEMO_MAX = 4096
_BUNDLE_SUMMARY_VERSION = 1  # Increment when summary counting/parsing semantics change.
_RACY_NS = 20_000_000  # mtime 이 방금 전이면 같은 tick 의 재기록을 못 알아볼 수 있어 키를 매번 다르게 한다


def _sig(p: Path) -> tuple | None:
    try:
        st = p.stat()
    except OSError:
        return None
    racy = (time.monotonic_ns(),) if time.time_ns() - st.st_mtime_ns < _RACY_NS else ()
    return (st.st_dev, st.st_ino, st.st_mtime_ns, st.st_ctime_ns, st.st_size, st.st_mode, *racy)


def _memo(key: tuple, fn: Callable[[], Any], store: dict = _MEMO, limit: int = _MEMO_MAX) -> Any:
    try:
        return store[key]
    except KeyError:
        if len(store) >= limit:
            store.clear()
        val = store[key] = fn()
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
    return f"{now:%Y%m%d-%H%M}-{secrets.token_hex(4)}"


# ── 상태 ──────────────────────────────────────────────────────────────────

def load_state(bdir: Path) -> dict:
    if DB.enabled():
        with _bundle_lifecycle_lock(bdir, shared=True):
            if not bdir.is_dir():
                raise ApiError(404, "bundle not found")
            return DB.read_bundle_state(bdir)
    p = bdir / "_state.json"
    if not p.exists():
        return {"name": bdir.name, "created_at": "", "review": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"name": bdir.name, "created_at": "", "review": {}}


def save_state(bdir: Path, state: dict) -> None:
    if DB.enabled():
        with _bundle_lifecycle_lock(bdir, shared=True):
            DB.write_bundle_state(bdir, state)
        return
    _atomic_write_json(bdir / "_state.json", state)


def update_state(bdir: Path, fn: Callable[[dict], None]) -> None:
    """_state.json 읽기-수정-쓰기. 워커가 여럿이라 파일 잠금으로 동시 변경이 서로 덮어쓰지 않게 한다."""
    if DB.enabled():
        with _bundle_lifecycle_lock(bdir, shared=True):
            if not bdir.is_dir():
                raise ApiError(404, "bundle not found")
            DB.update_bundle_state(bdir, fn)
        return
    with open(bdir / ".state.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_state(bdir)
        fn(state)
        save_state(bdir, state)


def disabled_ids(state: dict) -> set[str]:
    return set(state.get("disabled") or [])


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


_ZIP_ERRORS = (RuntimeError, zipfile.BadZipFile, zlib.error, EOFError)  # 암호·손상 항목


def _zip_entries(zf: zipfile.ZipFile) -> list[tuple[str, zipfile.ZipInfo]]:
    """항목 이름만 모은다. 내용은 _write_entries 가 하나씩 열어 복사한다."""
    out = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = _zip_name(info)
        norm = PurePosixPath(name.replace("\\", "/"))
        win = PureWindowsPath(name)
        if norm.is_absolute() or ".." in norm.parts or win.is_absolute() or win.drive:
            continue  # zip slip 방지
        out.append((name, info))
    return out


def _size(f: BinaryIO) -> int:
    f.seek(0, 2)
    n = f.tell()
    f.seek(0)
    return n


def check_upload_size(total: int, max_upload_bytes: int) -> None:
    if total > max_upload_bytes:
        raise ApiError(413, f"upload too large: {total} > {max_upload_bytes} bytes")


def process_upload(data_dir: Path, files: list[tuple[str, BinaryIO]], name: str | None,
                    max_upload_bytes: int) -> str:
    """업로드 파일 목록(zip 1개 또는 폴더식 다중 파일)을 분류해 번들을 만든다. 내용은 메모리에 올리지 않고 파일로 복사한다."""
    check_upload_size(sum(_size(f) for _, f in files), max_upload_bytes)
    if len(files) == 1 and files[0][0].lower().endswith(".zip"):
        try:
            zf = zipfile.ZipFile(files[0][1])
        except zipfile.BadZipFile:
            raise ApiError(400, "ZIP 파일을 열 수 없습니다.")
        with zf:
            entries = _zip_entries(zf)
            # Compressed upload size alone does not constrain the extracted payload.
            check_upload_size(sum(info.file_size for _, info in entries), max_upload_bytes)
            return _create_bundle(data_dir, name or Path(files[0][0]).stem, entries, zf.open)
    return _create_bundle(data_dir, name or (PurePosixPath(files[0][0]).parts[0] if files and len(files[0][0].split("/")) > 1
                                              else "bundle"), files)


def _create_bundle(data_dir: Path, bundle_name: str, entries: list[tuple[str, Any]],
                   open_src: Callable[[Any], BinaryIO] = lambda f: f) -> str:
    # macOS NFD 파일명을 NFC로 맞춰 폴더 키 인식과 다른 출처 파일과의 문서 매칭을 보장한다
    entries = [(unicodedata.normalize("NFC", relpath), src) for relpath, src in entries]
    kinds = {_storable_kind(relpath) for relpath, _ in entries}
    if not kinds.intersection(DOC_KINDS):
        if "ao_ui" in kinds:
            raise ApiError(400, "AO UI sidecar만으로는 문서를 만들 수 없습니다. 원본 이미지 또는 AO 추출 JSON을 함께 업로드하세요.")
        raise ApiError(400, "업로드에서 인식 가능한 문서 파일을 찾지 못했습니다.")

    bid = new_bundle_id()
    bdir = bundle_dir(data_dir, bid)
    root = bundles_root(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    with _bundle_lifecycle_lock(bdir):
        if bdir.exists():
            raise ApiError(409, "bundle id already exists")
        staging = root / f".upload-{bid}-{secrets.token_hex(4)}"
        staging.mkdir()
        metadata_saved = False
        try:
            _write_entries(staging, entries, open_src)
            state = {"name": bundle_name, "created_at": datetime.now(timezone.utc).isoformat(), "review": {}}
            if DB.enabled():
                save_state(bdir, state)
                metadata_saved = True
            else:
                save_state(staging, state)
            os.replace(staging, bdir)
        except Exception as e:  # 실패한 업로드는 번들을 남기지 않는다
            shutil.rmtree(staging, ignore_errors=True)
            if metadata_saved:
                try:
                    DB.delete_bundle(data_dir, bid)
                except Exception as cleanup_error:
                    raise RuntimeError(f"bundle publish failed and metadata cleanup failed: {cleanup_error}") from e
            if isinstance(e, OSError):
                raise ApiError(400, f"파일을 저장하지 못했습니다(파일명이 너무 길 수 있음): {e.filename or e}")
            raise
    return bid


def _write_entries(bdir: Path, entries: list[tuple[str, Any]], open_src: Callable[[Any], BinaryIO]) -> None:
    used: dict[tuple[str, str], int] = {}
    allocated: dict[str, set[str]] = {}
    # Reserve every literal source stem first. Otherwise a duplicate ``doc``
    # can be assigned ``doc~2`` and overwrite a distinct uploaded ``doc~2``.
    reserved = set()
    for relpath, _src in entries:
        kind = _storable_kind(relpath)
        if kind is not None:
            reserved.add((kind, _safe_upload_doc_id(relpath)))
    for relpath, src in entries:
        kind = _storable_kind(relpath)
        if kind is None:
            continue
        ext = Path(relpath).suffix.lower()
        doc_id = _safe_upload_doc_id(relpath)
        key = (kind, doc_id)
        n = used.get(key, 0)
        used[key] = n + 1
        kind_allocated = allocated.setdefault(kind, set())
        if n == 0:
            final_id = doc_id
        else:
            suffix = n + 1
            final_id = f"{doc_id}~{suffix}"
            while (kind, final_id) in reserved or final_id in kind_allocated:
                suffix += 1
                final_id = f"{doc_id}~{suffix}"
        if final_id in kind_allocated:
            # Distinct stems are reserved above, so this is only reachable for
            # malformed duplicate inputs after suffix allocation.
            suffix = max(n + 1, 2)
            final_id = f"{doc_id}~{suffix}"
            while (kind, final_id) in reserved or final_id in kind_allocated:
                suffix += 1
                final_id = f"{doc_id}~{suffix}"
        kind_allocated.add(final_id)
        dest = bdir / kind / f"{final_id}{ext}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open_src(src) as s, open(dest, "wb") as dst:
                shutil.copyfileobj(s, dst)
        except _ZIP_ERRORS as e:
            raise ApiError(400, f"ZIP 항목을 읽을 수 없습니다: {relpath} ({e})")


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
        raw = path.read_bytes()
    except OSError as e:
        return None, f"read error: {e}"
    return _load_json_bytes(raw, canonical)


def _load_json_bytes(raw: bytes, canonical: bool) -> tuple[dict | None, str | None]:
    try:
        try:
            source = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            source = raw.decode("cp949")
        data = json.loads(source)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, f"JSON parse error: {e}"
    docs = data.get("documents", []) if isinstance(data, dict) else None
    if not isinstance(docs, list) or not all(isinstance(d, dict) for d in docs):
        return None, "JSON 형식 오류: 최상위 객체와 documents 객체 목록이 필요합니다"
    if canonical:
        try:
            data = canonical_doc(data)
            _validate_golden(data, set_defaults=False)
        except ApiError as e:
            return None, f"JSON 형식 오류: {e.message}"
        except (AttributeError, KeyError, TypeError, ValueError) as e:
            return None, f"JSON 형식 오류: {e}"
    return data, None


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


def _doc_detail_unlocked(data_dir: Path, bundle_id: str, doc_id: str,
                         *, state_snapshot: dict | None = None,
                         include_pages: bool = True) -> dict:
    _safe_id(doc_id, "doc_id")
    bdir = bundle_dir(data_dir, bundle_id)
    if not bdir.is_dir():
        raise ApiError(404, "bundle not found")
    ids = doc_ids(bdir)
    if doc_id not in ids:
        raise ApiError(404, "document not found")
    state = state_snapshot if state_snapshot is not None else load_state(bdir)
    paths = {k: find_kind_file(bdir, k, doc_id) for k in DOC_KINDS}
    has = {k: paths[k] is not None for k in DOC_KINDS}
    has["ao_ui"] = find_kind_file(bdir, "ao_ui", doc_id) is not None
    golden_raw = paths["golden"].read_bytes() if paths["golden"] else None

    errors = []
    parsed: dict[str, dict | None] = {}
    for k in CORE_JSON_KINDS:
        data, err = (_load_json_bytes(golden_raw, True) if k == "golden" and golden_raw is not None
                     else (None, None) if k == "golden"
                     else load_doc_json(paths[k]))
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
        "golden_revision": golden_revision(golden_raw),
        "has": has,
        "errors": errors,
        "review": (state.get("review") or {}).get(doc_id, ""),
        "enabled": doc_id not in disabled_ids(state),
        "doc_type": label(_doc_type_of(parsed["golden"], parsed["ao_extract"], parsed["harness"])),
        "doc_type_mismatch": doc_type_mismatch(parsed["harness"]),
        "doc_type_suggest": _doc_type_suggest(parsed),
        "doc_types": DOC_TYPES,
        "classification": _classification(parsed),
        "doc_type_by_source": {k: label(_doc_type_of(parsed[j]), code=True) for k, j in
                               (("golden", "golden"), ("ao", "ao_extract"), ("harness", "harness"))},
        "pages": {
            "original": page_count(paths["original"]) if paths["original"] else 0,
            "preprocessed": page_count(paths["preprocessed"]) if paths["preprocessed"] else 0,
        } if include_pages else None,
        "golden": parsed["golden"], "ao": parsed["ao_extract"], "harness": parsed["harness"],
        "compare": rows,
        "score": {"ao": score(rows, "ao") if golden_doc else None,
                  "harness": score(rows, "harness") if golden_doc else None},
        "prev": ids_sorted[idx - 1] if idx > 0 else None,
        "next": ids_sorted[idx + 1] if idx < len(ids_sorted) - 1 else None,
    }


def doc_detail(data_dir: Path, bundle_id: str, doc_id: str, *, state_snapshot: dict | None = None,
               include_pages: bool = True) -> dict:
    """Read Golden bytes and parsed content under a shared lock for a coherent revision."""
    bdir = bundle_dir(data_dir, bundle_id)
    if not bdir.is_dir():
        raise ApiError(404, "bundle not found")
    _safe_id(doc_id, "doc_id")
    with _golden_lock(bdir, doc_id, shared=True):
        return _doc_detail_unlocked(data_dir, bundle_id, doc_id, state_snapshot=state_snapshot,
                                    include_pages=include_pages)


def _doc_summary(bdir: Path, doc_id: str, rv: str) -> dict:
    """bundle_view 의 문서 한 줄 요약. 문서 파일 시그니처+검수 상태가 같으면 캐시를 쓴다."""
    paths = {k: find_kind_file(bdir, k, doc_id) for k in (*DOC_KINDS, "ao_ui")}
    return _memo(("sum", str(bdir), doc_id, rv, tuple(_sig(p) if p else None for p in paths.values())),
                 lambda: _compute_summary(paths, doc_id, rv), _SUM_MEMO, _SUM_MEMO_MAX)


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


def _aggregate(docs: list[dict]) -> dict:
    """문서 요약 목록의 건수·채점·분류 집계. 분류 오답 문서는 필드 채점에서 뺀다."""
    agg = {"ao": {"MATCH": 0, "MISMATCH": 0, "MISSING": 0, "EXTRA": 0, "TYPE_MISMATCH": 0, "total": 0},
           "harness": {"MATCH": 0, "MISMATCH": 0, "MISSING": 0, "EXTRA": 0, "TYPE_MISMATCH": 0, "total": 0}}
    cls_sum = {"ao": [0, 0], "harness": [0, 0]}  # [정답 수, 판정 문서 수]
    n_golden = n_reviewed = n_missing = n_error = 0
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

    return {
        "docs": len(docs), "golden": n_golden, "reviewed": n_reviewed,
        "pending": len(docs) - n_reviewed, "missing": n_missing, "error": n_error,
        "score": {"ao": _finish(agg["ao"]), "harness": _finish(agg["harness"])},
        "classification": {s: {"correct": c, "total": t, "accuracy": round(c / t, 4)} if t else None
                           for s, (c, t) in cls_sum.items()},
    }


def bundle_view(data_dir: Path, bundle_id: str) -> dict:
    bdir = bundle_dir(data_dir, bundle_id)
    if not bdir.is_dir():
        raise ApiError(404, "bundle not found")
    state = load_state(bdir)
    review = state.get("review") or {}
    disabled = disabled_ids(state)
    # 캐시된 요약은 고치지 않고 활성 여부만 얹은 새 dict 를 만든다
    docs = [{**_doc_summary(bdir, doc_id, review.get(doc_id, "")), "enabled": doc_id not in disabled}
            for doc_id in doc_ids(bdir)]
    return {
        "id": bundle_id, "name": state.get("name", bundle_id), "created_at": state.get("created_at", ""),
        "docs": docs,
        "summary": _aggregate(docs),
        "summary_by_scope": {"enabled": _aggregate([d for d in docs if d["enabled"]]),
                             "disabled": _aggregate([d for d in docs if not d["enabled"]])},
    }


SCOPES = ("enabled", "disabled")


def scope_doc_ids(data_dir: Path, bundle_id: str, scope: str, *,
                  state_snapshot: dict | None = None) -> list[str]:
    """내보내기 범위(활성·비활성)에 드는 문서 ID."""
    if scope not in SCOPES:
        raise ApiError(422, f"scope must be one of {SCOPES}")
    bdir = bundle_dir(data_dir, bundle_id)
    if not bdir.is_dir():
        raise ApiError(404, "bundle not found")
    state = state_snapshot if state_snapshot is not None else load_state(bdir)
    disabled = disabled_ids(state)
    return [d for d in doc_ids(bdir) if (d in disabled) == (scope == "disabled")]


def _bundle_manifest(bdir: Path) -> tuple[str, list[str], list[str], dict[str, dict]]:
    """Cheap cross-process fingerprint plus per-document JSON fingerprints."""
    inventory = []
    file_signatures: dict[str, dict[str, list[int] | None]] = {}
    ids_set: set[str] = set()
    for kind in (*DOC_KINDS, "ao_ui"):
        directory = bdir / kind
        try:
            with os.scandir(directory) as entries:
                for entry in sorted((e for e in entries if not e.name.startswith(".")), key=lambda e: e.name):
                    try:
                        st = entry.stat(follow_symlinks=True)
                        sig = [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_mode]
                        if time.time_ns() - st.st_mtime_ns < _RACY_NS:
                            sig.append(time.monotonic_ns())
                    except OSError:
                        sig = None
                    inventory.append([kind, entry.name, sig])
                    file_signatures.setdefault(kind, {})[entry.name] = sig
                    if kind in DOC_KINDS:
                        ids_set.add(Path(entry.name).stem)
        except OSError:
            continue

    ids = sorted(ids_set, key=_natural_key)
    golden_files = file_signatures.get("golden", {})
    golden_ids = [doc_id for doc_id in ids if f"{doc_id}.json" in golden_files]
    doc_fingerprints: dict[str, dict] = {}
    for doc_id in ids:
        doc_signatures = {}
        for kind in (*CORE_JSON_KINDS, "ao_ui"):
            doc_signatures[kind] = file_signatures.get(kind, {}).get(f"{doc_id}.json")
        doc_fingerprints[doc_id] = doc_signatures
    encoded = json.dumps([_BUNDLE_SUMMARY_VERSION, inventory], ensure_ascii=False,
                        separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), ids, golden_ids, doc_fingerprints


def _doc_has_json_error(bdir: Path, doc_id: str) -> bool:
    for kind in (*CORE_JSON_KINDS, "ao_ui"):
        if load_json_safe(find_kind_file(bdir, kind, doc_id))[1]:
            return True
    return False


def _bundle_file_counts(bdir: Path, manifest: tuple[str, list[str], list[str], dict[str, dict]],
                        previous: dict | None = None) -> dict:
    _fingerprint, ids, golden_ids, doc_fingerprints = manifest
    previous = previous or {}
    if previous.get("version") != _BUNDLE_SUMMARY_VERSION:
        previous = {}
    old_fingerprints = previous.get("doc_fingerprints") or {}
    old_errors = set(previous.get("error_ids") or [])
    error_ids = []
    for doc_id in ids:
        if old_fingerprints.get(doc_id) == doc_fingerprints[doc_id]:
            has_error = doc_id in old_errors
        else:
            has_error = _doc_has_json_error(bdir, doc_id)
        if has_error:
            error_ids.append(doc_id)
    return {"version": _BUNDLE_SUMMARY_VERSION, "doc_ids": ids, "golden_ids": golden_ids,
            "doc_fingerprints": doc_fingerprints, "error_ids": error_ids}


def _public_bundle_counts(summary: dict, review: dict) -> dict:
    ids = summary.get("doc_ids") or []
    return {"docs": len(ids), "golden": len(summary.get("golden_ids") or []),
            "reviewed": sum(review.get(doc_id) == "done" for doc_id in ids),
            "error": len(summary.get("error_ids") or [])}


def _bundle_metadata(data_dir: Path, *, query: str, sort: str,
                     offset: int = 0, limit: int | None = None) -> tuple[int, int, list[dict]]:
    if sort not in ("newest", "oldest", "name"):
        raise ApiError(422, "sort must be one of newest, oldest, name")
    if DB.enabled():
        return DB.list_bundle_metadata(data_dir, query=query, sort=sort, offset=offset, limit=limit)
    root = bundles_root(data_dir)
    records = []
    if root.is_dir():
        for bdir in root.iterdir():
            if not bdir.is_dir() or bdir.name.startswith("."):
                continue
            with _bundle_lifecycle_lock(bdir, shared=True):
                if not bdir.is_dir():
                    continue
                state = load_state(bdir)
                records.append({"id": bdir.name, "name": state.get("name", bdir.name),
                                "created_at": state.get("created_at", ""),
                                "review": state.get("review") or {}})
    total = len(records)
    needle = str(query or "").lower()
    if needle:
        records = [r for r in records if needle in (r["name"] or "").lower()
                   or needle in r["id"].lower()]
    filtered_total = len(records)
    if sort == "newest":
        records.sort(key=lambda r: r["id"])
        records.sort(key=lambda r: r["created_at"], reverse=True)
    elif sort == "oldest":
        records.sort(key=lambda r: (r["created_at"], r["id"]))
    else:
        records.sort(key=lambda r: (r["name"].lower(), r["name"], r["id"]))
    return total, filtered_total, records[offset:offset + limit if limit is not None else None]


def _cached_bundle_counts(data_dir: Path, record: dict, cached: dict | None) -> tuple[dict, dict | None]:
    bdir = bundle_dir(data_dir, record["id"])
    if not bdir.is_dir():
        return {}, None
    previous = cached or _BUNDLE_SUMMARY_MEMO.get(str(bdir))
    computed = None
    for attempt in range(2):
        with _bundle_lifecycle_lock(bdir, shared=True):
            if not bdir.is_dir():
                return {}, None
            manifest = _bundle_manifest(bdir)
            fingerprint = manifest[0]
            if previous and previous.get("fingerprint") == fingerprint:
                summary = previous["counts"]
                next_cache = previous
            else:
                summary = _bundle_file_counts(bdir, manifest, (previous or {}).get("counts"))
                computed = {"fingerprint": fingerprint, "counts": summary}
                verified = _bundle_manifest(bdir)[0]
                if verified == fingerprint:
                    next_cache = computed
                    # Keep the write under the lifecycle guard so exclusive deletion
                    # cannot race it; a concurrent file change invalidates next time.
                    if DB.enabled():
                        DB.save_bundle_summaries(data_dir, {record["id"]: next_cache})
                else:
                    previous = computed
                    if attempt == 0:
                        continue
                    next_cache = None  # Do not publish a summary built during concurrent file edits.
            counts = _public_bundle_counts(summary, record.get("review") or {})
            return counts, next_cache
    return _public_bundle_counts((computed or {}).get("counts") or {}, record.get("review") or {}), None


def _finish_bundle_records(data_dir: Path, records: list[dict]) -> list[dict]:
    if not records:
        return []
    ids = [record["id"] for record in records]
    cached = DB.get_bundle_summaries(data_dir, ids) if DB.enabled() else {}
    output = []
    for record in records:
        bdir = bundle_dir(data_dir, record["id"])
        if not bdir.is_dir():
            continue
        counts, next_cache = _cached_bundle_counts(data_dir, record, cached.get(record["id"]))
        if not counts and not bdir.is_dir():
            continue
        output.append({"id": record["id"], "name": record["name"],
                       "created_at": record["created_at"], "counts": counts})
        if next_cache is not None:
            if not DB.enabled():
                if len(_BUNDLE_SUMMARY_MEMO) >= _BUNDLE_SUMMARY_MEMO_MAX:
                    _BUNDLE_SUMMARY_MEMO.clear()
                _BUNDLE_SUMMARY_MEMO[str(bdir)] = next_cache
    return output


def list_bundles(data_dir: Path, *, limit: int | None = None) -> list[dict]:
    if limit is not None:
        limit = max(0, int(limit))
    _total, _filtered_total, records = _bundle_metadata(
        data_dir, query="", sort="newest", offset=0, limit=limit)
    return _finish_bundle_records(data_dir, records)


def bundle_page(data_dir: Path, *, query: str = "", sort: str = "newest",
                page: int = 1, page_size: int = 50) -> dict:
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 100))
    offset = (page - 1) * page_size
    total, filtered_total, records = _bundle_metadata(
        data_dir, query=query, sort=sort, offset=offset, limit=page_size)
    last_page = max(1, (filtered_total + page_size - 1) // page_size)
    if page > last_page:
        page = last_page
        offset = (page - 1) * page_size
        total, filtered_total, records = _bundle_metadata(
            data_dir, query=query, sort=sort, offset=offset, limit=page_size)
    items = _finish_bundle_records(data_dir, records)
    return {"items": items, "total": total, "filtered_total": filtered_total,
            "page": page, "page_size": page_size}


@contextmanager
def _bundle_lifecycle_lock(bdir: Path, shared: bool = False):
    data_dir = bdir.parent.parent
    key = (DB.namespace(data_dir), bdir.name)
    held = _HELD_LIFECYCLE_LOCKS.get()
    current_mode = held.get(key)
    if current_mode is not None:
        if current_mode == "shared" and not shared:
            raise RuntimeError("bundle lifecycle lock cannot be upgraded from shared to exclusive")
        token = _HELD_LIFECYCLE_LOCKS.set(held)
        try:
            yield
        finally:
            _HELD_LIFECYCLE_LOCKS.reset(token)
        return

    mode = "shared" if shared else "exclusive"
    token = None
    if DB.enabled():
        with DB.session_lock(data_dir, f"bundle-lifecycle:{bdir.name}", shared=shared) as acquired:
            if not acquired:
                raise ApiError(409, "bundle is busy")
            token = _HELD_LIFECYCLE_LOCKS.set({**held, key: mode})
            try:
                yield
            finally:
                _HELD_LIFECYCLE_LOCKS.reset(token)
        return
    with open(bdir.parent / f".{bdir.name}.lifecycle.lock", "a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        token = _HELD_LIFECYCLE_LOCKS.set({**held, key: mode})
        try:
            yield
        finally:
            _HELD_LIFECYCLE_LOCKS.reset(token)


def delete_bundle(data_dir: Path, bundle_id: str) -> None:
    bdir = bundle_dir(data_dir, bundle_id)
    if not bdir.is_dir():
        raise ApiError(404, "bundle not found")
    with _bundle_lifecycle_lock(bdir):
        if not bdir.is_dir():
            raise ApiError(404, "bundle not found")
        if DB.enabled():
            tombstone = bdir.with_name(f".{bundle_id}.deleting-{secrets.token_hex(4)}")
            os.replace(bdir, tombstone)
            try:
                DB.delete_bundle(data_dir, bundle_id)
            except Exception:
                if tombstone.exists() and not bdir.exists():
                    os.replace(tombstone, bdir)
                raise
            shutil.rmtree(tombstone, ignore_errors=True)
        else:
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


def _current_golden_path(bdir: Path, doc_id: str) -> Path:
    return find_kind_file(bdir, "golden", doc_id) or golden_path(bdir, doc_id)


def _require_doc(bdir: Path, doc_id: str) -> None:
    if not bdir.is_dir():
        raise ApiError(404, "bundle not found")
    if doc_id not in doc_ids(bdir):
        raise ApiError(404, "document not found")


def _require_history_doc(bdir: Path, doc_id: str) -> None:
    """A golden-only document can disappear from doc_ids after deletion; its history remains addressable."""
    if not bdir.is_dir():
        raise ApiError(404, "bundle not found")
    if doc_id not in doc_ids(bdir) and not list_snapshots(bdir, doc_id, limit=1):
        raise ApiError(404, "document not found")


@contextmanager
def _golden_lock(bdir: Path, doc_id: str, shared: bool = False):
    with _bundle_lifecycle_lock(bdir, shared=True):
        if not bdir.is_dir():
            raise ApiError(404, "bundle not found")
        path: Path | None = None
        before: bytes | None = None

        def capture() -> None:
            nonlocal path, before
            path = _current_golden_path(bdir, doc_id)
            before = path.read_bytes() if not shared and path.exists() else None

        def rollback() -> None:
            if shared or path is None:
                return
            current = path.read_bytes() if path.exists() else None
            if current != before:
                if before is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_write_bytes(path, before)

        if DB.enabled():
            resource = f"golden:{bdir.name}:{doc_id}"
            # Session locks outlive the DB transaction and keep rollback protected
            # from both another writer and bundle deletion.
            with DB.session_lock(bdir.parent.parent, resource, shared=shared) as acquired:
                if not acquired:
                    raise ApiError(409, "golden is busy")
                capture()
                try:
                    with DB.connection():
                        yield path, before
                except BaseException:
                    rollback()
                    raise
        else:
            lock_name = hashlib.sha256(doc_id.encode("utf-8")).hexdigest()
            with open(bdir / f".golden-{lock_name}.lock", "a") as lock_file:
                fcntl.flock(lock_file, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
                capture()
                try:
                    yield path, before
                except BaseException:
                    rollback()
                    raise


def _check_golden_revision(raw: bytes | None, expected_revision: str | None) -> None:
    if expected_revision is not None and expected_revision != golden_revision(raw):
        raise ApiError(409, "golden revision conflict")


def _archive_baseline_if_needed(bdir: Path, doc_id: str, raw: bytes | None) -> None:
    if not list_snapshots(bdir, doc_id, limit=1):
        archive_snapshot(bdir, doc_id, raw, "baseline")


def create_golden(data_dir: Path, bundle_id: str, doc_id: str, source: str, doc_type: str | None = None,
                  expected_revision: str | None = None) -> dict:
    bdir = bundle_dir(data_dir, bundle_id)
    _safe_id(doc_id, "doc_id")
    _require_doc(bdir, doc_id)
    with _golden_lock(bdir, doc_id) as (gpath, before):
        _require_doc(bdir, doc_id)
        _check_golden_revision(before, expected_revision)
        if before is not None:
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
            docs = data.setdefault("documents", [])
            if not docs:
                docs.append(copy.deepcopy(EMPTY_GOLDEN["documents"][0]))
            if canon(docs[0].get("doc_type")) != name:
                docs[0] = apply_template(docs[0], name)
            else:
                docs[0]["doc_type"] = name
        _archive_baseline_if_needed(bdir, doc_id, before)
        _atomic_write_json(gpath, data)
        try:
            result = _doc_detail_unlocked(data_dir, bundle_id, doc_id)
            archive_snapshot(bdir, doc_id, gpath.read_bytes(), "create")
        except Exception:
            gpath.unlink(missing_ok=True)
            raise
    return result


def _validate_golden(data: Any, set_defaults: bool = True) -> None:
    if not isinstance(data, dict) or not isinstance(data.get("documents"), list):
        raise ApiError(422, "golden must have a 'documents' list")
    for doc in data["documents"]:
        if not isinstance(doc, dict):
            raise ApiError(422, "each document must be an object")
        if doc.get("doc_type") is not None and not isinstance(doc.get("doc_type"), str):
            raise ApiError(422, "doc_type must be a string")

        def records(value: Any, path: str) -> list:
            if value is None:
                return []
            if not isinstance(value, list):
                raise ApiError(422, f"{path} must be a list")
            return value

        def key_of(value: Any, path: str) -> str:
            if not isinstance(value, dict) or not isinstance(value.get("key"), str):
                raise ApiError(422, f"{path} must be an object with a string 'key'")
            return value["key"]

        def validate_cell(cell: Any, path: str) -> None:
            key_of(cell, path)
            dtype = cell.get("dtype")
            if dtype is None:
                if set_defaults:
                    cell["dtype"] = "string"
            elif not isinstance(dtype, str):
                raise ApiError(422, f"{path}.dtype must be a string")

        for i, cell in enumerate(records(doc.get("extracted_fields"), "extracted_fields")):
            validate_cell(cell, f"extracted_fields[{i}]")
        for i, group in enumerate(records(doc.get("extracted_groups"), "extracted_groups")):
            key_of(group, f"extracted_groups[{i}]")
            for j, cell in enumerate(records(group.get("fields"), f"extracted_groups[{i}].fields")):
                validate_cell(cell, f"extracted_groups[{i}].fields[{j}]")
        for i, table in enumerate(records(doc.get("extracted_tables"), "extracted_tables")):
            key_of(table, f"extracted_tables[{i}]")
            headers = records(table.get("headers"), f"extracted_tables[{i}].headers")
            if not all(isinstance(header, str) for header in headers):
                raise ApiError(422, f"extracted_tables[{i}].headers must contain strings")
            for j, row in enumerate(records(table.get("rows"), f"extracted_tables[{i}].rows")):
                if not isinstance(row, list):
                    raise ApiError(422, f"extracted_tables[{i}].rows[{j}] must be a list")
                for k, cell in enumerate(row):
                    validate_cell(cell, f"extracted_tables[{i}].rows[{j}][{k}]")


def save_golden(data_dir: Path, bundle_id: str, doc_id: str, data: Any,
                expected_revision: str | None = None) -> dict:
    _validate_golden(data)
    bdir = bundle_dir(data_dir, bundle_id)
    _safe_id(doc_id, "doc_id")
    _require_doc(bdir, doc_id)
    with _golden_lock(bdir, doc_id) as (p, before):
        _require_doc(bdir, doc_id)
        _check_golden_revision(before, expected_revision)
        _archive_baseline_if_needed(bdir, doc_id, before)
        _atomic_write_json(p, data)
        try:
            result = _doc_detail_unlocked(data_dir, bundle_id, doc_id)
            archive_snapshot(bdir, doc_id, p.read_bytes(), "save")
        except Exception:
            if before is None:
                p.unlink(missing_ok=True)
            else:
                _atomic_write_bytes(p, before)
            raise
        result = _doc_detail_unlocked(data_dir, bundle_id, doc_id)
    return result


def delete_golden(data_dir: Path, bundle_id: str, doc_id: str,
                  expected_revision: str | None = None) -> None:
    bdir = bundle_dir(data_dir, bundle_id)
    _safe_id(doc_id, "doc_id")
    _require_doc(bdir, doc_id)
    with _golden_lock(bdir, doc_id) as (p, before):
        _require_doc(bdir, doc_id)
        _check_golden_revision(before, expected_revision)
        if before is not None:
            _archive_baseline_if_needed(bdir, doc_id, before)
            p.unlink()
            try:
                archive_snapshot(bdir, doc_id, None, "delete")
            except Exception:
                _atomic_write_bytes(p, before)
                raise


def list_golden_history(data_dir: Path, bundle_id: str, doc_id: str, limit: int = 100,
                        before: str | None = None) -> dict:
    bdir = bundle_dir(data_dir, bundle_id)
    _safe_id(doc_id, "doc_id")
    with _golden_lock(bdir, doc_id, shared=True):
        _require_history_doc(bdir, doc_id)
        items = list_snapshots(bdir, doc_id, limit, before)
        current_path = _current_golden_path(bdir, doc_id)
        raw = current_path.read_bytes() if current_path.exists() else None
    return {"items": items, "next_cursor": items[-1]["id"] if len(items) == max(1, min(int(limit), 500)) else None,
            "golden_revision": golden_revision(raw)}


def get_golden_history(data_dir: Path, bundle_id: str, doc_id: str, history_id: str) -> dict:
    bdir = bundle_dir(data_dir, bundle_id)
    _safe_id(doc_id, "doc_id")
    with _golden_lock(bdir, doc_id, shared=True):
        _require_history_doc(bdir, doc_id)
        snapshot = read_snapshot(bdir, doc_id, history_id)
        if snapshot is None:
            raise ApiError(404, "golden history entry not found")
        metadata, raw = snapshot
        if raw is None:
            golden = None
        else:
            golden, err = _load_json_bytes(raw, True)
            if golden is None:
                raise ApiError(422, f"golden history snapshot is invalid: {err or 'invalid JSON'}")
        return {**metadata, "golden": golden}


def restore_golden(data_dir: Path, bundle_id: str, doc_id: str, history_id: str,
                   expected_revision: str) -> dict:
    bdir = bundle_dir(data_dir, bundle_id)
    _safe_id(doc_id, "doc_id")
    with _golden_lock(bdir, doc_id) as (p, before):
        _require_history_doc(bdir, doc_id)
        snapshot = read_snapshot(bdir, doc_id, history_id)
        if snapshot is None:
            raise ApiError(404, "golden history entry not found")
        _, restore_raw = snapshot
        if restore_raw is not None:
            restored_data, err = _load_json_bytes(restore_raw, True)
            if restored_data is None:
                raise ApiError(422, f"golden history snapshot is invalid: {err or 'invalid JSON'}")
        _check_golden_revision(before, expected_revision)
        _archive_baseline_if_needed(bdir, doc_id, before)
        if restore_raw is None:
            p.unlink(missing_ok=True)
        else:
            _atomic_write_bytes(p, restore_raw)
        try:
            if doc_id in doc_ids(bdir):
                result = _doc_detail_unlocked(data_dir, bundle_id, doc_id)
            else:
                result = {"id": doc_id, "golden_revision": golden_revision(None),
                          "has": {kind: False for kind in (*DOC_KINDS, "ao_ui")},
                          "golden": None}
            archive_snapshot(bdir, doc_id, restore_raw, "restore")
        except Exception:
            if before is None:
                p.unlink(missing_ok=True)
            else:
                _atomic_write_bytes(p, before)
            raise
    return result


def set_review(data_dir: Path, bundle_id: str, doc_id: str, review: str) -> None:
    if review not in ("done", "progress", ""):
        raise ApiError(422, "invalid review status")
    bdir = bundle_dir(data_dir, bundle_id)
    if doc_id not in doc_ids(bdir):
        raise ApiError(404, "document not found")


    def apply(state: dict) -> None:
        state.setdefault("review", {})
        if review:
            state["review"][doc_id] = review
        else:
            state["review"].pop(doc_id, None)
    update_state(bdir, apply)


def set_enabled(data_dir: Path, bundle_id: str, ids: Any, enabled: Any) -> None:
    """여러 문서의 활성 여부를 한 번에 바꾼다. 기본은 활성이라 비활성 문서 ID만 저장한다."""
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids) or not isinstance(enabled, bool):
        raise ApiError(422, "ids(list of str) and enabled(bool) required")
    bdir = bundle_dir(data_dir, bundle_id)
    if not bdir.is_dir():
        raise ApiError(404, "bundle not found")
    unknown = set(ids) - set(doc_ids(bdir))
    if unknown:
        raise ApiError(404, f"document not found: {sorted(unknown)[:5]}")

    def apply(state: dict) -> None:
        disabled = disabled_ids(state)
        disabled = disabled - set(ids) if enabled else disabled | set(ids)
        state["disabled"] = sorted(disabled, key=_natural_key)
    update_state(bdir, apply)


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
    source_stat = src.stat()
    source_sig = f"{source_stat.st_ino:x}-{source_stat.st_mtime_ns:x}-{source_stat.st_size:x}"
    if w is None:
        cached = cdir / f"{doc_id}.p{page}.{source_sig}.png"
    else:
        w = max(64, min(w, 1600))
        cached = cdir / f"{doc_id}.p{page}.{source_sig}.w{w}.jpg"
    if not cached.exists():
        tmp = cached.with_name(f".{secrets.token_hex(4)}{cached.name}")  # 워커 간 동시 생성에도 반쪽 파일이 보이지 않게
        try:
            with Image.open(src) as im:
                if ext in (".tif", ".tiff"):
                    im.seek(page - 1)
                im = ImageOps.exif_transpose(im).convert("RGB")
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
