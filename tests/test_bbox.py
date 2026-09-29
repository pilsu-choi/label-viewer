import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.compare import compare_bundle
from backend.bundle import ApiError, bundle_view, classify, create_golden, doc_detail, process_upload, stem_of


def cell(key, value):
    return {"key": key, "value": value, "dtype": "string"}


def token_box(key, value, box, page=1):
    return {"key": key, "value": value, "token_bbox": [{"page": page, "token_bbox": [box]}]}


def test_ao_ui_token_boxes_attach_to_fields_groups_and_aligned_table_rows():
    golden = {"documents": [{
        "extracted_fields": [cell("date", "20240101")],
        "extracted_groups": [{"key": "patient", "fields": [cell("name", "Kim")]}],
        "extracted_tables": [{"key": "items", "headers": ["label", "amount"], "rows": [
            [cell("label", "A"), cell("amount", "1")],
            [cell("label", "B"), cell("amount", "2")],
        ]}],
    }]}
    ao = {"documents": [{
        "extracted_fields": [cell("date", "20240101")],
        "extracted_groups": [{"key": "patient", "fields": [cell("name", "Kim")]}],
        "extracted_tables": [{"key": "items", "headers": ["label", "amount"], "rows": [
            [cell("label", "X"), cell("amount", "0")],
            [cell("label", "A"), cell("amount", "1")],
            [cell("label", "B"), cell("amount", "2")],
        ]}],
    }]}
    ui = {"documents": [{"result": {
        "fields": [token_box("date", "20240101", [.1, .2, .3, .04])],
        "groups": [{"key": "patient", "fields": [token_box("patient.name", "Kim", [.2, .3, .1, .02], 2)]}],
        "tables": [{"key": "items", "rows": [
            [token_box("items[0].label", "X", [.3, .4, .1, .03])],
            [token_box("items[1].label", "A", [.5, .6, .1, .03])],
            [token_box("items[2].label", "B", [.7, .8, .1, .03])],
        ]}],
    }}]}

    rows = {row["path"]: row for row in compare_bundle(golden, ao, None, ui)}
    assert rows["documents[0].fields[date]"]["bbox"] == [
        {"page": 1, "box": [.1, .2, .3, .04]},
    ]
    assert rows["documents[0].groups[patient].fields[name]"]["bbox"] == [
        {"page": 2, "box": [.2, .3, .1, .02]},
    ]
    # AO's inserted row X shifts Golden row B to AO/UI row 2.
    assert rows["documents[0].tables[items].rows[1].cells[label]"]["bbox"] == [
        {"page": 1, "box": [.7, .8, .1, .03]},
    ]


def test_missing_ao_ui_sidecar_keeps_compare_rows_without_boxes():
    ao = {"documents": [{"extracted_fields": [cell("date", "20240101")]}]}
    rows = compare_bundle(None, ao, None)
    assert rows[0]["bbox"] is None


def test_ao_ui_suffix_joins_the_original_document_id():
    path = "ao_ui/D2-DET-001.png.aiocr.ui.json"
    assert classify(path) == "ao_ui"
    assert stem_of(path) == "D2-DET-001"


def test_ao_ui_response_in_ao_extract_keeps_ao_kind():
    path = "ao_extract/D2-DET-001.png.aiocr.ui.json"
    assert classify(path) == "ao_extract"
    assert stem_of(path) == "D2-DET-001"


def test_sidecar_only_upload_returns_clear_error(tmp_path):
    path = "dummy/ao_ui/D2-DET-001.png.aiocr.ui.json"
    try:
        process_upload(tmp_path, [(path, b"{}")], None, 10000)
    except ApiError as error:
        assert error.status == 400
        assert "AO UI sidecar" in error.message
    else:
        raise AssertionError("sidecar-only upload must fail")


