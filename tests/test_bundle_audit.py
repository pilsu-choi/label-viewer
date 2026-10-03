from __future__ import annotations

import io
import os
import sys
from io import BytesIO
from contextlib import contextmanager
from pathlib import Path
import zipfile

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import bundle as B


def test_duplicate_upload_stems_never_overwrite_a_literal_suffix_name(tmp_path):
    bid = B.process_upload(tmp_path, [
        ("batch/original/doc.png", io.BytesIO(b"first doc")),
        ("batch/original/doc.png", io.BytesIO(b"duplicate doc")),
        ("batch/original/doc~2.png", io.BytesIO(b"literal doc~2")),
    ], None, 1_000_000)
    original = tmp_path / "bundles" / bid / "original"

    assert (original / "doc.png").read_bytes() == b"first doc"
    assert (original / "doc~2.png").read_bytes() == b"literal doc~2"
    assert (original / "doc~3.png").read_bytes() == b"duplicate doc"
    assert set(B.doc_ids(tmp_path / "bundles" / bid)) == {"doc", "doc~2", "doc~3"}


def test_unsupported_files_do_not_create_an_empty_bundle(tmp_path):
    with pytest.raises(B.ApiError) as error:
        B.process_upload(tmp_path, [
            ("batch/original/readme.txt", io.BytesIO(b"not an image")),
        ], None, 1_000_000)

    assert error.value.status == 400
    assert not (tmp_path / "bundles").exists()


def test_sidecar_plus_unsupported_files_still_requires_a_real_document(tmp_path):
    with pytest.raises(B.ApiError, match="AO UI sidecar") as error:
        B.process_upload(tmp_path, [
            ("batch/ao_ui/doc.aiocr.ui.json", io.BytesIO(b'{"documents":[]}')),
            ("batch/original/readme.txt", io.BytesIO(b"not an image")),
        ], None, 1_000_000)

    assert error.value.status == 400
    assert not (tmp_path / "bundles").exists()


@pytest.mark.parametrize("filename", ["bad\nid.png", "C:drive.png"])
def test_unsafe_source_document_ids_are_rejected_before_bundle_creation(tmp_path, filename):
    with pytest.raises(B.ApiError) as error:
        B.process_upload(tmp_path, [
            (f"batch/original/{filename}", io.BytesIO(b"image")),
        ], None, 1_000_000)

    assert error.value.status == 400
    assert not (tmp_path / "bundles").exists()


def test_windows_absolute_zip_paths_are_skipped():
    payload = BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr(r"C:\bundle\original\doc.png", b"image")
    payload.seek(0)
    with zipfile.ZipFile(payload) as archive:
        assert B._zip_entries(archive) == []


def test_save_rechecks_document_existence_after_acquiring_golden_lock(tmp_path, monkeypatch):
    bid = B.process_upload(tmp_path, [
        ("batch/golden/only.json", io.BytesIO(b'{"documents":[]}')),
    ], None, 1_000_000)
    path = tmp_path / "bundles" / bid / "golden" / "only.json"

    @contextmanager
    def concurrent_delete(_bdir, _doc_id, shared=False):
        path.unlink()
        yield path, None

    monkeypatch.setattr(B, "_golden_lock", concurrent_delete)
    with pytest.raises(B.ApiError) as error:
        B.save_golden(tmp_path, bid, "only", {"documents": []}, "missing")

    assert error.value.status == 404
    assert not path.exists()


def test_doc_detail_uses_supplied_state_snapshot_without_database_state_read(tmp_path, monkeypatch):
    bid = B.process_upload(tmp_path, [
        ("batch/original/doc.png", io.BytesIO(b"image")),
    ], None, 1_000_000)
    snapshot = {"review": {"doc": "done"}, "disabled": ["doc"]}

    def unexpected_state_read(_bdir):
        raise AssertionError("state snapshot should avoid a per-document state query")

    monkeypatch.setattr(B, "load_state", unexpected_state_read)
    detail = B.doc_detail(tmp_path, bid, "doc", state_snapshot=snapshot)

    assert detail["review"] == "done"
    assert detail["enabled"] is False


