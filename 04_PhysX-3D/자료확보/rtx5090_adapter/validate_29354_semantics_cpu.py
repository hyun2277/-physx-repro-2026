#!/usr/bin/env python3
"""CPU-only single-sample GT comparison for the saved 29354 decoder result."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/home/minsujo/Desktop/SH/PHYSx/cache/matplotlib")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import trimesh
from scipy import sparse
from scipy.sparse.csgraph import connected_components


ROOT = Path("/home/minsujo/Desktop/SH/PHYSx")
SOURCE = ROOT / "sources/physx-4f54e750a309"
MERGE = ROOT / "staging/merge-29354-20260925T180423Z"
RETRIEVAL = ROOT / "staging/retrieval-29354-20260925T183908Z"
RAW = ROOT / "staging/rtx5090-cached-decoder-29354-20260926T194524Z-d69f74359b60/mesh_physics_raw.pt"
MESH = ROOT / "staging/rtx5090-cached-decoder-29354-20260926T194524Z-d69f74359b60/mesh.obj"
JSON_PATH = MERGE / "physxnet/finaljson/29354.json"
PARTS = MERGE / "physxnet/partseg/29354/objs"
MODEL = MERGE / "phy_dataset/29354/model.obj"
MODEL_TEX = RETRIEVAL / "phy_dataset/29354/model_tex.obj"
HEAD = SOURCE / "pretrain/diffusion/ckpts_new/property_output_step0100000.pt"
OUTPUT = ROOT / "repro-records/04_PhysX-3D/자료확보/rtx5090_adapter/2026-09-27_29354-semantic-validation"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def head(features: torch.Tensor, state: dict, name: str) -> torch.Tensor:
    weight = state[f"output_layer_{name}.weight"][:, :, 1, 1].float()
    bias = state[f"output_layer_{name}.bias"].float()
    return features.float() @ weight.T + bias


def stats(value: np.ndarray) -> dict:
    return {
        "count": int(value.size),
        "finite": bool(np.isfinite(value).all()),
        "min": float(value.min()),
        "max": float(value.max()),
        "mean": float(value.mean()),
        "std_population": float(value.std()),
    }


def group_components(faces: np.ndarray, labels: np.ndarray, vertices: np.ndarray) -> dict[int, dict]:
    edges = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]), axis=0)
    edges = edges[labels[edges[:, 0]] == labels[edges[:, 1]]]
    n = len(labels)
    graph = sparse.coo_matrix(
        (np.ones(len(edges) * 2, dtype=np.uint8),
         (np.concatenate((edges[:, 0], edges[:, 1])), np.concatenate((edges[:, 1], edges[:, 0])))),
        shape=(n, n),
    ).tocsr()
    _, component = connected_components(graph, directed=False, return_labels=True)
    result = {}
    for group in (0, 1):
        group_vertices = np.flatnonzero(labels == group)
        ids, counts = np.unique(component[group_vertices], return_counts=True)
        order = np.argsort(counts)[::-1]
        ids, counts = ids[order], counts[order]
        details = []
        for component_id, count in zip(ids[:10], counts[:10]):
            vertex_ids = group_vertices[component[group_vertices] == component_id]
            details.append({
                "vertex_count": int(count),
                "coordinate_min": vertices[vertex_ids].min(axis=0).tolist(),
                "coordinate_max": vertices[vertex_ids].max(axis=0).tolist(),
            })
        result[group] = {
            "component_count_including_isolated_vertices": int(len(ids)),
            "largest_component_vertices": int(counts[0]) if len(counts) else 0,
            "largest_component_fraction": float(counts[0] / counts.sum()) if len(counts) else 0.0,
            "component_sizes_top10": [int(v) for v in counts[:10]],
            "components_top10": details,
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    inputs = [JSON_PATH, *[PARTS / f"{i}.obj" for i in range(6)], MODEL, MODEL_TEX, RAW, MESH, HEAD]
    for path in inputs:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"missing or empty input: {path}")
    with (args.output / "input_hashes.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["role", "path", "bytes", "sha256"])
        roles = ["physxnet_json", *[f"part_obj_{i}" for i in range(6)], "model_obj", "model_tex_obj", "raw_output", "generated_mesh", "property_output_checkpoint"]
        for role, path in zip(roles, inputs):
            writer.writerow([role, path, path.stat().st_size, sha256(path)])

    annotation = json.loads(JSON_PATH.read_text())
    dimensions = [float(v) for v in annotation["dimension"].split(" ")[0].split("*")]
    gt_scale = max(dimensions)
    gt_parts = []
    for part in annotation["parts"]:
        gt_parts.append({
            "label": part["label"], "name": part["name"], "material": part.get("material"),
            "density_text": part.get("density"), "density_g_cm3": float(part["density"].split(" ")[0]),
            "priority_rank": part.get("priority_rank"), "affordance_training_target": 1 - float(part["priority_rank"]) / 10,
        })
    with (args.output / "gt_part_properties.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(gt_parts[0]))
        writer.writeheader(); writer.writerows(gt_parts)

    saved = torch.load(RAW, map_location="cpu", weights_only=False)
    vertices = saved["vertices"].float().numpy()
    faces = saved["faces"].long().numpy()
    raw = saved["vertex_physics"].float()
    state = torch.load(HEAD, map_location="cpu", weights_only=True)
    physics = head(raw[:, -16:], state, "phy")
    physics[:, 0] = physics[:, 0] * 48 + 95
    physics[:, 2] = physics[:, 2] * 2.8 + 2.3
    physics[:, 4] = physics[:, 4] * 0.732 - 0.812
    physics[:, -1] = physics[:, -1] * 4
    physics_np = physics.numpy()
    group_id = physics_np[:, 3]

    group0 = (group_id > -0.5) & (group_id < 0.5)
    group1 = (group_id > 0.5) & (group_id < 1.5)
    if np.any(group0 & group1) or not np.all(group0 | group1):
        raise RuntimeError("this audit expects every vertex in exactly one of the observed groups 0/1")
    labels = group1.astype(np.int8)
    tri = vertices[faces]
    area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1) / 2
    votes = labels[faces].sum(axis=1)
    face_group = (votes >= 2).astype(np.int8)
    mixed = (votes > 0) & (votes < 3)
    components = group_components(faces, labels, vertices)

    groups = {}
    for group, mask in ((0, group0), (1, group1)):
        fmask = face_group == group
        homogeneous = votes == (0 if group == 0 else 3)
        groups[str(group)] = {
            "vertex_count": int(mask.sum()),
            "vertex_fraction": float(mask.mean()),
            "majority_assigned_face_count": int(fmask.sum()),
            "majority_assigned_face_fraction": float(fmask.mean()),
            "majority_assigned_surface_area": float(area[fmask].sum()),
            "majority_assigned_surface_area_fraction": float(area[fmask].sum() / area.sum()),
            "homogeneous_face_count": int(homogeneous.sum()),
            "homogeneous_surface_area": float(area[homogeneous].sum()),
            "coordinate_min": vertices[mask].min(axis=0).tolist(),
            "coordinate_max": vertices[mask].max(axis=0).tolist(),
            **components[group],
        }

    child = torch.from_numpy(group1)
    kinematic_map = torch.zeros((len(physics), 2), dtype=torch.long)
    kinematic_map[:, 0] = child.long()
    official_parent_error = None
    try:
        kinematic_map[:, 1] = (
            (physics[:, 3] > physics[:, 4][child] - 0.5)
            & (physics[:, 3] < physics[:, 4][child] + 0.5)
        ).long()
    except RuntimeError as exc:
        official_parent_error = str(exc)
    official_row_selection = physics[:, 5:-1][kinematic_map[0]]
    candidate_parameters = physics[:, 5:-1][child].mean(0)
    candidate_type = physics[:, -1][child].mean()

    bins = [-np.inf, 0.45, 0.49, 0.5, 0.505, 0.51, np.inf]
    boundary = []
    for left, right in zip(bins[:-1], bins[1:]):
        mask = (group_id >= left) & (group_id < right)
        boundary.append({
            "left_inclusive": "-inf" if np.isneginf(left) else left,
            "right_exclusive": "+inf" if np.isposinf(right) else right,
            "count": int(mask.sum()), "fraction": float(mask.mean()),
        })

    num_group = round(float(group_id.max())) + 1
    gt = {
        "object_name": annotation.get("object_name"), "category": annotation.get("category"),
        "dimension_field": annotation["dimension"], "dimension_vector_cm": dimensions,
        "scale_rule": "maximum numeric dimension", "scale_scalar_cm": gt_scale,
        "group_info": annotation.get("group_info"), "group_keys": list(annotation.get("group_info", {})),
        "fixed_under_merge_property_rule": list(annotation.get("group_info", {})) == ["0"],
        "parent_relation": None, "movement_type": None, "movement_direction": None,
        "movement_position": None, "movement_range": None,
        "missing_reason": "group_info contains only group 0 and no articulated-group tuple",
    }
    (args.output / "gt_annotation.json").write_text(json.dumps(gt, indent=2, ensure_ascii=False) + "\n")

    predicted_scale_mean = float(physics[:, 0].mean())
    second_group_meaningful = bool(groups["1"]["homogeneous_face_count"] > 0)
    prediction = {
        "scope": "official checkpoint head and exact example thresholds; CPU only",
        "group_id": {**stats(group_id), "vertices_ge_0_5": int((group_id >= 0.5).sum()), "fraction_ge_0_5": float((group_id >= 0.5).mean())},
        "num_group_formula": "round(float(max(group_id))) + 1",
        "num_group": num_group,
        "official_fixed_branch": num_group == 1,
        "groups": groups,
        "face_assignment": "triangle assigned by majority of its three thresholded vertex labels",
        "mixed_group_face_count": int(mixed.sum()), "mixed_group_face_fraction": float(mixed.mean()),
        "boundary_distribution": boundary,
        "scale": {
            "predicted_vertex_mean_cm": predicted_scale_mean, "gt_scalar_cm": gt_scale,
            "absolute_error_cm": abs(predicted_scale_mean - gt_scale),
            "relative_absolute_error": abs(predicted_scale_mean - gt_scale) / gt_scale,
        },
        "density_prediction_g_cm3": stats(physics_np[:, 2]),
        "affordance_prediction_before_display_minmax": stats(physics_np[:, 1]),
        "direct_generated_vertex_to_gt_part_mapping": False,
        "mapping_policy": "no nearest-part, ICP, or arbitrary alignment was created",
        "second_group_meaningful": second_group_meaningful,
        "meaningful_screen_rule": "a mesh surface region requires at minimum one triangle whose three vertices are group 1; this is a descriptive screen, not an official metric",
        "false_articulation_candidate": bool(gt["fixed_under_merge_property_rule"] and num_group > 1 and second_group_meaningful),
        "classification": "official max/round branch says articulated, but six threshold-crossing vertices do not form a meaningful second region",
    }
    (args.output / "official_code_result.json").write_text(json.dumps(prediction, indent=2, ensure_ascii=False) + "\n")
    official_indexing = {
        "status": "official kinematic postprocess is not a completed result for this sample",
        "child_mask_shape": [len(child)], "child_true_count": int(child.sum()),
        "line_207_parent_expression_error": official_parent_error,
        "line_211_row_selection_index": kinematic_map[0].tolist(),
        "line_211_row_selection_shape": list(official_row_selection.shape),
        "explanation": "kinematic_map[0] is a two-element integer row, not the N-element boolean group column",
    }
    (args.output / "official_indexing_result.json").write_text(json.dumps(official_indexing, indent=2, ensure_ascii=False) + "\n")
    candidate = {
        "status": "separate static correction candidate; not official output",
        "change": "use kinematic_map[:, (group_ind-1)*2].bool() as the group selection mask",
        "selected_vertex_count": int(child.sum()),
        "selected_parameter_shape": [int(child.sum()), 8],
        "group_mean_parameter": candidate_parameters.tolist(),
        "group_mean_type_before_round": float(candidate_type),
        "group_mean_type_rounded": round(float(candidate_type)),
        "scientific_limit": "indexing correction does not validate articulation, physical units, or GT agreement",
    }
    (args.output / "indexing_correction_candidate.json").write_text(json.dumps(candidate, indent=2, ensure_ascii=False) + "\n")

    synthetic_property = torch.arange(5 * 8, dtype=torch.float32).reshape(5, 8)
    synthetic_mask = torch.tensor([False, True, True, False, False])
    synthetic_map = torch.zeros((5, 2), dtype=torch.long)
    synthetic_map[:, 0] = synthetic_mask.long()
    synthetic = {
        "purpose": "CPU synthetic row/column indexing check",
        "group_column": synthetic_map[:, 0].tolist(),
        "official_row_index": synthetic_map[0].tolist(),
        "official_selected_rows": synthetic_property[synthetic_map[0]].tolist(),
        "candidate_selected_rows": synthetic_property[synthetic_map[:, 0].bool()].tolist(),
        "official_shape": list(synthetic_property[synthetic_map[0]].shape),
        "candidate_shape": list(synthetic_property[synthetic_map[:, 0].bool()].shape),
        "conclusion": "official expression uses a two-element integer row; candidate uses the intended N-element boolean column",
    }
    (args.output / "indexing_synthetic_check.json").write_text(json.dumps(synthetic, indent=2) + "\n")

    stride = max(1, len(vertices) // 70000)
    selected = slice(None, None, stride)
    fig, axes = plt.subplots(1, 4, figsize=(17, 4), constrained_layout=True)
    axes[0].scatter(vertices[selected, 0], vertices[selected, 2], c="#4472c4", s=0.2, linewidths=0)
    axes[0].scatter(vertices[group1, 0], vertices[group1, 2], c="red", s=18, marker="x", label="six group-1 vertices")
    axes[0].set_title("Predicted group (x-z vertex projection)"); axes[0].set_aspect("equal"); axes[0].set_axis_off()
    axes[0].legend(loc="lower center", fontsize=8)
    axes[1].hist(group_id, bins=120, color="#4c72b0"); axes[1].axvline(0.5, color="red", linestyle="--", label="official group-1 threshold")
    axes[1].set_yscale("log"); axes[1].set_xlabel("predicted group_id"); axes[1].set_ylabel("vertex count (log)"); axes[1].legend()
    axes[2].hist(physics_np[:, 2], bins=100, alpha=0.65, label="predicted density")
    axes[2].axvline(0.75, color="black", linestyle="--", label="all six GT parts: 0.75")
    axes[2].set_xlabel("density [g/cm³]"); axes[2].set_ylabel("vertex count"); axes[2].legend(); axes[2].set_title("Observation only: no part mapping")
    axes[3].hist(physics_np[:, 1], bins=100, alpha=0.65, label="predicted normalized target")
    for i, value in enumerate(sorted({part["affordance_training_target"] for part in gt_parts})):
        axes[3].axvline(value, color="black", alpha=0.55, linestyle="--", label="GT part targets" if i == 0 else None)
    axes[3].set_xlabel("1 - priority_rank/10"); axes[3].set_ylabel("vertex count"); axes[3].legend(); axes[3].set_title("Observation only: no part mapping")
    fig.suptitle("29354 single-sample CPU semantic audit (not paper quantitative evaluation)")
    fig.savefig(args.output / "semantic_preview.png", dpi=150)
    plt.close(fig)
    print(args.output)


if __name__ == "__main__":
    main()
