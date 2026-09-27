#!/usr/bin/env python3
"""Controlled 256/256-control/128 end-to-end adapter sensitivity probe.

Creates a new staging/log tree only. It never reuses or overwrites a prior
sample, latent, mesh, or public-only evaluation record.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_27281_articulated_pipeline as common
import run_articulated_sampling_candidates as sampling_gate

ROOT, SRC, PY, ADAPTER = common.ROOT, common.SRC, common.PY, common.ADAPTER
EVAL = ROOT / "repro-records/04_PhysX-3D/evaluation"
sys.path.insert(0, str(EVAL))
HARD_MIB, RESERVE_MIB = 28000, 4607
CONFIGS = (("baseline_a", 256), ("baseline_b_control", 256), ("tile_128", 128))
SAMPLES = {
    "29354": {
        "input": ROOT / "staging/render-cond-29354-portable-20260925T185825Z/datasets/PhysXNet/renders_cond/29354_/000.png",
        "gt": ROOT / "staging/merge-29354-20260925T180423Z/physxnet/finaljson/29354.json",
        "gtmesh": ROOT / "staging/merge-29354-20260925T180423Z/phy_dataset/29354/model.obj",
    },
    "29806": {
        "input": ROOT / "staging/articulated-sampling-29806-20260926T220010Z-ac2c1dfab94d/datasets/PhysXNet/renders_cond/29806_/000.png",
        "gt": ROOT / "staging/articulated-sampling-29806-20260926T220010Z-ac2c1dfab94d/work/physxnet/finaljson/29806.json",
        "gtmesh": ROOT / "staging/articulated-sampling-29806-20260926T220010Z-ac2c1dfab94d/work/phy_dataset/29806/model.obj",
    },
}


def sha(path: Path) -> str:
    return common.sha(Path(path))


def fingerprint(*values: object) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(str(value).encode())
        digest.update(b"\0")
    return digest.hexdigest()


def tensor_delta(a, b) -> dict:
    import torch
    result = {"same_shape": list(a.shape) == list(b.shape),
              "a_shape": list(a.shape), "b_shape": list(b.shape),
              "a_dtype": str(a.dtype), "b_dtype": str(b.dtype)}
    if not result["same_shape"]:
        return result
    result["finite"] = bool(torch.isfinite(a).all() and torch.isfinite(b).all()) if (a.is_floating_point() or b.is_floating_point()) else True
    if a.is_floating_point() or b.is_floating_point():
        delta = a.float() - b.float()
        denominator = torch.linalg.vector_norm(a.float()).clamp_min(1e-30)
        result.update(max_abs=float(delta.abs().max()), mean_abs=float(delta.abs().mean()),
                      relative_l2=float(torch.linalg.vector_norm(delta) / denominator), exact_equal=bool(torch.equal(a, b)))
    else:
        result.update(exact_equal=bool(torch.equal(a, b)), unequal_count=int((a != b).sum()))
    return result


def latent_delta(a_path: Path, b_path: Path) -> dict:
    import torch
    a = torch.load(a_path, map_location="cpu", weights_only=True)
    b = torch.load(b_path, map_location="cpu", weights_only=True)
    keys = ("slat_coords", "slat_feats", "phy_coords", "phy_feats")
    if set(a) != set(b):
        return {"same_key_set": False, "a_keys": sorted(a), "b_keys": sorted(b)}
    return {"same_key_set": True, "per_tensor": {key: tensor_delta(a[key], b[key]) for key in keys},
            "within_a_coordinate_equal": bool(torch.equal(a["slat_coords"], a["phy_coords"])),
            "within_b_coordinate_equal": bool(torch.equal(b["slat_coords"], b["phy_coords"]))}


def scale_mean(audit: dict) -> float | None:
    field = audit.get("field_stats", {}).get("scale_cm", {})
    return field.get("mean") if isinstance(field.get("mean"), (float, int)) else None


def group_signature(audit: dict) -> dict:
    from public_only_v1 import group_is_meaningful
    groups = audit["groups"]
    return {"predicted_num_group": audit["predicted_num_group"],
            "moving_group_meaningful": {group: group_is_meaningful(row)["meaningful"]
                                         for group, row in groups.items() if group != "0"}}


def guard_from_latent(latent: Path, output: Path) -> dict:
    gate = sampling_gate.latent_schema_and_estimate(latent, output.with_name("decoder_eligibility.json"))
    if not gate["decoder_eligible_under_current_policy"]:
        raise RuntimeError(f"decoder gate rejected latent: {gate}")
    gpu = common.gpu_guard()
    peak = float(gate["gate_peak_with_uncertainty_mib"])
    report = {"gate": gate, "gpu": gpu, "hard_limit_mib": HARD_MIB, "reserve_mib": RESERVE_MIB,
              "required_free_before_mib": peak + RESERVE_MIB,
              "pass": peak <= HARD_MIB and gpu["free_mib"] >= peak + RESERVE_MIB}
    common.write_json(output, report)
    if not report["pass"]:
        raise RuntimeError(f"proactive decoder memory guard failed: {report}")
    return report


def audit_command(r, directory: Path, mesh: Path, gt: Path, audit: Path) -> tuple[list[Path], dict]:
    cpu_env = os.environ.copy()
    cpu_env.update(CUDA_VISIBLE_DEVICES="", PYTHONDONTWRITEBYTECODE="1")
    r.child(directory, [PY, "-B", ADAPTER / "verify_articulated_output.py", "--raw", mesh / "mesh_physics_raw.pt",
             "--mesh", mesh / "mesh.obj", "--gt", gt, "--head", SRC / "pretrain/diffusion/ckpts_new/property_output_step0100000.pt",
             "--output", audit], env=cpu_env)
    return [audit / "official_result.json", audit / "vertex_physics_14ch.pt"], {"cpu_audit": True}


def compare(results: dict[str, dict[str, Path]], output: Path) -> None:
    import torch
    from public_only_v1 import canonical_bbox, geometry_result, load_mesh

    result = {"scope": "same input, seed=1, checkpoint, native spconv, overlay and memory policy; proposed public-only diagnostics, not paper Table 2",
              "tile_configs": dict(CONFIGS), "samples": {}}
    for oid, configs in results.items():
        entries = {}
        for label in dict(CONFIGS):
            root = configs[label]
            raw_path = root / "mesh/mesh_physics_raw.pt"
            raw = torch.load(raw_path, map_location="cpu", weights_only=True)
            audit = json.loads((root / "audit/official_result.json").read_text())
            mesh = load_mesh(root / "mesh/mesh.obj")
            entries[label] = {"paths": {"latent": str(root / "sampling/sampled_latents.pt"), "raw": str(raw_path), "mesh": str(root / "mesh/mesh.obj")},
                              "sha256": {"latent": sha(root / "sampling/sampled_latents.pt"), "raw": sha(raw_path), "mesh": sha(root / "mesh/mesh.obj")},
                              "raw_schema": {key: {"shape": list(value.shape), "dtype": str(value.dtype),
                                                   "finite": bool(torch.isfinite(value).all()) if value.is_floating_point() else True}
                                             for key, value in raw.items() if value is not None},
                              "obj_reload": {"vertices": len(mesh.vertices), "faces": len(mesh.faces)},
                              "scale_mean_cm": scale_mean(audit), "official_group_diagnostic": group_signature(audit)}
        baseline, control, tiled = (configs[name] for name in ("baseline_a", "baseline_b_control", "tile_128"))
        raw_base = torch.load(baseline / "mesh/mesh_physics_raw.pt", map_location="cpu", weights_only=True)
        raw_control = torch.load(control / "mesh/mesh_physics_raw.pt", map_location="cpu", weights_only=True)
        raw_tile = torch.load(tiled / "mesh/mesh_physics_raw.pt", map_location="cpu", weights_only=True)
        comparisons = {
            "control_256_repeat": {"latent": latent_delta(baseline / "sampling/sampled_latents.pt", control / "sampling/sampled_latents.pt"),
                                    "vertices": tensor_delta(raw_base["vertices"], raw_control["vertices"]),
                                    "vertex_physics_32ch": tensor_delta(raw_base["vertex_physics"], raw_control["vertex_physics"]),
                                    "property_head_14ch": tensor_delta(torch.load(baseline / "audit/vertex_physics_14ch.pt", map_location="cpu", weights_only=True), torch.load(control / "audit/vertex_physics_14ch.pt", map_location="cpu", weights_only=True))},
            "tile_128_vs_256": {"latent": latent_delta(baseline / "sampling/sampled_latents.pt", tiled / "sampling/sampled_latents.pt"),
                                "vertices": tensor_delta(raw_base["vertices"], raw_tile["vertices"]),
                                "vertex_physics_32ch": tensor_delta(raw_base["vertex_physics"], raw_tile["vertex_physics"]),
                                "property_head_14ch": tensor_delta(torch.load(baseline / "audit/vertex_physics_14ch.pt", map_location="cpu", weights_only=True), torch.load(tiled / "audit/vertex_physics_14ch.pt", map_location="cpu", weights_only=True))},
        }
        gt_mesh = load_mesh(SAMPLES[oid]["gtmesh"])
        geometry = {}
        for label in dict(CONFIGS):
            prediction = load_mesh(configs[label] / "mesh/mesh.obj")
            geometry[label] = {"raw": geometry_result(prediction, gt_mesh, count=8192, seed=20260928),
                               "canonical": geometry_result(canonical_bbox(prediction), canonical_bbox(gt_mesh), count=8192, seed=20260928)}
        baseline_mesh = load_mesh(baseline / "mesh/mesh.obj")
        output_geometry = {}
        for label, other in (("control_256_repeat", control), ("tile_128_vs_256", tiled)):
            other_mesh = load_mesh(other / "mesh/mesh.obj")
            output_geometry[label] = {
                "raw": geometry_result(baseline_mesh, other_mesh, count=8192, seed=20260928),
                "canonical": geometry_result(canonical_bbox(baseline_mesh), canonical_bbox(other_mesh), count=8192, seed=20260928),
            }
        b_sig, t_sig = entries["baseline_a"]["official_group_diagnostic"], entries["tile_128"]["official_group_diagnostic"]
        control_error = float(comparisons["control_256_repeat"]["vertices"].get("relative_l2", float("inf")))
        tile_error = float(comparisons["tile_128_vs_256"]["vertices"].get("relative_l2", float("inf")))
        same_semantics = b_sig == t_sig
        numeric_bound = max(4.0 * control_error, 1e-6)
        # Mesh topology can differ across same-seed CUDA runs, so topology-dependent
        # tensors cannot be compared rowwise.  Semantics use the predeclared public-only
        # group-count plus meaningful-moving-surface screen; numeric identity is stricter.
        exact = all(bool(comparisons["tile_128_vs_256"][key].get("exact_equal", False))
                    for key in ("vertices", "vertex_physics_32ch", "property_head_14ch"))
        judgement = "stable_under_tile_change" if same_semantics and exact else ("numerically_different_but_semantically_stable" if same_semantics else "output_sensitive_to_tile_change")
        result["samples"][oid] = {"configs": entries, "comparisons": comparisons, "public_only_geometry": geometry,
                                  "between_generated_mesh_geometry": output_geometry,
                                  "control_relative_l2_vertex": control_error, "tile_relative_l2_vertex": tile_error,
                                  "predeclared_numeric_bound": numeric_bound, "judgement": judgement}
    output.write_text(json.dumps(result, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--summarize-run", type=Path,
                        help="CPU-only: recompute comparison JSON for a completed sensitivity run")
    args = parser.parse_args()
    if args.self_test:
        assert dict(CONFIGS)["tile_128"] == 128 and RESERVE_MIB == 4607 and HARD_MIB == 28000
        print(json.dumps({"pass": True, "configs": CONFIGS, "comparison_keys": ["latent", "raw_32ch", "head_14ch", "geometry", "groups"]}))
        return
    if args.summarize_run:
        run = args.summarize_run.resolve()
        prior = json.loads((run / "result.json").read_text())
        if prior.get("status") != "success":
            raise RuntimeError("--summarize-run requires a successful completed run")
        stage = Path(prior["staging_dir"])
        results = {oid: {label: stage / oid / label for label, _ in CONFIGS} for oid in SAMPLES}
        for configs in results.values():
            for root in configs.values():
                for required in (root / "sampling/sampled_latents.pt", root / "mesh/mesh_physics_raw.pt",
                                 root / "mesh/mesh.obj", root / "audit/official_result.json",
                                 root / "audit/vertex_physics_14ch.pt"):
                    if not required.is_file():
                        raise RuntimeError(f"completed comparison output missing: {required}")
        output = run / "sensitivity_result_recomputed_v2.json"
        if output.exists():
            raise RuntimeError(f"refusing to overwrite recomputed comparison: {output}")
        compare(results, output)
        print(json.dumps({"status": "summarized", "output": str(output)}))
        return
    for sample in SAMPLES.values():
        for path in sample.values():
            if not path.is_file():
                raise RuntimeError(f"required saved input/GT file is missing: {path}")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    run_parent = ROOT / "logs/rtx5090-tile-sensitivity"
    run_parent.mkdir(parents=True, exist_ok=True)
    run = run_parent / run_id
    stage = ROOT / "staging" / ("rtx5090-tile-sensitivity-" + run_id)
    # Runner owns creation of the unique run/staging pair.  Do not pre-create
    # either path: a pre-existing path is an evidence-preservation failure.
    if run.exists() or stage.exists():
        raise RuntimeError(f"refusing to reuse existing run/staging path: {run} / {stage}")
    with (run_parent / ".runner.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        r = common.Runner(run, stage)
        env = common.cuda_env(run)
        env.update(PHYSX_OUTPUT_TILE_ENABLE="1", PHYSX_STREAMING_GROUPNORM_ENABLE="1",
                   PHYSX_STREAMING_GROUPNORM_CHUNK_ROWS="16384", PHYSX_GPU_RESERVE_MIB=str(RESERVE_MIB))
        results: dict[str, dict[str, Path]] = {}
        step_number = 0
        try:
            def source_preflight(directory):
                source = common.source_guard(); checkpoints = common.checkpoint_guard(); gpu = common.gpu_guard()
                common.write_json(directory / "source_guard.json", source)
                common.write_json(directory / "checkpoint_guard.json", checkpoints)
                common.write_json(directory / "gpu_preflight.json", gpu)
                return [directory / "source_guard.json", directory / "checkpoint_guard.json", directory / "gpu_preflight.json"], gpu
            step_number += 1
            r.step(step_number, "shared_preflight", fingerprint(common.HEAD, sha(common.MANIFEST)), source_preflight)
            for oid, paths in SAMPLES.items():
                results[oid] = {}
                for label, tile in CONFIGS:
                    root = stage / oid / label
                    sampling, physics, mesh, audit = root / "sampling", root / "physics/physics_cache.pt", root / "mesh", root / "audit"
                    local = {**env, "PHYSX_TILE_CHANNELS": str(tile)}
                    def sampling_action(directory, sampling=sampling, local=local, paths=paths, tile=tile):
                        common.write_json(directory / "gpu_preflight.json", common.gpu_guard())
                        r.child(directory, [PY, ADAPTER / "sample_latents_only.py", "--source", SRC, "--input", paths["input"], "--output", sampling, "--report", directory / "sampling_report.json", "--seed", "1"], env=local, cwd=SRC, gpu=True)
                        return [sampling / "sampled_latents.pt", sampling / "preprocessed.png", directory / "sampling_report.json"], {"seed": 1, "tile_channels": tile}
                    step_number += 1
                    r.step(step_number, f"{oid}_{label}_sampling", fingerprint(sha(paths["input"]), sha(ADAPTER / "sample_latents_only.py"), tile, 1), sampling_action)
                    def physics_action(directory, sampling=sampling, physics=physics, local=local):
                        common.write_json(directory / "gpu_preflight.json", common.gpu_guard())
                        guard_from_latent(sampling / "sampled_latents.pt", directory / "proactive_memory_guard.json")
                        physics.parent.mkdir(parents=True, exist_ok=False)
                        r.child(directory, [PY, ADAPTER / "decode_cached_split.py", "physics", "--latent", sampling / "sampled_latents.pt", "--source", SRC, "--output", physics, "--report", directory / "physics.json"], env=local, cwd=SRC, gpu=True)
                        return [physics, directory / "physics.json", directory / "proactive_memory_guard.json"], {"separate_child": True}
                    step_number += 1
                    r.step(step_number, f"{oid}_{label}_physics", fingerprint(sha(sampling / "sampled_latents.pt"), sha(ADAPTER / "decode_cached_split.py"), tile), physics_action)
                    def mesh_action(directory, sampling=sampling, physics=physics, mesh=mesh, local=local):
                        common.write_json(directory / "gpu_preflight.json", common.gpu_guard())
                        guard_from_latent(sampling / "sampled_latents.pt", directory / "proactive_memory_guard.json")
                        r.child(directory, [PY, ADAPTER / "decode_cached_split.py", "mesh", "--latent", sampling / "sampled_latents.pt", "--physics-cache", physics, "--source", SRC, "--output", mesh, "--report", directory / "mesh.json"], env=local, cwd=SRC, gpu=True)
                        return [mesh / "mesh_physics_raw.pt", mesh / "mesh.obj", directory / "mesh.json", directory / "proactive_memory_guard.json"], {"separate_child": True}
                    step_number += 1
                    r.step(step_number, f"{oid}_{label}_mesh", fingerprint(sha(physics), sha(ADAPTER / "decode_cached_split.py"), tile), mesh_action)
                    def audit_action(directory, audit=audit, mesh=mesh, paths=paths):
                        return audit_command(r, directory, mesh, paths["gt"], audit)
                    step_number += 1
                    r.step(step_number, f"{oid}_{label}_audit", fingerprint(sha(mesh / "mesh_physics_raw.pt"), sha(paths["gt"])), audit_action)
                    results[oid][label] = root
            compare(results, run / "sensitivity_result.json")
            r.result.update(status="success", reason=None, stage="complete", child_exit_code=0); r.save()
        except BaseException as exc:
            r.result.update(status="failed", reason=f"{type(exc).__name__}: {exc}"); r.save(); raise
    print(json.dumps({"status": "success", "run": str(run), "staging": str(stage)}))


if __name__ == "__main__":
    main()
