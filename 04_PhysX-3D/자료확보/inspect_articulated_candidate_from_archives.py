#!/usr/bin/env python3
"""Read-only PhysXNet/ShapeNet ZIP central-directory articulated candidate audit."""

from __future__ import annotations

import argparse
import csv
import json
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np


ROOT = Path("/home/minsujo/Desktop/SH/PHYSx")
SOURCE = ROOT / "sources/physx-4f54e750a309"
PHYSXNET = ROOT / "data/physxnet-download/PhysXNet.zip"
SHAPENET = ROOT / "data/shapenetcore/raw/04379243.zip"
OUTPUT = ROOT / "repro-records/04_PhysX-3D/자료확보/2026-09-27_관절표본_읽기전용선정"
SELECTED_OBJECT = "27281"


def texture_references(text: str) -> list[str]:
    references = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith(("map_kd ", "map_ka ", "map_ks ", "map_bump ", "bump ")):
            references.append(stripped.split()[-1].replace("\\", "/"))
    return references


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    test_ids = np.load(SOURCE / "val_test_list.npy").tolist()
    finalindex = json.loads((SOURCE / "dataset_toolkits/finalindex.json").read_text())
    with zipfile.ZipFile(PHYSXNET) as physx_zip, zipfile.ZipFile(SHAPENET) as shape_zip:
        physx_names = set(physx_zip.namelist())
        shape_names = set(shape_zip.namelist())
        part_counts = Counter()
        image_counts = Counter()
        for name in physx_names:
            pieces = name.split("/")
            if len(pieces) == 5 and pieces[:2] == ["version_1", "partseg"]:
                if pieces[3] == "objs" and name.endswith(".obj"):
                    part_counts[pieces[2]] += 1
                if pieces[3] == "imgs" and not name.endswith("/"):
                    image_counts[pieces[2]] += 1

        rows = []
        annotations = {}
        # The repository's correspondence table defines val_test_list[1000:] as
        # the 1,000-row test subset (29354 is test index 1 / source index 1001).
        for source_index, object_id in enumerate(test_ids):
            if source_index < 1000:
                continue
            test_index = source_index - 1000
            json_path = f"version_1/finaljson/{object_id}.json"
            if json_path not in physx_names:
                continue
            annotation = json.loads(physx_zip.read(json_path))
            group_info = annotation.get("group_info") or {}
            articulated_groups = {
                str(key): value for key, value in group_info.items()
                if str(key) != "0" and isinstance(value, list) and len(value) >= 4
            }
            if not articulated_groups:
                continue
            annotations[(source_index, object_id)] = annotation
            mapping = finalindex.get(object_id)
            category_id = model_id = None
            if mapping:
                category_id, model_id = mapping.split("/")[-2:]
            mesh_exists = mtl_exists = False
            textures: list[str] = []
            references: list[str] = []
            references_exist = False
            if category_id == "04379243" and model_id:
                base = f"04379243/{model_id}/"
                mesh_exists = base + "models/model_normalized.obj" in shape_names
                mtl_path = base + "models/model_normalized.mtl"
                mtl_exists = mtl_path in shape_names
                textures = sorted(
                    name for name in shape_names
                    if name.startswith(base + "images/") and not name.endswith("/")
                )
                if mtl_exists:
                    references = texture_references(shape_zip.read(mtl_path).decode("utf-8", "replace"))
                    references_exist = bool(references) and all(
                        base + "images/" + Path(reference).name in shape_names for reference in references
                    )
            group_values = list(articulated_groups.values())
            rows.append({
                "test_index_zero_based": test_index,
                "source_index_zero_based": source_index,
                "test_row_one_based": test_index + 1,
                "object_id": object_id,
                "json_path_in_physxnet_zip": json_path,
                "group_count": len(group_info),
                "articulated_group_count": len(articulated_groups),
                "part_obj_count": part_counts[object_id],
                "part_reference_image_count": image_counts[object_id],
                "parent_present": all(len(value) > 1 and value[1] is not None for value in group_values),
                "movement_type_present": all(len(value) > 3 and value[3] is not None for value in group_values),
                "direction_position_range_present": all(len(value) > 2 and isinstance(value[2], list) and len(value[2]) == 8 for value in group_values),
                "group_info_json": json.dumps(group_info, separators=(",", ":")),
                "parent_relations_json": json.dumps({key: value[1] for key, value in articulated_groups.items()}, separators=(",", ":")),
                "movement_types_json": json.dumps({key: value[3] for key, value in articulated_groups.items()}, separators=(",", ":")),
                "direction_position_range_json": json.dumps({key: value[2] for key, value in articulated_groups.items()}, separators=(",", ":")),
                "shapenet_mapping": mapping,
                "shapenet_category_id": category_id,
                "shapenet_model_id": model_id,
                "local_04379243_mesh": mesh_exists,
                "local_04379243_mtl": mtl_exists,
                "local_04379243_texture_file_count": len(textures),
                "local_04379243_mtl_texture_references_resolve": references_exist,
                "conditioning_image": "not_found; part reference PNGs are not conditioning renders",
                "transforms_json": "not_found",
                "currently_verifiable": "GT groups/parent/type/direction/position/range and raw asset linkage",
                "currently_blocked": "prediction comparison, rendered maps, instantiation distance, paper 30-view metrics",
            })

        fieldnames = list(rows[0])
        with (args.output / "all_articulated_test_candidates.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader(); writer.writerows(rows)
        local_category_rows = [row for row in rows if row["shapenet_category_id"] == "04379243"]
        with (args.output / "local_04379243_candidates.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader(); writer.writerows(local_category_rows)

        selected_rows = [row for row in rows if row["object_id"] == SELECTED_OBJECT]
        if len(selected_rows) != 1:
            raise RuntimeError(f"expected one selected test row, found {len(selected_rows)}")
        selected = selected_rows[0]
        selected_annotation = annotations[(selected["source_index_zero_based"], SELECTED_OBJECT)]
        model_id = selected["shapenet_model_id"]
        shape_base = f"04379243/{model_id}/"
        member_names = [
            shape_base + "models/model_normalized.obj",
            shape_base + "models/model_normalized.mtl",
            *sorted(name for name in shape_names if name.startswith(shape_base + "images/") and not name.endswith("/")),
        ]
        shape_members = []
        for member in member_names:
            info = shape_zip.getinfo(member)
            shape_members.append({
                "path": member, "uncompressed_bytes": info.file_size,
                "compressed_bytes": info.compress_size, "crc32": f"{info.CRC:08x}",
            })
        part_members = []
        part_prefix = f"version_1/partseg/{SELECTED_OBJECT}/objs/"
        for info in sorted(
            (item for item in physx_zip.infolist() if item.filename.startswith(part_prefix) and item.filename.endswith(".obj")),
            key=lambda item: item.filename,
        ):
            part_members.append({
                "path": info.filename, "uncompressed_bytes": info.file_size,
                "compressed_bytes": info.compress_size, "crc32": f"{info.CRC:08x}",
            })
        mapping = selected_annotation["group_info"]
        report = {
            "method": "ZIP central-directory and selected compressed JSON/MTL reads only; no extraction",
            "counts": {
                "test_rows": 1000, "articulated_test_rows": len(rows),
                "articulated_rows_with_finalindex": sum(row["shapenet_mapping"] is not None for row in rows),
                "articulated_rows_in_04379243": len(local_category_rows),
                "04379243_rows_with_mesh_mtl_and_resolved_texture": sum(
                    row["local_04379243_mesh"] and row["local_04379243_mtl"]
                    and row["local_04379243_mtl_texture_references_resolve"] for row in local_category_rows
                ),
            },
            "selected": selected,
            "selection_reason": "two nonfixed groups with explicit B translation and C rotation parameters, seven part OBJs, finalindex mapping, and locally verified OBJ/MTL/texture reference",
            "group_info": mapping,
            "group_field_interpretation": {
                "0": "fixed part labels [0,1,2,3,4]",
                "1": {"child_parts": [5], "parent_group": "0", "direction": mapping["1"][2][0:3], "position": mapping["1"][2][3:6], "range": mapping["1"][2][6:8], "movement_type": "B (translation)"},
                "2": {"child_parts": [6], "parent_group": "0", "direction": mapping["2"][2][0:3], "position": mapping["2"][2][3:6], "range": mapping["2"][2][6:8], "movement_type": "C (rotation about axis)"},
            },
            "part_obj_members": part_members,
            "shapenet_members": shape_members,
            "shape_mtl_texture_references": texture_references(shape_zip.read(shape_base + "models/model_normalized.mtl").decode("utf-8", "replace")),
            "existing_archive": {
                "path": str(SHAPENET), "bytes": SHAPENET.stat().st_size,
                "known_sha256_from_prior_record": "625701ed0a2de08cc28bce6fd4f3643c67ed573c6abcbba5f0cbbb5e810d0503",
            },
            "additional_download_required": False,
            "additional_download_bytes": 0,
            "object_7271_finalindex_mapping": finalindex.get("7271"),
            "conditioning": {
                "part_reference_png_count_in_physxnet_zip": image_counts[SELECTED_OBJECT],
                "conditioning_render_found": False, "transforms_json_found": False,
                "note": "part reference PNGs are annotation inputs, not official conditioning render/camera pairs",
            },
            "evaluation_boundary": "group structure can be checked; paper kinematic instantiation distance and prediction accuracy cannot be checked before a prediction and the missing evaluation contract",
        }
        (args.output / "selected_candidate_27281.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(args.output)


if __name__ == "__main__":
    main()
