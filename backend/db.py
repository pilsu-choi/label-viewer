"""Optional PostgreSQL metadata store shared by application workers."""
from __future__ import annotations

import contextvars
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator


_CURRENT_CONNECTION: contextvars.ContextVar[Any | None] = contextvars.ContextVar(
    "label_viewer_db_connection", default=None
)


def enabled() -> bool:
    return bool(os.environ.get("LABEL_VIEWER_DATABASE_URL"))


def _database_url() -> str:
    url = os.environ.get("LABEL_VIEWER_DATABASE_URL")
    if not url:
        raise RuntimeError("LABEL_VIEWER_DATABASE_URL is not configured")
    return url


def namespace(data_dir: Path) -> str:
    configured = os.environ.get("LABEL_VIEWER_DB_NAMESPACE")
    return configured if configured is not None else str(Path(data_dir).expanduser().resolve())


def _psycopg():
    try:
        import psycopg
        return psycopg
    except ImportError as exc:
        raise RuntimeError("PostgreSQL is configured but psycopg is not installed") from exc


def _connect(psycopg, url: str, autocommit: bool = False):
    options = psycopg.conninfo.conninfo_to_dict(url)
    if "connect_timeout" not in options:
        try:
            timeout = int(os.environ.get("LABEL_VIEWER_DB_CONNECT_TIMEOUT", "5"))
        except ValueError as exc:
            raise ValueError("LABEL_VIEWER_DB_CONNECT_TIMEOUT must be a positive integer") from exc
        if timeout <= 0:
            raise ValueError("LABEL_VIEWER_DB_CONNECT_TIMEOUT must be a positive integer")
        options["connect_timeout"] = timeout
    return psycopg.connect(**options, autocommit=autocommit)


@contextmanager
def connection() -> Iterator[Any]:
    """Yield a transaction connection; nested calls reuse the current connection."""
    current = _CURRENT_CONNECTION.get()
    if current is not None:
        yield current
        return
    psycopg = _psycopg()
    conn = _connect(psycopg, _database_url())
    token = _CURRENT_CONNECTION.set(conn)
    try:
        with conn.transaction():
            yield conn
    finally:
        _CURRENT_CONNECTION.reset(token)
        conn.close()


def _lock_keys(data_dir: Path, resource: str) -> tuple[int, int]:
    ns_digest = hashlib.sha256(namespace(data_dir).encode("utf-8")).digest()
    resource_digest = hashlib.sha256(resource.encode("utf-8")).digest()
    return (int.from_bytes(ns_digest[:4], "big", signed=True),
            int.from_bytes(resource_digest[:4], "big", signed=True))


@contextmanager
def lock(data_dir: Path, resource: str, shared: bool = False,
         blocking: bool = True) -> Iterator[bool]:
    """Hold a namespace-scoped transaction advisory lock until the outer transaction commits."""
    if not enabled():
        yield True
        return
    key1, key2 = _lock_keys(data_dir, resource)
    with connection() as conn:
        if shared:
            if blocking:
                conn.execute("SELECT pg_advisory_xact_lock_shared(%s, %s)", (key1, key2))
                acquired = True
            else:
                acquired = bool(conn.execute("SELECT pg_try_advisory_xact_lock_shared(%s, %s)",
                                             (key1, key2)).fetchone()[0])
        else:
            if blocking:
                conn.execute("SELECT pg_advisory_xact_lock(%s, %s)", (key1, key2))
                acquired = True
            else:
                acquired = bool(conn.execute("SELECT pg_try_advisory_xact_lock(%s, %s)",
                                             (key1, key2)).fetchone()[0])
        yield acquired


@contextmanager
def session_lock(data_dir: Path, resource: str, shared: bool = False,
                 blocking: bool = True) -> Iterator[bool]:
    """Hold a session advisory lock on a dedicated connection, independent of CRUD transactions."""
    if not enabled():
        yield True
        return
    key1, key2 = _lock_keys(data_dir, resource)
    conn = _connect(_psycopg(), _database_url(), autocommit=True)
    try:
        if shared:
            if blocking:
                conn.execute("SELECT pg_advisory_lock_shared(%s, %s)", (key1, key2))
                acquired = True
            else:
                acquired = bool(conn.execute("SELECT pg_try_advisory_lock_shared(%s, %s)",
                                             (key1, key2)).fetchone()[0])
        else:
            if blocking:
                conn.execute("SELECT pg_advisory_lock(%s, %s)", (key1, key2))
                acquired = True
            else:
                acquired = bool(conn.execute("SELECT pg_try_advisory_lock(%s, %s)",
                                             (key1, key2)).fetchone()[0])
        try:
            yield acquired
        finally:
            if acquired:
                unlock = "pg_advisory_unlock_shared" if shared else "pg_advisory_unlock"
                conn.execute(f"SELECT {unlock}(%s, %s)", (key1, key2))
    finally:
        conn.close()


