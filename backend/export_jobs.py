"""Filesystem backed export jobs shared by all application workers."""
from __future__ import annotations

import fcntl
import json
import os
import secrets
import socket
import shutil
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from . import bundle as B
from . import db as DB
from . import export as E

_JOB_TTL_SECONDS = 24 * 60 * 60
_MAX_CONCURRENT_EXPORTS = 2
_MAX_PENDING_EXPORTS = 20
_SLOT_POLL_SECONDS = 0.2
_PROGRESS_WRITE_INTERVAL = 0.5
_LEASE_SECONDS = 90
_HEARTBEAT_SECONDS = 15
_SHUTDOWN_JOIN_SECONDS = 5
_PG_INIT_PID = None
_PG_INIT_LOCK = threading.Lock()
_WORKERS: dict[tuple[str, str, str], threading.Thread] = {}
_WORKERS_LOCK = threading.Lock()
_SHUTTING_DOWN: set[str] = set()


def _pg(data_dir: Path) -> bool:
    return DB.enabled()


def _ensure_pg(data_dir: Path) -> bool:
    global _PG_INIT_PID
    if not _pg(data_dir):
        return False
    pid = os.getpid()
    if _PG_INIT_PID != pid:
        with _PG_INIT_LOCK:
            if _PG_INIT_PID != pid:
                DB.initialize()
                _PG_INIT_PID = pid
    return True


def _job_identity(job_dir: Path) -> tuple[Path, str, str]:
    return job_dir.parents[3], job_dir.parent.name, job_dir.name


def _job_lock_resource(bundle_id: str, job_id: str) -> str:
    return f"export-job:{bundle_id}:{job_id}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root(data_dir: Path) -> Path:
    return B.cache_root(data_dir) / "export-jobs"


def _bundle_job_root(data_dir: Path, bundle_id: str) -> Path:
    B.bundle_dir(data_dir, bundle_id)
    return _root(data_dir) / bundle_id


def _job_dir(data_dir: Path, bundle_id: str, job_id: str) -> Path:
    B._safe_id(job_id, "job_id")
    bdir = B.bundle_dir(data_dir, bundle_id)
    if not bdir.is_dir():
        raise B.ApiError(404, "bundle not found")
    _pg(data_dir)
    d = _bundle_job_root(data_dir, bundle_id) / job_id
    if not d.is_dir():
        raise B.ApiError(404, "export job not found")
    if DB.enabled():
        try:
            _read_state(d)
        except B.ApiError as exc:
            if exc.status == 404:
                raise B.ApiError(404, "export job not found") from exc
            raise
    return d


@contextmanager
def _locked(job_dir: Path, blocking: bool = True) -> Iterator[bool]:
    data_dir, bundle_id, job_id = _job_identity(job_dir)
    if _pg(data_dir):
        with DB.lock(data_dir, _job_lock_resource(bundle_id, job_id), blocking=blocking) as acquired:
            yield acquired
        return
    try:
        fd = os.open(job_dir / "job.lock", os.O_CREAT | os.O_RDWR, 0o600)
    except FileNotFoundError as exc:
        raise B.ApiError(404, "export job not found") from exc
    try:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


def _read_state(job_dir: Path) -> dict:
    data_dir, bundle_id, job_id = _job_identity(job_dir)
    if DB.enabled():
        with DB.connection() as conn:
            row = conn.execute(
                "SELECT state FROM export_jobs WHERE namespace=%s AND bundle_id=%s AND id=%s",
                (DB.namespace(data_dir), bundle_id, job_id),
            ).fetchone()
        if row is None:
            raise B.ApiError(404, "export job not found")
        state = row[0]
        if not isinstance(state, dict):
            raise B.ApiError(500, "export job state is invalid")
        return state
    try:
        with (job_dir / "job.json").open(encoding="utf-8") as stream:
            state = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise B.ApiError(500, f"export job state unreadable: {exc}") from exc
    if not isinstance(state, dict):
        raise B.ApiError(500, "export job state is invalid")
    return state


