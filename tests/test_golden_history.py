import io
import hashlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.bundle import (
    ApiError, create_golden, delete_golden, doc_detail, get_golden_history,
    list_golden_history, process_upload, restore_golden, save_golden,
)
from backend import bundle as B


def _bundle(tmp_path, extra=()):
    files = [("batch/original/doc.png", io.BytesIO(b"image")), *extra]
    return process_upload(tmp_path, files, None, 1_000_000)


def _golden(value):
    return {"documents": [{"extracted_fields": [{"key": "field", "value": value}],
                           "extracted_groups": [], "extracted_tables": []}]}


def test_history_archives_baseline_create_edit_delete_and_restore(tmp_path):
    initial = b'{"documents":[]}'
    bid = _bundle(tmp_path, [("batch/golden/doc.json", io.BytesIO(initial))])
    baseline_revision = doc_detail(tmp_path, bid, "doc")["golden_revision"]

    edited = save_golden(tmp_path, bid, "doc", _golden("edited"), baseline_revision)
    edited_revision = edited["golden_revision"]
    assert edited_revision != baseline_revision
    delete_golden(tmp_path, bid, "doc", edited_revision)
    assert doc_detail(tmp_path, bid, "doc")["golden_revision"] == "missing"

    listed = list_golden_history(tmp_path, bid, "doc")
    history = listed["items"]
    assert listed["golden_revision"] == "missing"
    assert [item["action"] for item in history] == ["delete", "save", "baseline"]
    assert history[-1]["revision"] == baseline_revision
    assert get_golden_history(tmp_path, bid, "doc", history[-1]["id"])["golden"] == {"documents": []}

    restored = restore_golden(tmp_path, bid, "doc", history[-1]["id"], "missing")
    assert restored["golden_revision"] == baseline_revision
    assert restored["golden"] == {"documents": []}


def test_history_records_missing_baseline_and_can_restore_deletion(tmp_path):
    bid = _bundle(tmp_path)
    created = create_golden(tmp_path, bid, "doc", "empty", expected_revision="missing")
    created_revision = created["golden_revision"]
    delete_golden(tmp_path, bid, "doc", created_revision)
    history = list_golden_history(tmp_path, bid, "doc")["items"]
    assert [item["action"] for item in history] == ["delete", "create", "baseline"]
    assert history[-1]["has_golden"] is False

    result = restore_golden(tmp_path, bid, "doc", history[-1]["id"], "missing")
    assert result["golden_revision"] == "missing"
    assert result["has"]["golden"] is False


def test_deleted_golden_only_document_remains_restorable(tmp_path):
    bid = _bundle(tmp_path, [("batch/golden/doc.json", io.BytesIO(b'{"documents":[]}'))])
    revision = doc_detail(tmp_path, bid, "doc")["golden_revision"]
    delete_golden(tmp_path, bid, "doc", revision)
    history = list_golden_history(tmp_path, bid, "doc")["items"]

    result = restore_golden(tmp_path, bid, "doc", history[-1]["id"], "missing")

    assert result["golden_revision"] == revision
    assert result["has"]["golden"] is True


@pytest.mark.parametrize("encoding", ["bom", "cp949"])
def test_history_preview_and_restore_accept_upload_json_encodings(tmp_path, encoding):
    payload = {"documents": [{"doc_type": "진료비영수증", "extracted_fields": [],
                               "extracted_groups": [], "extracted_tables": []}]}
    text = json.dumps(payload, ensure_ascii=False)
    raw = text.encode("utf-8-sig" if encoding == "bom" else "cp949")
    bid = _bundle(tmp_path, [("batch/golden/doc.json", io.BytesIO(raw))])
    revision = hashlib.sha256(raw).hexdigest()
    delete_golden(tmp_path, bid, "doc", revision)
    baseline = list_golden_history(tmp_path, bid, "doc")["items"][-1]

    preview = get_golden_history(tmp_path, bid, "doc", baseline["id"])
    restored = restore_golden(tmp_path, bid, "doc", baseline["id"], "missing")

    assert preview["golden"] == payload
    assert restored["golden_revision"] == revision
    assert restored["golden"] == payload


