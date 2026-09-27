"""CPU-only primitives for the proposed public-materials evaluation v1.

This module is deliberately separate from the paper evaluator: it operates only
on two explicitly named meshes already available locally.  It never chooses
benchmark cameras, aligns generated vertices to PartNet parts, or evaluates
maps/kinematics.  All numerical results therefore set ``paper_equivalent`` to
false.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import math
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree


class PublicOnlyError(ValueError):
    """Raised when a public-only input cannot be evaluated safely."""


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def occurrence_rows(object_ids: list[str], source_indices: list[int]) -> list[dict]:
    """Preserve row order and duplicate occurrences without assigning weights."""
    if len(object_ids) != len(source_indices):
        raise PublicOnlyError("object IDs and source indices must have equal length")
    counts: Counter[str] = Counter()
    rows = []
    for test_index, (object_id, source_index) in enumerate(zip(object_ids, source_indices)):
        if not isinstance(object_id, str) or not object_id:
            raise PublicOnlyError("object ID must be a nonempty string")
        if not isinstance(source_index, int):
            raise PublicOnlyError("source index must be an integer")
        counts[object_id] += 1
        rows.append({
            "item_key": f"test-{test_index:06d}", "test_index": test_index,
            "source_index": source_index, "object_id": object_id,
            "occurrence": counts[object_id],
        })
    return rows


def load_mesh(path: str | Path) -> trimesh.Trimesh:
    """Load one triangular mesh and reject empty, nonfinite, or invalid input."""
    path = Path(path)
    if not path.is_file():
        raise PublicOnlyError(f"mesh missing: {path}")
    mesh = trimesh.load(path, force="mesh", process=False)
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
    if not isinstance(mesh, trimesh.Trimesh):
        raise PublicOnlyError("input did not load as a mesh")
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) == 0:
        raise PublicOnlyError("mesh has no vertices")
    if faces.ndim != 2 or faces.shape[1] != 3 or len(faces) == 0:
        raise PublicOnlyError("mesh has no triangular faces")
    if not np.isfinite(vertices).all():
        raise PublicOnlyError("mesh vertices contain NaN or Inf")
    if (faces < 0).any() or (faces >= len(vertices)).any():
        raise PublicOnlyError("mesh faces reference an invalid vertex")
    triangles = vertices[faces]
    doubled_area = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1)
    if not np.isfinite(doubled_area).all() or not np.any(doubled_area > 0):
        raise PublicOnlyError("mesh has no positive-area triangle")
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def canonical_bbox(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Center each mesh at its bbox center and divide by its max bbox extent."""
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    lower, upper = vertices.min(axis=0), vertices.max(axis=0)
    extent = upper - lower
    maximum = float(extent.max())
    if not math.isfinite(maximum) or maximum <= 0:
        raise PublicOnlyError("mesh bbox max extent must be finite and positive")
    return trimesh.Trimesh(vertices=(vertices - (lower + upper) / 2.0) / maximum,
                           faces=np.asarray(mesh.faces, dtype=np.int64), process=False)


def sample_surface(mesh: trimesh.Trimesh, *, count: int, seed: int) -> np.ndarray:
    """Area-weighted deterministic barycentric surface samples using PCG64."""
    if not isinstance(count, int) or count <= 0:
        raise PublicOnlyError("sample count must be a positive integer")
    if not isinstance(seed, int):
        raise PublicOnlyError("sampling seed must be an integer")
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    triangles = vertices[faces]
    areas = 0.5 * np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1)
    total = float(areas.sum())
    if not math.isfinite(total) or total <= 0:
        raise PublicOnlyError("surface area must be finite and positive")
    rng = np.random.Generator(np.random.PCG64(seed))
    cumulative = np.cumsum(areas / total)
    chosen = np.searchsorted(cumulative, rng.random(count), side="right")
    chosen = np.minimum(chosen, len(triangles) - 1)
    u, v = rng.random(count), rng.random(count)
    root = np.sqrt(u)
    weights = np.column_stack((1.0 - root, root * (1.0 - v), root * v))
    points = (triangles[chosen] * weights[:, :, None]).sum(axis=1)
    if not np.isfinite(points).all():
        raise PublicOnlyError("surface sampling produced NaN or Inf")
    return points


