"""Optional PostgreSQL metadata store shared by application workers."""
from __future__ import annotations

import contextvars
import hashlib
import math
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator


_CURRENT_CONNECTION: contextvars.ContextVar[tuple[int, Any] | None] = contextvars.ContextVar(
    "label_viewer_db_connection", default=None
)
_POOL_LOCK = threading.RLock()
_POOL: Any | None = None
_POOL_PID: int | None = None
_POOL_KEY: tuple | None = None
_FORKED_POOL_REFS: list[Any] = []


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


def _connect_options(psycopg, url: str) -> dict[str, Any]:
    options = psycopg.conninfo.conninfo_to_dict(url)
    if "connect_timeout" not in options:
        try:
            timeout = int(os.environ.get("LABEL_VIEWER_DB_CONNECT_TIMEOUT", "5"))
        except ValueError as exc:
            raise ValueError("LABEL_VIEWER_DB_CONNECT_TIMEOUT must be a positive integer") from exc
        if timeout <= 0:
            raise ValueError("LABEL_VIEWER_DB_CONNECT_TIMEOUT must be a positive integer")
        options["connect_timeout"] = timeout
    return options


def _positive_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer >= {minimum}") from exc
    if value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _positive_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def _pool_options(psycopg, url: str) -> tuple[dict[str, Any], dict[str, Any], tuple]:
    kwargs = _connect_options(psycopg, url)
    min_size = _positive_int("LABEL_VIEWER_DB_POOL_MIN_SIZE", 0, 0)
    max_size = _positive_int("LABEL_VIEWER_DB_POOL_MAX_SIZE", 16)
    if min_size > max_size:
        raise ValueError("LABEL_VIEWER_DB_POOL_MIN_SIZE cannot exceed LABEL_VIEWER_DB_POOL_MAX_SIZE")
    timeout = _positive_float("LABEL_VIEWER_DB_POOL_TIMEOUT", 10.0)
    max_waiting = _positive_int("LABEL_VIEWER_DB_POOL_MAX_WAITING", 64, 0)
    max_idle = _positive_float("LABEL_VIEWER_DB_POOL_MAX_IDLE", 60.0)
    max_lifetime = _positive_float("LABEL_VIEWER_DB_POOL_MAX_LIFETIME", 1800.0)
    settings = {
        "min_size": min_size,
        "max_size": max_size,
        "timeout": timeout,
        "max_waiting": max_waiting,
        "max_idle": max_idle,
        "max_lifetime": max_lifetime,
        "reconnect_timeout": _positive_float("LABEL_VIEWER_DB_RECONNECT_TIMEOUT", 30.0),
        "num_workers": _positive_int("LABEL_VIEWER_DB_POOL_WORKERS", 2),
    }
    # libpq also reads PG* variables from the process environment (including
    # PGHOST/PGPORT/PGUSER/PGPASSWORD when the URL is just
    # postgresql:///db). Include them in the in-memory pool identity so a
    # runtime config change cannot keep handing out connections to the old
    # server or credentials. Values are never logged or exposed.
    pg_environment = tuple(sorted(
        (name, value) for name, value in os.environ.items()
        if name.startswith("PG")
    ))
    key = (url, tuple(sorted(kwargs.items())), pg_environment,
           tuple(sorted(settings.items())))
    return kwargs, settings, key


def _after_fork_child() -> None:
    """Discard inherited pool state; a forked worker must create its own pool."""
    global _POOL_LOCK, _POOL, _POOL_PID, _POOL_KEY
    if _POOL is not None:
        # Keep the inherited object alive: its worker threads vanished at fork,
        # and closing its sockets could send protocol data into the parent's pool.
        _FORKED_POOL_REFS.append(_POOL)
    _POOL = None
    _POOL_PID = None
    _POOL_KEY = None
    _POOL_LOCK = threading.RLock()
    _CURRENT_CONNECTION.set(None)


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork_child)


def _pool_for_current_process():
    global _POOL, _POOL_PID, _POOL_KEY
    psycopg = _psycopg()
    try:
        from psycopg_pool import ConnectionPool
    except ImportError as exc:
        raise RuntimeError("PostgreSQL is configured but psycopg_pool is not installed") from exc
    url = _database_url()
    kwargs, settings, key = _pool_options(psycopg, url)
    pid = os.getpid()
    with _POOL_LOCK:
        if _POOL is not None and _POOL_PID == pid and _POOL_KEY == key:
            return _POOL
        if _POOL is not None:
            old_pool, old_pid = _POOL, _POOL_PID
            _POOL = None
            _POOL_PID = None
            _POOL_KEY = None
            if old_pid == pid:
                old_pool.close()
            else:
                _FORKED_POOL_REFS.append(old_pool)
        pool = ConnectionPool(
            conninfo="",
            kwargs=kwargs,
            open=False,
            check=ConnectionPool.check_connection,
            **settings,
        )
        pool.open(wait=False)
        _POOL, _POOL_PID, _POOL_KEY = pool, pid, key
        return pool


def _pool_timeout() -> float:
    return _positive_float("LABEL_VIEWER_DB_POOL_TIMEOUT", 10.0)