def initialize() -> None:
    """Create the common schema once; callers must run this before metadata operations."""
    if not enabled():
        return
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s, %s)", (0x4C564945, 0x57455231))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bundles (
                namespace TEXT NOT NULL,
                bundle_id TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                extra JSONB NOT NULL DEFAULT '{}'::jsonb,
                PRIMARY KEY (namespace, bundle_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                namespace TEXT NOT NULL,
                bundle_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                review TEXT NOT NULL DEFAULT '',
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                PRIMARY KEY (namespace, bundle_id, doc_id),
                FOREIGN KEY (namespace, bundle_id) REFERENCES bundles(namespace, bundle_id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS golden_history (
                namespace TEXT NOT NULL,
                bundle_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                action TEXT NOT NULL,
                revision TEXT NOT NULL,
                raw BYTEA,
                PRIMARY KEY (namespace, bundle_id, doc_id, id),
                FOREIGN KEY (namespace, bundle_id) REFERENCES bundles(namespace, bundle_id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS export_jobs (
                namespace TEXT NOT NULL,
                bundle_id TEXT NOT NULL,
                id TEXT NOT NULL,
                state JSONB NOT NULL,
                PRIMARY KEY (namespace, bundle_id, id),
                FOREIGN KEY (namespace, bundle_id) REFERENCES bundles(namespace, bundle_id) ON DELETE CASCADE
            )
        """)


def read_bundle_state(bdir: Path) -> dict:
    ns = namespace(bdir.parent.parent)
    with connection() as conn:
        row = conn.execute(
            "SELECT name, created_at, extra FROM bundles WHERE namespace=%s AND bundle_id=%s",
            (ns, bdir.name),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"bundle metadata not found in PostgreSQL: {bdir.name}")
        name, created_at, extra = row
        docs = conn.execute(
            "SELECT doc_id, review, enabled FROM documents WHERE namespace=%s AND bundle_id=%s",
            (ns, bdir.name),
        ).fetchall()
    state = dict(extra or {})
    state.update(name=name, created_at=created_at)
    state["review"] = {doc_id: review for doc_id, review, _enabled in docs if review}
    state["disabled"] = [doc_id for doc_id, _review, is_enabled in docs if not is_enabled]
    return state


def write_bundle_state(bdir: Path, state: dict) -> None:
    ns = namespace(bdir.parent.parent)
    name = state.get("name", bdir.name)
    created_at = state.get("created_at", "")
    review = state.get("review") or {}
    disabled = set(state.get("disabled") or [])
    standard = {"name", "created_at", "review", "disabled"}
    extra = {key: value for key, value in state.items() if key not in standard}
    psycopg = _psycopg()
    with connection() as conn:
        conn.execute("""
            INSERT INTO bundles(namespace,bundle_id,name,created_at,extra)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT(namespace,bundle_id) DO UPDATE SET
              name=EXCLUDED.name, created_at=EXCLUDED.created_at, extra=EXCLUDED.extra
        """, (ns, bdir.name, name, created_at, psycopg.types.json.Jsonb(extra)))
        conn.execute("DELETE FROM documents WHERE namespace=%s AND bundle_id=%s", (ns, bdir.name))
        doc_ids = set(review) | disabled
        if doc_ids:
            conn.cursor().executemany(
                "INSERT INTO documents(namespace,bundle_id,doc_id,review,enabled) VALUES (%s,%s,%s,%s,%s)",
                [(ns, bdir.name, doc_id, review.get(doc_id, ""), doc_id not in disabled)
                 for doc_id in doc_ids],
            )


def update_bundle_state(bdir: Path, fn: Callable[[dict], None]) -> None:
    with lock(bdir.parent.parent, f"bundle-state:{bdir.name}") as acquired:
        if not acquired:
            raise RuntimeError("could not acquire bundle state lock")
        state = read_bundle_state(bdir)
        fn(state)
        write_bundle_state(bdir, state)


def delete_bundle(data_dir: Path, bundle_id: str) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM bundles WHERE namespace=%s AND bundle_id=%s",
                     (namespace(data_dir), bundle_id))


def insert_golden_history(data_dir: Path, bundle_id: str, doc_id: str, metadata: dict,
                          raw: bytes | None) -> None:
    with connection() as conn:
        conn.execute("""
            INSERT INTO golden_history(namespace,bundle_id,doc_id,id,created_at,action,revision,raw)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (namespace(data_dir), bundle_id, doc_id, metadata["id"], metadata["created_at"],
              metadata["action"], metadata["revision"], raw))


def list_golden_history(data_dir: Path, bundle_id: str, doc_id: str, limit: int,
                        before: str | None) -> list[dict]:
    ns = namespace(data_dir)
    with connection() as conn:
        if before is None:
            rows = conn.execute("""
                SELECT id,created_at,action,revision,raw IS NOT NULL FROM golden_history
                WHERE namespace=%s AND bundle_id=%s AND doc_id=%s ORDER BY id DESC LIMIT %s
            """, (ns, bundle_id, doc_id, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT id,created_at,action,revision,raw IS NOT NULL FROM golden_history
                WHERE namespace=%s AND bundle_id=%s AND doc_id=%s AND id < %s ORDER BY id DESC LIMIT %s
            """, (ns, bundle_id, doc_id, before, limit)).fetchall()
    return [{"id": i, "created_at": created, "action": action, "revision": revision,
             "has_golden": bool(has)} for i, created, action, revision, has in rows]


def read_golden_history(data_dir: Path, bundle_id: str, doc_id: str, history_id: str):
    with connection() as conn:
        row = conn.execute("""
            SELECT id,created_at,action,revision,raw FROM golden_history
            WHERE namespace=%s AND bundle_id=%s AND doc_id=%s AND id=%s
        """, (namespace(data_dir), bundle_id, doc_id, history_id)).fetchone()
    if row is None:
        return None
    i, created, action, revision, raw = row
    return ({"id": i, "created_at": created, "action": action, "revision": revision,
             "has_golden": raw is not None}, raw)
