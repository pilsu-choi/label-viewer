"""Immutable per-document snapshots for Golden mutations."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def golden_revision(raw: bytes | None) -> str:
    return hashlib.sha256(raw).hexdigest() if raw is not None else "missing"


def history_dir(bdir: Path, doc_id: str) -> Path:
    # doc_id has already passed bundle._safe_id; quote it so metadata cannot escape the directory.
    import urllib.parse
    return bdir / ".history" / "golden" / urllib.parse.quote(doc_id, safe="")


def archive_snapshot(bdir: Path, doc_id: str, raw: bytes | None, action: str) -> dict[str, Any]:
    """Write an immutable snapshot and metadata. Caller holds the document lock."""
    directory = history_dir(bdir, doc_id)
    directory.mkdir(parents=True, exist_ok=True)
    history_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{secrets.token_hex(4)}"
    revision = golden_revision(raw)
    if raw is not None:
        data_path = directory / f"{history_id}.json"
        tmp = directory / f".{history_id}.tmp"
        tmp.write_bytes(raw)
        tmp.replace(data_path)
    metadata = {"id": history_id, "created_at": datetime.now(timezone.utc).isoformat(),
                "action": action, "revision": revision, "has_golden": raw is not None}
    meta_path = directory / f"{history_id}.meta.json"
    tmp_meta = directory / f".{history_id}.meta.tmp"
    tmp_meta.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    tmp_meta.replace(meta_path)
    return metadata


def list_snapshots(bdir: Path, doc_id: str, limit: int = 100, before: str | None = None) -> list[dict[str, Any]]:
    directory = history_dir(bdir, doc_id)
    if not directory.is_dir():
        return []
    items = []
    for p in directory.glob("*.meta.json"):
        try:
            item = json.loads(p.read_text(encoding="utf-8"))
            if before is None or item["id"] < before:
                items.append(item)
        except (OSError, ValueError, KeyError):
            continue
    items.sort(key=lambda item: item["id"], reverse=True)
    return items[:max(1, min(int(limit), 500))]


def read_snapshot(bdir: Path, doc_id: str, history_id: str) -> tuple[dict[str, Any], bytes | None] | None:
    directory = history_dir(bdir, doc_id)
    # IDs are generated internally and must remain a single filename component.
    if not history_id or "/" in history_id or "\\" in history_id or history_id.startswith("."):
        return None
    try:
        meta = json.loads((directory / f"{history_id}.meta.json").read_text(encoding="utf-8"))
        raw = (directory / f"{history_id}.json").read_bytes() if meta.get("has_golden") else None
        return meta, raw
    except (OSError, ValueError):
        return None
