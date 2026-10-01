from backend.compare import cell_status


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