def geometry_result(prediction: trimesh.Trimesh, ground_truth: trimesh.Trimesh, *, count: int, seed: int) -> dict:
    """Symmetric nearest-surface metrics under one explicit coordinate condition.

    ``cd_l1_sum`` is mean(pred→GT Euclidean NN) + mean(GT→pred Euclidean
    NN). ``cd_l2_sum`` uses squared Euclidean nearest-neighbour distances in
    the same directional-sum form. F-score uses directional hit fractions and
    their harmonic mean at an Euclidean radius of 0.05.
    """
    # The identical seed makes a mesh self-comparison exactly zero. For two
    # different meshes it remains a deterministic independent surface draw
    # because triangle areas and the inverse-CDF mapping differ by mesh.
    pred_points = sample_surface(prediction, count=count, seed=seed)
    gt_points = sample_surface(ground_truth, count=count, seed=seed)
    pred_to_gt = cKDTree(gt_points).query(pred_points, k=1, workers=1)[0]
    gt_to_pred = cKDTree(pred_points).query(gt_points, k=1, workers=1)[0]
    if not np.isfinite(pred_to_gt).all() or not np.isfinite(gt_to_pred).all():
        raise PublicOnlyError("nearest-neighbour query produced NaN or Inf")
    p_mean, g_mean = float(pred_to_gt.mean()), float(gt_to_pred.mean())
    l1 = p_mean + g_mean
    l2 = float(np.square(pred_to_gt).mean() + np.square(gt_to_pred).mean())
    threshold = 0.05
    precision, recall = float((pred_to_gt <= threshold).mean()), float((gt_to_pred <= threshold).mean())
    fscore = 0.0 if precision + recall == 0 else 2.0 * precision * recall / (precision + recall)
    return {
        "status": "success", "paper_equivalent": False, "authority": "proposal",
        "sampling": {"method": "area_weighted_barycentric_pcg64", "seed": seed, "count_per_mesh": count},
        "symmetric_definition": "directional_mean_pred_to_gt_plus_gt_to_pred",
        "cd_l1_sum_raw": l1, "cd_l2_sum_raw": l2,
        "cd_l1_pred_to_gt_mean": p_mean, "cd_l1_gt_to_pred_mean": g_mean,
        "fscore_raw": fscore, "fscore_threshold_euclidean": threshold,
        "precision": precision, "recall": recall,
        "cd_l1_table_display_x1e3": l1 / 1e-3,
        "fscore_table_display_x1e2": fscore / 1e-2,
        "pred_sample_count": len(pred_points), "gt_sample_count": len(gt_points),
    }


def group_is_meaningful(group: dict, *, min_homogeneous_faces: int = 100,
                        min_majority_area_fraction: float = 0.001,
                        min_largest_component_fraction: float = 0.01) -> dict:
    """A predeclared descriptive screen, not a paper articulation metric."""
    components = group.get("components", {})
    checks = {
        "homogeneous_faces": int(group.get("homogeneous_face_count", 0)) >= min_homogeneous_faces,
        "majority_area_fraction": float(group.get("majority_area_fraction", 0.0)) >= min_majority_area_fraction,
        "largest_component_fraction": float(components.get("largest_fraction", 0.0)) >= min_largest_component_fraction,
    }
    return {"meaningful": all(checks.values()), "checks": checks,
            "thresholds": {"min_homogeneous_faces": min_homogeneous_faces,
                           "min_majority_area_fraction": min_majority_area_fraction,
                           "min_largest_component_fraction": min_largest_component_fraction}}


def articulation_classification(*, gt_num_group: int, predicted_num_group: int) -> dict:
    """Rule-based count diagnostic; it never matches generated groups to GT parts."""
    if not all(isinstance(x, int) and x >= 1 for x in (gt_num_group, predicted_num_group)):
        raise PublicOnlyError("group counts must be positive integers")
    fixed_false_positive = gt_num_group == 1 and predicted_num_group > 1
    articulated_false_negative = gt_num_group > 1 and predicted_num_group == 1
    multi_joint_underprediction = gt_num_group >= 3 and 1 < predicted_num_group < gt_num_group
    return {"gt_num_group": gt_num_group, "predicted_num_group": predicted_num_group,
            "absolute_group_count_error": abs(predicted_num_group - gt_num_group),
            "fixed_false_positive": fixed_false_positive,
            "articulated_false_negative": articulated_false_negative,
            "multi_joint_underprediction": multi_joint_underprediction,
            "direct_group_to_part_mapping": False,
            "parent_direction_position_range_evaluated": False}


def aggregate_status(records: list[dict], metric: str) -> dict:
    """Keep success, failed, and blocked rows in separate denominators."""
    relevant = [r for r in records if r.get("metric") == metric]
    buckets = {name: [r for r in relevant if r.get("status") == name] for name in ("success", "failed", "blocked")}
    return {"metric": metric, "declared": len(relevant), "success": len(buckets["success"]),
            "failed": len(buckets["failed"]), "blocked": len(buckets["blocked"]),
            "success_item_keys": [r["item_key"] for r in buckets["success"]],
            "excluded_from_numeric_denominator": [r["item_key"] for name in ("failed", "blocked") for r in buckets[name]]}
