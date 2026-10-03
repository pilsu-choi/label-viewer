from __future__ import annotations

import io
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import bundle as B
from backend import db as DB


def _upload(data_dir: Path, name: str, doc_id: str = "doc", *, bad: bool = False) -> str:
    golden = b"{x}" if bad else b"{} "
    return B.process_upload(data_dir, [
        (f"batch/original/{doc_id}.png", io.BytesIO(b"image")),
        (f"batch/golden/{doc_id}.json", io.BytesIO(golden)),
    ], name, 1_000_000)


@pytest.fixture
def file_mode(monkeypatch):
    monkeypatch.setattr(DB, "enabled", lambda: False)
    B._MEMO.clear()
    B._SUM_MEMO.clear()
    B._BUNDLE_SUMMARY_MEMO.clear()


def test_list_limit_counts_only_selected_bundles(tmp_path, file_mode, monkeypatch):
    data_dir = tmp_path / "storage"
    ids = [_upload(data_dir, f"bundle-{i}") for i in range(3)]
    for bid in ids:
        B._BUNDLE_SUMMARY_MEMO.pop(str(B.bundle_dir(data_dir, bid)), None)
        time.sleep(0.015)

    counted = []
    original = B._bundle_file_counts

    def count_one(bdir, manifest, previous=None):
        counted.append(bdir.name)
        return original(bdir, manifest, previous)

    monkeypatch.setattr(B, "_bundle_file_counts", count_one)
    result = B.list_bundles(data_dir, limit=1)
    assert len(result) == 1
    assert counted == [result[0]["id"]]


def test_bundle_page_filters_orders_and_counts_only_the_requested_page(tmp_path, file_mode, monkeypatch):
    data_dir = tmp_path / "storage"
    names = ["zulu", "Beta", "alpha", "beta"]
    ids = [_upload(data_dir, name, f"doc{i}", bad=(i == 2)) for i, name in enumerate(names)]

    counted = []
    original = B._bundle_file_counts

    def count_one(bdir, manifest, previous=None):
        counted.append(bdir.name)
        return original(bdir, manifest, previous)

    monkeypatch.setattr(B, "_bundle_file_counts", count_one)
    page = B.bundle_page(data_dir, sort="name", page=2, page_size=2)
    assert page["total"] == page["filtered_total"] == 4
    assert page["page"] == 2
    assert [row["name"] for row in page["items"]] == ["beta", "zulu"]
    assert set(counted) == {ids[3], ids[0]}

    filtered = B.bundle_page(data_dir, query="ALPHA", page_size=1)
    assert filtered["filtered_total"] == 1
    assert filtered["items"][0]["id"] == ids[2]
    assert filtered["items"][0]["counts"]["error"] == 1


def test_page_clamps_to_last_nonempty_page(tmp_path, file_mode):
    data_dir = tmp_path / "storage"
    ids = [_upload(data_dir, f"bundle-{i}") for i in range(3)]
    result = B.bundle_page(data_dir, page=99, page_size=2)
    assert result["page"] == 2
    assert [row["id"] for row in result["items"]] == [ids[0]]


def test_same_size_json_edit_with_restored_mtime_invalidates_cached_error_count(tmp_path, file_mode):
    data_dir = tmp_path / "storage"
    bid = _upload(data_dir, "edited")
    path = B.bundle_dir(data_dir, bid) / "golden" / "doc.json"
    # Ensure the starting file is valid and that the subsequent invalid edit has
    # exactly the same byte length and mtime.
    path.write_bytes(b"{} ")
    before = path.stat()
    assert B.list_bundles(data_dir)[0]["counts"]["error"] == 0
    path.write_bytes(b"{x}")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    assert path.stat().st_mtime_ns == before.st_mtime_ns
    assert B.list_bundles(data_dir)[0]["counts"]["error"] == 1


