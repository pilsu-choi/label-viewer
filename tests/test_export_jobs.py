from __future__ import annotations

import io
import json
import multiprocessing
import time
import zipfile
from pathlib import Path
from threading import Event

import pytest

from backend import export_jobs as J
from backend import export as E
from backend.bundle import ApiError, process_upload


def _make_bundle(data_dir: Path, ids=("D1", "D2", "D10")) -> str:
    files = []
    for doc_id in ids:
        files.extend([
            (f"batch/original/{doc_id}.png", io.BytesIO(b"image-bytes")),
            (f"batch/ao_extract/{doc_id}.aiocr.json", io.BytesIO(json.dumps({"documents": [
                {"doc_type": "", "extracted_fields": [], "extracted_groups": [], "extracted_tables": []},
            ]}).encode())),
            (f"batch/golden/{doc_id}.answer.json", io.BytesIO(json.dumps({"documents": [
                {"doc_type": "", "extracted_fields": [], "extracted_groups": [], "extracted_tables": []},
            ]}).encode())),
        ])
    return process_upload(data_dir, files, "Test Bundle", 1_000_000)


def _wait_state(data_dir: Path, bundle_id: str, job_id: str, wanted: str, timeout: float = 8) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = J.status(data_dir, bundle_id, job_id)
        if value["state"] == wanted:
            return value
        if value["state"] in ("failed", "cancelled") and value["state"] != wanted:
            pytest.fail(f"job ended as {value}")
        time.sleep(0.02)
    pytest.fail(f"job did not reach {wanted}")


def _read_status_child(data_dir: str, bundle_id: str, job_id: str, out) -> None:
    out.put(J.status(Path(data_dir), bundle_id, job_id))


def _cancel_child(data_dir: str, bundle_id: str, job_id: str, out) -> None:
    try:
        out.put(J.cancel(Path(data_dir), bundle_id, job_id))
    except Exception as exc:
        out.put({"error": str(exc)})


def test_zip_job_selection_ignores_scope_and_preserves_natural_order(tmp_path):
    bundle_id = _make_bundle(tmp_path)
    initial = J.start(tmp_path, bundle_id, "zip", scope="disabled", doc_ids=["D10", "D2"])
    ready = _wait_state(tmp_path, bundle_id, initial["id"], "ready")
    artifact, filename = J.result(tmp_path, bundle_id, initial["id"])

    assert ready["completed"] == ready["total"] == 2
    assert filename.endswith("-selected.zip")
    with zipfile.ZipFile(artifact) as zf:
        names = zf.namelist()
    assert names == ["original/D2.png", "ao_extract/D2.json", "golden/D2.json",
                     "original/D10.png", "ao_extract/D10.json", "golden/D10.json"]


def test_xlsx_export_skips_page_count_work_but_doc_detail_keeps_it(tmp_path, monkeypatch):
    bundle_id = _make_bundle(tmp_path, ids=("D1",))
    calls = []

    def page_count(path):
        calls.append(path)
        return 3

    monkeypatch.setattr(E.B, "page_count", page_count)
    detail = E.B.doc_detail(tmp_path, bundle_id, "D1")
    assert detail["pages"] == {"original": 3, "preprocessed": 0}
    assert len(calls) == 1

    calls.clear()
    artifact = E.export_golden_xlsx(tmp_path, bundle_id)
    assert artifact[:2] == b"PK"
    assert calls == []


def test_job_state_and_result_are_visible_in_another_process(tmp_path):
    bundle_id = _make_bundle(tmp_path, ids=("D1",))
    queued = J.start(tmp_path, bundle_id, "xlsx")
    _wait_state(tmp_path, bundle_id, queued["id"], "ready")

    ctx = multiprocessing.get_context("fork")
    out = ctx.Queue()
    child = ctx.Process(target=_read_status_child, args=(str(tmp_path), bundle_id, queued["id"], out))
    child.start()
    child.join(5)
    assert child.exitcode == 0
    assert out.get(timeout=1)["state"] == "ready"
    artifact, filename = J.result(tmp_path, bundle_id, queued["id"])
    assert artifact.is_file() and filename.endswith("-golden.xlsx")


def test_unknown_job_and_invalid_selection_fail_before_queueing(tmp_path):
    bundle_id = _make_bundle(tmp_path, ids=("D1",))
    with pytest.raises(ApiError) as error:
        J.start(tmp_path, bundle_id, "xlsx", doc_ids=[])
    assert error.value.status == 422
    with pytest.raises(ApiError) as error:
        J.start(tmp_path, bundle_id, "xlsx", doc_ids=["missing"])
    assert error.value.status == 404
    with pytest.raises(ApiError) as error:
        J.status(tmp_path, bundle_id, "missing")
    assert error.value.status == 404


def test_orphaned_jobs_do_not_fill_global_queue_after_worker_restart(tmp_path, monkeypatch):
    bundle_id = _make_bundle(tmp_path, ids=("D1",))
    monkeypatch.setattr(J, "_MAX_PENDING_EXPORTS", 1)
    old_id = "f" * 24
    old_dir = J._bundle_job_root(tmp_path, bundle_id) / old_id
    old_dir.mkdir(parents=True)
    J._write_state(old_dir, {
        "id": old_id, "state": "running", "completed": 0, "total": 1,
        "phase": "writing", "message": "stale", "filename": "stale.zip",
        "format": "zip", "scope": "enabled", "doc_ids": ["D1"],
        "owner_pid": 2_000_000_000,
    })

    queued = J.start(tmp_path, bundle_id, "zip")

    assert J.status(tmp_path, bundle_id, old_id)["state"] == "failed"
    assert queued["state"] in ("queued", "running", "ready")
    J.cancel(tmp_path, bundle_id, queued["id"])


