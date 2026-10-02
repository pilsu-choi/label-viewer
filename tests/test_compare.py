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


def test_master_reference_passthrough_in_evidence():
    ref = {"system_id": "EDI:의치과_급여", "code": "D1890002", "name": "γ-GTP [화학반응-장비측정]"}
    cell = lambda **h: {"key": "항목", "value": "강마지티피", "dtype": "string", "harness": {"final_value": "강마지티피", **h}}
    doc = lambda c: {"extracted_fields": [c], "extracted_groups": [], "extracted_tables": []}
    for extra in ({"master_reference": ref, "candidates": ["D1890002", "D1890003"]}, {"master_reference": {"name": "x"}}, {}):
        (row,) = compare_doc(0, doc(cell()), doc(cell()), doc(cell(**extra)))
        assert row["evidence"].get("master_reference") == extra.get("master_reference")
        assert row["evidence"].get("candidates") == extra.get("candidates")
