#!/usr/bin/env python3
"""Decode one verified public-only sampling run in isolated GPU children.

This contains no sampling or preprocessing.  It consumes a successful
``run_articulated_sampling_candidates`` run, validates all six source-stage
markers and hashes, then runs physics and mesh decoding in separate children.
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

ROOT, SRC, PY, ADAPTER = common.ROOT, common.SRC, common.PY, common.ADAPTER
HARD_LIMIT_MIB, RESERVE_MIB = 28000, 4607


def sha(path): return common.sha(Path(path))
def write_json(path, data): common.write_json(Path(path), data)
def fingerprint(*values):
    digest = hashlib.sha256()
    for value in values:
        digest.update(str(value).encode()); digest.update(b"\0")
    return digest.hexdigest()


def source_paths(source_run: Path):
    result = json.loads((source_run / "result.json").read_text())
    object_id = str(result.get("object_id", ""))
    if result.get("status") != "success" or not object_id.isdigit():
        raise RuntimeError("source sampling run is not a successful object run")
    source_stage = Path(result["staging_dir"])
    latent = source_stage / "sampling/sampled_latents.pt"
    gt = source_stage / f"work/physxnet/finaljson/{object_id}.json"
    gate_path = source_run / "steps/06_sampling_only_and_decoder_gate/decoder_eligibility.json"
    return object_id, source_stage, latent, gt, gate_path


def verify_source_run(source_run: Path):
    object_id, source_stage, latent, gt, gate_path = source_paths(source_run)
    checked = []
    for number in range(1, 7):
        matches = list((source_run / "steps").glob(f"{number:02d}_*/SUCCESS.json"))
        if len(matches) != 1:
            raise RuntimeError(f"source stage {number} SUCCESS marker missing or ambiguous")
        marker = json.loads(matches[0].read_text())
        for row in marker.get("outputs", []):
            path = Path(row["path"])
            if not path.is_file() or path.stat().st_size != row["bytes"] or sha(path) != row["sha256"]:
                raise RuntimeError(f"source stage {number} output hash mismatch: {path}")
        checked.append({"stage": number, "marker": str(matches[0]), "outputs": len(marker["outputs"])})
    gate = json.loads(gate_path.read_text())
    if not gate.get("decoder_eligible_under_current_policy"):
        raise RuntimeError(f"decoder gate did not approve this latent: {gate}")
    if not latent.is_file() or not gt.is_file():
        raise RuntimeError("verified sampling latent or GT JSON missing")
    return {"object_id": object_id, "source_stage": str(source_stage), "verified_stages": checked,
            "gate": gate, "latent": str(latent), "latent_sha256": sha(latent), "gt": str(gt), "gt_sha256": sha(gt)}


def proactive_guard(gpu, gate):
    peak = float(gate["gate_peak_with_uncertainty_mib"])
    required_free = peak + RESERVE_MIB
    report = {"physical_gpu": gpu, "expected_peak_with_uncertainty_mib": peak,
              "hard_limit_mib": HARD_LIMIT_MIB, "reserve_mib": RESERVE_MIB,
              "required_free_before_mib": required_free, "free_before_mib": gpu["free_mib"],
              "pass": peak <= HARD_LIMIT_MIB and gpu["free_mib"] >= required_free}
    if not report["pass"]:
        raise RuntimeError(f"proactive decoder memory guard failed: {report}")
    return report


def execute(run: Path, stage: Path, source_run: Path, resume: bool):
    manifest = verify_source_run(source_run)
    object_id, latent, gt = manifest["object_id"], Path(manifest["latent"]), Path(manifest["gt"])
    r = common.Runner(run, stage, resume=resume)
    env = common.cuda_env(run)
    env.update(PHYSX_OUTPUT_TILE_ENABLE="1", PHYSX_STREAMING_GROUPNORM_ENABLE="1",
               PHYSX_STREAMING_GROUPNORM_CHUNK_ROWS="16384", PHYSX_GPU_RESERVE_MIB=str(RESERVE_MIB))
    try:
        def s1(directory):
            gpu = common.gpu_guard(); guard = proactive_guard(gpu, manifest["gate"])
            write_json(directory / "source_run_manifest.json", manifest)
            write_json(directory / "proactive_memory_guard.json", guard)
            return [directory / "source_run_manifest.json", directory / "proactive_memory_guard.json", latent, gt], {"reused_source_stages": [1,2,3,4,5,6], "gpu": gpu}
        r.step(1, "reuse_sampling_and_memory_gate", fingerprint(manifest["latent_sha256"], manifest["gt_sha256"], manifest["gate"]), s1)

        def s2(directory):
            gpu = common.gpu_guard(); write_json(directory / "gpu_preflight.json", gpu); proactive_guard(gpu, manifest["gate"])
            r.child(directory, [PY, ADAPTER / "validate_candidate.py", "gpu"], env={**env, "PHYSX_TILE_ENABLE":"0"}, gpu=True, log_prefix="input_tiling")
            r.child(directory, [PY, ADAPTER / "validate_decoder_adapters.py"], env=env, gpu=True, log_prefix="output_norm")
            return [directory / "input_tiling.stdout.log", directory / "output_norm.stdout.log"], {"equivalence":"mandatory GPU checks passed"}
        r.step(2, "mandatory_small_gpu_equivalence", fingerprint(sha(ADAPTER / "validate_candidate.py"), sha(ADAPTER / "validate_decoder_adapters.py"), sha(ADAPTER / "channel_tiled_spconv.py"), sha(ADAPTER / "output_channel_tiled_spconv.py"), sha(ADAPTER / "memory_bounded_groupnorm.py")), s2)

        physics = stage / "physics/physics_cache.pt"
        def s3(directory):
            gpu = common.gpu_guard(); write_json(directory / "gpu_preflight.json", gpu); write_json(directory / "proactive_memory_guard.json", proactive_guard(gpu, manifest["gate"]))
            physics.parent.mkdir(parents=True, exist_ok=False)
            r.child(directory, [PY, ADAPTER / "decode_cached_split.py", "physics", "--latent", latent, "--source", SRC, "--output", physics, "--report", directory / "physics_report.json"], env=env, cwd=SRC, gpu=True)
            if not physics.is_file(): raise RuntimeError("physics cache missing")
            return [physics, directory / "physics_report.json"], {"separate_child":True}
        r.step(3, "physics_decoder_child", fingerprint(manifest["latent_sha256"], sha(SRC / "pretrain/diffusion/ckpts_new/property_decoder_step0100000.pt"), sha(ADAPTER / "decode_cached_split.py")), s3)

        mesh = stage / "mesh"
        def s4(directory):
            gpu = common.gpu_guard(); write_json(directory / "gpu_preflight.json", gpu); write_json(directory / "proactive_memory_guard.json", proactive_guard(gpu, manifest["gate"]))
            r.child(directory, [PY, ADAPTER / "decode_cached_split.py", "mesh", "--latent", latent, "--physics-cache", physics, "--source", SRC, "--output", mesh, "--report", directory / "mesh_report.json"], env=env, cwd=SRC, gpu=True)
            raw, obj = mesh / "mesh_physics_raw.pt", mesh / "mesh.obj"
            if not raw.is_file() or not obj.is_file(): raise RuntimeError("mesh outputs missing")
            return [raw, obj, directory / "mesh_report.json"], {"separate_child":True}
        r.step(4, "mesh_decoder_child", fingerprint(sha(physics), sha(SRC / "pretrain/diffusion/ckpts_new/decoder_step0100000.pt"), sha(ADAPTER / "decode_cached_split.py")), s4)

        audit = stage / "articulation_audit"
        def s5(directory):
            audit_env = os.environ.copy(); audit_env.update(CUDA_VISIBLE_DEVICES="", PYTHONDONTWRITEBYTECODE="1")
            r.child(directory, [PY, "-B", ADAPTER / "verify_articulated_output.py", "--raw", mesh / "mesh_physics_raw.pt", "--mesh", mesh / "mesh.obj", "--gt", gt, "--head", SRC / "pretrain/diffusion/ckpts_new/property_output_step0100000.pt", "--output", audit], env=audit_env)
            outputs = [audit / name for name in ("official_result.json", "indexing_correction_candidate.json", "gt_annotation.json", "input_hashes.json", "vertex_physics_14ch.pt")]
            return outputs, {"scope":"GT group/type/parent structural comparison only; no description, 30-view PSNR, density or affordance accuracy"}
        r.step(5, "cpu_gt_structure_audit", fingerprint(sha(mesh / "mesh_physics_raw.pt"), sha(gt), sha(ADAPTER / "verify_articulated_output.py")), s5)
        r.result.update(status="success", reason=None, stage="complete", child_exit_code=0); r.save()
    except BaseException as exc:
        r.result.update(status="failed", reason=f"{type(exc).__name__}: {exc}"); r.save(); raise
    return {"object_id":object_id, "run_dir":str(run), "staging_dir":str(stage), "status":"success"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    if args.plan:
        print(json.dumps(verify_source_run(args.source_run.resolve()), indent=2)); return
    source_run = args.source_run.resolve()
    object_id, _, _, _, _ = source_paths(source_run)
    if args.resume:
        run = args.resume.resolve(); previous = json.loads((run / "result.json").read_text()); stage = Path(previous["staging_dir"])
        if previous.get("status") not in ("failed", "interrupted", "not_run"): raise SystemExit("--resume requires unfinished decoder run")
        resume = True
    else:
        root = ROOT / "logs/public-only-v1-extension-decoder" / object_id; root.mkdir(parents=True, exist_ok=True)
        with open(root / ".runner.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            rid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
            run, stage, resume = root / rid, ROOT / f"staging/public-only-v1-extension-decoder-{object_id}-{rid}", False
            result = execute(run, stage, source_run, resume)
            print(json.dumps(result, ensure_ascii=False)); return
    result = execute(run, stage, source_run, resume)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__": main()