def close_pool() -> None:
    """Close this process's pool. Safe to call repeatedly during application shutdown."""
    global _POOL, _POOL_PID, _POOL_KEY
    pid = os.getpid()
    with _POOL_LOCK:
        if _POOL is None or _POOL_PID != pid:
            return
        pool = _POOL
        _POOL = None
        _POOL_PID = None
        _POOL_KEY = None
    pool.close(timeout=5.0)


@contextmanager
def connection() -> Iterator[Any]:
    """Yield a transaction connection; nested calls reuse the current connection."""
    current = _CURRENT_CONNECTION.get()
    pid = os.getpid()
    if current is not None and current[0] == pid:
        yield current[1]
        return
    if current is not None:
        _CURRENT_CONNECTION.set(None)
    pool = _pool_for_current_process()
    with pool.connection(timeout=_pool_timeout()) as conn:
        token = _CURRENT_CONNECTION.set((pid, conn))
        try:
            yield conn
        finally:
            _CURRENT_CONNECTION.reset(token)


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
    """Hold a session advisory lock on a pooled checkout, independent of CRUD transactions."""
    if not enabled():
        yield True
        return
    key1, key2 = _lock_keys(data_dir, resource)
    pool = _pool_for_current_process()
    with pool.connection(timeout=_pool_timeout()) as conn:
        previous_autocommit = conn.autocommit
        conn.autocommit = True
        acquired = False
        body_error: BaseException | None = None
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
            yield acquired
        except BaseException as exc:
            body_error = exc
            raise
        finally:
            if acquired:
                unlock = "pg_advisory_unlock_shared" if shared else "pg_advisory_unlock"
                try:
                    conn.execute(f"SELECT {unlock}(%s, %s)", (key1, key2))
                except BaseException:
                    # Closing the session is the only safe fallback if explicit
                    # unlock fails; the pool discards closed connections.
                    conn.close()
                    if body_error is None:
                        raise
            if not conn.closed:
                try:
                    conn.autocommit = previous_autocommit
                except BaseException:
                    conn.close()
                    if body_error is None:
                        raise


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
            CREATE TABLE IF NOT EXISTS bundle_summaries (
                namespace TEXT NOT NULL,
                bundle_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                counts JSONB NOT NULL,
                PRIMARY KEY (namespace, bundle_id),
                FOREIGN KEY (namespace, bundle_id) REFERENCES bundles(namespace, bundle_id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doc_summaries (
                namespace TEXT NOT NULL,
                bundle_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                summary JSONB NOT NULL,
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata_imports (
                namespace TEXT PRIMARY KEY,
                completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)


def read_bundle_state(bdir: Path) -> dict:
    ns = namespace(bdir.parent.parent)
    with connection() as conn:
        row = conn.execute(
            """
            SELECT b.name, b.created_at, b.extra,
                   COALESCE((
                       SELECT jsonb_object_agg(d.doc_id, d.review)
                       FROM documents d
                       WHERE d.namespace=b.namespace AND d.bundle_id=b.bundle_id AND d.review <> ''
                   ), '{}'::jsonb) AS review,
                   COALESCE((
                       SELECT jsonb_agg(d.doc_id)
                       FROM documents d
                       WHERE d.namespace=b.namespace AND d.bundle_id=b.bundle_id AND NOT d.enabled
                   ), '[]'::jsonb) AS disabled
            FROM bundles b WHERE b.namespace=%s AND b.bundle_id=%s
            """,
            (ns, bdir.name),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"bundle metadata not found in PostgreSQL: {bdir.name}")
        name, created_at, extra, review, disabled = row
    state = dict(extra or {})
    state.update(name=name, created_at=created_at)
    state["review"] = dict(review or {})
    state["disabled"] = list(disabled or [])
    return state


def list_bundle_metadata(data_dir: Path, *, query: str = "", sort: str = "newest",
                         offset: int = 0, limit: int | None = None) -> tuple[int, int, list[dict]]:
    """Fetch bundle metadata/review in one query; counts are maintained separately."""
    if sort not in ("newest", "oldest", "name"):
        raise ValueError("unsupported bundle sort")
    ns = namespace(data_dir)
    needle = str(query or "").lower()
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    ordering = {
        "newest": "created_at DESC, bundle_id ASC",
        "oldest": "created_at ASC, bundle_id ASC",
        "name": "lower(name) COLLATE \"C\" ASC, name COLLATE \"C\" ASC, bundle_id COLLATE \"C\" ASC",
    }[sort]
    with connection() as conn:
        rows = conn.execute(f"""
            WITH all_rows AS (
                SELECT b.bundle_id, b.name, b.created_at
                FROM bundles b WHERE b.namespace=%s
            ), filtered AS (
                SELECT * FROM all_rows
                WHERE %s='' OR lower(name) LIKE %s ESCAPE E'\\\\'
                             OR lower(bundle_id) LIKE %s ESCAPE E'\\\\'
            ), totals AS (
                SELECT (SELECT count(*) FROM all_rows) AS total,
                       (SELECT count(*) FROM filtered) AS filtered_total
            )
            SELECT totals.total, totals.filtered_total,
                   page.bundle_id, page.name, page.created_at,
                   COALESCE(review.review, '{{}}'::jsonb)
            FROM totals
            LEFT JOIN LATERAL (
                SELECT * FROM filtered ORDER BY {ordering} LIMIT %s OFFSET %s
            ) AS page ON TRUE
            LEFT JOIN LATERAL (
                SELECT jsonb_object_agg(d.doc_id, d.review)
                           FILTER (WHERE d.review <> '') AS review
                FROM documents d
                WHERE d.namespace=%s AND d.bundle_id=page.bundle_id
            ) AS review ON page.bundle_id IS NOT NULL
            ORDER BY {ordering}
        """, (ns, needle, pattern, pattern, limit, offset, ns)).fetchall()
    total = int(rows[0][0]) if rows else 0
    filtered_total = int(rows[0][1]) if rows else 0
    items = [{"id": bid, "name": name, "created_at": created, "review": dict(review or {})}
             for _total, _filtered_total, bid, name, created, review in rows if bid is not None]
    return total, filtered_total, items


def get_bundle_summaries(data_dir: Path, bundle_ids: list[str]) -> dict[str, dict]:
    if not bundle_ids:
        return {}
    with connection() as conn:
        rows = conn.execute("""
            SELECT bundle_id, fingerprint, counts FROM bundle_summaries
            WHERE namespace=%s AND bundle_id = ANY(%s::text[])
        """, (namespace(data_dir), bundle_ids)).fetchall()
    return {bid: {"fingerprint": fingerprint, "counts": dict(counts or {})}
            for bid, fingerprint, counts in rows}


def save_bundle_summaries(data_dir: Path, summaries: dict[str, dict]) -> None:
    if not summaries:
        return
    psycopg = _psycopg()
    ns = namespace(data_dir)
    with connection() as conn:
        conn.cursor().executemany("""
            INSERT INTO bundle_summaries(namespace,bundle_id,fingerprint,counts)
            SELECT %s,%s,%s,%s
            WHERE EXISTS (
                SELECT 1 FROM bundles WHERE namespace=%s AND bundle_id=%s
            )
            ON CONFLICT(namespace,bundle_id) DO UPDATE SET
                fingerprint=EXCLUDED.fingerprint, counts=EXCLUDED.counts
        """, [(ns, bid, value["fingerprint"], psycopg.types.json.Jsonb(value["counts"]), ns, bid)
              for bid, value in summaries.items()])


def get_doc_summaries(data_dir: Path, bundle_id: str, doc_ids: list[str]) -> dict[str, tuple[str, dict]]:
    """문서 요약 저장본. 원본 파일에서 다시 만들 수 있는 캐시다."""
    if not doc_ids:
        return {}
    with connection() as conn:
        rows = conn.execute("""
            SELECT doc_id, fingerprint, summary FROM doc_summaries
            WHERE namespace=%s AND bundle_id=%s AND doc_id = ANY(%s::text[])
        """, (namespace(data_dir), bundle_id, doc_ids)).fetchall()
    return {doc_id: (fingerprint, summary) for doc_id, fingerprint, summary in rows}


def save_doc_summaries(data_dir: Path, bundle_id: str, summaries: dict[str, tuple[str, dict]]) -> None:
    if not summaries:
        return
    psycopg = _psycopg()
    ns = namespace(data_dir)
    with connection() as conn:
        conn.cursor().executemany("""
            INSERT INTO doc_summaries(namespace,bundle_id,doc_id,fingerprint,summary)
            SELECT %s,%s,%s,%s,%s
            WHERE EXISTS (
                SELECT 1 FROM bundles WHERE namespace=%s AND bundle_id=%s
            )
            ON CONFLICT(namespace,bundle_id,doc_id) DO UPDATE SET
                fingerprint=EXCLUDED.fingerprint, summary=EXCLUDED.summary
        """, [(ns, bundle_id, doc_id, fp, psycopg.types.json.Jsonb(summary), ns, bundle_id)
              for doc_id, (fp, summary) in summaries.items()])


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
        doc_ids = set(review) | disabled
        rows = sorted(doc_ids)
        conn.execute("""
            DELETE FROM documents
            WHERE namespace=%s AND bundle_id=%s AND NOT (doc_id = ANY(%s::text[]))
        """, (ns, bdir.name, rows))
        if rows:
            conn.execute("""
                INSERT INTO documents(namespace,bundle_id,doc_id,review,enabled)
                SELECT %s,%s,incoming.doc_id,incoming.review,incoming.enabled
                FROM unnest(%s::text[],%s::text[],%s::boolean[])
                     AS incoming(doc_id,review,enabled)
                ON CONFLICT(namespace,bundle_id,doc_id) DO UPDATE SET
                    review=EXCLUDED.review, enabled=EXCLUDED.enabled
            """, (ns, bdir.name, rows, [review.get(i, "") for i in rows],
                  [i not in disabled for i in rows]))


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


def pool_stats() -> dict[str, Any]:
    """Return psycopg_pool counters for tests and local diagnostics."""
    if not enabled():
        return {}
    return _pool_for_current_process().get_stats()