def test_cancel_running_job_removes_partial_artifact(tmp_path, monkeypatch):
    bundle_id = _make_bundle(tmp_path, ids=("D1",))
    entered = Event()
    release = Event()

    def wait_for_cancel(data_dir, bundle_id, **kwargs):
        entered.set()
        assert release.wait(5)
        if kwargs["cancel_check"]():
            raise E.ExportCancelled("export cancelled")
        kwargs["progress"](1, 1, "writing")
        return None

    monkeypatch.setattr(J.E, "export_bundle_zip", wait_for_cancel)
    queued = J.start(tmp_path, bundle_id, "zip")
    assert entered.wait(5)
    ctx = multiprocessing.get_context("fork")
    out = ctx.Queue()
    child = ctx.Process(target=_cancel_child, args=(str(tmp_path), bundle_id, queued["id"], out))
    child.start()
    child.join(5)
    assert child.exitcode == 0
    cancelled = out.get(timeout=1)
    assert cancelled["state"] == "cancelled"
    release.set()

    state = _wait_state(tmp_path, bundle_id, queued["id"], "cancelled")
    job_dir = J._job_dir(tmp_path, bundle_id, queued["id"])
    assert not (job_dir / "artifact.part").exists()
    with pytest.raises(ApiError) as error:
        J.result(tmp_path, bundle_id, queued["id"])
    assert error.value.status == 409


def test_cancel_ready_job_keeps_handed_off_artifact_but_prevents_new_download(tmp_path):
    bundle_id = _make_bundle(tmp_path, ids=("D1",))
    queued = J.start(tmp_path, bundle_id, "zip")
    _wait_state(tmp_path, bundle_id, queued["id"], "ready")
    artifact, _ = J.result(tmp_path, bundle_id, queued["id"])
    assert artifact.is_file()

    cancelled = J.cancel(tmp_path, bundle_id, queued["id"])
    assert cancelled["state"] == "cancelled"
    # A FileResponse may not have opened the returned path yet. Keep the inode
    # available to that in-flight response and let normal TTL cleanup remove it.
    assert artifact.exists()
    J.cancel(tmp_path, bundle_id, queued["id"])
    assert artifact.exists()
    with pytest.raises(ApiError) as error:
        J.result(tmp_path, bundle_id, queued["id"])
    assert error.value.status == 409


@pytest.mark.parametrize("fmt,exporter", [("zip", E.export_bundle_zip), ("xlsx", E.export_golden_xlsx)])
def test_export_progress_hooks_include_finalizing_phase(tmp_path, fmt, exporter):
    bundle_id = _make_bundle(tmp_path, ids=("D1", "D2"))
    events = []
    out = io.BytesIO()
    result = exporter(tmp_path, bundle_id, ids=["D2"], progress=lambda *event: events.append(event),
                      cancel_check=lambda: False, out=out)

    assert result is None
    assert out.getbuffer().nbytes > 0
    assert events[0] == (0, 1, "preparing")
    assert events[-1] == (1, 1, "finalizing")
    assert any(phase == "writing" for _, _, phase in events)


def test_cancel_queued_job_before_worker_starts(tmp_path, monkeypatch):
    bundle_id = _make_bundle(tmp_path, ids=("D1",))
    entered = Event()
    release = Event()
    original = J._slot_lock

    def hold_slot(data_dir):
        entered.set()
        release.wait(5)
        return original(data_dir)

    monkeypatch.setattr(J, "_slot_lock", hold_slot)
    queued = J.start(tmp_path, bundle_id, "xlsx")
    assert entered.wait(5)
    assert J.cancel(tmp_path, bundle_id, queued["id"])["state"] == "cancelled"
    release.set()
    assert _wait_state(tmp_path, bundle_id, queued["id"], "cancelled")["state"] == "cancelled"
    assert not list(J._job_dir(tmp_path, bundle_id, queued["id"]).glob("artifact.*"))


def test_progress_reporter_throttles_writes_and_always_flushes_final_phase(tmp_path, monkeypatch):
    writes = []
    clock = [0.0]
    monkeypatch.setattr(J, "_update_progress", lambda _job_dir, *event: writes.append(event))
    reporter = J._ProgressReporter(tmp_path, interval=0.5, clock=lambda: clock[0])

    reporter(0, 200, "preparing")
    for completed in range(1, 201):
        clock[0] += 0.01
        reporter(completed, 200, "writing")
    reporter(200, 200, "finalizing")

    assert writes[0] == (0, 200, "preparing")
    assert writes[-1] == (200, 200, "finalizing")
    assert len(writes) <= 6


def test_xlsx_checks_cancellation_inside_a_large_document(tmp_path, monkeypatch):
    bundle_id = _make_bundle(tmp_path, ids=("D1",))
    detail = {
        "score": {"ao": None, "harness": None},
        "classification": {"ao": None, "harness": None},
        "doc_type": "", "review": "",
        "golden": {"documents": [{"extracted_fields": [
            {"key": f"field-{i}", "value": "value", "dtype": "string"} for i in range(1000)
        ], "extracted_groups": [], "extracted_tables": []}]},
        "compare": [],
    }
    monkeypatch.setattr(E.B, "doc_detail", lambda *_args, **_kwargs: detail)
    checks = [0]

    def cancel_after_a_few_rows():
        checks[0] += 1
        return checks[0] >= 4

    with pytest.raises(E.ExportCancelled):
        E.export_golden_xlsx(tmp_path, bundle_id, cancel_check=cancel_after_a_few_rows)
    assert checks[0] == 4
