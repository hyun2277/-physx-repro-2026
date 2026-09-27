#!/usr/bin/env python3
"""CPU-only actual eight-artifact public-only-v1 evaluation and coverage ledger."""
from __future__ import annotations

import json
import statistics
from pathlib import Path
import sys

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_public_only_v1 as base
from public_only_v1 import sha256
from run_public_only_v1_extension_results import RUNS, spec

ROOT = Path("/home/minsujo/Desktop/SH/PHYSx")
OUT = HERE / "2026-09-27_public-only-v1-eight-actual"
TIER = {"29354":"fixed", "21356":"fixed", "27703":"fixed", "30719":"fixed", "21314":"fixed", "32980":"fixed", "24566":"B_translation", "29806":"C_rotation"}
RAW = {
    "29354": ROOT / "staging/rtx5090-cached-decoder-29354-20260926T194524Z-d69f74359b60/mesh_physics_raw.pt",
    "24566": ROOT / "staging/articulated-decoder-24566-20260926T221319Z-a9491be93452/mesh/mesh_physics_raw.pt",
    "29806": ROOT / "staging/articulated-decoder-29806-20260927T050730Z-8271ccb5f82b/mesh/mesh_physics_raw.pt",
}
RAW.update({object_id: ROOT / f"staging/public-only-v1-extension-decoder-{object_id}-{decoder_id}/mesh/mesh_physics_raw.pt"
            for object_id, (_, decoder_id) in RUNS.items()})


def references(object_id, values):
    paths = {**values, "raw_physics": str(RAW[object_id])}
    checked, errors = {}, []
    for name, value in paths.items():
        path = Path(value)
        try:
            if not path.is_file() or not path.stat().st_size: raise ValueError("missing or empty")
            checked[name] = {"path":str(path), "bytes":path.stat().st_size, "sha256":sha256(path)}
            if name in ("property", "raw_physics"):
                value = torch.load(path, map_location="cpu", weights_only=True)
                tensor = value if isinstance(value, torch.Tensor) else value.get("vertex_attrs", value.get("phy_property")) if isinstance(value, dict) else None
                if tensor is None or not torch.isfinite(tensor).all(): raise ValueError("tensor missing or non-finite")
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    return checked, errors


def mean_median(values):
    values = [float(v) for v in values]
    return {"n":len(values), "mean":float(statistics.mean(values)), "median":float(statistics.median(values))} if values else {"n":0, "mean":None, "median":None}


def aggregate(items):
    measures = {"raw_cd_l1":[], "raw_cd_l2":[], "raw_fscore":[], "canonical_cd_l1":[], "canonical_cd_l2":[], "canonical_fscore":[], "scale_error_cm":[], "group_count_absolute_error":[]}
    for item in items:
        geo, scale, articulation = item["geometry"], item["scale"], item["articulation"]
        measures["raw_cd_l1"].append(geo["raw_coordinate"]["cd_l1_sum_raw"])
        measures["raw_cd_l2"].append(geo["raw_coordinate"]["cd_l2_sum_raw"])
        measures["raw_fscore"].append(geo["raw_coordinate"]["fscore_raw"])
        measures["canonical_cd_l1"].append(geo["bbox_center_max_extent_canonical"]["cd_l1_sum_raw"])
        measures["canonical_cd_l2"].append(geo["bbox_center_max_extent_canonical"]["cd_l2_sum_raw"])
        measures["canonical_fscore"].append(geo["bbox_center_max_extent_canonical"]["fscore_raw"])
        measures["scale_error_cm"].append(scale["raw"])
        measures["group_count_absolute_error"].append(articulation["absolute_group_count_error"])
    return {key:mean_median(value) for key, value in measures.items()}


