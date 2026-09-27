#!/usr/bin/env python3
"""CPU-only audit of the stored 24-view conditioning renders.

This script neither invokes Blender nor loads a model.  It validates each
transforms.json/PNG pair and makes labelled contact sheets from the existing
renders.  View suitability remains a human visual observation, recorded in
the accompanying README rather than inferred from camera metadata.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path("/home/minsujo/Desktop/SH/PHYSx")
OUT = ROOT / "repro-records/04_PhysX-3D/01_재현실행/자료확보/2026-09-27_관절표본_conditioning_시점조사"
SAMPLES = {
    "24566": ROOT / "staging/articulated-sampling-24566-20260926T213719Z-83a8565c7136/datasets/PhysXNet/renders_cond/24566_",
    "29806": ROOT / "staging/articulated-sampling-29806-20260926T220010Z-ac2c1dfab94d/datasets/PhysXNet/renders_cond/29806_",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite_matrix(matrix: object) -> bool:
    return (
        isinstance(matrix, list)
        and len(matrix) == 4
        and all(isinstance(row, list) and len(row) == 4 for row in matrix)
        and all(isinstance(value, (int, float)) and math.isfinite(value) for row in matrix for value in row)
    )


def contact_sheet(sample: str, entries: list[dict]) -> Path:
    thumb_size = (240, 240)
    columns, rows = 6, 4
    header, label = 36, 24
    canvas = Image.new("RGB", (columns * thumb_size[0], header + rows * (thumb_size[1] + label)), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 10), f"PhysX-3D conditioning views — object {sample}; inference input 000.png highlighted", fill="black")
    for index, entry in enumerate(entries):
        path = Path(entry["absolute_path"])
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail(thumb_size, Image.Resampling.LANCZOS)
            tile = Image.new("RGB", thumb_size, "white")
            tile.paste(image, ((thumb_size[0] - image.width) // 2, (thumb_size[1] - image.height) // 2))
        x = (index % columns) * thumb_size[0]
        y = header + (index // columns) * (thumb_size[1] + label)
        canvas.paste(tile, (x, y))
        color = "#d62728" if entry["file_path"] == "000.png" else "#202020"
        width = 5 if entry["file_path"] == "000.png" else 1
        draw.rectangle((x, y, x + thumb_size[0] - 1, y + thumb_size[1] - 1), outline=color, width=width)
        draw.text((x + 5, y + thumb_size[1] + 4), entry["file_path"], fill=color)
    output = OUT / f"{sample}_24view_contact_sheet.png"
    canvas.save(output)
    return output


def audit(sample: str, view_dir: Path) -> dict:
    transforms_path = view_dir / "transforms.json"
    transforms = json.loads(transforms_path.read_text(encoding="utf-8"))
    frames = transforms.get("frames")
    if not isinstance(frames, list) or len(frames) != 24:
        raise RuntimeError(f"{sample}: expected exactly 24 frames, found {type(frames).__name__} {len(frames) if isinstance(frames, list) else ''}")
    entries = []
    seen = set()
    for frame in frames:
        file_path = frame.get("file_path") if isinstance(frame, dict) else None
        matrix = frame.get("transform_matrix") if isinstance(frame, dict) else None
        if not isinstance(file_path, str) or Path(file_path).name != file_path or file_path in seen:
            raise RuntimeError(f"{sample}: invalid or duplicate frame path {file_path!r}")
        if not finite_matrix(matrix):
            raise RuntimeError(f"{sample}: non-finite or invalid transform for {file_path}")
        seen.add(file_path)
        path = view_dir / file_path
        if not path.is_file():
            raise RuntimeError(f"{sample}: missing PNG {path}")
        with Image.open(path) as image:
            image.load()
            if image.format != "PNG":
                raise RuntimeError(f"{sample}: {file_path} is {image.format}, not PNG")
            size, mode = image.size, image.mode
        entries.append({
            "file_path": file_path,
            "absolute_path": str(path),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
            "size": list(size),
            "mode": mode,
            "camera_angle_x": frame.get("camera_angle_x"),
            "transform_matrix": matrix,
        })
    actual_pngs = sorted(path.name for path in view_dir.glob("*.png"))
    referenced_pngs = sorted(entry["file_path"] for entry in entries)
    if actual_pngs != referenced_pngs:
        raise RuntimeError(f"{sample}: transforms PNG set differs from directory PNG set")
    sheet = contact_sheet(sample, entries)
    return {
        "sample": sample,
        "status": "verified",
        "transforms": {"path": str(transforms_path), "sha256": sha256(transforms_path), "frame_count": len(entries)},
        "inference_input": next(entry for entry in entries if entry["file_path"] == "000.png"),
        "frames": entries,
        "contact_sheet": str(sheet),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"method": "CPU-only PNG decode, transforms validation, and contact-sheet generation", "samples": {}}
    for sample, view_dir in SAMPLES.items():
        report["samples"][sample] = audit(sample, view_dir)
    (OUT / "conditioning_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({sample: item["status"] for sample, item in report["samples"].items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
