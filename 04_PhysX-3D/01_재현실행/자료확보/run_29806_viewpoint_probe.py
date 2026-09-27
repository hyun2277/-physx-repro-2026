#!/usr/bin/env python3
"""One controlled, qualitative 000-versus-006 probe for object 29806.

The runner reuses the successful existing 24-view conditioning render.  It
does not extract data, retrieve texture, or invoke Blender.  It runs each
input through a fresh sampling child followed by separate physics and mesh
decoder children, then audits both results with the same official grouping
formula.  It is deliberately not a paper evaluation runner.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_27281_articulated_pipeline as common
from run_articulated_sampling_candidates import latent_schema_and_estimate

ROOT, SRC, PY, ADAPTER = common.ROOT, common.SRC, common.PY, common.ADAPTER
OBJECT = "29806"
SOURCE_RUN = ROOT / "logs/articulated-sampling-only/29806/20260926T220010Z-ac2c1dfab94d"
SOURCE_STAGE = ROOT / "staging/articulated-sampling-29806-20260926T220010Z-ac2c1dfab94d"
VIEWS = SOURCE_STAGE / "datasets/PhysXNet/renders_cond/29806_"
GT = SOURCE_STAGE / "work/physxnet/finaljson/29806.json"
SEED = 1
FRAMES = {
    "000": "ecc444a491dd490412acafcb93ab77b9b8ef03ded976b37e691da03e7c9cf6ea",
    "006": "89f691cce979ae2b7e86929c60541d69b1c37da7c77d7a521eca0a2b0cc7782b",
}
HARD_LIMIT_MIB, RESERVE_MIB = 28000, 4607


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(path: Path) -> str:
    return common.sha(Path(path))


def write_json(path: Path, value: object) -> None:
    common.write_json(Path(path), value)


def fingerprint(*values: object) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(str(value).encode())
        digest.update(b"\0")
    return digest.hexdigest()


def marker_output(marker: dict, filename: str) -> Path:
    """Return one recorded output by basename, never by constructed step path."""
    matches = [Path(row["path"]) for row in marker.get("outputs", []) if Path(row.get("path", "")).name == filename]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {filename} in step marker, found {len(matches)}")
    path = matches[0]
    if not path.is_file():
        raise RuntimeError(f"recorded step output is missing: {path}")
    return path


def verify_marker(marker: Path) -> dict:
    data = json.loads(marker.read_text())
    if data.get("status") != "success":
        raise RuntimeError(f"source stage is not successful: {marker}")
    for row in data.get("outputs", []):
        path = Path(row["path"])
        if not path.is_file() or path.stat().st_size != row["bytes"] or sha(path) != row["sha256"]:
            raise RuntimeError(f"source output hash mismatch: {path}")
    return {"marker": str(marker), "input_fingerprint": data.get("input_fingerprint"), "outputs": len(data.get("outputs", []))}


def reused_conditioning_manifest() -> dict:
    result = json.loads((SOURCE_RUN / "result.json").read_text())
    if result.get("status") != "success" or result.get("object_id") != OBJECT:
        raise RuntimeError("29806 source sampling run is not a successful 29806 run")
    stages = []
    for number in range(1, 6):
        found = list((SOURCE_RUN / "steps").glob(f"{number:02d}_*/SUCCESS.json"))
        if len(found) != 1:
            raise RuntimeError(f"source stage {number} SUCCESS marker missing/ambiguous")
        stages.append(verify_marker(found[0]))
    sampling_report = SOURCE_RUN / "steps/06_sampling_only_and_decoder_gate/sampling_report.json"
    command = SOURCE_RUN / "steps/06_sampling_only_and_decoder_gate/command.json"
    report = json.loads(sampling_report.read_text())
    command_doc = json.loads(command.read_text())
    if report.get("status") != "success" or report.get("seed") != SEED:
        raise RuntimeError(f"existing seed record is not the required seed {SEED}")
    if command_doc.get("argv", [])[-1:] != [str(SEED)]:
        raise RuntimeError("existing sampling command does not record --seed 1")
    transforms = VIEWS / "transforms.json"
    doc = json.loads(transforms.read_text())
    frames = doc.get("frames")
    if not isinstance(frames, list) or len(frames) != 24:
        raise RuntimeError("existing conditioning render does not have exactly 24 frames")
    by_name = {frame.get("file_path"): frame for frame in frames if isinstance(frame, dict)}
    selected = {}
    for label, expected in FRAMES.items():
        name = f"{label}.png"
        image = VIEWS / name
        matrix = by_name.get(name, {}).get("transform_matrix")
        if not image.is_file() or sha(image) != expected:
            raise RuntimeError(f"conditioning input hash mismatch: {image}")
        if not (isinstance(matrix, list) and len(matrix) == 4 and all(isinstance(row, list) and len(row) == 4 for row in matrix)):
            raise RuntimeError(f"missing 4x4 camera transform for {name}")
        selected[label] = {"path": str(image), "sha256": expected, "frame": by_name[name]}
    return {
        "source_sampling_run": str(SOURCE_RUN),
        "source_staging": str(SOURCE_STAGE),
        "verified_source_stages_1_to_5": stages,
        "existing_sampling_seed": SEED,
        "existing_sampling_command": command_doc,
        "existing_sampling_report": report,
        "transforms": {"path": str(transforms), "sha256": sha(transforms), "frame_count": 24},
        "probe_inputs": selected,
    }


def proactive_guard(gpu: dict, gate: dict) -> dict:
    required = gate["gate_peak_with_uncertainty_mib"] + RESERVE_MIB
    report = {
        "physical_gpu": gpu,
        "expected_peak_with_uncertainty_mib": gate["gate_peak_with_uncertainty_mib"],
        "hard_limit_mib": HARD_LIMIT_MIB,
        "reserve_mib": RESERVE_MIB,
        "required_free_before_mib": required,
        "free_before_mib": gpu["free_mib"],
        "pass": gate["gate_peak_with_uncertainty_mib"] <= HARD_LIMIT_MIB and gpu["free_mib"] >= required,
    }
    if not report["pass"]:
        raise RuntimeError(f"proactive decoder memory guard failed: {report}")
    return report


def env_for(run: Path) -> dict:
    env = common.cuda_env(run)
    env.update(
        PHYSX_OUTPUT_TILE_ENABLE="1",
        PHYSX_STREAMING_GROUPNORM_ENABLE="1",
        PHYSX_STREAMING_GROUPNORM_CHUNK_ROWS="16384",
        PHYSX_GPU_RESERVE_MIB=str(RESERVE_MIB),
    )
    return env


def compare(frame_outputs: dict, output: Path, manifest: dict) -> None:
    rows = {}
    for label, values in frame_outputs.items():
        official = json.loads((values["audit"] / "official_result.json").read_text())
        groups = official["groups"]
        rows[label] = {
            "input": manifest["probe_inputs"][label],
            "seed": SEED,
            "raw_sha256": sha(values["raw"]),
            "mesh_sha256": sha(values["mesh"]),
            "property_head_sha256": sha(values["audit"] / "vertex_physics_14ch.pt"),
            "official_num_group": official["predicted_num_group"],
            "gt_num_group": official["gt_num_group"],
            "groups": {
                group: {key: value for key, value in item.items() if key in (
                    "vertex_count", "majority_face_count", "majority_area", "components")}
                for group, item in groups.items()
            },
            "limits": "No generated-vertex to GT-part correspondence; parent/direction/position/range accuracy omitted.",
        }
    write_json(output, {
        "scope": "same-seed, single-input-view qualitative probe; not official paper evaluation or general performance evidence",
        "object_id": OBJECT,
        "seed": SEED,
        "frames": rows,
        "shared_conditions": {
            "checkpoint_manifest": common.checkpoint_guard(),
            "source_head": common.source_guard(),
            "physical_gpu": 1,
            "spconv_algo": "native",
            "cuda_overlay": "per-run CUDA 12.8.1 overlay with GCC/G++ 12",
            "adapters": ["input channel tiling", "output channel tiling", "memory-bounded GroupNorm"],
            "sampled_monitor_limit_mib": HARD_LIMIT_MIB,
            "reserve_mib": RESERVE_MIB,
        },
    })


def execute(run: Path, stage: Path, resume: bool) -> None:
    runner = common.Runner(run, stage, resume=resume)
    manifest = reused_conditioning_manifest()
    env = env_for(run)
    frame_outputs: dict[str, dict] = {}
    try:
        def stage_one(directory: Path):
            write_json(directory / "source_conditioning_manifest.json", manifest)
            return [directory / "source_conditioning_manifest.json", GT], {"reused": "existing stages 1-5 and 24-view render"}
        runner.step(1, "reuse_29806_conditioning_and_seed_record", fingerprint(json.dumps(manifest, sort_keys=True), sha(GT)), stage_one)

        def stage_two(directory: Path):
            gpu = common.gpu_guard()
            write_json(directory / "gpu_preflight.json", gpu)
            runner.child(directory, [PY, ADAPTER / "validate_candidate.py", "gpu"], env={**env, "PHYSX_TILE_ENABLE": "0"}, gpu=True, log_prefix="input_tiling")
            runner.child(directory, [PY, ADAPTER / "validate_decoder_adapters.py"], env=env, gpu=True, log_prefix="output_norm")
            return [directory / "input_tiling.stdout.log", directory / "output_norm.stdout.log"], {"equivalence": "mandatory small GPU checks passed"}
        runner.step(2, "mandatory_native_adapter_equivalence", fingerprint(sha(ADAPTER / "validate_candidate.py"), sha(ADAPTER / "validate_decoder_adapters.py"), sha(ADAPTER / "channel_tiled_spconv.py"), sha(ADAPTER / "output_channel_tiled_spconv.py"), sha(ADAPTER / "memory_bounded_groupnorm.py")), stage_two)

        for label in FRAMES:
            image = VIEWS / f"{label}.png"
            sampling = stage / f"frame_{label}" / "sampling"
            physics_cache = stage / f"frame_{label}" / "physics" / "physics_cache.pt"
            mesh_out = stage / f"frame_{label}" / "mesh"
            audit = stage / f"frame_{label}" / "articulation_audit"

            def sample_action(directory: Path, image=image, sampling=sampling, label=label):
                gpu = common.gpu_guard(); write_json(directory / "gpu_preflight.json", gpu)
                runner.child(directory, [PY, ADAPTER / "sample_latents_only.py", "--source", SRC, "--input", image, "--output", sampling, "--report", directory / "sampling_report.json", "--seed", str(SEED)], env=env, cwd=SRC, gpu=True)
                latent = sampling / "sampled_latents.pt"
                if not latent.is_file(): raise RuntimeError(f"{label}: sampling latent missing")
                return [latent, sampling / "preprocessed.png", directory / "sampling_report.json"], {"frame": label, "input_sha256": sha(image), "seed": SEED}
            runner.step(3 if label == "000" else 8, f"sampling_{label}", fingerprint(sha(image), SEED, common.HEAD, sha(ADAPTER / "sample_latents_only.py")), sample_action)

            latent = sampling / "sampled_latents.pt"
            def gate_action(directory: Path, latent=latent, label=label):
                estimate = latent_schema_and_estimate(latent, directory / "decoder_eligibility.json")
                if not estimate["decoder_eligible_under_current_policy"]:
                    raise RuntimeError(f"{label}: decoder prohibited by current reserve policy: {estimate}")
                return [directory / "decoder_eligibility.json"], {"frame": label, "rows_N": estimate["rows_N"], "N_x_64": estimate["maximum_subdivision_points_N_x_64"]}
            gate_marker = runner.step(4 if label == "000" else 9, f"decoder_gate_{label}", fingerprint(sha(latent), sha(Path(__file__).resolve()), HARD_LIMIT_MIB, RESERVE_MIB), gate_action)
            gate_path = marker_output(gate_marker, "decoder_eligibility.json")
            gate = json.loads(gate_path.read_text())
            def physics_action(directory: Path, latent=latent, physics_cache=physics_cache, gate=gate, label=label):
                gpu = common.gpu_guard(); write_json(directory / "gpu_preflight.json", gpu); write_json(directory / "proactive_memory_guard.json", proactive_guard(gpu, gate))
                physics_cache.parent.mkdir(parents=True, exist_ok=False)
                runner.child(directory, [PY, ADAPTER / "decode_cached_split.py", "physics", "--latent", latent, "--source", SRC, "--output", physics_cache, "--report", directory / "physics_report.json"], env=env, cwd=SRC, gpu=True)
                return [physics_cache, directory / "physics_report.json"], {"frame": label, "separate_child": True}
            runner.step(5 if label == "000" else 10, f"physics_decoder_{label}", fingerprint(sha(latent), sha(SRC / "pretrain/diffusion/ckpts_new/property_decoder_step0100000.pt"), sha(ADAPTER / "decode_cached_split.py")), physics_action)

            def mesh_action(directory: Path, latent=latent, physics_cache=physics_cache, mesh_out=mesh_out, gate=gate, label=label):
                gpu = common.gpu_guard(); write_json(directory / "gpu_preflight.json", gpu); write_json(directory / "proactive_memory_guard.json", proactive_guard(gpu, gate))
                runner.child(directory, [PY, ADAPTER / "decode_cached_split.py", "mesh", "--latent", latent, "--physics-cache", physics_cache, "--source", SRC, "--output", mesh_out, "--report", directory / "mesh_report.json"], env=env, cwd=SRC, gpu=True)
                raw, mesh = mesh_out / "mesh_physics_raw.pt", mesh_out / "mesh.obj"
                if not raw.is_file() or not mesh.is_file(): raise RuntimeError(f"{label}: mesh outputs missing")
                return [raw, mesh, directory / "mesh_report.json"], {"frame": label, "separate_child": True}
            runner.step(6 if label == "000" else 11, f"mesh_decoder_{label}", fingerprint(sha(physics_cache), sha(SRC / "pretrain/diffusion/ckpts_new/decoder_step0100000.pt"), sha(ADAPTER / "decode_cached_split.py")), mesh_action)

            def audit_action(directory: Path, mesh_out=mesh_out, audit=audit, label=label):
                audit_env = {**os.environ, "CUDA_VISIBLE_DEVICES": "", "PYTHONDONTWRITEBYTECODE": "1"}
                runner.child(directory, [PY, "-B", ADAPTER / "verify_articulated_output.py", "--raw", mesh_out / "mesh_physics_raw.pt", "--mesh", mesh_out / "mesh.obj", "--gt", GT, "--head", SRC / "pretrain/diffusion/ckpts_new/property_output_step0100000.pt", "--output", audit], env=audit_env)
                outputs = [audit / name for name in ("official_result.json", "indexing_correction_candidate.json", "gt_annotation.json", "input_hashes.json", "vertex_physics_14ch.pt")]
                return outputs, {"frame": label, "scope": "official grouping plus separate indexing candidate; no GT correspondence assertion"}
            runner.step(7 if label == "000" else 12, f"cpu_articulation_audit_{label}", fingerprint(sha(mesh_out / "mesh_physics_raw.pt"), sha(GT), sha(ADAPTER / "verify_articulated_output.py")), audit_action)
            frame_outputs[label] = {"raw": mesh_out / "mesh_physics_raw.pt", "mesh": mesh_out / "mesh.obj", "audit": audit}

        def comparison_action(directory: Path):
            comparison = directory / "qualitative_probe_comparison.json"
            compare(frame_outputs, comparison, manifest)
            return [comparison], {"scope": "same-seed qualitative input-view probe only"}
        runner.step(13, "same_seed_qualitative_comparison", fingerprint(*(sha(frame_outputs[x]["raw"]) for x in FRAMES), sha(GT), SEED), comparison_action)
        runner.result.update(status="success", reason="same-seed single-input-view qualitative probe complete", stage="complete", child_exit_code=0)
        runner.save()
    except KeyboardInterrupt:
        runner.result.update(status="interrupted", reason="Ctrl+C")
        runner.save()
        raise
    except BaseException as exc:
        runner.result.update(status="failed", reason=f"{type(exc).__name__}: {exc}")
        runner.save()
        raise
    print(f"SUCCESS object={OBJECT} frames=000,006 log={run} staging={stage}")


def self_test() -> dict:
    manifest = reused_conditioning_manifest()
    assert manifest["existing_sampling_seed"] == SEED
    assert set(manifest["probe_inputs"]) == set(FRAMES)
    for label, row in manifest["probe_inputs"].items():
        assert row["sha256"] == FRAMES[label]
        assert Path(row["path"]).name == f"{label}.png"
    gate = {"gate_peak_with_uncertainty_mib": 11268.889}
    safe = {"index": 1, "uuid": "mock", "name": "mock", "total_mib": 32607, "free_mib": 32000}
    assert proactive_guard(safe, gate)["pass"]
    try:
        proactive_guard({**safe, "free_mib": gate["gate_peak_with_uncertainty_mib"] + RESERVE_MIB - 1}, gate)
    except RuntimeError:
        pass
    else:
        raise RuntimeError("unsafe reserve mock accepted")
    import tempfile
    with tempfile.TemporaryDirectory(dir=ROOT / "logs") as tmp:
        base = Path(tmp)
        for label, directory_name in (("000", "04_decoder_gate_000"), ("006", "09_decoder_gate_006")):
            output = base / directory_name / "decoder_eligibility.json"
            output.parent.mkdir(); output.write_text(json.dumps({"frame": label}))
            marker = {"outputs": [{"path": str(output)}]}
            assert marker_output(marker, "decoder_eligibility.json") == output
    return {"reused_24_view_hashes":"PASS", "recorded_seed_1":"PASS", "same_seed_pair":"PASS", "reserve_guard":"PASS", "unsafe_reserve_rejected":"PASS", "marker_output_path_000":"PASS", "marker_output_path_006":"PASS"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--resume", type=Path, help="resume a failed probe run without replacing verified outputs")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), indent=2)); return
    if args.plan:
        print(json.dumps({"object_id": OBJECT, "frames": list(FRAMES), "seed": SEED, "steps": ["reuse and verify existing conditioning", "GPU adapter equivalence", "sampling 000", "gate 000", "physics/mesh/audit 000", "sampling 006", "gate 006", "physics/mesh/audit 006", "CPU comparison"], "not_paper_evaluation": True, "hard_limit_mib": HARD_LIMIT_MIB, "reserve_mib": RESERVE_MIB}, indent=2)); return
    parent = ROOT / "logs/29806-viewpoint-probe"
    parent.mkdir(parents=True, exist_ok=True)
    with (parent / ".runner.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.resume:
            run = args.resume.resolve()
            prior = json.loads((run / "result.json").read_text())
            if prior.get("status") not in ("failed", "interrupted", "not_run"):
                raise SystemExit("--resume accepts only an unfinished probe run")
            execute(run, Path(prior["staging_dir"]), True)
        else:
            rid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
            execute(parent / rid, ROOT / f"staging/29806-viewpoint-probe-{rid}", False)


if __name__ == "__main__":
    main()
