import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.bundle import ApiError, process_upload


def test_zip_expanded_size_over_limit_rejected_before_bundle_creation(tmp_path):
    archive = io.BytesIO()
    payload = b"0" * 4096
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("batch/original/doc.png", payload)

    compressed = archive.getvalue()
    limit = 1024
    assert len(compressed) < limit

    with pytest.raises(ApiError) as error:
        process_upload(tmp_path, [("batch.zip", io.BytesIO(compressed))], None, limit)

    assert error.value.status == 413
    assert "upload too large" in error.value.message
    bundles = tmp_path / "bundles"
    assert not bundles.exists() or not any(bundles.iterdir())
