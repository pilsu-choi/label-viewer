"""PostgreSQL export job coverage; requires LABEL_VIEWER_TEST_DATABASE_URL."""
from __future__ import annotations

import io
import json
import multiprocessing
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, enumerate as enumerate_threads

import pytest

from backend import bundle as B
from backend import db as DB
from backend import export as E
from backend import export_jobs as J
from backend.bundle import ApiError, process_upload


@pytest.fixture
def pg_data_dir(tmp_path, monkeypatch):
    dsn = os.environ.get("LABEL_VIEWER_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("LABEL_VIEWER_TEST_DATABASE_URL is not configured")
    monkeypatch.setenv("LABEL_VIEWER_DATABASE_URL", dsn)
    namespace = f"test:exports:{uuid.uuid4()}"
    monkeypatch.setenv("LABEL_VIEWER_DB_NAMESPACE", namespace)
    DB.initialize()
    yield tmp_path
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and any(t.name.startswith("export-") for t in enumerate_threads()):
        time.sleep(0.02)
    assert not any(t.name.startswith("export-") for t in enumerate_threads()), "export worker leaked past test"
    with DB.connection() as conn:
        conn.execute("DELETE FROM bundles WHERE namespace=%s", (namespace,))


def _make_bundle(data_dir: Path, ids=("D1",)) -> str:
    files = []
    for doc_id in ids:
        raw = json.dumps({"documents": [{"doc_type": "", "extracted_fields": [],
                                          "extracted_groups": [], "extracted_tables": []}]}).encode()
        files.extend([
            (f"batch/original/{doc_id}.png", io.BytesIO(b"image-bytes")),
            (f"batch/ao_extract/{doc_id}.aiocr.json", io.BytesIO(raw)),
            (f"batch/golden/{doc_id}.answer.json", io.BytesIO(raw)),
        ])
    return process_upload(data_dir, files, "Postgres export test", 1_000_000)


def _child_status(data_dir: str, bundle_id: str, job_id: str, out) -> None:
    from backend import export_jobs
    out.put(export_jobs.status(Path(data_dir), bundle_id, job_id))


def _child_cancel(data_dir: str, bundle_id: str, job_id: str, out) -> None:
    from backend import export_jobs
    out.put(export_jobs.cancel(Path(data_dir), bundle_id, job_id))


def _child_hold_slot(data_dir: str, ready, release, acquired_out) -> None:
    from backend import export_jobs
    slot = export_jobs._slot_lock(Path(data_dir))
    acquired_out.put(slot is not None)
    ready.set()
    if slot is not None:
        release.wait(10)
        export_jobs._release_slot(slot)


def _wait_state(data_dir: Path, bundle_id: str, job_id: str, wanted: str, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = J.status(data_dir, bundle_id, job_id)
        if state["state"] == wanted:
            return state
        if state["state"] in ("failed", "cancelled"):
            pytest.fail(f"job entered unexpected terminal state: {state}")
        time.sleep(0.03)
    pytest.fail(f"job did not reach {wanted}")


def test_job_state_is_persistent_and_visible_from_another_worker(pg_data_dir):
    bundle_id = _make_bundle(pg_data_dir)
    started = J.start(pg_data_dir, bundle_id, "zip")
    _wait_state(pg_data_dir, bundle_id, started["id"], "ready")

    context = multiprocessing.get_context("fork")
    out = context.Queue()
    child = context.Process(target=_child_status,
                            args=(str(pg_data_dir), bundle_id, started["id"], out))
    child.start()
    child.join(10)
    assert child.exitcode == 0
    assert out.get(timeout=2)["state"] == "ready"
    artifact, _filename = J.result(pg_data_dir, bundle_id, started["id"])
    assert artifact.is_file()


def test_cancel_from_another_worker_stops_running_export(pg_data_dir, monkeypatch):
    bundle_id = _make_bundle(pg_data_dir)
    entered, release = Event(), Event()

    def held_export(_data_dir, _bundle_id, **kwargs):
        entered.set()
        assert release.wait(10)
        if kwargs["cancel_check"]():
            raise E.ExportCancelled("cancelled")
        return None

    monkeypatch.setattr(J.E, "export_bundle_zip", held_export)
    started = J.start(pg_data_dir, bundle_id, "zip")
    assert entered.wait(5)

    context = multiprocessing.get_context("fork")
    out = context.Queue()
    child = context.Process(target=_child_cancel,
                            args=(str(pg_data_dir), bundle_id, started["id"], out))
    child.start()
    child.join(10)
    assert child.exitcode == 0
    assert out.get(timeout=2)["state"] == "cancelled"
    release.set()
    assert _wait_state(pg_data_dir, bundle_id, started["id"], "cancelled")["state"] == "cancelled"
    assert not list(J._job_dir(pg_data_dir, bundle_id, started["id"]).glob("artifact.*"))


def test_global_database_slots_limit_concurrent_workers(pg_data_dir):
    context = multiprocessing.get_context("fork")
    processes = []
    releases = []
    try:
        for _ in range(2):
            ready, release, result = context.Event(), context.Event(), context.Queue()
            process = context.Process(target=_child_hold_slot,
                                      args=(str(pg_data_dir), ready, release, result))
            process.start()
            processes.append(process)
            releases.append(release)
            assert ready.wait(5)
            assert result.get(timeout=2) is True
        assert J._slot_lock(pg_data_dir) is None
    finally:
        for release in releases:
            release.set()
        for process in processes:
            process.join(10)
    assert all(process.exitcode == 0 for process in processes)
    slot = J._slot_lock(pg_data_dir)
    assert slot is not None
    J._release_slot(slot)


def test_stale_database_lease_fails_job_and_releases_pending_quota(pg_data_dir, monkeypatch):
    bundle_id = _make_bundle(pg_data_dir)
    monkeypatch.setattr(J, "_MAX_PENDING_EXPORTS", 1)
    old_id = "f" * 24
    job_dir = J._bundle_job_root(pg_data_dir, bundle_id) / old_id
    job_dir.mkdir(parents=True)
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=J._LEASE_SECONDS + 10)).isoformat()
    J._write_state(job_dir, {
        "id": old_id, "state": "running", "completed": 0, "total": 1,
        "phase": "writing", "message": "stale", "filename": "old.zip",
        "format": "zip", "scope": "enabled", "doc_ids": ["D1"],
        "owner_token": "dead-worker", "owner_host": "unavailable-host",
        "created_at": stale_time, "heartbeat_at": stale_time,
    }, create=True)

    started = J.start(pg_data_dir, bundle_id, "zip")
    assert J.status(pg_data_dir, bundle_id, old_id)["state"] == "failed"
    with pytest.raises(E.ExportCancelled):
        J._update_progress(job_dir, 1, 1, "writing")
    assert J.status(pg_data_dir, bundle_id, old_id)["state"] == "failed"
    assert started["state"] in ("queued", "running", "ready")
    J.cancel(pg_data_dir, bundle_id, started["id"])