@pytest.fixture
def postgres_namespace(tmp_path, monkeypatch):
    import os

    dsn = os.environ.get("LABEL_VIEWER_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("LABEL_VIEWER_TEST_DATABASE_URL is not configured")
    monkeypatch.setenv("LABEL_VIEWER_DATABASE_URL", dsn)
    ns = f"test:bundle-summary:{uuid.uuid4()}"
    monkeypatch.setenv("LABEL_VIEWER_DB_NAMESPACE", ns)
    DB.initialize()
    yield tmp_path
    with DB.connection() as conn:
        conn.execute("DELETE FROM bundles WHERE namespace=%s", (ns,))


def test_postgres_summary_reuses_unchanged_counts_and_refreshes_one_changed_document(
        postgres_namespace, monkeypatch):
    data_dir = postgres_namespace
    bid = B.process_upload(data_dir, [
        ("batch/original/a.png", io.BytesIO(b"a")),
        ("batch/golden/a.json", io.BytesIO(b"{} ")),
        ("batch/original/b.png", io.BytesIO(b"b")),
        ("batch/golden/b.json", io.BytesIO(b"{} ")),
    ], "cache", 1_000_000)

    time.sleep(0.03)  # Let newly written files leave the deliberately uncached mtime window.
    B._MEMO.clear()
    B._BUNDLE_SUMMARY_MEMO.clear()
    B.list_bundles(data_dir)
    B._MEMO.clear()
    B._BUNDLE_SUMMARY_MEMO.clear()
    parses = []
    original = B._load_json_bytes

    def counted(raw, canonical):
        parses.append(raw)
        return original(raw, canonical)

    monkeypatch.setattr(B, "_load_json_bytes", counted)
    assert B.list_bundles(data_dir)[0]["counts"]["error"] == 0
    assert parses == []

    path = B.bundle_dir(data_dir, bid) / "golden" / "a.json"
    before = path.stat()
    path.write_bytes(b"{x}")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert B.list_bundles(data_dir)[0]["counts"]["error"] == 1
    assert parses == [b"{x}"]


def test_summary_version_change_rechecks_unchanged_documents(tmp_path, file_mode, monkeypatch):
    _upload(tmp_path, "rules", bad=True)
    time.sleep(0.03)
    assert B.list_bundles(tmp_path)[0]["counts"]["error"] == 1
    checked = []

    def new_error_policy(_bdir, doc_id):
        checked.append(doc_id)
        return False

    monkeypatch.setattr(B, "_doc_has_json_error", new_error_policy)
    monkeypatch.setattr(B, "_BUNDLE_SUMMARY_VERSION", B._BUNDLE_SUMMARY_VERSION + 1)
    assert B.list_bundles(tmp_path)[0]["counts"]["error"] == 0
    assert checked == ["doc"]


def test_review_changes_use_persisted_counts_without_parsing_and_delete_cascades(
        postgres_namespace, monkeypatch):
    bid = _upload(postgres_namespace, "reviews")
    time.sleep(0.03)
    B.list_bundles(postgres_namespace)
    B._MEMO.clear()
    B._BUNDLE_SUMMARY_MEMO.clear()

    def unexpected(*_args, **_kwargs):
        raise AssertionError("unchanged files should neither parse nor rewrite cached counts")

    monkeypatch.setattr(B, "_load_json_bytes", unexpected)
    monkeypatch.setattr(DB, "save_bundle_summaries", unexpected)
    B.set_review(postgres_namespace, bid, "doc", "done")
    assert B.list_bundles(postgres_namespace)[0]["counts"]["reviewed"] == 1
    B.set_enabled(postgres_namespace, bid, ["doc"], False)
    assert B.list_bundles(postgres_namespace)[0]["counts"]["docs"] == 1
    B.set_review(postgres_namespace, bid, "doc", "progress")
    assert B.list_bundles(postgres_namespace)[0]["counts"]["reviewed"] == 0
    B.delete_bundle(postgres_namespace, bid)
    assert DB.get_bundle_summaries(postgres_namespace, [bid]) == {}
