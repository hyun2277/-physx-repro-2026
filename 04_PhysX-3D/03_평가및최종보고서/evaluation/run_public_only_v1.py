#!/usr/bin/env python3
"""Generate a new public-materials-only v1 record from three existing outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))
from physx_eval.metrics import evaluate
from public_only_v1 import (PublicOnlyError, aggregate_status, articulation_classification,
                            canonical_bbox, geometry_result, group_is_meaningful,
                            load_mesh, occurrence_rows, sha256)

OUT = ROOT / "evaluation" / "2026-09-27_public-only-v1"
SOURCE = Path("/home/minsujo/Desktop/SH/PHYSx/sources/physx-4f54e750a309")

SAMPLES = {
    "29354": {
        "gt_json": "/home/minsujo/Desktop/SH/PHYSx/staging/merge-29354-20260925T180423Z/physxnet/finaljson/29354.json",
        "gt_mesh": "/home/minsujo/Desktop/SH/PHYSx/staging/merge-29354-20260925T180423Z/phy_dataset/29354/model.obj",
        "generated_mesh": "/home/minsujo/Desktop/SH/PHYSx/staging/rtx5090-cached-decoder-29354-20260926T194524Z-d69f74359b60/mesh.obj",
        "property": "/home/minsujo/Desktop/SH/PHYSx/staging/rtx5090-cached-decoder-29354-20260926T194524Z-d69f74359b60/mesh_physics_raw.pt",
        "audit": "/home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/01_재현실행/자료확보/rtx5090_adapter/2026-09-27_29354-semantic-validation/official_code_result.json",
    },
    "24566": {
        "gt_json": "/home/minsujo/Desktop/SH/PHYSx/staging/articulated-sampling-24566-20260926T213719Z-83a8565c7136/work/physxnet/finaljson/24566.json",
        "gt_mesh": "/home/minsujo/Desktop/SH/PHYSx/staging/articulated-sampling-24566-20260926T213719Z-83a8565c7136/work/phy_dataset/24566/model.obj",
        "generated_mesh": "/home/minsujo/Desktop/SH/PHYSx/staging/articulated-decoder-24566-20260926T221319Z-a9491be93452/mesh/mesh.obj",
        "property": "/home/minsujo/Desktop/SH/PHYSx/staging/articulated-decoder-24566-20260926T221319Z-a9491be93452/articulation_audit/vertex_physics_14ch.pt",
        "audit": "/home/minsujo/Desktop/SH/PHYSx/staging/articulated-decoder-24566-20260926T221319Z-a9491be93452/articulation_audit/official_result.json",
    },
    "29806": {
        "gt_json": "/home/minsujo/Desktop/SH/PHYSx/staging/articulated-sampling-29806-20260926T220010Z-ac2c1dfab94d/work/physxnet/finaljson/29806.json",
        "gt_mesh": "/home/minsujo/Desktop/SH/PHYSx/staging/articulated-sampling-29806-20260926T220010Z-ac2c1dfab94d/work/phy_dataset/29806/model.obj",
        "generated_mesh": "/home/minsujo/Desktop/SH/PHYSx/staging/articulated-decoder-29806-20260927T050730Z-8271ccb5f82b/mesh/mesh.obj",
        "property": "/home/minsujo/Desktop/SH/PHYSx/staging/articulated-decoder-29806-20260927T050730Z-8271ccb5f82b/articulation_audit/vertex_physics_14ch.pt",
        "audit": "/home/minsujo/Desktop/SH/PHYSx/staging/articulated-decoder-29806-20260927T050730Z-8271ccb5f82b/articulation_audit/official_result.json",
    },
}


def write_json(name, value):
    path = OUT / name
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def reference(path):
    path = Path(path)
    if not path.is_file():
        return {"status": "blocked", "path": str(path), "reason": "missing file"}
    return {"status": "present", "path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def gt_scalar(annotation):
    values = [float(x) for x in annotation["dimension"].split(" ")[0].split("*")]
    return max(values)


def raw_property_scale(sample, audit):
    if sample == "29354":
        return float(audit["scale"]["predicted_vertex_mean_cm"]), "existing official-code audit: predicted vertex mean"
    value = torch.load(SAMPLES[sample]["property"], map_location="cpu", weights_only=True)
    if not isinstance(value, torch.Tensor) or value.ndim != 2 or value.shape[1] != 14:
        raise PublicOnlyError("expected existing 14-channel property tensor")
    if not torch.isfinite(value).all():
        raise PublicOnlyError("property tensor contains NaN or Inf")
    return float(value[:, 0].mean().item()), "existing property-head channel 0 vertex mean"


def metric_audit():
    return [
        ["appearance_psnr", "paper: mean PSNR over 30 random unit-sphere views", "code: render_video/render_multiview exist", "proposal: no value", "camera/seed/mask/range/GT RGB missing"],
        ["cd", "paper: CD x10^-3", "code: no evaluator", "proposal: deterministic area samples; L1/L2 symmetric sums", "paper sampling/alignment missing"],
        ["fscore", "paper: threshold 0.05, x10^-2", "code: no evaluator", "proposal: directional hit F-score at 0.05", "paper point/sampling convention missing"],
        ["scale_l2", "paper: Euclidean distance", "code: GT max dimension; example vertex mean", "proposal: scalar L2 on those expressions", "test aggregation/duplicates missing"],
        ["density_psnr", "paper: PSNR", "code: GT part density and display normalization", "proposal: blocked", "vertex-part mapping/map/mask/range missing"],
        ["affordance_psnr", "paper: PSNR", "code: GT rank and display normalization", "proposal: blocked", "vertex-part mapping/map/mask/range missing"],
        ["description_psnr", "paper: cosine score-map PSNR", "code: example slice/question path", "proposal: blocked", "question/part mapping and slice disagreement missing"],
        ["kinematics_cov", "paper: Instantiation Distance COV", "code: README links NAP", "proposal: blocked", "PhysX-to-NAP conversion/matching/aggregation missing"],
        ["kinematics_mmd", "paper: Instantiation Distance MMD", "code: README links NAP", "proposal: blocked", "PhysX-to-NAP conversion/matching/aggregation missing"],
    ]


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    test = np.load(SOURCE / "val_test_list.npy", allow_pickle=False)[-1000:]
    # Build occurrence numbers over the complete official test order first,
    # then select the three rows.  This retains the original test index and
    # would preserve a repeated ID's true occurrence number.
    all_rows = occurrence_rows([str(x) for x in test], [1000 + i for i in range(len(test))])
    rows = [row for row in all_rows if row["object_id"] in SAMPLES]
    records, manifest_items = [], []
    for row in rows:
        object_id = row["object_id"]
        spec = SAMPLES[object_id]
        files = {kind: reference(path) for kind, path in spec.items()}
        manifest_items.append(dict(row, files=files, status="success" if all(x["status"] == "present" for x in files.values()) else "blocked"))
        if any(x["status"] != "present" for x in files.values()):
            records.append(dict(row, metric="all", status="blocked", reason="required artifact missing"))
            continue
        annotation = json.loads(Path(spec["gt_json"]).read_text(encoding="utf-8"))
        audit = json.loads(Path(spec["audit"]).read_text(encoding="utf-8"))
        gt_groups, predicted_groups = len(annotation["group_info"]), int(audit.get("predicted_num_group", audit.get("num_group")))
        group_data = {key: group_is_meaningful(value) for key, value in audit["groups"].items() if key != "0"}
        articulation = articulation_classification(gt_num_group=gt_groups, predicted_num_group=predicted_groups)
        records.append(dict(row, metric="articulation_diagnostic", status="success", value={**articulation, "moving_groups": group_data, "gt_types": [v[-1] for k, v in annotation["group_info"].items() if k != "0"]}))
        predicted_scale, scale_expression = raw_property_scale(object_id, audit)
        scale_result = evaluate("scale_l2", {"values": [predicted_scale], "unit": "cm"}, {"values": [gt_scalar(annotation)], "unit": "cm"}, {"authority": "code_verified", "unit": "cm", "normalization": {"kind": "identity"}, "representation": "scalar"})
        records.append(dict(row, metric="scale_l2", status="success", value={**scale_result, "prediction_expression": scale_expression, "gt_expression": "max JSON dimension, matching example_render_gt_foreval.py:141-145"}))
        try:
            generated, ground_truth = load_mesh(spec["generated_mesh"]), load_mesh(spec["gt_mesh"])
            raw = geometry_result(generated, ground_truth, count=8192, seed=20260927)
            canonical = geometry_result(canonical_bbox(generated), canonical_bbox(ground_truth), count=8192, seed=20260927)
            records.append(dict(row, metric="geometry", status="success", value={"raw_coordinate": raw, "bbox_center_max_extent_canonical": canonical}))
        except PublicOnlyError as exc:
            records.append(dict(row, metric="geometry", status="failed", reason=str(exc)))
        for metric, reason in (("appearance_psnr", "no paired RGB renders, official 30-view cameras, masks, or range"),
                               ("density_psnr", "no generated-vertex to GT-part mapping or paired numeric maps/masks/range"),
                               ("affordance_psnr", "no generated-vertex to GT-part mapping or paired numeric maps/masks/range"),
                               ("description_psnr", "question/part correspondence and official literal/training slice disagreement unresolved"),
                               ("kinematics_cov", "no official PhysX-to-NAP conversion, matching, or aggregation"),
                               ("kinematics_mmd", "no official PhysX-to-NAP conversion, matching, or aggregation")):
            records.append(dict(row, metric=metric, status="blocked", reason=reason))
    summaries = {metric: aggregate_status(records, metric) for metric in sorted({r["metric"] for r in records})}
    articulation_by_id = {r["object_id"]: r["value"] for r in records if r["metric"] == "articulation_diagnostic" and r["status"] == "success"}
    scale_by_id = {r["object_id"]: r["value"]["raw"] for r in records if r["metric"] == "scale_l2" and r["status"] == "success"}
    consistency_checks = {
        "29354_fixed_false_positive": articulation_by_id["29354"]["fixed_false_positive"],
        "24566_articulated_false_negative": articulation_by_id["24566"]["articulated_false_negative"],
        "29806_multi_joint_underprediction": articulation_by_id["29806"]["multi_joint_underprediction"],
        "29354_scale_error_cm_matches_prior_audit": abs(scale_by_id["29354"] - 20.21143341064453) < 1e-6,
    }
    if not all(consistency_checks.values()):
        raise PublicOnlyError("new evaluation contradicts a previously verified small-sample observation")
    success_scale = [r["value"]["raw"] for r in records if r["metric"] == "scale_l2" and r["status"] == "success"]
    success_geometry = [r["value"] for r in records if r["metric"] == "geometry" and r["status"] == "success"]
    aggregate = {"scale_l2_macro_mean_cm": float(np.mean(success_scale)), "scale_l2_micro_mean_cm": float(np.sum(success_scale) / len(success_scale)),
                 "geometry_macro_mean_raw_cd_l1": float(np.mean([x["raw_coordinate"]["cd_l1_sum_raw"] for x in success_geometry])),
                 "geometry_micro_point_weighted_raw_cd_l1": float(sum(x["raw_coordinate"]["cd_l1_sum_raw"] * (x["raw_coordinate"]["pred_sample_count"] + x["raw_coordinate"]["gt_sample_count"]) for x in success_geometry) / sum(x["raw_coordinate"]["pred_sample_count"] + x["raw_coordinate"]["gt_sample_count"] for x in success_geometry)),
                 "note": "Proposal-only summaries. Equal 8192-per-mesh samples make geometry macro and this point-weighted micro equal here."}
    manifest = {"protocol": "public-materials-independent-evaluation-v1", "paper_equivalent": False,
                "official_source_head": "4f54e750a309fe9cd9f20816916ecc0e8a9ae594", "duplicate_policy": "preserve source rows; no benchmark aggregation", "items": manifest_items}
    write_json("manifest.json", manifest); write_json("results.json", {"paper_equivalent": False, "records": records, "summaries": summaries, "aggregate": aggregate, "consistency_checks": consistency_checks})
    write_json("metric_audit.json", {"rows": metric_audit(), "official_gt_static_findings": [
        "example_render_gt_foreval.py:102-139 processes only group_info['1']", "example_render_gt_foreval.py:152-155 loads stale meshname instead of current part", "example_render_gt_foreval.py:161 calls unseeded np.random.randint inside the part loop", "example_render_gt_foreval.py:163 overwrites des_index.npy each part; selected description_ind is not saved with its matching part"]})
    with (OUT / "records.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream); writer.writerow(["item_key", "object_id", "source_index", "metric", "status", "reason_or_raw"])
        for record in records: writer.writerow([record["item_key"], record["object_id"], record["source_index"], record["metric"], record["status"], record.get("reason", json.dumps(record.get("value", {}).get("raw", "")))])
    print(json.dumps({"output": str(OUT), "records": len(records), "aggregate": aggregate}, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
