import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.compare import compare_bundle
from backend.bundle import classify, stem_of


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
