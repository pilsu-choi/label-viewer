"""정규화 · 정답지-AO-하네스 셀 비교 · 채점."""
from __future__ import annotations

import difflib
from functools import partial
from itertools import zip_longest
import re
import unicodedata
from typing import Any

STATUSES = ("MATCH", "MISMATCH", "MISSING", "EXTRA", "TYPE_MISMATCH")
_EMPTY_TOKENS = {"", "-", "null", "none", "[]"}
_NUM_RE = re.compile(r"-?\d+(\.\d+)?")
_DATE8_RE = re.compile(r"^\d{8}$")
_DATE_RE = re.compile(r"^(\d{4})[.\-/년](\d{1,2})[.\-/월]?(\d{1,2})일?\.?$")
# 항목명·요양기관종류는 하네스가 표준명으로 내고 정답지는 서식 원문을 적는다 — 같은 값의 인쇄 변형은 맞음(2026-10-02 결정)
_LABEL_MARKS = re.compile(r"[·・ㆍ‧,.\-()]")
_LABEL_ALIASES = {
    "치료재료료": "치료재료대", "재활및물리치료": "재활및물리치료료",
    "의원": "의원급보건기관", "의원급": "의원급보건기관", "보건기관": "의원급보건기관", "병원": "병원급",
}
_RECEIPT_ALIASES = {"계": "합계"}  # 세부내역서는 계·합계가 다른 행이다


def norm(value: Any) -> str | None:
    """None→None, 공백 제거, 전각→반각, 빈 표기 통일, 숫자/날짜 정규화."""
    if value is None:
        return None
    s = unicodedata.normalize("NFKC", str(value))
    s = re.sub(r"\s+", "", s)
    if s.lower() in _EMPTY_TOKENS:
        return ""
    date = _to_yyyymmdd(s)
    if date:
        return date
    cleaned = s.replace(",", "").replace("원", "")
    if _NUM_RE.fullmatch(cleaned):
        f = float(cleaned)
        return str(int(f)) if f == int(f) else repr(f)
    return s


def _to_yyyymmdd(s: str) -> str | None:
    if _DATE8_RE.fullmatch(s):
        return s
    m = _DATE_RE.match(s)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{int(y):04d}{int(mo):02d}{int(d):02d}"


def _is_numeric(s: str) -> bool:
    return bool(_NUM_RE.fullmatch(s))


def harness_value(cell: dict | None) -> Any:
    """하네스 값 = cell.harness.final_value 있으면 그것, 없으면 value."""
    if not cell:
        return None
    h = cell.get("harness")
    if h and "final_value" in h and h["final_value"] is not None:
        return h["final_value"]
    return cell.get("value")


def _label(s: str | None, receipt: bool) -> str | None:
    if not s:
        return s
    s = _LABEL_MARKS.sub("", s).replace("제재료", "제제료")
    return (_RECEIPT_ALIASES.get(s) if receipt else None) or _LABEL_ALIASES.get(s, s)


def cell_status(dtype: str | None, golden_val: Any, other_val: Any, key: str = "", receipt: bool = False) -> str:
    gn, on = norm(golden_val), norm(other_val)
    if key == "항목" or key.endswith("요양기관종류"):
        gn, on = _label(gn, receipt), _label(on, receipt)
    if gn == on:
        return "MATCH"
    if not gn:
        return "EXTRA" if on else "MATCH"
    if not on:
        return "MISSING"
    if (dtype or "").lower() in ("int", "float", "number") and not _is_numeric(on):
        return "TYPE_MISMATCH"
    return "MISMATCH"


class DocIndex:
    """문서 하나를 key로 찾을 수 있게 인덱싱한다. 그룹 이름이 달라도 key로 되짚는다."""

    def __init__(self, doc: dict | None, is_harness: bool = False):
        doc = doc or {}
        self.is_harness = is_harness
        self.fields: dict[str, dict] = {c.get("key"): c for c in doc.get("extracted_fields") or []}
        self.groups: dict[str, dict[str, dict]] = {}
        self.by_key: dict[str, dict] = dict(self.fields)
        for g in doc.get("extracted_groups") or []:
            cells = {c.get("key"): c for c in g.get("fields") or []}
            self.groups[g.get("key")] = cells
            for k, c in cells.items():
                self.by_key.setdefault(k, c)
        self.tables: dict[str, dict] = {t.get("key"): t for t in doc.get("extracted_tables") or []}

    def value(self, cell: dict | None) -> Any:
        return harness_value(cell) if self.is_harness else (cell or {}).get("value")

    def find(self, group: str | None, key: str) -> dict | None:
        if group is not None:
            c = self.groups.get(group, {}).get(key)
            if c is not None:
                return c
        elif key in self.fields:
            return self.fields[key]
        return self.by_key.get(key)


