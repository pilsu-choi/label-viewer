"""정답 JSON 표본에서 문서 종류별 양식 템플릿(backend/doc_templates.json)을 만든다.

사용: python scripts/make_doc_templates.py [표본결과 경로]
문서 종류별로 문서의 50% 이상에 나타난 field/group/table key 만 남긴다.
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.doctype import DOC_TYPES, REQUIRED_FIELDS, canon  # noqa: E402

DEFAULT_SRC = "/home/pilsu/projects/mirae-assets/e2e/표본결과"
OUT = Path(__file__).resolve().parent.parent / "backend" / "doc_templates.json"


def keep(counter: Counter, n: int) -> list[str]:
    """Counter 는 첫 등장 순서를 유지한다. n 문서의 절반 이상에 나온 key 만."""
    return [k for k, c in counter.items() if c * 2 >= n]


def build(docs: list[dict], name: str) -> dict:
    n = len(docs)
    fields, groups, gfields, tables, theaders, tcount = Counter(), Counter(), {}, Counter(), {}, Counter()
    for d in docs:
        for c in d.get("extracted_fields") or []:
            fields[c["key"]] += 1
        for g in d.get("extracted_groups") or []:
            groups[g["key"]] += 1
            gf = gfields.setdefault(g["key"], Counter())
            for c in g.get("fields") or []:
                gf[c["key"]] += 1
        for t in d.get("extracted_tables") or []:
            tables[t["key"]] += 1
            th = theaders.setdefault(t["key"], Counter())
            for h in t.get("headers") or []:
                th[h] += 1
    for group, keys in REQUIRED_FIELDS.get(name, {}).items():
        gfields.setdefault(group, Counter()).update({k: n for k in keys})

    return {
        "doc_type": name,
        "extracted_fields": [{"key": k, "value": ""} for k in keep(fields, n)],
        "extracted_groups": [{"key": g, "fields": [{"key": k, "value": ""} for k in keep(gfields[g], groups[g])]}
                             for g in keep(groups, n)],
        "extracted_tables": [{"key": t, "headers": keep(theaders[t], tables[t]), "rows": []} for t in keep(tables, n)],
    }


def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC)
    by_type: dict[str, list[dict]] = {}
    for p in sorted(src.glob("*/*.answer.json")):
        for d in json.loads(p.read_text(encoding="utf-8")).get("documents") or []:
            name = canon(d.get("doc_type")) or canon(p.parent.name)
            if name:
                by_type.setdefault(name, []).append(d)
    out = {name: build(by_type[name], name) for name in DOC_TYPES if name in by_type}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, t in out.items():
        print(name, len(by_type[name]), "docs:", len(t["extracted_fields"]), "fields,",
              len(t["extracted_groups"]), "groups,", len(t["extracted_tables"]), "tables")


if __name__ == "__main__":
    main()
