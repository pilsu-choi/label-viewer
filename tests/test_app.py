"""backend 통합 테스트. 더미 번들 생성기로 tmp_path 에 데이터를 만들고 FastAPI TestClient 로 검증한다."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import create_app
from backend.bundle import classify, stem_of
from scripts import make_dummy_bundle as dummy


def _entries(root: Path) -> list[tuple[str, bytes]]:
    return [(str(p.relative_to(root)), p.read_bytes()) for p in sorted(root.rglob("*")) if p.is_file()]


@pytest.fixture
def dummy_root(tmp_path) -> Path:
    root = tmp_path / "dummy_src"
    root.mkdir()
    dummy.build(root)
    return root


@pytest.fixture
def client(tmp_path) -> TestClient:
    app = create_app(tmp_path / "storage")
    return TestClient(app)


def _upload_folder(client: TestClient, root: Path, name: str = "dummy-folder"):
    files = [("files", (relpath, data, "application/octet-stream")) for relpath, data in _entries(root)]
    return client.post("/api/bundles", files=files, data={"name": name})


@pytest.fixture
def bundle(client: TestClient, dummy_root: Path) -> dict:
    resp = _upload_folder(client, dummy_root)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── health ────────────────────────────────────────────────────────────────

def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


# ── classify / stem ──────────────────────────────────────────────────────

def test_classify_folders():
    assert classify("original/MC001.png") == "original"
    assert classify("preprocessed/x.png") == "preprocessed"
    assert classify("ao_extract/x.aiocr.json") == "ao_extract"
    assert classify("harness/x.harness.json") == "harness"
    assert classify("golden/x.json") == "golden"
    assert classify("정답지/x.json") == "golden"
    assert classify("foo/__MACOSX/bar.png") is None


def test_classify_suffix_fallback():
    assert classify("flat/ABC001.answer.json") == "golden"
    assert classify("flat/ABC001.harness.json") == "harness"
    assert classify("flat/ABC001.aiocr.json") == "ao_extract"
    assert classify("flat/ABC001.png") == "original"
    assert classify("flat/ABC001.unrelated.json") is None


def test_stem_across_extensions():
    assert stem_of("ABC001.jpg") == "ABC001"
    assert stem_of("ABC001.png") == "ABC001"
    assert stem_of("ABC001.json") == "ABC001"
    assert stem_of("ABC001.tif.aiocr.json") == "ABC001"
    assert stem_of("ABC001.p2.png") == "ABC001"
    assert stem_of("ABC001.answer.json") == "ABC001"


# ── upload ────────────────────────────────────────────────────────────────

def test_upload_zip(client: TestClient, dummy_root: Path):
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, "w") as zf:
        for relpath, data in _entries(dummy_root):
            zf.writestr(relpath, data)
    resp = client.post("/api/bundles", files={"files": ("dummy.zip", zip_bytes.getvalue(), "application/zip")})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["summary"]["docs"] == 6


def test_upload_folder_style(bundle: dict):
    assert bundle["summary"]["docs"] == 6
    assert bundle["summary"]["golden"] == 3


def test_zip_slip_rejected(client: TestClient, tmp_path: Path):
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, "w") as zf:
        zf.writestr("../evil.txt", "pwned")
        zf.writestr("original/ok.png", b"\x89PNG\r\n")
    resp = client.post("/api/bundles", files={"files": ("evil.zip", zip_bytes.getvalue(), "application/zip")})
    assert resp.status_code == 201
    data_dir = tmp_path / "storage"
    assert not (data_dir / "evil.txt").exists()
    assert not list(data_dir.rglob("evil.txt"))


# ── missing/broken status ────────────────────────────────────────────────

def test_missing_and_broken(bundle: dict):
    docs = {d["id"]: d for d in bundle["docs"]}
    assert docs["PH003"]["has"]["harness"] is False
    assert docs["PH003"]["has"]["golden"] is False
    assert docs["OP004"]["has"]["preprocessed"] is False
    assert docs["DX006"]["has"] == {"original": True, "preprocessed": False, "ao_extract": False,
                                     "harness": False, "golden": False}
    assert docs["MC005"]["errors"], "broken harness json should be reported"
    assert "harness" in docs["MC005"]["errors"][0]


# ── compare statuses ─────────────────────────────────────────────────────

def test_compare_statuses(client: TestClient, bundle: dict):
    doc = client.get(f"/api/bundles/{bundle['id']}/docs/MC001").json()
    by_key = {(r["container"], r["row"], r["key"]): r for r in doc["compare"]}

    assert by_key[("", "", "발행일")]["ao_status"] == "MATCH"  # 2026-09-01 vs 20260901
    assert by_key[("", "", "공단부담총액")]["ao_status"] == "TYPE_MISMATCH"
    assert by_key[("", "", "공단부담총액")]["harness_status"] == "MATCH"

    row0 = by_key[("항목내역", 0, "금액")]
    assert row0["ao_status"] == "MISMATCH"  # 33000 != 35000
    assert row0["harness_status"] == "MATCH"  # harness 33000 -> 35000

    extra = [r for r in doc["compare"] if str(r["row"]).startswith("+")]
    assert extra, "extra table row (재료대) should be detected"
    assert any(r["ao_status"] == "EXTRA" for r in extra)
    assert any(r["harness_status"] == "EXTRA" for r in extra)

    doc2 = client.get(f"/api/bundles/{bundle['id']}/docs/DX002").json()
    by_key2 = {r["key"]: r for r in doc2["compare"]}
    assert by_key2["병명코드"]["ao_status"] == "MISMATCH"
    assert by_key2["병명코드"]["harness_status"] == "MATCH"
    assert by_key2["작성일자"]["ao_status"] == "MATCH"
    assert by_key2["작성일자"]["harness_status"] == "MISMATCH"  # 악화
    assert by_key2["병명"]["ao_status"] == "MISSING"
    assert by_key2["병명"]["harness_status"] == "MISSING"


def test_doc_detail_without_golden_matches_list_api(client: TestClient, bundle: dict):
    """Golden 없는 문서는 목록 API(bundle_view)처럼 compare=[], score=None 이어야 한다(가짜 EXTRA 불일치 금지)."""
    bid = bundle["id"]
    doc = client.get(f"/api/bundles/{bid}/docs/PH003").json()
    assert doc["has"]["golden"] is False
    assert doc["compare"] == []
    assert doc["score"] == {"ao": None, "harness": None}


def test_list_mismatch_matches_compare(client: TestClient, bundle: dict):
    """목록 API의 mismatch 는 상세 compare 에서 ao_status/harness_status 가 MATCH 가 아닌 행 수와 같아야 한다."""
    bid = bundle["id"]
    for summary in bundle["docs"]:
        if not summary["has"]["golden"]:
            continue
        doc = client.get(f"/api/bundles/{bid}/docs/{summary['id']}").json()
        expected = sum(
            1 for r in doc["compare"]
            if r["ao_status"] not in ("", "MATCH") or r["harness_status"] not in ("", "MATCH")
        )
        assert summary["mismatch"] == expected, summary["id"]


# ── golden create/save/delete ────────────────────────────────────────────

def test_create_golden_from_ao(client: TestClient, bundle: dict):
    bid = bundle["id"]
    resp = client.post(f"/api/bundles/{bid}/docs/PH003/golden", json={"from": "ao"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["golden"]["documents"][0]["extracted_fields"]


def test_create_golden_409(client: TestClient, bundle: dict):
    bid = bundle["id"]
    resp = client.post(f"/api/bundles/{bid}/docs/MC001/golden", json={"from": "ao"})
    assert resp.status_code == 409


def test_create_golden_missing_source_404(client: TestClient, bundle: dict):
    bid = bundle["id"]
    resp = client.post(f"/api/bundles/{bid}/docs/PH003/golden", json={"from": "harness"})
    assert resp.status_code == 404


def test_golden_from_harness_strips_and_uses_final_value(client: TestClient, bundle: dict):
    bid = bundle["id"]
    d = client.delete(f"/api/bundles/{bid}/docs/MC001/golden")
    assert d.status_code == 204
    resp = client.post(f"/api/bundles/{bid}/docs/MC001/golden", json={"from": "harness"})
    assert resp.status_code == 200, resp.text
    golden = resp.json()["golden"]
    doc = golden["documents"][0]
    assert "harness" not in doc
    fields = {c["key"]: c for c in doc["extracted_fields"]}
    assert "harness" not in fields["공단부담총액"]
    assert fields["공단부담총액"]["value"] == "9000"  # final_value 로 대체됨
    table_cells = {c["key"]: c for c in doc["extracted_tables"][0]["rows"][0]}
    assert table_cells["금액"]["value"] == "35000"
    assert "harness" not in table_cells["금액"]


def test_put_golden_persists(client: TestClient, bundle: dict):
    bid = bundle["id"]
    new_golden = {"documents": [{"doc_type": "약제비영수증",
                                  "extracted_fields": [{"key": "조제일자", "value": "2026-09-05"}],
                                  "extracted_groups": [], "extracted_tables": []}]}
    r = client.put(f"/api/bundles/{bid}/docs/PH003/golden", json={"golden": new_golden})
    assert r.status_code == 200, r.text
    assert r.json()["golden"]["documents"][0]["extracted_fields"][0]["dtype"] == "string"  # 기본값 채움

    reloaded = client.get(f"/api/bundles/{bid}/docs/PH003").json()
    assert reloaded["golden"]["documents"][0]["extracted_fields"][0]["value"] == "2026-09-05"


def test_put_golden_invalid_422(client: TestClient, bundle: dict):
    bid = bundle["id"]
    r = client.put(f"/api/bundles/{bid}/docs/PH003/golden", json={"golden": {"nope": True}})
    assert r.status_code == 422


def test_delete_golden(client: TestClient, bundle: dict):
    bid = bundle["id"]
    r = client.delete(f"/api/bundles/{bid}/docs/OP004/golden")
    assert r.status_code == 204
    doc = client.get(f"/api/bundles/{bid}/docs/OP004").json()
    assert doc["has"]["golden"] is False


# ── AO/harness immutability ──────────────────────────────────────────────

def _hash_tree(root: Path) -> dict[str, str]:
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def test_ao_harness_files_never_modified(client: TestClient, bundle: dict, tmp_path: Path):
    bid = bundle["id"]
    bdir = tmp_path / "storage" / "bundles" / bid
    before = {**_hash_tree(bdir / "ao_extract"), **_hash_tree(bdir / "harness")}

    client.post(f"/api/bundles/{bid}/docs/PH003/golden", json={"from": "ao"})
    client.delete(f"/api/bundles/{bid}/docs/MC001/golden")
    client.post(f"/api/bundles/{bid}/docs/MC001/golden", json={"from": "harness"})
    client.put(f"/api/bundles/{bid}/docs/OP004/golden",
               json={"golden": {"documents": [{"doc_type": "x", "extracted_fields": [],
                                                "extracted_groups": [], "extracted_tables": []}]}})
    client.get(f"/api/bundles/{bid}/export/golden.xlsx")

    after = {**_hash_tree(bdir / "ao_extract"), **_hash_tree(bdir / "harness")}
    assert before == after


# ── review state ─────────────────────────────────────────────────────────

def test_review_state(client: TestClient, bundle: dict):
    bid = bundle["id"]
    r = client.put(f"/api/bundles/{bid}/docs/MC001/review", json={"review": "done"})
    assert r.status_code == 204
    doc = client.get(f"/api/bundles/{bid}/docs/MC001").json()
    assert doc["review"] == "done"

    view = client.get(f"/api/bundles/{bid}").json()
    assert view["summary"]["reviewed"] == 1

    client.put(f"/api/bundles/{bid}/docs/MC001/review", json={"review": ""})
    doc = client.get(f"/api/bundles/{bid}/docs/MC001").json()
    assert doc["review"] == ""


# ── export ───────────────────────────────────────────────────────────────

def test_export_zip(client: TestClient, bundle: dict):
    bid = bundle["id"]
    r = client.get(f"/api/bundles/{bid}/export/golden.zip")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
    assert any(n.endswith("MC001.json") for n in names)


def test_export_xlsx(client: TestClient, bundle: dict):
    bid = bundle["id"]
    r = client.get(f"/api/bundles/{bid}/export/golden.xlsx")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert set(wb.sheetnames) == {"요약", "필드", "표", "비교"}
    assert wb["요약"].max_row >= 2


# ── images ───────────────────────────────────────────────────────────────

def test_image_endpoints(client: TestClient, bundle: dict):
    bid = bundle["id"]
    r = client.get(f"/api/bundles/{bid}/docs/MC001/image", params={"view": "original"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")

    r2 = client.get(f"/api/bundles/{bid}/docs/PH003/image", params={"view": "original", "page": 1})
    assert r2.status_code == 200
    assert r2.headers["x-pages"] == "2"

    r3 = client.get(f"/api/bundles/{bid}/docs/PH003/image", params={"view": "original", "page": 2})
    assert r3.status_code == 200
    assert r3.content != r2.content

    r4 = client.get(f"/api/bundles/{bid}/docs/DX006/image", params={"view": "preprocessed"})
    assert r4.status_code == 404


def test_raw_endpoint(client: TestClient, bundle: dict):
    bid = bundle["id"]
    r = client.get(f"/api/bundles/{bid}/docs/MC001/raw/ao_extract")
    assert r.status_code == 200
    assert json.loads(r.text)["transaction_id"] == "txn-mc001"

    r2 = client.get(f"/api/bundles/{bid}/docs/MC005/raw/harness")
    assert r2.status_code == 200  # 원문 그대로(파싱 실패여도)
    assert "not valid json" in r2.text

    r3 = client.get(f"/api/bundles/{bid}/docs/DX006/raw/golden")
    assert r3.status_code == 404


# ── delete bundle ────────────────────────────────────────────────────────

def test_delete_bundle(client: TestClient, bundle: dict):
    bid = bundle["id"]
    r = client.delete(f"/api/bundles/{bid}")
    assert r.status_code == 204
    assert client.get(f"/api/bundles/{bid}").status_code == 404
    assert bid not in [b["id"] for b in client.get("/api/bundles").json()]


def test_path_traversal_rejected(client: TestClient, bundle: dict):
    bid = bundle["id"]
    r = client.get(f"/api/bundles/{bid}/docs/..%2f..%2fetc/image")
    assert r.status_code in (400, 404, 422)
