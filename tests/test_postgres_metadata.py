"""PostgreSQL integration coverage; skipped unless LABEL_VIEWER_TEST_DATABASE_URL is set."""
from __future__ import annotations

import io
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import db as DB
from backend import bundle as B


@pytest.fixture
def postgres_namespace(tmp_path, monkeypatch):
    dsn = os.environ.get("LABEL_VIEWER_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("LABEL_VIEWER_TEST_DATABASE_URL is not configured")
    monkeypatch.setenv("LABEL_VIEWER_DATABASE_URL", dsn)
    ns = f"test:{uuid.uuid4()}"
    monkeypatch.setenv("LABEL_VIEWER_DB_NAMESPACE", ns)
    DB.initialize()
    yield tmp_path
    with DB.connection() as conn:
        conn.execute("DELETE FROM bundles WHERE namespace=%s", (ns,))


def _upload(data_dir: Path) -> str:
    return B.process_upload(data_dir, [("batch/original/doc.png", io.BytesIO(b"image"))], None, 1_000_000)


def _golden(value: str) -> dict:
    return {"documents": [{"extracted_fields": [{"key": "field", "value": value}],
                           "extracted_groups": [], "extracted_tables": []}]}


def test_state_round_trips_through_database_and_ignores_stale_file(postgres_namespace):
    data_dir = postgres_namespace
    bid = _upload(data_dir)
    bdir = B.bundle_dir(data_dir, bid)
    B.update_state(bdir, lambda state: (state.setdefault("review", {}).update(doc="done"),
                                        state.setdefault("disabled", []).append("doc")))

    # DB mode treats the database as authoritative, even if an old state file exists.
    (bdir / "_state.json").write_text('{"name":"stale","review":{}}', encoding="utf-8")
    state = B.load_state(bdir)

    assert state["review"] == {"doc": "done"}
    assert state["disabled"] == ["doc"]
    assert state["name"] != "stale"
    assert B.scope_doc_ids(data_dir, bid, "disabled") == ["doc"]


def test_nested_connection_reuses_context_connection(postgres_namespace):
    with DB.connection() as outer:
        with DB.connection() as inner:
            assert inner is outer
            assert inner.execute("SELECT 1").fetchone() == (1,)


def test_golden_history_is_transactional_database_backed_and_cascades(postgres_namespace):
    data_dir = postgres_namespace
    bid = _upload(data_dir)
    initial = B.save_golden(data_dir, bid, "doc", _golden("initial"), "missing")
    edited = B.save_golden(data_dir, bid, "doc", _golden("edited"), initial["golden_revision"])
    history = B.list_golden_history(data_dir, bid, "doc")
    assert history["golden_revision"] == edited["golden_revision"]
    assert [item["action"] for item in history["items"]] == ["save", "save", "baseline"]

    # The first save from an absent Golden archives its missing baseline.
    snapshot = B.get_golden_history(data_dir, bid, "doc", history["items"][-1]["id"])
    assert snapshot["golden"] is None

    B.delete_bundle(data_dir, bid)
    with DB.connection() as conn:
        assert conn.execute("SELECT count(*) FROM bundles WHERE namespace=%s AND bundle_id=%s",
                            (DB.namespace(data_dir), bid)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM golden_history WHERE namespace=%s AND bundle_id=%s",
                            (DB.namespace(data_dir), bid)).fetchone()[0] == 0


def test_golden_commit_failure_rolls_back_before_releasing_distributed_lock(postgres_namespace, monkeypatch):
    data_dir = postgres_namespace
    bid = _upload(data_dir)
    initial = B.save_golden(data_dir, bid, "doc", _golden("initial"), "missing")
    path = data_dir / "bundles" / bid / "golden" / "doc.json"
    original = path.read_bytes()
    lock_depth = 0

    @contextmanager
    def session_lock(_data_dir, _resource, shared=False, blocking=True):
        nonlocal lock_depth
        lock_depth += 1
        try:
            yield True
        finally:
            assert lock_depth > 0
            assert path.read_bytes() == original
            lock_depth -= 1

    @contextmanager
    def failed_commit():
        yield object()
        raise RuntimeError("commit failed")

    with monkeypatch.context() as patcher:
        patcher.setattr(DB, "session_lock", session_lock)
        patcher.setattr(DB, "connection", failed_commit)
        patcher.setattr(B, "list_snapshots", lambda *_args, **_kwargs: [])
        patcher.setattr(B, "archive_snapshot", lambda *_args, **_kwargs: {})
        patcher.setattr(B, "_doc_detail_unlocked", lambda *_args, **_kwargs: {})
        with pytest.raises(RuntimeError, match="commit failed"):
            B.save_golden(data_dir, bid, "doc", _golden("uncommitted"), initial["golden_revision"])

    assert lock_depth == 0
    assert path.read_bytes() == original


def test_bundle_delete_restores_directory_if_database_delete_fails(postgres_namespace, monkeypatch):
    data_dir = postgres_namespace
    bid = _upload(data_dir)
    bdir = B.bundle_dir(data_dir, bid)

    def fail_delete(_data_dir, _bundle_id):
        raise RuntimeError("database delete failed")

    monkeypatch.setattr(DB, "delete_bundle", fail_delete)
    with pytest.raises(RuntimeError, match="database delete failed"):
        B.delete_bundle(data_dir, bid)

    assert bdir.is_dir()
    assert B.load_state(bdir)["name"] == "batch"


def test_upload_removes_files_if_database_metadata_insert_fails(postgres_namespace, monkeypatch):
    data_dir = postgres_namespace
    bid = "failed-upload"
    monkeypatch.setattr(B, "new_bundle_id", lambda: bid)
    monkeypatch.setattr(B, "save_state", lambda *_args: (_ for _ in ()).throw(RuntimeError("DB insert failed")))

    with pytest.raises(RuntimeError, match="DB insert failed"):
        B.process_upload(data_dir, [("batch/original/doc.png", io.BytesIO(b"image"))], None, 1_000_000)

    assert not B.bundle_dir(data_dir, bid).exists()


def test_upload_id_collision_leaves_existing_bundle_and_metadata_intact(postgres_namespace, monkeypatch):
    data_dir = postgres_namespace
    bid = _upload(data_dir)
    bdir = B.bundle_dir(data_dir, bid)
    original_image = (bdir / "original" / "doc.png").read_bytes()
    original_state = B.load_state(bdir)
    monkeypatch.setattr(B, "new_bundle_id", lambda: bid)

    with pytest.raises(B.ApiError) as error:
        B.process_upload(data_dir, [("other/original/new.png", io.BytesIO(b"new image"))], None, 1_000_000)

    assert error.value.status == 409
    assert (bdir / "original" / "doc.png").read_bytes() == original_image
    assert B.load_state(bdir) == original_state


def test_upload_staging_is_invisible_to_concurrent_bundle_listing(postgres_namespace, monkeypatch):
    data_dir = postgres_namespace
    original = B._write_entries
    stage_ready = threading.Event()
    publish = threading.Event()

    def pause_after_files(bdir, entries, open_src):
        original(bdir, entries, open_src)
        assert bdir.name.startswith(".upload-")
        stage_ready.set()
        assert publish.wait(3)

    monkeypatch.setattr(B, "_write_entries", pause_after_files)
    with ThreadPoolExecutor(max_workers=1) as pool:
        upload = pool.submit(_upload, data_dir)
        assert stage_ready.wait(3)
        assert B.list_bundles(data_dir) == []
        publish.set()
        bid = upload.result(timeout=3)

    assert [item["id"] for item in B.list_bundles(data_dir)] == [bid]


def test_lifecycle_shared_lock_reuses_context_held_lock(postgres_namespace, monkeypatch):
    bdir = postgres_namespace / "bundles" / "test"
    bdir.mkdir(parents=True)
    acquired = []

    @contextmanager
    def session_lock(_data_dir, resource, shared=False, blocking=True):
        acquired.append(resource)
        yield True

    monkeypatch.setattr(DB, "session_lock", session_lock)
    with B._bundle_lifecycle_lock(bdir, shared=True):
        with B._bundle_lifecycle_lock(bdir, shared=True):
            pass

    assert acquired == ["bundle-lifecycle:test"]


def test_delete_unknown_bundle_returns_404_for_empty_data_dir(postgres_namespace):
    with pytest.raises(B.ApiError) as error:
        B.delete_bundle(postgres_namespace, "absent")
    assert error.value.status == 404


def test_bundle_delete_waits_for_golden_save_and_cannot_be_undone_by_rollback(postgres_namespace, monkeypatch):
    data_dir = postgres_namespace
    bid = _upload(data_dir)
    initial = B.save_golden(data_dir, bid, "doc", _golden("initial"), "missing")
    archive_started = threading.Event()
    finish_archive = threading.Event()
    delete_started = threading.Event()
    original_archive = B.archive_snapshot

    def pause_save_archive(bdir, doc_id, raw, action):
        if action == "save":
            archive_started.set()
            assert finish_archive.wait(3)
        return original_archive(bdir, doc_id, raw, action)

    monkeypatch.setattr(B, "archive_snapshot", pause_save_archive)
    with ThreadPoolExecutor(max_workers=2) as pool:
        save = pool.submit(B.save_golden, data_dir, bid, "doc", _golden("saved"), initial["golden_revision"])
        assert archive_started.wait(3)

        def delete():
            delete_started.set()
            B.delete_bundle(data_dir, bid)

        deletion = pool.submit(delete)
        assert delete_started.wait(3)
        time.sleep(0.05)
        assert not deletion.done()
        finish_archive.set()
        save.result(timeout=3)
        deletion.result(timeout=3)

    assert not B.bundle_dir(data_dir, bid).exists()
    with DB.connection() as conn:
        assert conn.execute("SELECT 1 FROM bundles WHERE namespace=%s AND bundle_id=%s",
                            (DB.namespace(data_dir), bid)).fetchone() is None
