#!/usr/bin/env python3
"""CPU-only 27281 raw physics/head/articulation audit."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import connected_components
import torch
import trimesh


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def summary(values):
    values = np.asarray(values)
    return {"shape": list(values.shape), "finite": bool(np.isfinite(values).all()),
            "min": float(values.min()), "max": float(values.max()),
            "mean": float(values.mean()), "std": float(values.std())}


def components(faces, labels, group):
    ids = np.flatnonzero(labels == group)
    if not len(ids):
        return {"count_including_isolated": 0, "largest_vertices": 0}
    edge = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    edge = edge[(labels[edge[:, 0]] == group) & (labels[edge[:, 1]] == group)]
    graph = sparse.coo_matrix((np.ones(len(edge) * 2),
        (np.r_[edge[:, 0], edge[:, 1]], np.r_[edge[:, 1], edge[:, 0]])),
        shape=(len(labels), len(labels))).tocsr()
    _, cc = connected_components(graph, directed=False)
    _, counts = np.unique(cc[ids], return_counts=True)
    return {"count_including_isolated": int(len(counts)),
            "largest_vertices": int(counts.max()),
            "largest_fraction": float(counts.max() / len(ids)),
            "sizes_desc_top20": sorted(map(int, counts), reverse=True)[:20]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", required=True)
    p.add_argument("--mesh", required=True)
    p.add_argument("--gt", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    out = Path(a.output); out.mkdir(parents=True, exist_ok=False)
    paths = {k: Path(v).resolve() for k, v in vars(a).items() if k in {"raw", "mesh", "gt", "head"}}
    for path in paths.values():
        if not path.is_file() or not path.stat().st_size:
            raise RuntimeError(f"missing input: {path}")
    (out / "input_hashes.json").write_text(json.dumps({k: {"path": str(v), "bytes": v.stat().st_size,
        "sha256": sha(v)} for k, v in paths.items()}, indent=2) + "\n")

    saved = torch.load(paths["raw"], map_location="cpu", weights_only=False)
    vertices = saved["vertices"].float().numpy(); faces = saved["faces"].long().numpy()
    raw = saved["vertex_physics"].float()
    if raw.ndim != 2 or raw.shape[1] != 32 or not torch.isfinite(raw).all():
        raise RuntimeError("raw vertex physics must be finite N x 32")
    obj = trimesh.load(paths["mesh"], force="mesh", process=False)
    if len(obj.vertices) != len(vertices) or len(obj.faces) != len(faces):
        raise RuntimeError("OBJ/raw vertex or face count mismatch")
    state = torch.load(paths["head"], map_location="cpu", weights_only=True)
    weight = state["output_layer_phy.weight"][:, :, 1, 1].float()
    bias = state["output_layer_phy.bias"].float()
    if list(weight.shape) != [14, 16]:
        raise RuntimeError(f"unexpected property head weight shape {list(weight.shape)}")
    physics = raw[:, -16:] @ weight.T + bias
    physics[:, 0] = physics[:, 0] * 48 + 95
    physics[:, 2] = physics[:, 2] * 2.8 + 2.3
    physics[:, 4] = physics[:, 4] * .732 - .812
    physics[:, -1] = physics[:, -1] * 4
    if not torch.isfinite(physics).all():
        raise RuntimeError("nonfinite 14-channel property head output")
    torch.save(physics, out / "vertex_physics_14ch.pt")
    phy = physics.numpy(); group_value = phy[:, 3]
    num_group = round(float(group_value.max())) + 1
    labels = np.full(len(group_value), -1, dtype=np.int64)
    for group in range(max(num_group, 0)):
        labels[(group_value > group - .5) & (group_value < group + .5)] = group
    tri = vertices[faces]
    area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1) / 2
    groups = {}
    for group in range(max(num_group, 0)):
        vmask = labels == group
        votes = (labels[faces] == group).sum(1)
        majority = votes >= 2; homogeneous = votes == 3
        groups[str(group)] = {
            "vertex_count": int(vmask.sum()), "vertex_fraction": float(vmask.mean()),
            "majority_face_count": int(majority.sum()), "majority_face_fraction": float(majority.mean()),
            "majority_area": float(area[majority].sum()),
            "majority_area_fraction": float(area[majority].sum() / area.sum()),
            "homogeneous_face_count": int(homogeneous.sum()),
            "homogeneous_area": float(area[homogeneous].sum()),
            "bbox_min": vertices[vmask].min(0).tolist() if vmask.any() else None,
            "bbox_max": vertices[vmask].max(0).tolist() if vmask.any() else None,
            "components": components(faces, labels, group),
        }
    annotation = json.loads(paths["gt"].read_text())
    gt_info = annotation.get("group_info", {})
    gt_groups = len(gt_info)
    official = {"num_group_formula": "round(float(max(group_id))) + 1",
                "predicted_num_group": num_group, "gt_num_group": gt_groups,
                "group_value": summary(group_value), "unassigned_vertex_count": int((labels < 0).sum()),
                "groups": groups, "indexing": []}
    candidate = {"status": "separate indexing correction candidate; not official output", "groups": []}
    for group in range(1, max(num_group, 1)):
        child = (physics[:, 3] > group - .5) & (physics[:, 3] < group + .5)
        row = {"group": group, "child_vertices": int(child.sum())}
        try:
            parent = ((physics[:, 3] > physics[:, 4][child] - .5) &
                      (physics[:, 3] < physics[:, 4][child] + .5))
            row["parent_expression_shape"] = list(parent.shape)
        except Exception as exc:
            row["parent_expression_error"] = f"{type(exc).__name__}: {exc}"
        kmap = torch.zeros((len(physics), max(0, (num_group - 1) * 2)), dtype=torch.long)
        if kmap.shape[1]:
            kmap[:, (group - 1) * 2] = child.long()
            try:
                selected = physics[:, 5:-1][kmap[(group - 1) * 2]]
                row["official_row_index_result_shape"] = list(selected.shape)
            except Exception as exc:
                row["official_row_index_error"] = f"{type(exc).__name__}: {exc}"
        official["indexing"].append(row)
        candidate["groups"].append({"group": group, "selected_vertices": int(child.sum()),
            "parameters_mean": physics[:, 5:-1][child].mean(0).tolist() if child.any() else None,
            "type_mean": float(physics[:, -1][child].mean()) if child.any() else None})
    fields = {
        "scale_cm": summary(phy[:, 0]), "affordance_unitless": summary(phy[:, 1]),
        "density_g_cm3": summary(phy[:, 2]), "group_id_continuous": summary(phy[:, 3]),
        "parent_group_id_continuous": summary(phy[:, 4]),
        "movement_parameters_8ch_coordinate_units_unresolved": summary(phy[:, 5:13]),
        "movement_type_continuous_before_round": summary(phy[:, 13]),
    }
    official.update({"head_input_slice": "raw[:, -16:] (identical to official raw[:,16:] for N x 32)",
                     "output_shape": list(physics.shape), "channels": summary(phy), "field_stats": fields,
                     "description": "not generated: official example/training language slice discrepancy unresolved",
                     "texture_glb_and_videos": "not produced in this runner scope"})
    (out / "official_result.json").write_text(json.dumps(official, indent=2) + "\n")
    (out / "indexing_correction_candidate.json").write_text(json.dumps(candidate, indent=2) + "\n")
    (out / "gt_annotation.json").write_text(json.dumps({"object": annotation.get("object_id", "27281"),
        "group_count": gt_groups, "group_info": gt_info,
        "limits": "no nearest-part/ICP/manual matching; direction/position/range accuracy omitted until coordinate system and units are established"},
        indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"verified": True, "vertices": len(vertices), "faces": len(faces),
                      "raw_shape": list(raw.shape), "property_shape": list(physics.shape),
                      "gt_groups": gt_groups, "predicted_groups": num_group}))


if __name__ == "__main__":
    main()