def _write_state(job_dir: Path, state: dict, *, create: bool = False) -> None:
    state["updated_at"] = _now()
    data_dir, bundle_id, job_id = _job_identity(job_dir)
    if DB.enabled():
        with DB.connection() as conn:
            encoded = json.dumps(state, ensure_ascii=False)
            if create:
                conn.execute("""
                    INSERT INTO export_jobs(namespace,bundle_id,id,state)
                    VALUES (%s,%s,%s,%s::jsonb)
                """, (DB.namespace(data_dir), bundle_id, job_id, encoded))
            else:
                result = conn.execute("""
                    UPDATE export_jobs SET state=%s::jsonb
                    WHERE namespace=%s AND bundle_id=%s AND id=%s
                """, (encoded, DB.namespace(data_dir), bundle_id, job_id))
                if result.rowcount == 0:
                    raise B.ApiError(404, "export job not found")
        return
    B._atomic_write_json(job_dir / "job.json", state)


def _public(state: dict) -> dict:
    return {key: state.get(key) for key in (
        "id", "state", "completed", "total", "phase", "message", "filename",
    )}


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _recover_orphaned(job_dir: Path, state: dict) -> dict:
    if state.get("state") in ("queued", "running"):
        data_dir, _bundle_id, _job_id = _job_identity(job_dir)
        if DB.enabled():
            heartbeat = state.get("heartbeat_at") or state.get("updated_at") or state.get("created_at")
            try:
                stale = not heartbeat or time.time() - datetime.fromisoformat(heartbeat).timestamp() > _LEASE_SECONDS
            except (TypeError, ValueError):
                stale = True
        else:
            pid = state.get("owner_pid")
            stale = isinstance(pid, int) and not _is_alive(pid)
        if stale:
            state.update(state="failed", phase="failed", message="내보내기 작업 프로세스가 종료되었습니다.")
            (job_dir / "artifact.part").unlink(missing_ok=True)
            _write_state(job_dir, state)
    return state


def _cleanup_expired(root: Path, data_dir: Path) -> None:
    if DB.enabled():
        namespace = DB.namespace(data_dir)
        with DB.connection() as conn:
            rows = conn.execute(
                "SELECT bundle_id,id,state FROM export_jobs WHERE namespace=%s",
                (namespace,),
            ).fetchall()
        known_dirs = {(bundle_id, job_id) for bundle_id, job_id, _state in rows}
        for bundle_id, job_id, _ in rows:
            job_dir = root / bundle_id / job_id
            if not job_dir.is_dir():
                with DB.connection() as conn:
                    conn.execute("DELETE FROM export_jobs WHERE namespace=%s AND bundle_id=%s AND id=%s",
                                 (namespace, bundle_id, job_id))
                continue
            remove = False
            try:
                with _locked(job_dir, blocking=False) as acquired:
                    if not acquired:
                        continue
                    state = _recover_orphaned(job_dir, _read_state(job_dir))
                    stamp = state.get("updated_at") or state.get("created_at")
                    try:
                        old = bool(stamp) and time.time() - datetime.fromisoformat(stamp).timestamp() > _JOB_TTL_SECONDS
                    except (TypeError, ValueError):
                        old = True
                    if old and state.get("state") not in ("queued", "running"):
                        with DB.connection() as conn:
                            conn.execute("DELETE FROM export_jobs WHERE namespace=%s AND bundle_id=%s AND id=%s",
                                         (namespace, bundle_id, job_id))
                        remove = True
            except B.ApiError:
                continue
            if remove:
                shutil.rmtree(job_dir, ignore_errors=True)
        # A hard process stop after bundle cascade can leave files with no row to
        # drive the usual TTL cleanup. Remove such directories only after their
        # own contents have been idle for the full retention interval.
        cutoff = time.time() - _JOB_TTL_SECONDS
        if root.is_dir():
            for bundle_dir in root.iterdir():
                if not bundle_dir.is_dir() or bundle_dir.name.startswith("."):
                    continue
                for job_dir in bundle_dir.iterdir():
                    if not job_dir.is_dir() or (bundle_dir.name, job_dir.name) in known_dirs:
                        continue
                    try:
                        children = list(job_dir.iterdir())
                        activity = (max(child.stat().st_mtime for child in children)
                                    if children else job_dir.stat().st_mtime)
                    except OSError:
                        continue
                    if activity < cutoff:
                        shutil.rmtree(job_dir, ignore_errors=True)
        return
    if not root.is_dir():
        return
    cutoff = time.time() - _JOB_TTL_SECONDS
    for bundle_dir in root.iterdir():
        if not bundle_dir.is_dir() or bundle_dir.name.startswith("."):
            continue
        for job_dir in bundle_dir.iterdir():
            if not job_dir.is_dir():
                continue
            try:
                old = job_dir.stat().st_mtime < cutoff
            except OSError:
                continue
            if not old:
                continue
            expired_dir = bundle_dir / f".expired-{job_dir.name}-{secrets.token_hex(3)}"
            try:
                with _locked(job_dir, blocking=False) as acquired:
                    if not acquired:
                        continue
                    try:
                        state = _recover_orphaned(job_dir, _read_state(job_dir))
                    except B.ApiError:
                        # An aged, incomplete directory cannot be active after holding its lock.
                        state = {"state": "failed"}
                    if state.get("state") not in ("queued", "running"):
                        try:
                            os.replace(job_dir, expired_dir)
                        except FileNotFoundError:
                            pass
            except B.ApiError:
                continue
            shutil.rmtree(expired_dir, ignore_errors=True)


