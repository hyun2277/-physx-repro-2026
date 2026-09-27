#!/usr/bin/env python3
"""Safely extract two observed group_info candidates without unpacking the ZIP."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path("/home/minsujo/Desktop/SH/PHYSx")
ARCHIVE = ROOT / "data/physxnet-download/PhysXNet.zip"
OUTPUT = ROOT / "data/physxnet-minimal/2026-09-22"
EXPECTED_SIZE = 16_306_354_206
EXPECTED_SHA256 = "a4970a3936e8a1fc823d17b64d23b167d73997a13686011bc46f7b98774a7e75"
CANDIDATES = [
    {"test_index": 0, "source_index": 1000, "object_id": "7271", "role": "articulated_candidate", "group_count": 3},
    {"test_index": 1, "source_index": 1001, "object_id": "29354", "role": "fixed_candidate", "group_count": 0},
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_member(info: zipfile.ZipInfo, prefix: str) -> bool:
    name = info.filename
    if not name.startswith(prefix) or name.endswith("/"):
        return False
    rel = Path(name[len(prefix):])
    if not rel.parts or any(part in {"", ".", ".."} for part in rel.parts):
        raise RuntimeError(f"unsafe archive member: {name}")
    # Reject Unix symlinks; selected data must be ordinary files.
    mode = (info.external_attr >> 16) & 0xFFFF
    if mode and (mode & 0o170000) == 0o120000:
        raise RuntimeError(f"symlink archive member: {name}")
    return True


def main() -> int:
    if not ARCHIVE.is_file():
        raise RuntimeError(f"archive missing: {ARCHIVE}")
    if ARCHIVE.stat().st_size != EXPECTED_SIZE:
        raise RuntimeError("archive size does not match verified download")
    actual_hash = sha256(ARCHIVE)
    if actual_hash != EXPECTED_SHA256:
        raise RuntimeError("archive SHA256 does not match verified download")
    if OUTPUT.exists():
        raise RuntimeError(f"refusing to overwrite existing output: {OUTPUT}")
    OUTPUT.mkdir(parents=True)
    records = []
    try:
        with zipfile.ZipFile(ARCHIVE) as archive:
            infos = archive.infolist()
            names = {info.filename: info for info in infos}
            for candidate in CANDIDATES:
                oid = candidate["object_id"]
                base = f"version_1/partseg/{oid}/"
                json_name = f"version_1/finaljson/{oid}.json"
                if json_name not in names:
                    raise RuntimeError(f"annotation missing: {json_name}")
                selected = [names[json_name]]
                selected.extend(info for info in infos if safe_member(info, base + "objs/"))
                selected.extend(info for info in infos if safe_member(info, base + "imgs/"))
                if not any(info.filename.endswith(".obj") for info in selected):
                    raise RuntimeError(f"OBJ members missing for {oid}")
                if not any(info.filename.endswith(".png") for info in selected):
                    raise RuntimeError(f"PNG members missing for {oid}")
                folder = OUTPUT / f"{candidate['test_index']:03d}-test-{oid}-{candidate['role']}"
                folder.mkdir()
                files = []
                for info in selected:
                    if info.filename == json_name:
                        rel = Path("annotation") / f"{oid}.json"
                    else:
                        rel = Path(info.filename).relative_to(base)
                    target = folder / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open("xb") as sink:
                        while block := source.read(8 * 1024 * 1024):
                            sink.write(block)
                    files.append({"archive_member": info.filename, "path": str(target.relative_to(OUTPUT)),
                                  "bytes": target.stat().st_size, "sha256": sha256(target)})
                records.append({**candidate, "archive_member_prefix": base, "files": files,
                    "connections": {
                        "json_obj_png_object_id": "confirmed by version_1 path and selected members",
                        "input_image": "PNG part images are present; benchmark conditioning-image role is not confirmed",
                        "camera": "not present in selected JSON/OBJ/PNG set; camera parameters/view mapping unconfirmed",
                        "texture": "not selected; texture asset mapping unconfirmed",
                        "evaluation_gt": "annotation/parts and meshes are present; metric-ready GT correspondence is not confirmed",
                    }})
    except Exception:
        # Keep partial output for forensic inspection, but never claim completion.
        raise
    result = {"archive": {"path": str(ARCHIVE), "bytes": EXPECTED_SIZE, "sha256": actual_hash},
              "output": str(OUTPUT), "full_archive_extracted": False, "preserved_test_order": True,
              "classification_basis": "observed group_info candidate; not official paper classification",
              "candidates": records}
    (OUTPUT / "extraction-manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(OUTPUT), "candidate_count": len(records),
                      "file_count": sum(len(r["files"]) for r in records), "archive_sha256": actual_hash}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
