import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.bundle import (
    ApiError,
    create_golden,
    delete_golden,
    doc_detail,
    load_doc_json,
    process_upload,
    save_golden,
)


def _bundle(tmp_path, extra=()):
    files = [("batch/original/doc.png", io.BytesIO(b"image")), *extra]
    return process_upload(tmp_path, files, None, 1_000_000)


@pytest.mark.parametrize("operation", ["create", "save", "delete"])
def test_golden_mutations_require_existing_bundle(tmp_path, operation):
    data = {"documents": [{"extracted_fields": [], "extracted_groups": [], "extracted_tables": []}]}
    with pytest.raises(ApiError) as error:
        if operation == "create":
            create_golden(tmp_path, "missing", "doc", "empty")
        elif operation == "save":
            save_golden(tmp_path, "missing", "doc", data)
        else:
            delete_golden(tmp_path, "missing", "doc")
    assert error.value.status == 404
    assert not (tmp_path / "bundles" / "missing").exists()


@pytest.mark.parametrize("operation", ["create", "save", "delete"])
def test_golden_mutations_require_existing_document(tmp_path, operation):
    bid = _bundle(tmp_path)
    data = {"documents": [{"extracted_fields": [], "extracted_groups": [], "extracted_tables": []}]}
    with pytest.raises(ApiError) as error:
        if operation == "create":
            create_golden(tmp_path, bid, "missing", "empty")
        elif operation == "save":
            save_golden(tmp_path, bid, "missing", data)
        else:
            delete_golden(tmp_path, bid, "missing")
    assert error.value.status == 404
    golden_dir = tmp_path / "bundles" / bid / "golden"
    assert not list(golden_dir.glob("*.json")) if golden_dir.exists() else True


def test_create_golden_from_empty_ao_documents_with_doc_type(tmp_path):
    bid = _bundle(tmp_path, [("batch/ao_extract/doc.aiocr.json", io.BytesIO(b'{"documents":[]}'))])

    result = create_golden(tmp_path, bid, "doc", "ao", "진단서")

    assert result["golden"]["documents"][0]["doc_type"] == "진단서"


@pytest.mark.parametrize("golden", [
    {"documents": [{"extracted_fields": [1]}]},
    {"documents": [{"extracted_groups": ["bad"]}]},
    {"documents": [{"extracted_groups": [{"key": "g", "fields": "bad"}]}]},
    {"documents": [{"extracted_tables": [{"key": "t", "headers": [1]}]}]},
    {"documents": [{"extracted_tables": [{"key": "t", "rows": ["bad"]}]}]},
    {"documents": [{"extracted_tables": [{"key": "t", "rows": [[{"key": []}]]}]}]},
])
def test_save_golden_rejects_invalid_nested_schema_without_replacing_existing_golden(tmp_path, golden):
    bid = _bundle(tmp_path)
    valid = {"documents": [{"extracted_fields": [{"key": "existing", "value": "safe"}],
                            "extracted_groups": [], "extracted_tables": []}]}
    save_golden(tmp_path, bid, "doc", valid)
    golden_path = tmp_path / "bundles" / bid / "golden" / "doc.json"
    before = golden_path.read_bytes()
    with pytest.raises(ApiError) as error:
        save_golden(tmp_path, bid, "doc", golden)
    assert error.value.status == 422
    assert golden_path.read_bytes() == before
    assert doc_detail(tmp_path, bid, "doc")["golden"]["documents"][0]["extracted_fields"][0]["value"] == "safe"


@pytest.mark.parametrize("payload", [
    {"documents": [{"extracted_fields": [1]}]},
    {"documents": [{"result": {"fields": [1]}}]},
])
def test_malformed_canonical_ao_json_is_reported_as_read_error(tmp_path, payload):
    raw = json.dumps(payload).encode()
    bid = _bundle(tmp_path, [("batch/ao_extract/doc.aiocr.json", io.BytesIO(raw))])
    path = tmp_path / "bundles" / bid / "ao_extract" / "doc.json"
    parsed, error = load_doc_json(path)
    assert parsed is None
    assert error and "JSON 형식 오류" in error

    detail = doc_detail(tmp_path, bid, "doc")
    assert any("ao_extract: JSON 형식 오류" in item for item in detail["errors"])


def test_read_validation_does_not_add_defaults_to_cached_json(tmp_path):
    bid = _bundle(tmp_path, [("batch/ao_extract/doc.aiocr.json", io.BytesIO(
        b'{"documents":[{"extracted_fields":[{"key":"a"}]}]}'))])
    path = tmp_path / "bundles" / bid / "ao_extract" / "doc.json"
    first, error = load_doc_json(path)
    second, second_error = load_doc_json(path)
    assert error is None and second_error is None
    assert first["documents"][0]["extracted_fields"][0] == {"key": "a"}
    assert second["documents"][0]["extracted_fields"][0] == {"key": "a"}