def test_failed_history_archive_rolls_back_golden_bytes(tmp_path, monkeypatch):
    initial = b'{"documents":[]}'
    bid = _bundle(tmp_path, [("batch/golden/doc.json", io.BytesIO(initial))])
    real_archive = B.archive_snapshot
    calls = 0

    def fail_operation_snapshot(bdir, doc_id, raw, action):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("history storage unavailable")
        return real_archive(bdir, doc_id, raw, action)

    monkeypatch.setattr(B, "archive_snapshot", fail_operation_snapshot)
    with pytest.raises(OSError):
        save_golden(tmp_path, bid, "doc", _golden("new"))

    path = tmp_path / "bundles" / bid / "golden" / "doc.json"
    assert path.read_bytes() == initial
    assert [item["action"] for item in list_golden_history(tmp_path, bid, "doc")["items"]] == ["baseline"]


def test_stale_revision_rejects_save_without_changing_file_or_history(tmp_path):
    bid = _bundle(tmp_path)
    current = save_golden(tmp_path, bid, "doc", _golden("first"), "missing")
    path = tmp_path / "bundles" / bid / "golden" / "doc.json"
    before = path.read_bytes()
    history_before = list_golden_history(tmp_path, bid, "doc")["items"]

    with pytest.raises(ApiError) as error:
        save_golden(tmp_path, bid, "doc", _golden("stale"), "missing")

    assert error.value.status == 409
    assert path.read_bytes() == before
    assert list_golden_history(tmp_path, bid, "doc")["items"] == history_before
    assert current["golden_revision"] == doc_detail(tmp_path, bid, "doc")["golden_revision"]


def test_concurrent_writes_with_same_revision_allow_only_one(tmp_path):
    bid = _bundle(tmp_path)
    revision = save_golden(tmp_path, bid, "doc", _golden("initial"), "missing")["golden_revision"]

    def write(value):
        try:
            save_golden(tmp_path, bid, "doc", _golden(value), revision)
            return "saved"
        except ApiError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, ("left", "right")))

    assert sorted(outcomes, key=str) == [409, "saved"]
    final = doc_detail(tmp_path, bid, "doc")
    assert final["golden"]["documents"][0]["extracted_fields"][0]["value"] in {"left", "right"}


def test_detail_revision_and_payload_use_the_same_raw_snapshot(tmp_path, monkeypatch):
    bid = _bundle(tmp_path)
    saved = save_golden(tmp_path, bid, "doc", _golden("before"), "missing")
    path = tmp_path / "bundles" / bid / "golden" / "doc.json"
    raw_before = path.read_bytes()
    original = B._load_json_bytes
    replaced = False

    def replace_after_capture(raw, canonical):
        nonlocal replaced
        if canonical and not replaced:
            replaced = True
            path.write_bytes(b'{"documents":[{"extracted_fields":[{"key":"field","value":"external"}]}]}')
        return original(raw, canonical)

    monkeypatch.setattr(B, "_load_json_bytes", replace_after_capture)
    detail = doc_detail(tmp_path, bid, "doc")

    assert detail["golden_revision"] == hashlib.sha256(raw_before).hexdigest() == saved["golden_revision"]
    assert detail["golden"]["documents"][0]["extracted_fields"][0]["value"] == "before"


def test_save_response_is_captured_before_next_writer_can_replace_it(tmp_path, monkeypatch):
    bid = _bundle(tmp_path)
    initial = save_golden(tmp_path, bid, "doc", _golden("initial"), "missing")
    original = B._doc_detail_unlocked
    response_ready = threading.Event()
    release_response = threading.Event()
    b_started = threading.Event()

    def pause_first_response(data_dir, bundle_id, doc_id):
        result = original(data_dir, bundle_id, doc_id)
        value = result["golden"]["documents"][0]["extracted_fields"][0]["value"]
        if value == "writer A" and not response_ready.is_set():
            response_ready.set()
            assert release_response.wait(3)
        return result

    monkeypatch.setattr(B, "_doc_detail_unlocked", pause_first_response)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(save_golden, tmp_path, bid, "doc", _golden("writer A"), initial["golden_revision"])
        assert response_ready.wait(3)
        second = pool.submit(lambda: (b_started.set(), save_golden(
            tmp_path, bid, "doc", _golden("writer B"),
            hashlib.sha256((tmp_path / "bundles" / bid / "golden" / "doc.json").read_bytes()).hexdigest()))[1])
        assert b_started.wait(3)
        release_response.set()
        first_result = first.result(timeout=3)
        second_result = second.result(timeout=3)

    assert first_result["golden"]["documents"][0]["extracted_fields"][0]["value"] == "writer A"
    assert first_result["golden_revision"] != second_result["golden_revision"]
