"""Filesystem backed export jobs shared by all application workers."""
from __future__ import annotations

import fcntl
import json
import os
import secrets
import shutil
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from . import bundle as B
from . import export as E

_JOB_TTL_SECONDS = 24 * 60 * 60
_MAX_CONCURRENT_EXPORTS = 2
_MAX_PENDING_EXPORTS = 20
_SLOT_POLL_SECONDS = 0.2


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
    d = _bundle_job_root(data_dir, bundle_id) / job_id
    if not d.is_dir():
        raise B.ApiError(404, "export job not found")
    return d


@contextmanager
def _locked(job_dir: Path, blocking: bool = True) -> Iterator[bool]:
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
    try:
        with (job_dir / "job.json").open(encoding="utf-8") as stream:
            state = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise B.ApiError(500, f"export job state unreadable: {exc}") from exc
    if not isinstance(state, dict):
        raise B.ApiError(500, "export job state is invalid")
    return state


def _write_state(job_dir: Path, state: dict) -> None:
    state["updated_at"] = _now()
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
        pid = state.get("owner_pid")
        if isinstance(pid, int) and not _is_alive(pid):
            state.update(state="failed", phase="failed", message="내보내기 작업 프로세스가 종료되었습니다.")
            (job_dir / "artifact.part").unlink(missing_ok=True)
            _write_state(job_dir, state)
    return state


def _cleanup_expired(root: Path) -> None:
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
def _queue_lock(root: Path) -> Iterator[None]:
    fd = os.open(root / ".queue.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _pending_count(root: Path) -> int:
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
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _cancelled(job_dir: Path) -> bool:
    return (job_dir / "cancel.flag").exists()


def _update_progress(job_dir: Path, completed: int, total: int, phase: str) -> None:
    with _locked(job_dir) as _:
        state = _read_state(job_dir)
        if state.get("state") == "cancelled" or _cancelled(job_dir):
            raise E.ExportCancelled("export cancelled")
        if state.get("state") != "running":
            raise E.ExportCancelled("export stopped")
        state.update(completed=completed, total=total, phase=phase,
                     message={"preparing": "내보내기를 준비하고 있습니다.",
                              "writing": "문서를 내보내고 있습니다.",
                              "finalizing": "파일을 마무리하고 있습니다."}.get(phase, phase))
        _write_state(job_dir, state)


def _mark_cancelled(job_dir: Path) -> None:
    with _locked(job_dir) as _:
        try:
            state = _read_state(job_dir)
        except B.ApiError:
            return
        if state.get("state") in ("cancelled", "ready"):
            state.update(state="cancelled", phase="cancelled", message="내보내기를 취소했습니다.")
            _write_state(job_dir, state)
        elif state.get("state") in ("queued", "running"):
            state.update(state="cancelled", phase="cancelled", message="내보내기를 취소했습니다.")
            _write_state(job_dir, state)
    (job_dir / "artifact.part").unlink(missing_ok=True)
    (job_dir / "artifact.zip").unlink(missing_ok=True)
    (job_dir / "artifact.xlsx").unlink(missing_ok=True)


def _run_job(data_dir: Path, bundle_id: str, job_dir: Path) -> None:
    slot = None
    try:
        while slot is None:
            if _cancelled(job_dir):
                _mark_cancelled(job_dir)
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
                             owner_pid=os.getpid())
                _write_state(job_dir, state)
        if stopped:
            _mark_cancelled(job_dir)
            return

        fmt = state["format"]
        target = job_dir / "artifact.part"
        with target.open("wb") as out:
            hooks = {"ids": state["doc_ids"],
                     "progress": lambda n, total, phase: _update_progress(job_dir, n, total, phase),
                     "cancel_check": lambda: _cancelled(job_dir),
                     "out": out}
            if fmt == "zip":
                E.export_bundle_zip(data_dir, bundle_id, scope=state["scope"], **hooks)
            else:
                E.export_golden_xlsx(data_dir, bundle_id, scope=state["scope"], **hooks)
            out.flush()
            os.fsync(out.fileno())
        with _locked(job_dir) as _:
            state = _read_state(job_dir)
            if state.get("state") == "cancelled" or _cancelled(job_dir):
                state.update(state="cancelled", phase="cancelled", message="내보내기를 취소했습니다.")
                _write_state(job_dir, state)
                target.unlink(missing_ok=True)
                return
            artifact = job_dir / f"artifact.{fmt}"
            os.replace(target, artifact)
            state.update(state="ready", completed=state["total"], phase="ready",
                         message="내보내기가 완료되었습니다.", artifact=artifact.name)
            _write_state(job_dir, state)
    except E.ExportCancelled:
        _mark_cancelled(job_dir)
    except BaseException as exc:
        with _locked(job_dir) as _:
            state = _read_state(job_dir)
            if state.get("state") != "cancelled":
                state.update(state="failed", phase="failed", message=f"내보내기에 실패했습니다: {exc}")
                _write_state(job_dir, state)
        (job_dir / "artifact.part").unlink(missing_ok=True)
    finally:
        _release_slot(slot)


def start(data_dir: Path, bundle_id: str, format: str, scope: str = "enabled",
          doc_ids: list[str] | None = None) -> dict:
    """Validate and start a shared, background export job."""
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
    _cleanup_expired(root)
    with _queue_lock(root):
        if _pending_count(root) >= _MAX_PENDING_EXPORTS:
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
        _write_state(job_dir, state)
    try:
        threading.Thread(target=_run_job, args=(Path(data_dir), bundle_id, job_dir), daemon=True,
                         name=f"export-{job_id}").start()
    except Exception as exc:
        state.update(state="failed", phase="failed", message=f"내보내기 작업을 시작하지 못했습니다: {exc}")
        _write_state(job_dir, state)
    return _public(state)


def status(data_dir: Path, bundle_id: str, job_id: str) -> dict:
    job_dir = _job_dir(data_dir, bundle_id, job_id)
    with _locked(job_dir) as _:
        state = _recover_orphaned(job_dir, _read_state(job_dir))
        return _public(state)


def cancel(data_dir: Path, bundle_id: str, job_id: str) -> dict:
    job_dir = _job_dir(data_dir, bundle_id, job_id)
    (job_dir / "cancel.flag").touch(exist_ok=True)
    with _locked(job_dir) as _:
        state = _read_state(job_dir)
        if state.get("state") in ("queued", "running", "ready"):
            state.update(state="cancelled", phase="cancelled", message="내보내기를 취소했습니다.")
            _write_state(job_dir, state)
        (job_dir / "artifact.part").unlink(missing_ok=True)
        (job_dir / "artifact.zip").unlink(missing_ok=True)
        (job_dir / "artifact.xlsx").unlink(missing_ok=True)
        return _public(state)


def result(data_dir: Path, bundle_id: str, job_id: str) -> tuple[Path, str]:
    job_dir = _job_dir(data_dir, bundle_id, job_id)
    with _locked(job_dir) as _:
        state = _read_state(job_dir)
        if state.get("state") != "ready":
            raise B.ApiError(409, "export job is not ready")
        artifact = job_dir / state["artifact"]
        if not artifact.is_file():
            raise B.ApiError(410, "export artifact expired")
        return artifact, state["filename"]