def test_malformed_history_id_is_a_not_found_in_file_mode(tmp_path):
    bid = B.process_upload(tmp_path, [
        ("batch/golden/doc.json", io.BytesIO(b'{"documents":[]}')),
    ], None, 1_000_000)

    with pytest.raises(B.ApiError) as error:
        B.get_golden_history(tmp_path, bid, "doc", "..\x00/secret")

    assert error.value.status == 404


@pytest.mark.parametrize("ext,fmt", [("bmp", "BMP"), ("tif", "TIFF")])
def test_converted_image_cache_key_changes_when_source_is_replaced(tmp_path, ext, fmt):
    def encoded(color):
        buffer = BytesIO()
        Image.new("RGB", (12, 8), color).save(buffer, format=fmt)
        return buffer.getvalue()

    bid = B.process_upload(tmp_path, [
        (f"batch/original/doc.{ext}", BytesIO(encoded("red"))),
    ], None, 1_000_000)
    src = tmp_path / "bundles" / bid / "original" / f"doc.{ext}"
    old_mtime = src.stat().st_mtime_ns
    first_cache, _ = B.get_image(tmp_path, bid, "doc", "original", 1)
    replacement = src.with_name("replacement.tmp")
    replacement.write_bytes(encoded("blue"))
    os.replace(replacement, src)
    os.utime(src, ns=(old_mtime, old_mtime))

    second_cache, _ = B.get_image(tmp_path, bid, "doc", "original", 1)

    assert second_cache != first_cache
    with Image.open(second_cache) as result:
        assert result.getpixel((0, 0))[2] > result.getpixel((0, 0))[0]


def test_jpeg_thumbnail_applies_exif_orientation(tmp_path):
    source = Image.new("RGB", (80, 40), "red")
    exif = Image.Exif()
    exif[274] = 6  # rotate 90 degrees clockwise for display
    buffer = BytesIO()
    source.save(buffer, format="JPEG", exif=exif)
    bid = B.process_upload(tmp_path, [
        ("batch/original/rotated.jpg", BytesIO(buffer.getvalue())),
    ], None, 1_000_000)

    thumbnail, _ = B.get_image(tmp_path, bid, "rotated", "original", 1, w=160)

    with Image.open(thumbnail) as result:
        assert result.height > result.width


def test_failed_detail_build_does_not_archive_a_golden_save(tmp_path, monkeypatch):
    bid = B.process_upload(tmp_path, [
        ("batch/original/doc.png", io.BytesIO(b"image")),
    ], None, 1_000_000)
    first = B.save_golden(tmp_path, bid, "doc", {"documents": []}, "missing")
    path = tmp_path / "bundles" / bid / "golden" / "doc.json"
    before = path.read_bytes()
    history_before = B.list_golden_history(tmp_path, bid, "doc")["items"]

    def fail_detail(*_args, **_kwargs):
        raise RuntimeError("detail assembly failed")

    monkeypatch.setattr(B, "_doc_detail_unlocked", fail_detail)
    with pytest.raises(RuntimeError, match="detail assembly failed"):
        B.save_golden(tmp_path, bid, "doc", {"documents": [{"doc_type": "new"}]},
                      first["golden_revision"])

    assert path.read_bytes() == before
    assert B.list_golden_history(tmp_path, bid, "doc")["items"] == history_before


def test_failed_detail_build_does_not_archive_a_golden_restore(tmp_path, monkeypatch):
    bid = B.process_upload(tmp_path, [
        ("batch/original/doc.png", io.BytesIO(b"image")),
    ], None, 1_000_000)
    first = B.save_golden(tmp_path, bid, "doc", {"documents": []}, "missing")
    second = B.save_golden(tmp_path, bid, "doc", {"documents": [{"doc_type": "second"}]},
                           first["golden_revision"])
    history = B.list_golden_history(tmp_path, bid, "doc")["items"]
    target = next(item for item in history if item["revision"] == first["golden_revision"])
    path = tmp_path / "bundles" / bid / "golden" / "doc.json"
    before = path.read_bytes()

    def fail_detail(*_args, **_kwargs):
        raise RuntimeError("detail assembly failed")

    monkeypatch.setattr(B, "_doc_detail_unlocked", fail_detail)
    with pytest.raises(RuntimeError, match="detail assembly failed"):
        B.restore_golden(tmp_path, bid, "doc", target["id"], second["golden_revision"])

    assert path.read_bytes() == before
    assert B.list_golden_history(tmp_path, bid, "doc")["items"] == history
