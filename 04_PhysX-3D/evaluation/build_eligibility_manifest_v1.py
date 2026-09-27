#!/usr/bin/env python3
"""Read-only eligibility census for the 1,000 official test rows.

No archive members are extracted.  ZIP central-directory membership and small
JSON members are read only; all result files are newly created below OUT.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))
from eligibility_v1 import VALID_STATUSES, classify_status

PHYSX = Path("/home/minsujo/Desktop/SH/PHYSx")
SOURCE = PHYSX / "sources/physx-4f54e750a309"
PHYSX_ZIP = PHYSX / "data/physxnet-download/PhysXNet.zip"
SHAPENET_RAW = PHYSX / "data/shapenetcore/raw"
SHAPENET_MINIMAL = PHYSX / "data/shapenetcore/minimal"
OUT = ROOT / "evaluation/2026-09-27_public-only-v1-eligibility"

COMPLETE = {
    "29354": {
        "conditioning": PHYSX / "staging/render-cond-29354-portable-20260925T185825Z/datasets/PhysXNet/renders_cond/29354_/transforms.json",
        "generated_mesh": PHYSX / "staging/rtx5090-cached-decoder-29354-20260926T194524Z-d69f74359b60/mesh.obj",
        "raw_physics": PHYSX / "staging/rtx5090-cached-decoder-29354-20260926T194524Z-d69f74359b60/mesh_physics_raw.pt",
        "property_output": ROOT / "자료확보/rtx5090_adapter/2026-09-27_29354-semantic-validation/official_code_result.json",
        "memory_evidence": ROOT / "자료확보/rtx5090_adapter/2026-09-27_cached-decoder-success-stats.json",
    },
    "24566": {
        "conditioning": PHYSX / "staging/articulated-sampling-24566-20260926T213719Z-83a8565c7136/datasets/PhysXNet/renders_cond/24566_/transforms.json",
        "generated_mesh": PHYSX / "staging/articulated-decoder-24566-20260926T221319Z-a9491be93452/mesh/mesh.obj",
        "raw_physics": PHYSX / "staging/articulated-decoder-24566-20260926T221319Z-a9491be93452/mesh/mesh_physics_raw.pt",
        "property_output": PHYSX / "staging/articulated-decoder-24566-20260926T221319Z-a9491be93452/articulation_audit/vertex_physics_14ch.pt",
        "memory_evidence": PHYSX / "logs/articulated-decoder/24566/20260926T221319Z-a9491be93452/result.json",
    },
    "29806": {
        "conditioning": PHYSX / "staging/articulated-sampling-29806-20260926T220010Z-ac2c1dfab94d/datasets/PhysXNet/renders_cond/29806_/transforms.json",
        "generated_mesh": PHYSX / "staging/articulated-decoder-29806-20260927T050730Z-8271ccb5f82b/mesh/mesh.obj",
        "raw_physics": PHYSX / "staging/articulated-decoder-29806-20260927T050730Z-8271ccb5f82b/mesh/mesh_physics_raw.pt",
        "property_output": PHYSX / "staging/articulated-decoder-29806-20260927T050730Z-8271ccb5f82b/articulation_audit/vertex_physics_14ch.pt",
        "memory_evidence": PHYSX / "logs/articulated-decoder/29806/20260927T050730Z-8271ccb5f82b/result.json",
    },
}


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def local_ref(path: Path):
    if not path.is_file():
        return {"present": False, "path": str(path)}
    return {"present": True, "path": str(path), "bytes": path.stat().st_size, "sha256": hash_file(path)}


def shapenet_files(category: str, model: str, raw_names: set[str]):
    prefix = f"{category}/{model}/"
    raw_obj = prefix + "models/model_normalized.obj"
    raw_mtl = prefix + "models/model_normalized.mtl"
    raw_textures = sorted(name for name in raw_names if name.startswith(prefix + "images/") and not name.endswith("/"))
    minimal_root = SHAPENET_MINIMAL / model
    # Existing minimal extraction is identified by the mapped model ID, not the PhysX ID.
    minimal_obj = minimal_root / "models/model_normalized.obj"
    minimal_mtl = minimal_root / "models/model_normalized.mtl"
    minimal_textures = sorted((minimal_root / "images").glob("*")) if (minimal_root / "images").is_dir() else []
    raw_ok = raw_obj in raw_names and raw_mtl in raw_names and bool(raw_textures)
    minimal_ok = minimal_obj.is_file() and minimal_mtl.is_file() and any(p.is_file() for p in minimal_textures)
    return {"available": raw_ok or minimal_ok, "raw_zip": str(SHAPENET_RAW / f"{category}.zip"),
            "raw_obj_member": raw_obj if raw_obj in raw_names else None,
            "raw_mtl_member": raw_mtl if raw_mtl in raw_names else None,
            "raw_texture_members": raw_textures,
            "minimal_obj": str(minimal_obj) if minimal_obj.is_file() else None,
            "minimal_mtl": str(minimal_mtl) if minimal_mtl.is_file() else None,
            "minimal_textures": [str(p) for p in minimal_textures if p.is_file()]}


def build_physx_index(zf: zipfile.ZipFile, target_ids: set[str]):
    """Scan the ZIP central directory once; never extract a member."""
    index = {object_id: {"json": None, "obj": [], "png": []} for object_id in target_ids}
    for info in zf.infolist():
        parts = info.filename.split("/")
        if len(parts) == 3 and parts[0:2] == ["version_1", "finaljson"] and parts[2].endswith(".json"):
            object_id = parts[2][:-5]
            if object_id in index:
                index[object_id]["json"] = info
        elif len(parts) >= 5 and parts[0:2] == ["version_1", "partseg"]:
            object_id = parts[2]
            if object_id in index:
                if parts[3] == "objs" and info.filename.endswith(".obj"):
                    index[object_id]["obj"].append(info)
                elif parts[3] == "imgs" and info.filename.endswith(".png"):
                    index[object_id]["png"].append(info)
    return index


def group_profile(annotation):
    info = annotation.get("group_info")
    if not isinstance(info, dict) or "0" not in info:
        return {"group_count": None, "motion_classes": [], "tier": "unknown"}
    classes = []
    for group, item in info.items():
        if group != "0" and isinstance(item, list) and item:
            classes.append(str(item[-1]))
    if not classes:
        tier = "fixed"
    elif "B" in classes:
        tier = "B_translation"
    elif "C" in classes:
        tier = "C_rotation"
    else:
        tier = "other_articulated"
    return {"group_count": len(info), "motion_classes": classes, "tier": tier}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    test_ids = [str(x) for x in np.load(SOURCE / "val_test_list.npy", allow_pickle=False)[-1000:]]
    finalindex = json.loads((SOURCE / "dataset_toolkits/finalindex.json").read_text(encoding="utf-8"))
    raw_zip = SHAPENET_RAW / "04379243.zip"
    with zipfile.ZipFile(PHYSX_ZIP) as physx_zip, zipfile.ZipFile(raw_zip) as shape_zip:
        raw_names = set(shape_zip.namelist())
        physx_index = build_physx_index(physx_zip, set(test_ids))
        occurrences = Counter()
        rows = []
        categories = defaultdict(lambda: {"rows": [], "object_ids": set()})
        for test_index, object_id in enumerate(test_ids):
            occurrences[object_id] += 1
            indexed = physx_index[object_id]
            json_name, json_info, obj_infos, png_infos = f"version_1/finaljson/{object_id}.json", indexed["json"], indexed["obj"], indexed["png"]
            source_ok = json_info is not None and bool(obj_infos) and bool(png_infos)
            annotation, profile = None, {"group_count": None, "motion_classes": [], "tier": "unknown"}
            if json_info is not None:
                try:
                    annotation = json.loads(physx_zip.read(json_info).decode("utf-8"))
                    profile = group_profile(annotation)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    source_ok = False
            mapping = finalindex.get(object_id)
            category = model = None
            if isinstance(mapping, str) and mapping.startswith("shapenet/") and len(mapping.split("/")) == 3:
                _, category, model = mapping.split("/")
            mapping_ok = category is not None
            texture = shapenet_files(category, model, raw_names) if mapping_ok else {"available": False}
            artifact_paths = COMPLETE.get(object_id, {})
            artifacts = {name: local_ref(path) for name, path in artifact_paths.items()}
            conditioning_ok = artifacts.get("conditioning", {}).get("present", False)
            generated_ok = all(artifacts.get(name, {}).get("present", False) for name in ("generated_mesh", "raw_physics", "property_output"))
            memory_known = artifacts.get("memory_evidence", {}).get("present", False)
            status = classify_status(source_ok=source_ok, mapping_ok=mapping_ok, texture_ok=texture["available"], conditioning_ok=conditioning_ok, generated_ok=generated_ok, memory_known=memory_known)
            reasons = []
            if not source_ok: reasons.append("PhysXNet ZIP lacks JSON, part OBJ, or part PNG")
            if source_ok and not mapping_ok: reasons.append("finalindex has no ShapeNet category/model mapping")
            if source_ok and mapping_ok and not texture["available"]: reasons.append("mapped ShapeNet OBJ+MTL+texture absent from current raw ZIP/minimal extraction")
            if source_ok and mapping_ok and texture["available"] and not conditioning_ok: reasons.append("no current conditioning transforms artifact")
            if source_ok and mapping_ok and texture["available"] and conditioning_ok and not generated_ok: reasons.append("no generated mesh/raw physics/property artifact")
            if source_ok and mapping_ok and texture["available"] and conditioning_ok and not generated_ok and not memory_known: reasons.append("no comparable sampling/decoder memory evidence")
            if mapping_ok:
                categories[category]["rows"].append(test_index)
                categories[category]["object_ids"].add(object_id)
            rows.append({"test_index": test_index, "source_index": 1000 + test_index, "object_id": object_id,
                         "same_id_occurrence": occurrences[object_id], "physxnet": {"source_ok": source_ok, "json_member": json_name if json_info else None,
                         "json_crc32": f"{json_info.CRC:08x}" if json_info else None, "part_obj_count": len(obj_infos), "part_png_count": len(png_infos)},
                         "group_profile": profile, "mapping": {"present": mapping_ok, "value": mapping, "category": category, "model_id": model},
                         "shapenet": texture, "artifacts": artifacts, "memory_evidence_available": memory_known,
                         "eligibility": status, "reasons": reasons})
    required = []
    for category, values in sorted(categories.items()):
        if category == "04379243":
            required.append({"category": category, "archive": str(SHAPENET_RAW / f"{category}.zip"), "archive_status": "PRESENT", "confirmed_bytes": raw_zip.stat().st_size,
                             "object_ids": sorted(values["object_ids"]), "test_row_count": len(values["rows"]), "enables_if_present": "texture audit only; conditioning/generated artifacts still required"})
        else:
            required.append({"category": category, "archive": f"ShapeNetCore/{category}.zip", "archive_status": "NEEDED_FOR_MAPPED_ROWS", "confirmed_bytes": "unknown_not_checked_in_this_task",
                             "object_ids": sorted(values["object_ids"]), "test_row_count": len(values["rows"]), "enables_if_present": "mapped source rows can advance from NEEDS_SHAPENET_FILE; conditioning/generated artifacts still required"})
    # Pick 10 *new* candidates in eligibility order, balanced by GT tier.
    # READY_FOR_INFERENCE would precede NEEDS_CONDITIONING, which precedes an
    # explicitly listed missing ShapeNet archive. Completed samples are kept in
    # the census but not counted again as expansion targets.
    priority = {"READY_FOR_INFERENCE": 0, "NEEDS_CONDITIONING": 1, "NEEDS_SHAPENET_FILE": 2}
    candidates = sorted((r for r in rows if r["eligibility"] in priority and r["object_id"] not in COMPLETE),
                        key=lambda r: (priority[r["eligibility"]], r["test_index"]))
    proposal = []
    for tier, wanted in (("fixed", 4), ("B_translation", 3), ("C_rotation", 3)):
        proposal.extend([r for r in candidates if r["group_profile"]["tier"] == tier][:wanted])
    status_counts = Counter(r["eligibility"] for r in rows)
    validation = {"status": "success", "test_rows": len(rows), "valid_statuses": all(r["eligibility"] in VALID_STATUSES for r in rows),
                  "order_preserved": [r["object_id"] for r in rows] == test_ids,
                  "duplicate_occurrences_preserved": all(r["same_id_occurrence"] == test_ids[:i+1].count(r["object_id"]) for i, r in enumerate(rows)),
                  "complete_now_ids": [r["object_id"] for r in rows if r["eligibility"] == "COMPLETE_NOW"],
                  "complete_artifact_hashes_present": all(all(v.get("present", False) for v in r["artifacts"].values()) for r in rows if r["eligibility"] == "COMPLETE_NOW"),
                  "required_category_alignment": all(any(row["mapping"]["category"] == item["category"] for row in rows if row["mapping"]["present"]) for item in required),
                  "status_counts": dict(sorted(status_counts.items()))}
    if not all(validation[k] for k in ("valid_statuses", "order_preserved", "duplicate_occurrences_preserved", "complete_artifact_hashes_present", "required_category_alignment")):
        raise RuntimeError("eligibility manifest validation failed")
    write_json(OUT / "eligibility_manifest.json", {"protocol": "public-materials-independent-evaluation-v1", "paper_equivalent": False, "rows": rows})
    write_json(OUT / "validation_result.json", validation)
    with (OUT / "required_files.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["category", "archive", "archive_status", "confirmed_bytes", "test_row_count", "object_ids", "enables_if_present"])
        for item in required: w.writerow([item["category"], item["archive"], item["archive_status"], item["confirmed_bytes"], item["test_row_count"], ";".join(item["object_ids"]), item["enables_if_present"]])
    with (OUT / "proposal_10_new_samples.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["priority", "test_index", "object_id", "tier", "group_count", "motion_classes", "status", "reason"])
        for priority, row in enumerate(proposal, 1): w.writerow([priority, row["test_index"], row["object_id"], row["group_profile"]["tier"], row["group_profile"]["group_count"], ";".join(row["group_profile"]["motion_classes"]), row["eligibility"], "; ".join(row["reasons"])])
    print(json.dumps({"output": str(OUT), "status_counts": validation["status_counts"], "proposal_count": len(proposal)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