def test_failure_message_does_not_expose_database_error_text(pg_data_dir, monkeypatch):
    bundle_id = _make_bundle(pg_data_dir)

    def fail(*_args, **_kwargs):
        raise RuntimeError("postgresql://user:secret@db.example/private")

    monkeypatch.setattr(J.E, "export_bundle_zip", fail)
    started = J.start(pg_data_dir, bundle_id, "zip")
    state = _wait_state(pg_data_dir, bundle_id, started["id"], "failed")
    assert "secret" not in state["message"]
    assert "db.example" not in state["message"]


def test_export_job_requires_registered_bundle_foreign_key(pg_data_dir):
    with pytest.raises(ApiError) as error:
        J.start(pg_data_dir, "missing-bundle", "zip")
    assert error.value.status == 404


def test_deleting_bundle_during_export_does_not_recreate_job_row(pg_data_dir, monkeypatch):
    entered, release, finished = Event(), Event(), Event()
    bundle_id = _make_bundle(pg_data_dir)

    def export_then_touch_progress(_data_dir, _bundle_id, **kwargs):
        entered.set()
        try:
            assert release.wait(10)
            kwargs["progress"](1, 1, "writing")
        finally:
            finished.set()

    monkeypatch.setattr(J.E, "export_bundle_zip", export_then_touch_progress)
    started = J.start(pg_data_dir, bundle_id, "zip")
    assert entered.wait(5)

    B.delete_bundle(pg_data_dir, bundle_id)
    release.set()
    assert finished.wait(5)
    deadline = time.monotonic() + 5
    thread_name = f"export-{started['id']}"
    while time.monotonic() < deadline and any(t.name == thread_name for t in enumerate_threads()):
        time.sleep(0.02)

    assert not any(t.name == thread_name for t in enumerate_threads())
    with DB.connection() as conn:
        assert conn.execute("SELECT count(*) FROM export_jobs WHERE namespace=%s AND bundle_id=%s AND id=%s",
                            (DB.namespace(pg_data_dir), bundle_id, started["id"])).fetchone()[0] == 0