def test_doc_detail_exposes_optional_ao_ui_sidecar(tmp_path):
    image = "dummy/original/D2-DET-001.png"
    ao = "dummy/ao_extract/D2-DET-001.png.aiocr.ui.json"
    sidecar = "dummy/ao_ui/D2-DET-001.png.aiocr.ui.json"
    bundle_id = process_upload(tmp_path, [(image, b"image"), (ao, b'{"documents":[]}'), (sidecar, b'{"documents":[]}')], None, 10000)

    has = doc_detail(tmp_path, bundle_id, "D2-DET-001")["has"]
    assert has["original"] is True
    assert has["ao_extract"] is True
    assert has["ao_ui"] is True


def test_ao_ui_response_in_ao_extract_is_canonicalized_but_raw_is_preserved(tmp_path):
    image = "dummy/original/D2-DET-001.png"
    ao_path = "dummy/ao_extract/D2-DET-001.png.aiocr.ui.json"
    response = {"documents": [{"result": {
        "doc_type": "receipt",
        "fields": [token_box("date", "20240101", [.1, .2, .3, .04])],
        "groups": [{"key": "patient", "fields": [token_box("patient.name", "Kim", [.2, .3, .1, .02], 2)]}],
        "tables": [{"key": "items", "headers": ["label", "amount"], "rows": [
            [token_box("items[0].label", "A", [.3, .4, .1, .03]), token_box("items[0].amount", "1", [.4, .5, .1, .03])],
        ]}],
    }}]}
    import json
    raw = json.dumps(response, ensure_ascii=False).encode()
    bundle_id = process_upload(tmp_path, [(image, b"image"), (ao_path, raw)], None, 10000)
    detail = create_golden(tmp_path, bundle_id, "D2-DET-001", "ao")
    doc = detail["ao"]["documents"][0]

    assert detail["doc_type"] == "receipt"
    assert doc["extracted_fields"][0]["bbox"] == [{"page": 1, "box": [.1, .2, .3, .04]}]
    assert doc["extracted_groups"][0]["fields"][0]["key"] == "name"
    assert doc["extracted_groups"][0]["fields"][0]["bbox"] == [{"page": 2, "box": [.2, .3, .1, .02]}]
    table = doc["extracted_tables"][0]
    assert table["rows"][0][0]["key"] == "label"
    assert table["rows"][0][0]["bbox"] == [{"page": 1, "box": [.3, .4, .1, .03]}]
    assert all(row["ao_status"] == "MATCH" for row in detail["compare"])
    assert bundle_view(tmp_path, bundle_id)["summary"]["score"]["ao"]["accuracy"] == 1.0
    assert (tmp_path / "bundles" / bundle_id / "ao_extract" / "D2-DET-001.json").read_bytes() == raw


def test_run_result_harness_without_documents_creates_golden_draft(tmp_path):
    import json
    run = {"stage": "extract", "harness": {"tier": "pass"}, "result": {
        "doc_type": "receipt",
        "fields": [{**token_box("date", "20240101", [.1, .2, .3, .04]), "harness": {"final_value": "20240102"}}],
        "groups": [{"key": "patient", "fields": [token_box("patient.name", "Kim", [.2, .3, .1, .02])]}],
        "tables": [{"key": "items", "headers": ["amount"], "rows": [[token_box("items[0].amount", "1", [.4, .5, .1, .03])]]}],
    }}
    files = [("out/original/D1.png", b"image"),
             ("out/harness/D1.harness.json", json.dumps(run).encode()),
             ("out/ao_extract/D1.aiocr.json", json.dumps(run).encode())]
    bundle_id = process_upload(tmp_path, files, None, 10000)
    doc = create_golden(tmp_path, bundle_id, "D1", "harness")["golden"]["documents"][0]

    assert doc["doc_type"] == "receipt"
    assert "harness" not in doc and "harness" not in doc["extracted_fields"][0]
    assert doc["extracted_groups"][0]["fields"][0]["key"] == "name"
    assert doc["extracted_tables"][0]["rows"][0][0]["key"] == "amount"
