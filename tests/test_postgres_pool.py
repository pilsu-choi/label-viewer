"""Pool lifecycle and reuse tests; requires LABEL_VIEWER_TEST_DATABASE_URL."""
from __future__ import annotations

import os
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from psycopg_pool import PoolTimeout

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import db as DB


@pytest.fixture
def pg_pool(tmp_path, monkeypatch):
    dsn = os.environ.get("LABEL_VIEWER_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("LABEL_VIEWER_TEST_DATABASE_URL is not configured")
    DB.close_pool()
    monkeypatch.setenv("LABEL_VIEWER_DATABASE_URL", dsn)
    monkeypatch.setenv("LABEL_VIEWER_DB_NAMESPACE", f"pool-test:{uuid.uuid4()}")
    monkeypatch.setenv("LABEL_VIEWER_DB_POOL_MIN_SIZE", "0")
    monkeypatch.setenv("LABEL_VIEWER_DB_POOL_MAX_SIZE", "2")
    monkeypatch.setenv("LABEL_VIEWER_DB_POOL_MAX_WAITING", "4")
    monkeypatch.setenv("LABEL_VIEWER_DB_POOL_TIMEOUT", "0.5")
    monkeypatch.setenv("LABEL_VIEWER_DB_CONNECT_TIMEOUT", "2")
    DB.initialize()
    yield tmp_path
    DB.close_pool()


def test_connections_are_reused_and_nested_contexts_share_one_checkout(pg_pool):
    with DB.connection() as outer:
        pid = outer.execute("SELECT pg_backend_pid()").fetchone()[0]
        with DB.connection() as nested:
            assert nested is outer
            assert nested.execute("SELECT pg_backend_pid()").fetchone()[0] == pid

    with DB.connection() as reused:
        assert reused.execute("SELECT pg_backend_pid()").fetchone()[0] == pid

    stats = DB.pool_stats()
    assert stats["pool_max"] == 2
    assert stats["pool_size"] <= 2


def test_transaction_rollback_returns_clean_connection(pg_pool):
    with pytest.raises(RuntimeError, match="rollback this transaction"):
        with DB.connection() as conn:
            conn.execute("SELECT 1")
            raise RuntimeError("rollback this transaction")

    with DB.connection() as conn:
        assert conn.info.transaction_status.name == "IDLE"
        assert conn.execute("SELECT 2").fetchone() == (2,)


def test_pool_connection_limit_is_bounded_and_waiter_times_out(pg_pool):
    entered = [threading.Event(), threading.Event()]
    release = threading.Event()

    def hold(index):
        with DB.connection() as conn:
            pid = conn.execute("SELECT pg_backend_pid()").fetchone()[0]
            entered[index].set()
            assert release.wait(4)
            return pid

    def request_third():
        with DB.connection():
            return "unexpected third checkout"

    with ThreadPoolExecutor(max_workers=3) as executor:
        first = executor.submit(hold, 0)
        second = executor.submit(hold, 1)
        assert entered[0].wait(3)
        assert entered[1].wait(3)
        third = executor.submit(request_third)
        with pytest.raises(PoolTimeout):
            third.result(timeout=3)
        release.set()
        first.result(timeout=3)
        second.result(timeout=3)

    stats = DB.pool_stats()
    assert stats["pool_max"] == 2
    assert stats["pool_size"] <= 2


def test_session_lock_unlocks_and_restores_connection_after_body_error(pg_pool):
    data_dir = pg_pool
    resource = f"exception:{uuid.uuid4()}"
    with pytest.raises(ValueError, match="inside lock"):
        with DB.session_lock(data_dir, resource):
            raise ValueError("inside lock")

    with DB.session_lock(data_dir, resource, blocking=False) as acquired:
        assert acquired is True

    with DB.connection() as conn:
        assert conn.autocommit is False
        assert conn.execute("SELECT 1").fetchone() == (1,)


def test_session_lock_returns_false_when_held_by_another_checkout(pg_pool):
    resource = f"contended:{uuid.uuid4()}"
    with DB.session_lock(pg_pool, resource) as acquired:
        assert acquired is True
        with DB.session_lock(pg_pool, resource, blocking=False) as nested_acquired:
            assert nested_acquired is False


def test_pool_reconfigures_when_pool_settings_change(pg_pool, monkeypatch):
    assert DB.pool_stats()["pool_max"] == 2
    monkeypatch.setenv("LABEL_VIEWER_DB_POOL_MAX_SIZE", "3")
    assert DB.pool_stats()["pool_max"] == 3


def test_pool_reconfigures_when_libpq_environment_changes(pg_pool, monkeypatch):
    with DB.connection() as conn:
        old_backend = conn.execute("SELECT pg_backend_pid()").fetchone()[0]
    monkeypatch.setenv("PGAPPNAME", f"pool-refresh-{uuid.uuid4()}")
    with DB.connection() as conn:
        new_backend = conn.execute("SELECT pg_backend_pid()").fetchone()[0]
        app_name = conn.execute("SELECT current_setting('application_name')").fetchone()[0]
    assert DB.pool_stats()["pool_max"] == 2
    assert app_name.startswith("pool-refresh-")
    assert new_backend != old_backend


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX fork")
def test_pool_is_recreated_in_a_forked_worker(pg_pool):
    with DB.connection() as conn:
        parent_backend = conn.execute("SELECT pg_backend_pid()").fetchone()[0]
    reader, writer = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(reader)
        try:
            with DB.connection() as conn:
                child_backend = conn.execute("SELECT pg_backend_pid()").fetchone()[0]
            os.write(writer, str(child_backend).encode("ascii"))
            os._exit(0)
        except BaseException as exc:
            os.write(writer, f"error:{type(exc).__name__}:{exc}".encode("utf-8", "replace"))
            os._exit(1)
    os.close(writer)
    result = os.read(reader, 256).decode("utf-8")
    _, status = os.waitpid(child, 0)
    os.close(reader)

    assert os.waitstatus_to_exitcode(status) == 0, result
    assert int(result) != parent_backend


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "0", "-1"])
def test_pool_deadlines_reject_non_finite_or_non_positive_values(monkeypatch, value):
    monkeypatch.setenv("LABEL_VIEWER_DB_POOL_TIMEOUT", value)
    with pytest.raises(ValueError, match="positive number"):
        DB._positive_float("LABEL_VIEWER_DB_POOL_TIMEOUT", 10)