def _row_sig(cell_map: dict[str, dict], headers: list[str]) -> str:
    if not headers:
        return ""
    first = norm((cell_map.get(headers[0]) or {}).get("value")) or ""
    rest = "".join((norm((cell_map.get(h) or {}).get("value")) or "")[:4] for h in headers[1:])
    return first + rest


def _align(headers: list[str], grows: list[dict], orows: list[dict]) -> tuple[dict[int, int], set[int]]:
    sig_g = [_row_sig(r, headers) for r in grows]
    sig_o = [_row_sig(r, headers) for r in orows]
    g_to_o: dict[int, int] = {}
    o_extra = set(range(len(orows)))
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, sig_g, sig_o, autojunk=False).get_opcodes():
        if op in ("equal", "replace"):
            n = min(i2 - i1, j2 - j1)
            for k in range(n):
                g_to_o[i1 + k] = j1 + k
                o_extra.discard(j1 + k)
    return g_to_o, o_extra


def _token_boxes(cell: dict | None) -> list[dict]:
    boxes = []
    for region in (cell or {}).get("token_bbox") or []:
        page = region.get("page", 1)
        for box in region.get("token_bbox") or []:
            if isinstance(box, list) and len(box) == 4:
                boxes.append({"page": page, "box": box})
    return boxes


def _ui_bbox_index(doc: dict | None) -> dict[tuple[str, str, Any, str], list[dict]]:
    """AO UI field/group/table cells → compare row locator to normalized boxes."""
    result = (doc or {}).get("result") or {}
    boxes: dict[tuple[str, str, Any, str], list[dict]] = {}
    for cell in result.get("fields") or []:
        if cell.get("key"):
            boxes[("field", "", "", cell["key"])] = _token_boxes(cell)
    for group in result.get("groups") or []:
        group_key = group.get("key", "")
        for cell in group.get("fields") or []:
            key = cell.get("key", "").removeprefix(f"{group_key}.")
            if key:
                boxes[("group", group_key, "", key)] = _token_boxes(cell)
    for table in result.get("tables") or []:
        table_key = table.get("key", "")
        for row_index, row in enumerate(table.get("rows") or []):
            for cell in row:
                key = cell.get("key", "").rsplit(".", 1)[-1]
                if key:
                    boxes[("table", table_key, row_index, key)] = _token_boxes(cell)
    return boxes


def _row(doc_i: int, area: str, container: str, row: Any, key: str, dtype: str,
         gcell: dict | None, acell: dict | None, hcell: dict | None,
         ui_bbox: list[dict] | None = None, receipt: bool = False) -> dict:
    gval = (gcell or {}).get("value") if gcell is not None else None
    aval = acell.get("value") if acell is not None else None
    hval = harness_value(hcell) if hcell is not None else None
    has_golden = gcell is not None
    ao_status = cell_status(dtype, gval, aval, key, receipt) if (has_golden or acell is not None) else ""
    harness_status = cell_status(dtype, gval, hval, key, receipt) if (has_golden or hcell is not None) else ""
    if area == "table":
        path = f"documents[{doc_i}].tables[{container}].rows[{row}].cells[{key}]"
    elif area == "group":
        path = f"documents[{doc_i}].groups[{container}].fields[{key}]"
    else:
        path = f"documents[{doc_i}].fields[{key}]"
    evidence = (hcell or {}).get("harness") if hcell is not None else None
    bbox = None
    for c in (gcell, acell, hcell):
        if c and c.get("bbox"):
            bbox = c["bbox"]
            break
    bbox = bbox or ui_bbox
    return {
        "path": path, "doc": doc_i, "area": area, "container": container or "",
        "row": row if row is not None else "", "key": key, "dtype": dtype,
        "golden": gval, "ao": aval, "harness": hval,
        "ao_status": ao_status, "harness_status": harness_status,
        "evidence": evidence,
        "ao_confidence": (acell or {}).get("confidence") if acell else None,
        "bbox": bbox,
    }