@contextmanager
def _queue_lock(data_dir: Path, root: Path) -> Iterator[None]:
    if DB.enabled():
        with DB.lock(data_dir, "export-jobs-queue") as acquired:
            if not acquired:
                raise B.ApiError(503, "could not acquire export queue lock")
            yield
        return
    fd = os.open(root / ".queue.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _pending_count(root: Path, data_dir: Path) -> int:
    if DB.enabled():
        namespace = DB.namespace(data_dir)
        with DB.connection() as conn:
            rows = conn.execute("SELECT bundle_id,id,state FROM export_jobs WHERE namespace=%s", (namespace,)).fetchall()
        count = 0
        for bundle_id, job_id, state in rows:
            job_dir = root / bundle_id / job_id
            if not job_dir.is_dir():
                continue
            try:
                with _locked(job_dir) as _:
                    state = _recover_orphaned(job_dir, _read_state(job_dir))
            except B.ApiError:
                continue
            if state.get("state") in ("queued", "running"):
                count += 1
        return count
    count = 0
    for bundle_dir in root.iterdir():
        if not bundle_dir.is_dir() or bundle_dir.name.startswith("."):
            continue
        for job_dir in bundle_dir.iterdir():
            if not job_dir.is_dir() or job_dir.name.startswith("."):
                continue
            try:
                with _locked(job_dir) as _:
                    state = _recover_orphaned(job_dir, _read_state(job_dir))
            except B.ApiError:
                continue
            if state.get("state") in ("queued", "running"):
                count += 1
    return count


def _slot_lock(data_dir: Path):
    if DB.enabled():
        for index in range(_MAX_CONCURRENT_EXPORTS):
            lock = DB.session_lock(data_dir, f"export-jobs-slot:{index}", blocking=False)
            acquired = lock.__enter__()
            if acquired:
                return ("pg", lock)
            lock.__exit__(None, None, None)
        return None
    slots = _root(data_dir) / ".slots"
    slots.mkdir(parents=True, exist_ok=True)
    for index in range(_MAX_CONCURRENT_EXPORTS):
        fd = os.open(slots / f"{index}.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            os.close(fd)
    return None


def _release_slot(fd: int | None) -> None:
    if fd is not None:
        if isinstance(fd, tuple) and fd[0] == "pg":
            fd[1].__exit__(None, None, None)
            return
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _cancelled(job_dir: Path) -> bool:
    if DB.enabled():
        try:
            return _read_state(job_dir).get("state") == "cancelled"
        except B.ApiError:
            return True
    return (job_dir / "cancel.flag").exists()


class _CancellationProbe:
    def __init__(self, job_dir: Path, owner_token: str = "", lease_lost: threading.Event | None = None):
        self.job_dir = job_dir
        self.owner_token = owner_token
        self.lease_lost = lease_lost
        self.last_check = 0.0
        self.value = False
        self.lease_failure_reported = False

    def __call__(self) -> bool:
        if self.lease_lost is not None and self.lease_lost.is_set():
            if not self.lease_failure_reported:
                self.lease_failure_reported = True
                _mark_lease_lost(self.job_dir, self.owner_token)
            return True
        if not DB.enabled():
            return _cancelled(self.job_dir)
        now = time.monotonic()
        if now - self.last_check >= 0.2:
            self.value = _cancelled(self.job_dir)
            self.last_check = now
        return self.value


def _mark_lease_lost(job_dir: Path, owner_token: str) -> None:
    try:
        with _locked(job_dir) as _:
            state = _read_state(job_dir)
            if state.get("state") == "running" and state.get("owner_token") == owner_token:
                state.update(state="failed", phase="failed",
                             message="작업 상태 연결이 끊겨 내보내기를 중단했습니다.")
                _write_state(job_dir, state)
    except Exception:
        # The database can still be unavailable; an expired lease is recovered later.
        pass


def _update_progress(job_dir: Path, completed: int, total: int, phase: str) -> None:
    with _locked(job_dir) as _:
        state = _read_state(job_dir)
        if state.get("state") == "cancelled" or _cancelled(job_dir):
            raise E.ExportCancelled("export cancelled")
        if state.get("state") != "running":
            raise E.ExportCancelled("export stopped")
        state.update(completed=completed, total=total, phase=phase,
                     heartbeat_at=_now(),
                     message={"preparing": "내보내기를 준비하고 있습니다.",
                              "writing": "문서를 내보내고 있습니다.",
                              "finalizing": "파일을 마무리하고 있습니다."}.get(phase, phase))
        _write_state(job_dir, state)


class _ProgressReporter:
    """Persist progress at most twice a second, with preparing/finalizing always visible."""
    def __init__(self, job_dir: Path, interval: float = _PROGRESS_WRITE_INTERVAL,
                 clock=time.monotonic):
        self.job_dir = job_dir
        self.interval = interval
        self.clock = clock
        self.last_write: float | None = None
        self.latest: tuple[int, int, str] | None = None

    def __call__(self, completed: int, total: int, phase: str) -> None:
        now = self.clock()
        self.latest = (completed, total, phase)
        if (self.last_write is None or phase in ("preparing", "finalizing")
                or now - self.last_write >= self.interval):
            self.flush(now)

    def flush(self, now: float | None = None) -> None:
        if self.latest is None:
            return
        completed, total, phase = self.latest
        _update_progress(self.job_dir, completed, total, phase)
        self.latest = None
        self.last_write = self.clock() if now is None else now


def _mark_cancelled(job_dir: Path) -> None:
    with _locked(job_dir) as _:
        try:
            state = _read_state(job_dir)
        except B.ApiError:
            return
        if state.get("state") in ("cancelled", "ready"):
            state.update(state="cancelled", phase="cancelled", message="내보내기를 취소했습니다.")
            try:
                _write_state(job_dir, state)
            except B.ApiError as exc:
                if exc.status != 404:
                    raise
        elif state.get("state") in ("queued", "running"):
            state.update(state="cancelled", phase="cancelled", message="내보내기를 취소했습니다.")
            try:
                _write_state(job_dir, state)
            except B.ApiError as exc:
                if exc.status != 404:
                    raise
    (job_dir / "artifact.part").unlink(missing_ok=True)


def _best_effort_mark_cancelled(job_dir: Path) -> None:
    try:
        _mark_cancelled(job_dir)
    except Exception:
        # Cancellation was already recorded by the request, or PostgreSQL is
        # temporarily unavailable. Do not strand a worker thread on error reporting.
        pass


def _heartbeat_loop(job_dir: Path, owner_token: str, stopped: threading.Event,
                    lease_lost: threading.Event) -> None:
    failure_since = None
    while not stopped.wait(_HEARTBEAT_SECONDS):
        try:
            with _locked(job_dir) as _:
                state = _read_state(job_dir)
                if state.get("state") not in ("queued", "running") or state.get("owner_token") != owner_token:
                    lease_lost.set()
                    return
                state["heartbeat_at"] = _now()
                _write_state(job_dir, state)
        except Exception:
            if failure_since is None:
                failure_since = time.monotonic()
            elif time.monotonic() - failure_since >= _LEASE_SECONDS:
                lease_lost.set()
                return
            continue
        failure_since = None


def _worker_key(data_dir: Path, bundle_id: str, job_id: str) -> tuple[str, str, str]:
    return str(Path(data_dir).expanduser().resolve()), bundle_id, job_id


def _worker_entry(data_dir: Path, bundle_id: str, job_dir: Path) -> None:
    key = _worker_key(data_dir, bundle_id, job_dir.name)
    try:
        _run_job(data_dir, bundle_id, job_dir)
    finally:
        with _WORKERS_LOCK:
            _WORKERS.pop(key, None)


def startup(data_dir: Path) -> None:
    """Allow exports for a new application lifespan in the current process."""
    root = str(Path(data_dir).expanduser().resolve())
    with _WORKERS_LOCK:
        _SHUTTING_DOWN.discard(root)


def shutdown(data_dir: Path) -> None:
    """Cancel this process's pending exports and join workers before DB pool shutdown."""
    data_dir = Path(data_dir)
    root = str(data_dir.expanduser().resolve())
    with _WORKERS_LOCK:
        _SHUTTING_DOWN.add(root)
        workers = [(key, thread) for key, thread in _WORKERS.items() if key[0] == root]
    if DB.enabled() and workers:
        bundle_ids = [key[1] for key, _thread in workers]
        job_ids = [key[2] for key, _thread in workers]
        try:
            with DB.connection() as conn:
                # Take the same per-job advisory locks as worker state updates so
                # a stale progress snapshot cannot overwrite the shutdown cancel.
                for bundle_id, job_id in sorted(set(zip(bundle_ids, job_ids))):
                    with DB.lock(data_dir, _job_lock_resource(bundle_id, job_id)) as acquired:
                        if not acquired:
                            raise B.ApiError(503, "could not lock export job during shutdown")
                conn.execute("""
                    UPDATE export_jobs
                    SET state=state || %s::jsonb
                    WHERE namespace=%s AND state->>'state' IN ('queued','running')
                      AND (bundle_id,id) IN (SELECT * FROM unnest(%s::text[],%s::text[]))
                """, (json.dumps({"state": "cancelled", "phase": "cancelled",
                                   "message": "서버 종료로 내보내기를 취소했습니다.",
                                   "updated_at": _now()}, ensure_ascii=False),
                      DB.namespace(data_dir), bundle_ids, job_ids))
        except Exception:
            # Workers still get a bounded join; a later startup recovers expired leases.
            pass
    else:
        for (worker_root, bundle_id, job_id), _thread in workers:
            try:
                cancel(Path(worker_root), bundle_id, job_id)
            except Exception:
                pass
    for (worker_root, bundle_id, job_id), _thread in workers:
        try:
            (Path(worker_root) / ".cache" / "export-jobs" / bundle_id / job_id / "artifact.part").unlink(missing_ok=True)
        except OSError:
            pass
    deadline = time.monotonic() + _SHUTDOWN_JOIN_SECONDS
    for _key, thread in workers:
        thread.join(max(0.0, deadline - time.monotonic()))


def _run_job(data_dir: Path, bundle_id: str, job_dir: Path) -> None:
    slot = None
    heartbeat_stop = threading.Event()
    lease_lost = threading.Event()
    heartbeat_thread = None
    owner_token = ""
    try:
        if DB.enabled():
            initial = _read_state(job_dir)
            owner_token = initial.get("owner_token", "")
            heartbeat_thread = threading.Thread(target=_heartbeat_loop,
                                               args=(job_dir, owner_token, heartbeat_stop, lease_lost),
                                               daemon=True, name=f"export-heartbeat-{job_dir.name}")
            heartbeat_thread.start()
        while slot is None:
            if _cancelled(job_dir):
                _best_effort_mark_cancelled(job_dir)
                return
            slot = _slot_lock(data_dir)
            if slot is None:
                time.sleep(_SLOT_POLL_SECONDS)
        stopped = False
        with _locked(job_dir) as _:
            state = _read_state(job_dir)
            if state.get("state") != "queued" or _cancelled(job_dir):
                stopped = True
            else:
                state.update(state="running", phase="preparing", message="내보내기를 준비하고 있습니다.",
                             owner_pid=os.getpid(), heartbeat_at=_now())
                _write_state(job_dir, state)
        if stopped:
            _best_effort_mark_cancelled(job_dir)
            return

        fmt = state["format"]
        target = job_dir / "artifact.part"
        cancel_probe = _CancellationProbe(job_dir, owner_token, lease_lost)
        progress_reporter = _ProgressReporter(job_dir)
        with target.open("wb") as out:
            hooks = {"ids": state["doc_ids"],
                     "progress": progress_reporter,
                     "cancel_check": cancel_probe,
                     "out": out}
            if fmt == "zip":
                E.export_bundle_zip(data_dir, bundle_id, scope=state["scope"], **hooks)
            else:
                E.export_golden_xlsx(data_dir, bundle_id, scope=state["scope"], **hooks)
            out.flush()
            os.fsync(out.fileno())
        with _locked(job_dir) as _:
            state = _read_state(job_dir)
            if lease_lost.is_set():
                if state.get("state") == "running" and state.get("owner_token") == owner_token:
                    state.update(state="failed", phase="failed",
                                 message="작업 상태 연결이 끊겨 내보내기를 중단했습니다.")
                    _write_state(job_dir, state)
                target.unlink(missing_ok=True)
                return
            if state.get("state") == "cancelled" or _cancelled(job_dir):
                state.update(state="cancelled", phase="cancelled", message="내보내기를 취소했습니다.")
                _write_state(job_dir, state)
                target.unlink(missing_ok=True)
                return
            if ((owner_token and state.get("owner_token") != owner_token)
                    or state.get("state") != "running"):
                target.unlink(missing_ok=True)
                return
            artifact = job_dir / f"artifact.{fmt}"
            os.replace(target, artifact)
            state.update(state="ready", completed=state["total"], phase="ready",
                         message="내보내기가 완료되었습니다.", artifact=artifact.name)
            _write_state(job_dir, state)
    except E.ExportCancelled:
        _best_effort_mark_cancelled(job_dir)
    except BaseException:
        try:
            with _locked(job_dir) as _:
                state = _read_state(job_dir)
                if state.get("state") != "cancelled":
                    # Driver and filesystem exception text can contain credentials or
                    # deployment paths. Keep client-visible messages generic.
                    state.update(state="failed", phase="failed", message="내보내기에 실패했습니다.")
                    _write_state(job_dir, state)
        except Exception:
            # If the database is unavailable, let the heartbeat lease recover the
            # job after connectivity returns instead of leaking a worker exception.
            pass
        (job_dir / "artifact.part").unlink(missing_ok=True)
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=1)
        try:
            _release_slot(slot)
        except Exception:
            # Closing the failed session releases its advisory lock server-side.
            pass
        if DB.enabled():
            try:
                _read_state(job_dir)
            except B.ApiError as exc:
                if exc.status == 404:
                    shutil.rmtree(job_dir, ignore_errors=True)
            except Exception:
                # A transient DB outage is not evidence that the row was deleted.
                pass


def start(data_dir: Path, bundle_id: str, format: str, scope: str = "enabled",
          doc_ids: list[str] | None = None) -> dict:
    """Validate and start a shared, background export job."""
    _ensure_pg(data_dir)
    root_key = str(Path(data_dir).expanduser().resolve())
    with _WORKERS_LOCK:
        if root_key in _SHUTTING_DOWN:
            raise B.ApiError(503, "export service is shutting down")
    if format not in ("xlsx", "zip"):
        raise B.ApiError(422, "format must be 'xlsx' or 'zip'")
    bdir = B.bundle_dir(data_dir, bundle_id)
    if not bdir.is_dir():
        raise B.ApiError(404, "bundle not found")
    _, selected = E._resolve_doc_ids(data_dir, bundle_id, None, scope, doc_ids)
    if not selected:
        raise B.ApiError(422, "no documents in export")
    root = _root(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    _cleanup_expired(root, data_dir)
    with _queue_lock(data_dir, root):
        if _pending_count(root, data_dir) >= _MAX_PENDING_EXPORTS:
            raise B.ApiError(429, "too many export jobs queued")
        job_id = secrets.token_hex(12)
        job_dir = _bundle_job_root(data_dir, bundle_id) / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        state = {
            "id": job_id, "state": "queued", "completed": 0, "total": len(selected),
            "phase": "queued", "message": "대기 중입니다.",
            "filename": f"{bundle_id}{'-selected' if doc_ids is not None else '-disabled' if scope == 'disabled' else ''}"
                        f"{'-golden.xlsx' if format == 'xlsx' else '.zip'}",
            "format": format, "scope": scope, "doc_ids": selected,
            "owner_pid": os.getpid(), "created_at": _now(), "updated_at": _now(),
        }
        if DB.enabled():
            state.update(owner_token=secrets.token_hex(16), owner_host=socket.gethostname(), heartbeat_at=_now())
        try:
            _write_state(job_dir, state, create=True)
        except Exception:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise
    try:
        worker = threading.Thread(target=_worker_entry, args=(Path(data_dir), bundle_id, job_dir), daemon=True,
                                  name=f"export-{job_id}")
        key = _worker_key(Path(data_dir), bundle_id, job_id)
        with _WORKERS_LOCK:
            if root_key in _SHUTTING_DOWN:
                state.update(state="failed", phase="failed", message="서버가 종료 중이라 작업을 시작하지 못했습니다.")
                _write_state(job_dir, state)
                return _public(state)
            _WORKERS[key] = worker
            worker.start()
    except Exception:
        with _WORKERS_LOCK:
            _WORKERS.pop(_worker_key(Path(data_dir), bundle_id, job_id), None)
        state.update(state="failed", phase="failed", message="내보내기 작업을 시작하지 못했습니다.")
        _write_state(job_dir, state)
    return _public(state)


def status(data_dir: Path, bundle_id: str, job_id: str) -> dict:
    _ensure_pg(data_dir)
    job_dir = _job_dir(data_dir, bundle_id, job_id)
    with _locked(job_dir) as _:
        state = _recover_orphaned(job_dir, _read_state(job_dir))
        return _public(state)


def cancel(data_dir: Path, bundle_id: str, job_id: str) -> dict:
    _ensure_pg(data_dir)
    job_dir = _job_dir(data_dir, bundle_id, job_id)
    if not DB.enabled():
        (job_dir / "cancel.flag").touch(exist_ok=True)
    with _locked(job_dir) as _:
        state = _read_state(job_dir)
        was_ready = state.get("state") == "ready" or (
            state.get("state") == "cancelled" and bool(state.get("artifact")))
        if state.get("state") in ("queued", "running", "ready"):
            state.update(state="cancelled", phase="cancelled", message="내보내기를 취소했습니다.")
            _write_state(job_dir, state)
        (job_dir / "artifact.part").unlink(missing_ok=True)
        # Keep a ready artifact until TTL cleanup: result() may already have handed
        # its path to FileResponse, which opens it just after releasing this lock.
        if not was_ready:
            (job_dir / "artifact.zip").unlink(missing_ok=True)
            (job_dir / "artifact.xlsx").unlink(missing_ok=True)
        return _public(state)


def result(data_dir: Path, bundle_id: str, job_id: str) -> tuple[Path, str]:
    _ensure_pg(data_dir)
    job_dir = _job_dir(data_dir, bundle_id, job_id)
    with _locked(job_dir) as _:
        state = _read_state(job_dir)
        if state.get("state") != "ready":
            raise B.ApiError(409, "export job is not ready")
        artifact = job_dir / state["artifact"]
        if not artifact.is_file():
            raise B.ApiError(410, "export artifact expired")
        return artifact, state["filename"]