def main():
    if OUT.exists(): raise RuntimeError(f"refusing to overwrite {OUT}")
    samples = dict(base.SAMPLES)
    samples.update({object_id:spec(object_id,*run) for object_id,run in RUNS.items()})
    # Preflight creates the requested per-artifact hash ledger before the CPU metrics.
    preflight = {}; usable = {}
    for object_id, values in samples.items():
        hashes, errors = references(object_id, values)
        preflight[object_id] = {"tier":TIER[object_id], "status":"success" if not errors else "failed", "artifacts":hashes, "errors":errors}
        if not errors: usable[object_id] = values
    base.OUT = OUT
    base.SAMPLES = usable
    base.main()
    results = json.loads((OUT / "results.json").read_text())
    records = results["records"]
    by_id = {}
    for object_id in usable:
        metric = {x["metric"]:x for x in records if x["object_id"] == object_id}
        geometry = metric["geometry"]; scale = metric["scale_l2"]; articulation = metric["articulation_diagnostic"]
        if any(x["status"] != "success" for x in (geometry, scale, articulation)):
            preflight[object_id]["status"] = "failed"; preflight[object_id]["errors"].append("one or more primary CPU metrics failed")
            continue
        audit = json.loads(Path(usable[object_id]["audit"]).read_text())
        groups = audit["groups"]
        by_id[object_id] = {"object_id":object_id, "tier":TIER[object_id], "test_row":next(x["test_index"] for x in records if x["object_id"]==object_id),
                            "geometry":geometry["value"], "scale":scale["value"], "articulation":articulation["value"],
                            "official_groups":groups, "status":"success"}
    successful = list(by_id.values())
    subgroup = {name:aggregate([x for x in successful if x["tier"] == name]) for name in ("fixed","B_translation","C_rotation")}
    coverage = {"artifact_complete":len(successful), "metric_failed":len(samples)-len(successful), "blocked_metric_rows":sum(x["status"]=="blocked" for x in records),
                "test_rows_total":1000, "test_order_and_duplicate_policy":"the v1 manifest retains source test row and duplicate occurrence; this eight-item subset does not deduplicate."}
    failure_ledger = [
        {"object_id":"23787", "status":"failed", "included_in_numeric_denominator":False, "reason":"official texture retrieval output non-finite OBJ"},
        {"object_id":"27281", "status":"excluded", "included_in_numeric_denominator":False, "reason":"mesh decoder OOM under preserved 28,000 MiB hard limit and 4,607 MiB reserve policy"},
    ]
    report = {"protocol":"public-materials-independent-evaluation-v1", "paper_equivalent":False,
              "geometry_definition":{"sampling":"area-weighted barycentric PCG64","seed":20260927,"points_per_mesh":8192,
                "symmetric_cd_l1":"mean(pred→GT Euclidean NN) + mean(GT→pred Euclidean NN)", "symmetric_cd_l2":"same directional sum using squared NN distance",
                "fscore":"harmonic mean of directional hit fractions at Euclidean threshold 0.05", "canonical":"independently subtract bbox center and divide each mesh by its maximum bbox extent; raw and canonical are never mixed"},
              "coverage":coverage, "samples":successful, "all_macro":aggregate(successful), "subgroup_macro":subgroup,
              "artifact_preflight":preflight, "blocked_areas":{
                "appearance_density_affordance_psnr":"no paired GT maps/masks, official 30-view camera manifest, normalization/range, or generated↔GT vertex/pixel correspondence",
                "description_psnr":"official question/part correspondence unresolved and example literal slice disagrees with training path",
                "nap_cov_mmd":"official PhysX-to-NAP conversion, group matching, coordinate/unit convention, and aggregation unavailable",
                "paper_table2_aggregation":"test conditioning manifest, duplicate/failure denominator rule, and official evaluator config unavailable"},
              "failure_ledger":failure_ledger}
    (OUT / "eight_sample_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    with (OUT / "eight_sample_summary.csv").open("w") as f:
        f.write("object_id,tier,status,raw_cd_l1,raw_cd_l2,raw_fscore,canonical_cd_l1,canonical_cd_l2,canonical_fscore,scale_error_cm,gt_groups,predicted_groups\n")
        for x in successful:
            g=x["geometry"]; a=x["articulation"]; s=x["scale"]
            f.write(f'{x["object_id"]},{x["tier"]},success,{g["raw_coordinate"]["cd_l1_sum_raw"]},{g["raw_coordinate"]["cd_l2_sum_raw"]},{g["raw_coordinate"]["fscore_raw"]},{g["bbox_center_max_extent_canonical"]["cd_l1_sum_raw"]},{g["bbox_center_max_extent_canonical"]["cd_l2_sum_raw"]},{g["bbox_center_max_extent_canonical"]["fscore_raw"]},{s["raw"]},{a["gt_num_group"]},{a["predicted_num_group"]}\n')
    (OUT / "failure_ledger.json").write_text(json.dumps(failure_ledger, ensure_ascii=False, indent=2)+"\n")
    (OUT / "README.md").write_text("# Public-only v1: eight actual artifacts\n\nThis is an independent public-materials evaluation condition, **not** PhysX-3D Table 2 reproduction. Eight of 1,000 test rows have artifact-complete outputs. `eight_sample_report.json` keeps raw-coordinate and canonical-shape geometry separate, records deterministic sampling, and excludes 23787/27281 from numeric denominators while retaining them in `failure_ledger.json`.\n\nTo extend to 10–30 samples, first freeze an eligible manifest, validate source and ShapeNet texture members, render conditioning, then use the measured sampling latent gate before any decoder. The current census identifies missing ShapeNet category archives and still leaves the paper evaluator inputs unavailable.\n", encoding="utf-8")
    print(json.dumps({"output":str(OUT), "successful":len(successful), "coverage":coverage}, ensure_ascii=False))


if __name__ == "__main__": main()
