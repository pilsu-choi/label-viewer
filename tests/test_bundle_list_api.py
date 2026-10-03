from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path / "storage"))


def _upload(client: TestClient, name: str, doc_id: str, *, bad_golden: bool = False,
            bad_ao_ui: bool = False) -> dict:
    files = [
        ("files", (f"batch/original/{doc_id}.png", b"image", "application/octet-stream")),
        ("files", (f"batch/golden/{doc_id}.json", b"{" if bad_golden else b'{"documents":[]}',
                    "application/json")),
    ]
    if bad_ao_ui:
        files.append(("files", (f"batch/ao_ui/{doc_id}.aiocr.ui.json", b"{", "application/json")))
    response = client.post("/api/bundles", files=files, data={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def test_legacy_bundle_list_remains_array_and_limit_is_bounded(client):
    for i in range(3):
        _upload(client, f"bundle-{i}", f"DOC{i}")
        time.sleep(0.01)

    legacy = client.get("/api/bundles")
    assert legacy.status_code == 200
    assert isinstance(legacy.json(), list)
    assert len(legacy.json()) == 3

    limited = client.get("/api/bundles", params={"limit": 2})
    assert limited.status_code == 200
    assert isinstance(limited.json(), list)
    assert [b["id"] for b in limited.json()] == [b["id"] for b in legacy.json()[:2]]

    for value in (0, 101, "not-a-number"):
        response = client.get("/api/bundles", params={"limit": value})
        assert response.status_code == 422


def test_bundle_page_filters_case_insensitively_and_escapes_like_wildcards(client):
    special = _upload(client, "Alpha%_Bundle", "DocSpecial")
    _upload(client, "AlphaXYBundle", "DocNearMatch")
    _upload(client, "another", "Other")

    by_name = client.get("/api/bundles/page", params={"query": "%_bUnDlE"})
    assert by_name.status_code == 200, by_name.text
    assert [b["id"] for b in by_name.json()["items"]] == [special["id"]]

    by_id = client.get("/api/bundles/page", params={"query": special["id"].swapcase()})
    assert by_id.status_code == 200, by_id.text
    assert [b["id"] for b in by_id.json()["items"]] == [special["id"]]


def test_bundle_page_sorting_counts_and_page_clamping(client):
    names = ["zulu", "Beta", "alpha", "beta"]
    uploaded = []
    for i, name in enumerate(names):
        uploaded.append(_upload(client, name, f"DOC{i}", bad_golden=(i == 2), bad_ao_ui=(i == 3)))
        time.sleep(0.01)

    newest = client.get("/api/bundles/page", params={"sort": "newest", "page_size": 2}).json()
    assert newest["total"] == newest["filtered_total"] == 4
    assert newest["page"] == 1 and newest["page_size"] == 2
    assert [b["id"] for b in newest["items"]] == [uploaded[3]["id"], uploaded[2]["id"]]

    oldest = client.get("/api/bundles/page", params={"sort": "oldest"}).json()
    assert oldest["items"][0]["id"] == uploaded[0]["id"]

    by_name = client.get("/api/bundles/page", params={"sort": "name", "page_size": 4}).json()
    assert [b["name"] for b in by_name["items"]] == ["alpha", "Beta", "beta", "zulu"]
    by_name_errors = {b["name"]: b["counts"]["error"] for b in by_name["items"]}
    assert by_name_errors["alpha"] >= 1
    assert by_name_errors["beta"] >= 1
    assert by_name_errors["Beta"] == 0

    clamped = client.get("/api/bundles/page", params={"page": 99, "page_size": 3}).json()
    assert clamped["page"] == 2
    assert len(clamped["items"]) == 1

    for params in ({"sort": "random"}, {"page": 0}, {"page_size": 0}, {"page_size": 101}):
        assert client.get("/api/bundles/page", params=params).status_code == 422


def test_static_page_route_precedes_literal_page_bundle_id_route(client, monkeypatch):
    from backend import bundle as B

    monkeypatch.setattr(B, "new_bundle_id", lambda: "page")
    bundle = _upload(client, "page", "DOC")
    response = client.get("/api/bundles/page")
    assert response.status_code == 200
    assert response.json()["total"] == 1

    # The exact static path is the list endpoint; nested routes still resolve the
    # literal bundle ID through their dynamic segment.
    detail = client.get("/api/bundles/page/docs/DOC")
    assert detail.status_code == 200
    assert detail.json()["id"] == "DOC"
    assert bundle["id"] == "page"
