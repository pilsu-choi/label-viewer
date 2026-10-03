"""Regression checks for errors at API boundaries."""
import io
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import PoolTimeout, TooManyRequests
from backend import bundle as B, db as DB, migration as M
from backend.app import create_app


def test_raw_binary_json_reports_encoding_error(tmp_path, monkeypatch):
    monkeypatch.delenv('LABEL_VIEWER_DATABASE_URL', raising=False)
    bid = B.process_upload(tmp_path, [('batch/golden/doc.json', io.BytesIO(b'\xff\xff'))], None, 10000)
    with TestClient(create_app(tmp_path)) as client:
        response = client.get(f'/api/bundles/{bid}/docs/doc/raw/golden')
        assert response.status_code == 422
        assert '인코딩' in response.json()['detail']


@pytest.mark.parametrize('error', [PoolTimeout, TooManyRequests])
def test_pool_resource_errors_return_503(tmp_path, monkeypatch, error):
    monkeypatch.setenv('LABEL_VIEWER_DATABASE_URL', 'postgresql://unavailable/db')
    monkeypatch.setattr(M, 'import_files', lambda *_args, **_kwargs: {})

    @contextmanager
    def exhausted():
        raise error('internal-resource-details')
        yield

    monkeypatch.setattr(DB, 'connection', exhausted)
    with TestClient(create_app(tmp_path)) as client:
        response = client.get('/api/health')
        assert response.status_code == 503
        assert 'internal-resource-details' not in response.text
