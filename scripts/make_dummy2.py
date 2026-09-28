#!/usr/bin/env python3
"""Build a local Label Viewer bundle from curated real E2E samples.

Usage: python3 scripts/make_dummy2.py [--source-root ../e2e/표본결과] [--ao-format ui|classic] [--out samples/dummy2]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


SAMPLES = (
    ("REC", "진료비영수증", "20230127_202555.jpg"),
    ("REC", "진료비영수증", "SA2019123048574_301912301635140g.tif"),
    ("DET", "진료비세부산정내역서", "3022030712433802-1.png"),
    ("DET", "진료비세부산정내역서", "SA2020010683597_3020010610592200.tif"),
    ("DX", "진단서", "[꾸미기]진단서07[꾸미기].jpg"),
    ("DX", "진단서", "20230228095647474003.tif"),
    ("OP", "소견서", "20230228172033976130.tif"),
    ("OP", "소견서", "신한life_test_220316_소견서4.png"),
    ("SUR", "수술확인서", "신한life_test_220316_수술확인서20.png"),
    ("SUR", "수술확인서", "20230621_130741.jpg"),
    ("INP", "입퇴원확인서", "20230621_140539.jpg"),
    ("INP", "입퇴원확인서", "20230228155325819098.tif"),
    ("PHR", "약제비영수증", "image_47.tif"),
    ("PHR", "약제비영수증", "1546586316234823.jpg"),
)
KINDS = ("original", "ao_extract", "harness", "golden")
SUFFIXES = ("", ".aiocr.json", ".harness.json", ".answer.json")
AO_UI_RUN = "ao-ui-205-20260927-204626"
OUTPUT_KINDS = (*KINDS, "ao_ui")


def sample_ids():
    counts: dict[str, int] = {}
    for code, folder, image_name in SAMPLES:
        counts[code] = counts.get(code, 0) + 1
        yield f"D2-{code}-{counts[code]:03d}", folder, image_name


def source_files(root: Path) -> list[tuple[str, str, Path]]:
    files = []
    for alias, folder, image_name in sample_ids():
        image = root / folder / image_name
        for suffix in SUFFIXES:
            source = image if not suffix else image.with_name(image.name + suffix)
            if not source.is_file():
                raise FileNotFoundError(f"required sample file missing: {source}")
            if suffix:
                try:
                    payload = json.loads(source.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise ValueError(f"invalid JSON sample {source}: {exc}") from exc
                if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
                    raise ValueError(f"unexpected sample JSON shape: {source}")
            files.append((alias, suffix, source))
    return files


def build(source_root: Path, out: Path, ui_root: Path | None = None, ao_format: str = "ui") -> Path:
    source_root = source_root.resolve()
    out = out.resolve()
    files = source_files(source_root)
    ui_root = ui_root.resolve() if ui_root else None
    ui_files = []
    for alias, folder, image_name in sample_ids():
        source = (ui_root / folder / f"{image_name}.aiocr.ui.json") if ui_root else None
        if source and source.is_file():
            try:
                payload = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid AO UI sample {source}: {exc}") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
                raise ValueError(f"unexpected AO UI JSON shape: {source}")
            ui_files.append((alias, image_name, source))
    if ao_format == "ui" and len(ui_files) != len(SAMPLES):
        raise FileNotFoundError("AO UI response가 모든 샘플에 필요합니다. --ui-root를 확인하거나 --ao-format classic을 사용하세요.")
    ui_by_alias = {alias: source for alias, _, source in ui_files}
    manifest = []
    outputs = []
    for kind in KINDS if ao_format == "ui" else OUTPUT_KINDS:
        (out / kind).mkdir(parents=True, exist_ok=True)
    targets = []
    for alias, suffix, source in files:
        kind = KINDS[SUFFIXES.index(suffix)]
        source_root_label = "samples"
        if kind == "ao_extract" and ao_format == "ui":
            source = ui_by_alias[alias]
            suffix = ".aiocr.ui.json"
            source_root_label = "ui"
        target = out / kind / f"{alias}{Path(source.name.removesuffix(suffix)).suffix.lower()}{suffix}"
        targets.append((target, alias, kind, source, source_root_label))
    if ao_format == "classic":
        for alias, image_name, source in ui_files:
            target = out / "ao_ui" / f"{alias}{Path(image_name).suffix.lower()}.aiocr.ui.json"
            targets.append((target, alias, "ao_ui", source, "ui"))
    expected = {target for target, *_ in targets}
    for kind in OUTPUT_KINDS:
        for existing in (out / kind).iterdir() if (out / kind).is_dir() else ():
            if existing.is_file() and existing not in expected:
                raise ValueError(f"unexpected file in output; choose a clean --out: {existing}")
    for target, alias, kind, source, source_root_label in targets:
        data = source.read_bytes()
        target.write_bytes(data)
        outputs.append(target)
        manifest.append({
            "id": alias,
            "kind": kind,
            "source_root": source_root_label,
            "source": source.relative_to(ui_root if source_root_label == "ui" else source_root).as_posix(),
            "sha256": hashlib.sha256(data).hexdigest(),
        })

    (out / "provenance.local.json").write_text(
        json.dumps({"source_root": str(source_root), "ui_root": str(ui_root) if ui_root else None,
                    "files": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    archive = out.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(outputs):
            zf.write(path, arcname=path.relative_to(out.parent))
    return archive


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    default_source = next(
        (parent / "e2e" / "표본결과" for parent in (repo, *repo.parents)
         if (parent / "e2e" / "표본결과").is_dir()),
        repo.parent / "e2e" / "표본결과",
    )
    default_ui = next(
        (parent / "e2e" / "out" / AO_UI_RUN for parent in (repo, *repo.parents)
         if (parent / "e2e" / "out" / AO_UI_RUN).is_dir()),
        None,
    )
    parser.add_argument("--source-root", type=Path, default=default_source)
    parser.add_argument("--ui-root", type=Path, default=default_ui)
    parser.add_argument("--ao-format", choices=("ui", "classic"), default="ui")
    parser.add_argument("--out", type=Path, default=repo / "samples" / "dummy2")
    args = parser.parse_args()
    archive = build(args.source_root, args.out, args.ui_root, args.ao_format)
    print(f"generated {len(SAMPLES)} documents at {args.out.resolve()}")
    print(f"zipped to {archive}")


if __name__ == "__main__":
    main()
