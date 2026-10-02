#!/usr/bin/env python3
"""테스트용 더미 번들 생성기. 실제 AO/하네스 응답 형태를 흉내 낸 문서 6종을 만든다.

사용법:
  python3 scripts/make_dummy_bundle.py --out samples/dummy_bundle
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SEED = 42


def load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        str(Path.home() / ".local/share/fonts/NanumGothic-Regular.ttf"),
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    for root in ("/usr/share/fonts", str(Path.home() / ".local/share/fonts")):
        rp = Path(root)
        if not rp.is_dir():
            continue
        for f in rp.rglob("*.tt*"):
            low = f.name.lower()
            if "nanum" in low or "cjk" in low or "noto" in low:
                try:
                    return ImageFont.truetype(str(f), size)
                except Exception:
                    continue
    return ImageFont.load_default()


TITLE_FONT = load_font(34)
BODY_FONT = load_font(20)
SMALL_FONT = load_font(16)


def draw_doc(title: str, fields: list[tuple[str, str]], table_headers: list[str],
             table_rows: list[list[str]], size=(1000, 1300)) -> Image.Image:
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, size[0] - 1, size[1] - 1], outline="black", width=2)
    d.text((40, 30), title, fill="black", font=TITLE_FONT)
    d.line([(30, 90), (size[0] - 30, 90)], fill="black", width=2)

    y = 120
    for key, value in fields:
        d.text((50, y), f"{key} : {value}", fill="black", font=BODY_FONT)
        y += 36

    if table_headers:
        y += 20
        n_cols = len(table_headers)
        x0, x1 = 50, size[0] - 50
        col_w = (x1 - x0) // n_cols
        row_h = 34
        d.rectangle([x0, y, x1, y + row_h], outline="black", width=1)
        for i, h in enumerate(table_headers):
            d.text((x0 + i * col_w + 6, y + 8), h, fill="black", font=SMALL_FONT)
            if i:
                d.line([(x0 + i * col_w, y), (x0 + i * col_w, y + row_h)], fill="black")
        y += row_h
        for row in table_rows:
            d.rectangle([x0, y, x1, y + row_h], outline="black", width=1)
            for i, v in enumerate(row):
                d.text((x0 + i * col_w + 6, y + 8), str(v), fill="black", font=SMALL_FONT)
                if i:
                    d.line([(x0 + i * col_w, y), (x0 + i * col_w, y + row_h)], fill="black")
            y += row_h
    return im


def to_preprocessed(im: Image.Image) -> Image.Image:
    return im.convert("L").rotate(1.5, expand=True, fillcolor=255).convert("RGB")


def field(key, value, dtype="string", confidence=0.98):
    return {"key": key, "value": value, "masked_value": None, "confidence": confidence,
            "field_code": None, "predicted_value": value, "predicted_masked_value": None, "dtype": dtype}


def harness_block(tier, final_value, ao_value=None, correction_basis=None, decision_rule_no="1",
                   rule_result="pass", rule_detail="", master_reference=None, candidates=None) -> dict:
    return {
        "tier": tier,
        "evidence": {
            "rule": [{"rule_id": "R-DUMMY-01", "category": "CALC", "severity": "medium",
                      "result": rule_result, "detail": rule_detail}],
            "reread": {"status": "unavailable", "value": None, "engine_id": "none",
                       "detail": "dummy: 재판독 미구성"},
            "master": {"status": "not_applicable"},
        },
        "final_value": final_value,
        "decision_rule_no": decision_rule_no,
        **({"correction_basis": correction_basis} if correction_basis else {}),
        **({"master_reference": master_reference} if master_reference else {}),
        **({"candidates": candidates} if candidates else {}),
    }


def harness_field(key, ao_value, final_value, dtype="string", tier="pass", correction_basis=None,
                   rule_result="pass", rule_detail="", **ref):
    c = field(key, ao_value, dtype)
    c["harness"] = harness_block(tier, final_value, ao_value, correction_basis, rule_result=rule_result,
                                  rule_detail=rule_detail, **ref)
    return c


def ao_doc(document_id, doc_type, extracted_fields, extracted_tables=None, extracted_groups=None):
    return {"document_id": document_id, "status": "pass", "doc_type": doc_type,
            "extracted_fields": extracted_fields, "extracted_groups": extracted_groups or [],
            "extracted_tables": extracted_tables or []}


def ao_response(transaction_id, docs):
    return {"transaction_id": transaction_id, "status": "completed", "documents": docs}


def harness_response(transaction_id, docs):
    return {
        "meta": {"adapted": {"from": "dummy"}, "processed_at": "2026-09-28T00:00:00+09:00"},
        "status": "completed",
        "harness": {"tier": "mixed", "harness_version": "2.0.0-dummy"},
        "documents": [
            {**d, "harness": {"tier": "pass", "summary": {"pass": len(d["extracted_fields"]), "repaired": 0}}}
            for d in docs
        ],
    }


def golden_doc(doc_type, extracted_fields, extracted_tables=None, extracted_groups=None):
    return {"doc_type": doc_type, "extracted_fields": extracted_fields,
            "extracted_groups": extracted_groups or [], "extracted_tables": extracted_tables or []}


def build(out: Path) -> None:
    original = out / "original"
    preprocessed = out / "preprocessed"
    ao_dir = out / "ao_extract"
    harness_dir = out / "harness"
    golden_dir = out / "golden"
    for d in (original, preprocessed, ao_dir, harness_dir, golden_dir):
        d.mkdir(parents=True, exist_ok=True)

    # ── MC001: 진료비영수증 — 정상 + 숫자오독 보정 + type mismatch 보정 + 표 extra row ──
    mc001_img = draw_doc("진료비 영수증", [("발행일", "2026-09-01"), ("외래/입원", "01")],
                          ["항목", "금액"], [["진찰료", "35,000"], ["처치료", "12,000"]])
    mc001_img.save(original / "MC001.png")
    to_preprocessed(mc001_img).save(preprocessed / "MC001.png")

    mc001_ao_fields = [field("발행일", "20260901", "string"), field("외래/입원", "01", "string"),
                        field("공단부담총액", "미상", "int", confidence=0.31)]
    mc001_ao_table = [{"key": "항목내역", "field_code": None, "headers": ["항목", "금액"], "rows": [
        [field("항목", "진찰료", "string"), field("금액", "33000", "int")],
        [field("항목", "처치료", "string"), field("금액", "12000", "int")],
        [field("항목", "재료대", "string"), field("금액", "500", "int")],
    ]}]
    mc001_ao = ao_response("txn-mc001", [ao_doc("doc-mc001", "진료비영수증", mc001_ao_fields, mc001_ao_table)])
    (ao_dir / "MC001.aiocr.json").write_text(json.dumps(mc001_ao, ensure_ascii=False, indent=1), encoding="utf-8")

    mc001_h_fields = [field("발행일", "20260901", "string"),
                       field("외래/입원", "01", "string"),
                       harness_field("공단부담총액", "미상", "9000", "int", tier="repaired",
                                     correction_basis="rule", rule_result="fail",
                                     rule_detail="금액 형식 오류 → 규칙 재계산")]
    mc001_h_table = [{"key": "항목내역", "field_code": None, "headers": ["항목", "금액"], "rows": [
        [harness_field("항목", "진찰료", "진찰료", master_reference={"system_id": "EDI:의치과_급여", "code": "AA154", "name": "초진 진찰료"},
                       candidates=["AA154", "AA254"]),
         harness_field("금액", "33000", "35000", "int", tier="repaired",
                                                        correction_basis="rule", rule_result="fail",
                                                        rule_detail="합계 불일치 → 원문 재검산")],
        [field("항목", "처치료", "string"), field("금액", "12000", "int")],
        [field("항목", "재료대", "string"), field("금액", "500", "int")],
    ]}]
    mc001_h = harness_response("txn-mc001", [ao_doc("doc-mc001", "진료비영수증", mc001_h_fields, mc001_h_table)])
    (harness_dir / "MC001.harness.json").write_text(json.dumps(mc001_h, ensure_ascii=False, indent=1),
                                                      encoding="utf-8")

    mc001_golden = {"documents": [golden_doc("진료비영수증", [
        field("발행일", "2026-09-01", "string"), field("외래/입원", "01", "string"),
        field("공단부담총액", "9000", "int"),
    ], [{"key": "항목내역", "headers": ["항목", "금액"], "rows": [
        [field("항목", "진찰료", "string"), field("금액", "35000", "int")],
        [field("항목", "처치료", "string"), field("금액", "12000", "int")],
    ]}])]}
    (golden_dir / "MC001.json").write_text(json.dumps(mc001_golden, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── DX002: 진단서 — 병명코드 오독 보정성공 + 작성일자 악화 + 병명 필드 누락 ──
    dx002_img = draw_doc("진단서", [("병명코드", "K123"), ("작성일자", "2026-09-10"), ("병명", "고혈압")], [], [])
    dx002_img.save(original / "DX002.jpg")
    to_preprocessed(dx002_img).save(preprocessed / "DX002.png")

    dx002_ao_fields = [field("병명코드", "K128", "string", confidence=0.62), field("작성일자", "20260910", "string")]
    dx002_ao = ao_response("txn-dx002", [ao_doc("doc-dx002", "진단서", dx002_ao_fields)])
    (ao_dir / "DX002.aiocr.json").write_text(json.dumps(dx002_ao, ensure_ascii=False, indent=1), encoding="utf-8")

    dx002_h_fields = [
        harness_field("병명코드", "K128", "K123", "string", tier="repaired", correction_basis="master",
                       rule_result="fail", rule_detail="상병코드 마스터 대조 불일치 → 교정"),
        harness_field("작성일자", "20260910", "20260911", "string", tier="repaired", correction_basis="reread",
                       rule_result="warn", rule_detail="재판독 값과 상이(더미: 의도적 악화 사례)"),
    ]
    dx002_h = harness_response("txn-dx002", [ao_doc("doc-dx002", "진단서", dx002_h_fields)])
    (harness_dir / "DX002.harness.json").write_text(json.dumps(dx002_h, ensure_ascii=False, indent=1),
                                                      encoding="utf-8")

    dx002_golden = {"documents": [golden_doc("진단서", [
        field("병명코드", "K123", "string"), field("작성일자", "2026-09-10", "string"),
        field("병명", "고혈압", "string"),
    ])]}
    (golden_dir / "DX002.json").write_text(json.dumps(dx002_golden, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── PH003: 약제비영수증 — harness 없음, golden 없음, 원본 tif(2페이지) ──
    ph003_p1 = draw_doc("약제비 영수증 (1/2)", [("조제일자", "2026-09-05"), ("약국명", "가나다약국")], [], [])
    ph003_p2 = draw_doc("약제비 영수증 (2/2)", [("합계금액", "18,500")], [], [])
    ph003_p1.save(original / "PH003.tif", save_all=True, append_images=[ph003_p2])
    to_preprocessed(ph003_p1).save(preprocessed / "PH003.png")

    ph003_ao_fields = [field("조제일자", "20260905", "string"), field("약국명", "가나다약국", "string"),
                        field("합계금액", "18500", "int")]
    ph003_ao = ao_response("txn-ph003", [ao_doc("doc-ph003", "약제비영수증", ph003_ao_fields)])
    (ao_dir / "PH003.aiocr.json").write_text(json.dumps(ph003_ao, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── OP004: 소견서 — 전처리 이미지 없음 ──
    op004_img = draw_doc("소견서", [("작성일", "2026-09-12"), ("소견", "안정가료 필요")], [], [])
    op004_img.save(original / "OP004.png")

    op004_ao_fields = [field("작성일", "20260912", "string"), field("소견", "안정가료 필요", "string")]
    op004_ao = ao_response("txn-op004", [ao_doc("doc-op004", "소견서", op004_ao_fields)])
    (ao_dir / "OP004.aiocr.json").write_text(json.dumps(op004_ao, ensure_ascii=False, indent=1), encoding="utf-8")

    op004_h_fields = [field("작성일", "20260912", "string"), field("소견", "안정가료 필요", "string")]
    op004_h = harness_response("txn-op004", [ao_doc("doc-op004", "소견서", op004_h_fields)])
    (harness_dir / "OP004.harness.json").write_text(json.dumps(op004_h, ensure_ascii=False, indent=1),
                                                      encoding="utf-8")

    op004_golden = {"documents": [golden_doc("소견서", [
        field("작성일", "2026-09-12", "string"), field("소견", "안정가료 필요", "string"),
    ])]}
    (golden_dir / "OP004.json").write_text(json.dumps(op004_golden, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── MC005: 진료비영수증 — harness JSON 깨짐(broken), golden 없음 ──
    mc005_img = draw_doc("진료비 영수증", [("발행일", "2026-09-20")], [], [])
    mc005_img.save(original / "MC005.jpg")
    to_preprocessed(mc005_img).save(preprocessed / "MC005.png")

    mc005_ao_fields = [field("발행일", "20260920", "string")]
    mc005_ao = ao_response("txn-mc005", [ao_doc("doc-mc005", "진료비영수증", mc005_ao_fields)])
    (ao_dir / "MC005.aiocr.json").write_text(json.dumps(mc005_ao, ensure_ascii=False, indent=1), encoding="utf-8")
    (harness_dir / "MC005.harness.json").write_text("{ this is not valid json ", encoding="utf-8")

    # ── DX006: 진단서 — 이미지만 존재 ──
    dx006_img = draw_doc("진단서 (미처리)", [("비고", "OCR 대기중")], [], [])
    dx006_img.save(original / "DX006.png")

    print(f"generated dummy bundle at {out}")


def zip_dir(src: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                zf.write(p, arcname=str(p.relative_to(src.parent)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="samples/dummy_bundle")
    args = parser.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    build(out)
    zip_path = out.with_suffix(".zip")
    zip_dir(out, zip_path)
    print(f"zipped to {zip_path}")


if __name__ == "__main__":
    main()