def test_shutdown_cancels_and_joins_owned_export_workers(pg_data_dir, monkeypatch):
    entered = Event()

    def cooperative_export(_data_dir, _bundle_id, **kwargs):
        entered.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if kwargs["cancel_check"]():
                raise E.ExportCancelled("cancelled")
            time.sleep(0.01)
        pytest.fail("shutdown did not make cancellation visible")

    bundle_id = _make_bundle(pg_data_dir)
    monkeypatch.setattr(J.E, "export_bundle_zip", cooperative_export)
    started = J.start(pg_data_dir, bundle_id, "zip")
    assert entered.wait(5)

    J.shutdown(pg_data_dir)

    assert J.status(pg_data_dir, bundle_id, started["id"])["state"] == "cancelled"
    assert not any(t.name == f"export-{started['id']}" for t in enumerate_threads())
    with pytest.raises(ApiError) as error:
        J.start(pg_data_dir, bundle_id, "zip")
    assert error.value.status == 503
    J.startup(pg_data_dir)
    monkeypatch.setattr(J.E, "export_bundle_zip", lambda *_args, **_kwargs: None)
    restarted = J.start(pg_data_dir, bundle_id, "zip")
    assert _wait_state(pg_data_dir, bundle_id, restarted["id"], "ready")["state"] == "ready"


def test_fast_many_document_progress_coalesces_database_updates(pg_data_dir, monkeypatch):
    bundle_id = _make_bundle(pg_data_dir, ids=tuple(f"D{i:03}" for i in range(200)))
    progress_writes = []
    original_update = J._update_progress

    def count_progress(job_dir, completed, total, phase):
        progress_writes.append((completed, total, phase))
        return original_update(job_dir, completed, total, phase)

    def fast_export(_data_dir, _bundle_id, **kwargs):
        ids = kwargs["ids"]
        total = len(ids)
        kwargs["progress"](0, total, "preparing")
        for completed in range(1, total + 1):
            kwargs["progress"](completed, total, "writing")
        kwargs["progress"](total, total, "finalizing")

    monkeypatch.setattr(J, "_update_progress", count_progress)
    monkeypatch.setattr(J.E, "export_bundle_zip", fast_export)
    started = J.start(pg_data_dir, bundle_id, "zip")
    state = _wait_state(pg_data_dir, bundle_id, started["id"], "ready")

    assert state["completed"] == state["total"] == 200
    assert progress_writes[0] == (0, 200, "preparing")
    assert progress_writes[-1] == (200, 200, "finalizing")
    assert len(progress_writes) <= 3


def test_xlsx_reads_bundle_review_state_once_for_200_documents(pg_data_dir, monkeypatch):
    bundle_id = _make_bundle(pg_data_dir, ids=tuple(f"D{i:03}" for i in range(200)))
    state_reads = []
    original_load_state = B.load_state

    def counted_load_state(bdir):
        state_reads.append(bdir)
        return original_load_state(bdir)

    monkeypatch.setattr(B, "load_state", counted_load_state)
    result = E.export_golden_xlsx(pg_data_dir, bundle_id)

    assert result and result.startswith(b"PK")
    assert len(state_reads) == 1


def test_ttl_cleanup_removes_old_job_files_without_database_rows(pg_data_dir):
    bundle_id = _make_bundle(pg_data_dir)
    stale = J._bundle_job_root(pg_data_dir, bundle_id) / "orphaned-job"
    stale.mkdir(parents=True)
    marker = stale / "artifact.part"
    marker.write_bytes(b"partial")
    old = time.time() - J._JOB_TTL_SECONDS - 5
    os.utime(marker, (old, old))

    J._cleanup_expired(J._root(pg_data_dir), pg_data_dir)

    assert not stale.exists()


def test_lost_heartbeat_lease_stops_worker_before_publish(pg_data_dir, monkeypatch):
    entered = Event()
    monkeypatch.setattr(J, "_LEASE_SECONDS", 0.15)
    monkeypatch.setattr(J, "_HEARTBEAT_SECONDS", 0.02)

    def wait_for_lease_loss(_data_dir, _bundle_id, **kwargs):
        entered.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if kwargs["cancel_check"]():
                raise E.ExportCancelled("lease lost")
            time.sleep(0.01)
        pytest.fail("heartbeat loss did not stop exporter")

    bundle_id = _make_bundle(pg_data_dir)
    monkeypatch.setattr(J.E, "export_bundle_zip", wait_for_lease_loss)
    started = J.start(pg_data_dir, bundle_id, "zip")
    assert entered.wait(5)

    original_pool = DB._pool_for_current_process

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("temporary database outage")

    monkeypatch.setattr(DB, "_pool_for_current_process", unavailable)
    deadline = time.monotonic() + 5
    thread_name = f"export-{started['id']}"
    while time.monotonic() < deadline and any(t.name == thread_name for t in enumerate_threads()):
        time.sleep(0.02)
    monkeypatch.setattr(DB, "_pool_for_current_process", original_pool)

    assert not any(t.name == thread_name for t in enumerate_threads())
    state = J.status(pg_data_dir, bundle_id, started["id"])
    assert state["state"] == "failed"
    assert not list(J._job_dir(pg_data_dir, bundle_id, started["id"]).glob("artifact.*"))
