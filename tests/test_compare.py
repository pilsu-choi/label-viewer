from backend.compare import cell_status, compare_doc


def test_label_print_variants_match():
    assert cell_status("string", "보철·교정료", "보철교정료", "항목") == "MATCH"
    assert cell_status("string", "전혈및혈액성분제재료", "전혈및혈액성분제제료", "항목") == "MATCH"
    assert cell_status("string", "의원급・보건기관", "의원급·보건기관", "의료기관정보-요양기관종류") == "MATCH"
    assert cell_status("string", "병원", "병원급", "요양기관종류") == "MATCH"


def test_label_misread_still_mismatch():
    assert cell_status("string", "전혈및혈액성분제제료", "전혈및혈장성분제제료", "항목") == "MISMATCH"
    assert cell_status("string", "병원급", "의원급", "요양기관종류") == "MISMATCH"
    assert cell_status("string", "보철·교정료", "보철교정료", "EDI명칭") == "MISMATCH"


def test_total_alias_receipt_only():
    assert cell_status("string", "계", "합계", "항목", receipt=True) == "MATCH"
    assert cell_status("string", "계", "합계", "항목") == "MISMATCH"


def test_total_alias_receipt_by_ao_code():
    # 기준 문서 종류가 AO 코드여도 영수증으로 보고 계·합계를 같은 행으로 본다
    cell = lambda v: {"key": "항목", "value": v, "dtype": "string"}
    for dt in ("진료비영수증", "AC02922011", " AC02922011 "):
        doc = lambda v: {"doc_type": dt, "extracted_fields": [cell(v)], "extracted_groups": [], "extracted_tables": []}
        (row,) = compare_doc(0, doc("계"), doc("계"), doc("합계"))
        assert row["harness_status"] == "MATCH", dt


def test_master_reference_passthrough_in_evidence():
    ref = {"system_id": "EDI:의치과_급여", "code": "D1890002", "name": "γ-GTP [화학반응-장비측정]"}
    cell = lambda **h: {"key": "항목", "value": "강마지티피", "dtype": "string", "harness": {"final_value": "강마지티피", **h}}
    doc = lambda c: {"extracted_fields": [c], "extracted_groups": [], "extracted_tables": []}
    for extra in ({"master_reference": ref, "candidates": ["D1890002", "D1890003"]}, {"master_reference": {"name": "x"}}, {}):
        (row,) = compare_doc(0, doc(cell()), doc(cell()), doc(cell(**extra)))
        assert row["evidence"].get("master_reference") == extra.get("master_reference")
        assert row["evidence"].get("candidates") == extra.get("candidates")


def test_name_row_gets_code_master_reference():
    from backend.compare import compare_bundle
    ref = {"system_id": "EDI", "code": "D1", "name": "원장명"}
    cell = lambda k, **h: {"key": k, "value": "x", "dtype": "string", **({"harness": h} if h else {})}
    def doc(code_h):
        rows = [[cell("EDI코드", **code_h), cell("EDI명칭")], [cell("EDI코드"), cell("EDI명칭")]]
        return {"extracted_fields": [cell("병명코드", **code_h), cell("병명")], "extracted_groups": [],
                "extracted_tables": [{"key": "세부", "headers": ["EDI코드", "EDI명칭"], "rows": rows}]}
    out = {(r["area"], r["row"], r["key"]): r for r in compare_bundle(None, {"documents": [doc({})]}, {"documents": [doc({"master_reference": ref})]})}
    assert out[("table", 0, "EDI명칭")]["code_master_reference"] == ref
    assert out[("field", "", "병명")]["code_master_reference"] == ref
    for k in (("table", 1, "EDI명칭"), ("table", 0, "EDI코드"), ("field", "", "병명코드")):
        assert "code_master_reference" not in out[k]
    assert "code_master_reference" not in {r["key"]: r for r in compare_bundle(None, {"documents": [doc({})]}, {"documents": [doc({})]})}["병명"]


# ── 결과(AO·Harness) 자체가 없는 쪽은 채점하지 않는다 ─────────────────────
def _cell(key, value, dtype="string"):
    return {"key": key, "value": value, "dtype": dtype}


GOLDEN_DOC = {"doc_type": "세부내역서",
              "extracted_fields": [_cell("사고발생일자", "20230309")],
              "extracted_groups": [{"key": "합계", "fields": [_cell("급여_급여총액", None), _cell("비급여총액", "")]}],
              "extracted_tables": [{"key": "항목내역", "headers": ["EDI코드", "총액"],
                                    "rows": [[_cell("EDI코드", "AA154"), _cell("총액", "17320", "int")]]}]}


def _statuses(rows, side):
    return {r["path"]: r[f"{side}_status"] for r in rows}


def test_golden_only_is_not_scored():
    """결과가 없으면 Golden 빈칸이 '둘 다 빈칸' MATCH 로, 값 칸이 MISSING 으로 잡혀 정확도가 생기면 안 된다."""
    from backend.compare import score
    rows = compare_doc(0, GOLDEN_DOC, None, None)
    assert rows and all(r["ao_status"] == "" and r["harness_status"] == "" for r in rows)
    assert score(rows, "ao") is None and score(rows, "harness") is None


def test_one_side_present_scores_only_that_side():
    from backend.compare import score
    ao = {"doc_type": "세부내역서", "extracted_fields": [_cell("사고발생일자", "20230309")],
          "extracted_groups": [], "extracted_tables": []}
    rows = compare_doc(0, GOLDEN_DOC, ao, None)
    st = _statuses(rows, "ao")
    # 결과는 있는데 칸이 없으면 기존대로: 값 칸 MISSING, Golden 빈칸 MATCH
    assert st["documents[0].fields[사고발생일자]"] == "MATCH"
    assert st["documents[0].groups[합계].fields[비급여총액]"] == "MATCH"
    assert st["documents[0].tables[항목내역].rows[0].cells[EDI코드]"] == "MISSING"
    assert score(rows, "ao")["total"] == len(rows)
    assert all(r["harness_status"] == "" for r in rows)
    assert score(rows, "harness") is None


def test_result_missing_later_document_is_not_scored():
    """Golden 이 문서 2개, 결과가 1개면 두 번째 문서는 그 결과 쪽 채점에서 빠진다(문서 단위 결과 없음)."""
    from backend.compare import compare_bundle, score
    golden = {"documents": [GOLDEN_DOC, GOLDEN_DOC]}
    ao = {"documents": [GOLDEN_DOC]}
    rows = compare_bundle(golden, ao, None)
    doc0 = [r for r in rows if r["doc"] == 0]
    doc1 = [r for r in rows if r["doc"] == 1]
    assert all(r["ao_status"] == "MATCH" for r in doc0)
    assert all(r["ao_status"] == "" for r in doc1)
    assert score(rows, "ao")["total"] == len(doc0)