def compare_doc(doc_i: int, gdoc: dict | None, adoc: dict | None, hdoc: dict | None,
                ui_doc: dict | None = None) -> list[dict]:
    """golden 이 있으면 golden 기준, 없으면 AO(없으면 harness) 구조 기준으로 비교 행을 만든다."""
    has_golden = gdoc is not None
    base = gdoc if has_golden else (adoc if adoc is not None else hdoc)
    if base is None:
        return []
    ai = DocIndex(adoc, is_harness=False)
    hi = DocIndex(hdoc, is_harness=True)
    ui_boxes = _ui_bbox_index(ui_doc)
    make_row = partial(_row, receipt=base.get("doc_type") == "진료비영수증")
    rows: list[dict] = []
    consumed_a: set[int] = set()
    consumed_h: set[int] = set()

    def take(idx: DocIndex, group: str | None, key: str, consumed: set[int]) -> dict | None:
        c = idx.find(group, key)
        if c is not None:
            consumed.add(id(c))
        return c

    for c in base.get("extracted_fields") or []:
        key, dtype = c.get("key"), c.get("dtype") or "string"
        acell = take(ai, None, key, consumed_a) if has_golden else ai.find(None, key)
        hcell = take(hi, None, key, consumed_h) if has_golden else hi.find(None, key)
        gcell = c if has_golden else None
        rows.append(make_row(doc_i, "field", "", "", key, dtype, gcell, acell, hcell,
                         ui_boxes.get(("field", "", "", key))))

    for g in base.get("extracted_groups") or []:
        gk = g.get("key")
        for c in g.get("fields") or []:
            key, dtype = c.get("key"), c.get("dtype") or "string"
            acell = take(ai, gk, key, consumed_a) if has_golden else ai.find(gk, key)
            hcell = take(hi, gk, key, consumed_h) if has_golden else hi.find(gk, key)
            gcell = c if has_golden else None
            rows.append(make_row(doc_i, "group", gk, "", key, dtype, gcell, acell, hcell,
                             ui_boxes.get(("group", gk, "", key))))

    for t in base.get("extracted_tables") or []:
        tk = t.get("key")
        headers = t.get("headers") or []
        grows = [{c.get("key"): c for c in r} for r in t.get("rows") or []]
        atable = ai.tables.get(tk)
        htable = hi.tables.get(tk)
        arows = [{c.get("key"): c for c in r} for r in (atable or {}).get("rows") or []]
        hrows = [{c.get("key"): c for c in r} for r in (htable or {}).get("rows") or []]

        if has_golden:
            # 표인데 결과에 같은 key의 스칼라 필드가 있으면 TYPE_MISMATCH
            for label, idx, tables in (("ao", ai, ai.tables), ("harness", hi, hi.tables)):
                if tk not in tables and idx.by_key.get(tk) is not None:
                    scalar = idx.by_key[tk]
                    val = harness_value(scalar) if label == "harness" else scalar.get("value")
                    r = make_row(doc_i, "table", tk, "", tk, "string", {"value": None}, None, None)
                    r[label] = val
                    r[f"{label}_status"] = "TYPE_MISMATCH"
                    rows.append(r)
            g_to_a, a_extra = _align(headers, grows, arows)
            g_to_h, h_extra = _align(headers, grows, hrows)
            for gi, grow in enumerate(grows):
                arow = arows[g_to_a[gi]] if gi in g_to_a else {}
                hrow = hrows[g_to_h[gi]] if gi in g_to_h else {}
                for col in headers:
                    gcell = grow.get(col)
                    if gcell is None:
                        continue
                    dtype = gcell.get("dtype") or "string"
                    ui_row = g_to_a.get(gi)
                    rows.append(make_row(doc_i, "table", tk, gi, col, dtype, gcell, arow.get(col), hrow.get(col),
                                     ui_boxes.get(("table", tk, ui_row, col)) if ui_row is not None else None))
            # 정답에 없는 결과 행: AO·Harness 의 k번째 추가 행을 한 줄로 묶는다
            for k, (ai_idx, hi_idx) in enumerate(zip_longest(sorted(a_extra), sorted(h_extra))):
                arow = arows[ai_idx] if ai_idx is not None else {}
                hrow = hrows[hi_idx] if hi_idx is not None else {}
                for col in dict.fromkeys([*arow, *hrow]):
                    cell = arow.get(col) or hrow.get(col)
                    rows.append(make_row(doc_i, "table", tk, f"+{len(grows) + k}", col, cell.get("dtype") or "string",
                                      None, arow.get(col), hrow.get(col),
                                      ui_boxes.get(("table", tk, ai_idx if ai_idx is not None else hi_idx, col))))
        else:
            # golden 없음: base(ao 또는 harness) 표 그대로 보여주고, 있으면 다른 쪽 값도 같은 행 index로 곁들인다
            other_rows = hrows if adoc is not None else []
            for ridx, row in enumerate(grows):
                other = other_rows[ridx] if ridx < len(other_rows) else {}
                for col in headers:
                    cell = row.get(col)
                    if cell is None:
                        continue
                    dtype = cell.get("dtype") or "string"
                    if adoc is not None:
                        rows.append(make_row(doc_i, "table", tk, ridx, col, dtype, None, cell, other.get(col),
                                         ui_boxes.get(("table", tk, ridx, col))))
                    else:
                        rows.append(make_row(doc_i, "table", tk, ridx, col, dtype, None, None, cell,
                                         ui_boxes.get(("table", tk, ridx, col))))

    if has_golden:
        # 정답에 없는 필드: key 로 AO·Harness 를 한 줄로 묶는다
        extra: dict[str, list] = {}
        for i, (idx, consumed) in enumerate(((ai, consumed_a), (hi, consumed_h))):
            cell_group = {id(c): gk for gk, cells in idx.groups.items() for c in cells.values()}
            for key, cell in idx.by_key.items():
                if id(cell) in consumed or key in idx.tables:
                    continue
                group = cell_group.get(id(cell))
                extra.setdefault(key, [group, None, None])[i + 1] = cell
        for key, (group, acell, hcell) in extra.items():
            dtype = (acell or hcell).get("dtype") or "string"
            area = "group" if group else "field"
            ui_bbox = ui_boxes.get((area, group or "", "", key))
            if ui_bbox is None and area == "field":
                ui_bbox = ui_boxes.get(("group", group or "", "", key))
            rows.append(make_row(doc_i, area, group or "", "", key, dtype, None, acell, hcell, ui_bbox))

    return rows


