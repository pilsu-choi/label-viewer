"""문서 종류 정규화 · 양식 템플릿 · 분류 채점."""
from __future__ import annotations

import copy
import json
from pathlib import Path

DOC_TYPES = ["진료비영수증", "세부내역서", "약제비영수증", "진단서", "입퇴원확인서", "소견서", "수술확인서"]
AO_CODES = {
    "AC02922011": "진료비영수증", "Y000707100": "세부내역서", "Y000707300": "약제비영수증",
    "Y000701200": "진단서", "Y000701300": "입퇴원확인서", "Y000701333": "소견서", "Y00071250": "수술확인서",
}
_ALIAS = {
    **AO_CODES,
    "약제영수증": "약제비영수증", "입원확인서": "입퇴원확인서",
    "진료비세부산정내역서": "세부내역서", "진료비세부내역서": "세부내역서",
}
_TEMPLATE_FILE = Path(__file__).with_name("doc_templates.json")
TEMPLATES: dict[str, dict] = json.loads(_TEMPLATE_FILE.read_text(encoding="utf-8")) if _TEMPLATE_FILE.exists() else {}


def canon(value) -> str:
    """AO 코드/별칭/이름 → 표준 문서 종류. 비었거나 모르면 ''."""
    v = str(value or "").strip()
    v = _ALIAS.get(v, v)
    return v if v in DOC_TYPES else ""


def label(value) -> str:
    """화면 표시용 문서 종류. AO 코드면 '진료비영수증 (AC02922011)'."""
    v = str(value or "").strip()
    return f"{AO_CODES[v]} ({v})" if v in AO_CODES else v


def _first_type(data: dict | None) -> str:
    docs = (data or {}).get("documents") or []
    return canon(docs[0].get("doc_type")) if docs else ""


def classified(golden: dict | None, other: dict | None) -> bool | None:
    """Golden 대비 분류 일치 여부. 어느 쪽이든 종류를 알 수 없으면 None."""
    g, o = _first_type(golden), _first_type(other)
    return g == o if g and o else None


def apply_template(doc: dict, doc_type: str) -> dict:
    """doc_type 양식 뼈대로 바꾸되 같은 key 의 값(표는 행)을 유지한다."""
    name = canon(doc_type)
    out = copy.deepcopy(TEMPLATES[name])
    out["doc_type"] = name
    old = {c.get("key"): c for c in doc.get("extracted_fields") or []}
    for g in doc.get("extracted_groups") or []:
        old.update({c.get("key"): c for c in g.get("fields") or []})
    cells = out["extracted_fields"] + [c for g in out["extracted_groups"] for c in g["fields"]]
    for c in cells:
        if c["key"] in old:
            c["value"] = old[c["key"]].get("value", "")
    src = {t.get("key"): t for t in doc.get("extracted_tables") or []}
    for t in out["extracted_tables"]:
        if t["key"] in src:
            t["rows"] = [[c for c in row if c.get("key") in t["headers"]] for row in src[t["key"]].get("rows") or []]
    return out
