"""Migration integration tests; require LABEL_VIEWER_TEST_DATABASE_URL."""
from __future__ import annotations

import json
import os
import stat
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import bundle as B
from backend import db as DB
from backend import migration as M
from backend.golden_history import golden_revision, history_dir


@pytest.fixture
def pg_root(tmp_path, monkeypatch):
    dsn = os.environ.get("LABEL_VIEWER_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("LABEL_VIEWER_TEST_DATABASE_URL is not configured")
    namespace = f"migration-test:{uuid.uuid4()}"
    monkeypatch.setenv("LABEL_VIEWER_DATABASE_URL", dsn)
    monkeypatch.setenv("LABEL_VIEWER_DB_NAMESPACE", namespace)
    DB.initialize()
    yield tmp_path
    with DB.connection() as conn:
        conn.execute("DELETE FROM bundles WHERE namespace=%s", (namespace,))
        conn.execute("DELETE FROM metadata_imports WHERE namespace=%s", (namespace,))


def _legacy_bundle(data_dir: Path, bundle_id: str = "legacy") -> Path:
    bdir = data_dir / "bundles" / bundle_id
    (bdir / "original").mkdir(parents=True)
    (bdir / "original" / "doc.png").write_bytes(b"image")
    (bdir / "_state.json").write_text(json.dumps({
        "name": "Imported name", "created_at": "2026-10-01T00:00:00+00:00",
        "review": {"doc": "progress"}, "disabled": [], "custom": {"keep": True},
    }), encoding="utf-8")
    return bdir


def test_import_rerun_preserves_database_edits(pg_root):
    data_dir = pg_root
    bdir = _legacy_bundle(data_dir)
    first = M.import_files(data_dir)
    assert first["bundles"] == 1
    B.update_state(bdir, lambda state: state.update(name="Database edited", review={"doc": "done"}))

    second = M.import_files(data_dir)

    assert second["bundles"] == 0
    state = B.load_state(bdir)
    assert state["name"] == "Database edited"
    assert state["review"] == {"doc": "done"}
    assert state["custom"] == {"keep": True}


def test_history_import_export_preserves_raw_bytes_and_checksums(pg_root):
    data_dir = pg_root
    bdir = _legacy_bundle(data_dir)
    doc_id = "문서 (1)"
    raw = b'\xef\xbb\xbf{"documents":[]}'
    hid = "20260101T000000000000Z-a1b2c3d4"
    metadata = {"id": hid, "created_at": "2026-01-01T00:00:00+00:00",
                "action": "baseline", "revision": golden_revision(raw), "has_golden": True}
    directory = history_dir(bdir, doc_id)
    directory.mkdir(parents=True)
    (directory / f"{hid}.json").write_bytes(raw)
    (directory / f"{hid}.meta.json").write_text(json.dumps(metadata), encoding="utf-8")

    imported = M.import_files(data_dir)
    snapshot = DB.read_golden_history(data_dir, "legacy", doc_id, hid)
    assert imported["history"] == 1
    assert snapshot is not None and snapshot[1] == raw

    (directory / f"{hid}.json").unlink()
    exported = M.export_files(data_dir)

    assert exported["history"] == 1
    assert (directory / f"{hid}.json").read_bytes() == raw
    assert json.loads((directory / f"{hid}.meta.json").read_text(encoding="utf-8")) == metadata


def test_export_preflights_all_bundle_paths_before_writing_any_state(tmp_path, monkeypatch):
    present = tmp_path / "bundles" / "a-present"
    present.mkdir(parents=True)
    state_path = present / "_state.json"
    state_path.write_bytes(b"preserve this file if any bundle is missing")

    class Cursor:
        def fetchall(self):
            return [("a-present",), ("z-missing",)]

    class Connection:
        def execute(self, query, _params):
            assert query.startswith("SELECT bundle_id FROM bundles")
            return Cursor()

    @contextmanager
    def fake_lock(*_args, **_kwargs):
        yield True

    @contextmanager
    def fake_connection():
        yield Connection()

    monkeypatch.setattr(DB, "enabled", lambda: True)
    monkeypatch.setattr(DB, "namespace", lambda _data_dir: "test")
    monkeypatch.setattr(DB, "lock", fake_lock)
    monkeypatch.setattr(DB, "connection", fake_connection)
    monkeypatch.setattr(DB, "read_bundle_state", lambda bdir: {"name": bdir.name})

    with pytest.raises(RuntimeError, match="Bundle files are missing"):
        M.export_files(tmp_path)

    assert state_path.read_bytes() == b"preserve this file if any bundle is missing"


def test_import_fails_queued_jobs_and_rerun_does_not_resurrect_them(pg_root):
    data_dir = pg_root
    _legacy_bundle(data_dir)
    job_id = "job-one"
    job_path = data_dir / ".cache" / "export-jobs" / "legacy" / job_id / "job.json"
    job_path.parent.mkdir(parents=True)
    job = {"id": job_id, "state": "queued", "phase": "queued", "completed": 0, "total": 1}
    job_path.write_text(json.dumps(job), encoding="utf-8")

    M.import_files(data_dir)
    with DB.connection() as conn:
        row = conn.execute("SELECT state FROM export_jobs WHERE namespace=%s AND bundle_id=%s AND id=%s",
                           (DB.namespace(data_dir), "legacy", job_id)).fetchone()
    assert row[0]["state"] == "failed"

    with DB.connection() as conn:
        conn.execute("UPDATE export_jobs SET state=%s WHERE namespace=%s AND bundle_id=%s AND id=%s",
                     (json.dumps({**row[0], "state": "cancelled"}), DB.namespace(data_dir), "legacy", job_id))
    M.import_files(data_dir)
    with DB.connection() as conn:
        state = conn.execute("SELECT state FROM export_jobs WHERE namespace=%s AND bundle_id=%s AND id=%s",
                             (DB.namespace(data_dir), "legacy", job_id)).fetchone()[0]
    assert state["state"] == "cancelled"


def test_database_outage_returns_503_without_state_file_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("LABEL_VIEWER_DATABASE_URL", "postgresql://bad:bad@127.0.0.1:1/bad?connect_timeout=1")
    monkeypatch.setenv("LABEL_VIEWER_DB_NAMESPACE", f"outage:{uuid.uuid4()}")
    monkeypatch.setattr(M, "import_files", lambda _data_dir, **_kwargs: {})
    bdir = tmp_path / "bundles" / "legacy"
    bdir.mkdir(parents=True)
    (bdir / "_state.json").write_text('{"name":"stale file"}', encoding="utf-8")

    from backend.app import create_app
    client = TestClient(create_app(tmp_path))

    assert client.get("/api/health").status_code == 503
    assert client.get("/api/bundles/legacy").status_code == 503


def test_saved_database_configuration_has_private_permissions(pg_root, monkeypatch):
    with monkeypatch.context() as patch_env:
        patch_env.setenv("LABEL_VIEWER_DATABASE_URL", "postgresql://user:secret@localhost/database")
        patch_env.setenv("LABEL_VIEWER_DB_NAMESPACE", f"saved:{uuid.uuid4()}")
        expected_namespace = DB.namespace(pg_root)
        M.save_configuration(pg_root)

    config = pg_root / "_database.json"
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert json.loads(config.read_text(encoding="utf-8"))["namespace"] == expected_namespace


def test_local_configuration_preserves_namespace_with_explicit_database_url(tmp_path, monkeypatch):
    config = tmp_path / '_database.json'
    config.write_text(json.dumps({'url': 'postgresql://saved/db', 'namespace': 'dataset-one'}))
    monkeypatch.setenv('LABEL_VIEWER_DATABASE_URL', 'postgresql://explicit/db')
    monkeypatch.delenv('LABEL_VIEWER_DB_NAMESPACE', raising=False)
    M.configure_from_file(tmp_path)
    assert os.environ['LABEL_VIEWER_DATABASE_URL'] == 'postgresql://explicit/db'
    assert DB.namespace(tmp_path) == 'dataset-one'
    monkeypatch.setenv('LABEL_VIEWER_DB_NAMESPACE', 'explicit-dataset')
    M.configure_from_file(tmp_path)
    assert DB.namespace(tmp_path) == 'explicit-dataset'


def test_bootstrap_marker_skips_obsolete_files_without_resurrecting_deleted_jobs(pg_root):
    bdir = _legacy_bundle(pg_root)
    assert M.import_files(pg_root, only_if_needed=True)['bundles'] == 1
    (bdir / '_state.json').write_text('broken old state', encoding='utf-8')
    job = pg_root / '.cache/export-jobs/legacy/stale-job/job.json'
    job.parent.mkdir(parents=True)
    job.write_text('{"id":"stale-job","state":"ready"}')
    assert M.import_files(pg_root, only_if_needed=True) == {'bundles': 0, 'history': 0, 'jobs': 0}
    with DB.connection() as conn:
        assert conn.execute('SELECT count(*) FROM export_jobs WHERE namespace=%s', (DB.namespace(pg_root),)).fetchone()[0] == 0


def test_failed_import_does_not_mark_namespace_complete(pg_root):
    bdir = _legacy_bundle(pg_root)
    (bdir / '_state.json').write_text('broken')
    with pytest.raises(ValueError):
        M.import_files(pg_root, only_if_needed=True)
    with DB.connection() as conn:
        assert conn.execute('SELECT 1 FROM metadata_imports WHERE namespace=%s', (DB.namespace(pg_root),)).fetchone() is None