def compare_bundle(golden: dict | None, ao: dict | None, harness: dict | None,
                   ao_ui: dict | None = None) -> list[dict]:
    gdocs = (golden or {}).get("documents") or []
    adocs = (ao or {}).get("documents") or []
    hdocs = (harness or {}).get("documents") or []
    if golden is not None:
        n = len(gdocs)
    else:
        n = max(len(adocs), len(hdocs))
    rows: list[dict] = []
    for i in range(n):
        gdoc = gdocs[i] if i < len(gdocs) and golden is not None else None
        adoc = adocs[i] if i < len(adocs) else None
        hdoc = hdocs[i] if i < len(hdocs) else None
        ui_docs = (ao_ui or {}).get("documents") or []
        ui_doc = ui_docs[i] if i < len(ui_docs) else None
        rows += compare_doc(i, gdoc, adoc, hdoc, ui_doc)
    return rows


def score(rows: list[dict], side: str) -> dict | None:
    """side = 'ao'|'harness'. golden 이 없으면(모든 status가 "") None."""
    key = f"{side}_status"
    counts = {s: 0 for s in STATUSES}
    total = 0
    for r in rows:
        st = r.get(key)
        if not st:
            continue
        counts[st] = counts.get(st, 0) + 1
        total += 1
    if total == 0:
        return None
    accuracy = counts["MATCH"] / total if total else None
    return {**counts, "total": total, "accuracy": round(accuracy, 4) if accuracy is not None else None}
