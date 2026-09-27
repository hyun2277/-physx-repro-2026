#!/usr/bin/env python3
"""Run bounded numerical fidelity checks without sampling a new PhysXGen output."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/minsujo/Desktop/SH/PHYSx")
REPO = ROOT / "repro-records"
SRC = ROOT / "sources/physx-4f54e750a309"
ADAPTER = REPO / "04_PhysX-3D/01_재현실행/자료확보/rtx5090_adapter"
PY = ROOT / "envs/physxgen/bin/python"
LATENT = ROOT / "logs/rtx5090-adapter-29354/20260926T192709Z-db921ba64aaa/sampled_latents.pt"
REFERENCE = ROOT / "staging/rtx5090-cached-decoder-29354-20260926T194524Z-d69f74359b60/mesh_physics_raw.pt"
CUDA_HELPER = REPO / "04_PhysX-3D/01_재현실행/실행스크립트/cuda_jit_environment.sh"
TOOLKIT = ROOT / "toolchains/cuda-12.8.1"
EXPECTED_HEAD = "4f54e750a309fe9cd9f20816916ecc0e8a9ae594"
HARD_LIMIT_MIB, RESERVE_MIB = 28000, 4607


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def command(args, env=None, cwd=None, stdout=None, stderr=None):
    return subprocess.Popen([str(x) for x in args], env=env, cwd=cwd, stdout=stdout, stderr=stderr, start_new_session=True)


def gpu_guard():
    rows = subprocess.check_output(["nvidia-smi", "--query-gpu=index,uuid,memory.total,memory.free", "--format=csv,noheader,nounits"], text=True).splitlines()
    matches = [[x.strip() for x in row.split(",")] for row in rows if row.split(",")[0].strip() == "1"]
    if len(matches) != 1: raise RuntimeError("GPU 1 missing or ambiguous")
    index, gpu_uuid, total, free = matches[0]
    apps = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid,gpu_uuid,used_memory", "--format=csv,noheader,nounits"], text=True)
    if any(len(p := row.split(",")) >= 2 and p[1].strip() == gpu_uuid for row in apps.splitlines()):
        raise RuntimeError("GPU 1 has a compute process")
    return {"index": int(index), "uuid": gpu_uuid, "total_mib": int(total), "free_mib": int(free)}


def cuda_env(run: Path, gpu_uuid: str) -> dict:
    raw = subprocess.check_output(["bash", "-c", 'source "$1"; cuda_jit_prepare "$2" "$3" /usr/bin/gcc-12 /usr/bin/g++-12; env -0', "bash", str(CUDA_HELPER), str(run), str(TOOLKIT)])
    env = {k.decode(): v.decode() for item in raw.split(b"\0") if item for k, v in [item.split(b"=", 1)]}
    env.update(CUDA_VISIBLE_DEVICES=gpu_uuid, SPCONV_ALGO="native", PHYSX_TILE_ENABLE="1",
               PHYSX_OUTPUT_TILE_ENABLE="1", PHYSX_STREAMING_GROUPNORM_ENABLE="1",
               PHYSX_STREAMING_GROUPNORM_CHUNK_ROWS="16384", PHYSX_GPU_RESERVE_MIB=str(RESERVE_MIB),
               PYTHONPATH=f"{ADAPTER}:{SRC}" + (f":{os.environ['PYTHONPATH']}" if os.environ.get("PYTHONPATH") else ""),
               HOME=str(run / "home"), XDG_CACHE_HOME=str(ROOT / "cache"), TORCH_HOME=str(ROOT / "cache/torch"),
               HF_HOME=str(ROOT / "cache/huggingface"), PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
    return env


def monitored_child(label, argv, env, run, timeout=1800):
    stdout, stderr = run / f"{label}.stdout.log", run / f"{label}.stderr.log"
    with stdout.open("w") as out, stderr.open("w") as err:
        child = command(argv, env=env, cwd=SRC, stdout=out, stderr=err)
        peak = 0; samples = [] ; started = time.monotonic()
        while child.poll() is None:
            if time.monotonic() - started > timeout:
                os.killpg(child.pid, signal.SIGTERM); raise RuntimeError(f"{label}: timeout")
            query = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,gpu_uuid,used_memory", "--format=csv,noheader,nounits"], capture_output=True, text=True)
            if query.returncode: os.killpg(child.pid, signal.SIGTERM); raise RuntimeError(f"{label}: GPU monitor failed")
            used = 0
            for row in query.stdout.splitlines():
                cols = [x.strip() for x in row.split(",")]
                if len(cols) >= 3 and cols[1] == env["CUDA_VISIBLE_DEVICES"] and cols[2].isdigit(): used = max(used, int(cols[2]))
            peak = max(peak, used); samples.append({"utc": datetime.now(timezone.utc).isoformat(), "used_mib": used})
            if used > HARD_LIMIT_MIB:
                os.killpg(child.pid, signal.SIGTERM); raise RuntimeError(f"{label}: {used} MiB exceeds hard limit {HARD_LIMIT_MIB}")
            time.sleep(1)
        rc = child.wait()
    (run / f"{label}.gpu_usage.json").write_text(json.dumps({"peak_observed_mib": peak, "samples": samples}, indent=2) + "\n")
    if rc: raise RuntimeError(f"{label}: child exited {rc}; see {stderr}")
    return {"returncode": rc, "peak_observed_mib": peak, "stdout": str(stdout), "stderr": str(stderr)}


def source_guard():
    if subprocess.check_output(["git", "-C", str(SRC), "rev-parse", "HEAD"], text=True).strip() != EXPECTED_HEAD:
        raise RuntimeError("source HEAD mismatch")
    for file in (LATENT, REFERENCE, PY, ADAPTER / "adapter_fidelity_worker.py", ADAPTER / "decode_cached_split.py", ADAPTER / "decode_cached_29354.py"):
        if not file.is_file() or not file.stat().st_size: raise RuntimeError(f"missing required file: {file}")


def coverage() -> dict:
    paths = {
        "channel_tiled_large": ROOT / "logs/rtx5090-adapter-29354/20260926T192709Z-db921ba64aaa/example.stdout.log",
        "29354_decoder": ROOT / "logs/rtx5090-cached-decoder-29354/20260926T194524Z-d69f74359b60/decoder.stdout.log",
        "24566_decoder": ROOT / "logs/articulated-decoder/24566/20260926T221319Z-a9491be93452/steps/03_physics_decoder_child/stdout.log",
        "29806_decoder": ROOT / "logs/articulated-decoder/29806/20260927T050730Z-8271ccb5f82b/steps/03_physics_decoder_child/stdout.log",
    }
    out = {}
    for label, path in paths.items():
        text = path.read_text(errors="replace") if path.is_file() else ""
        out[label] = {"path": str(path), "exists": path.is_file(),
                      "channel_tiled_subm": "channel_tiled_subm" in text,
                      "output_tiled": "input_output_channel_tiled_subm" in text,
                      "memory_bounded_groupnorm": "memory_bounded_sparse_groupnorm32" in text}
    return out


def main():
    source_guard()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    run = ROOT / "logs/rtx5090-adapter-fidelity" / run_id; run.mkdir(parents=True, exist_ok=False)
    result = {"run_id": run_id, "status": "running", "scope": "adapter fidelity only; no image sampling or evaluation",
              "source_head": EXPECTED_HEAD, "hard_limit_mib": HARD_LIMIT_MIB, "reserve_mib": RESERVE_MIB,
              "legacy_sequential_raw": {"path": str(REFERENCE), "sha256": sha(REFERENCE)},
              "latent": {"path": str(LATENT), "sha256": sha(LATENT)}, "coverage_before": coverage()}
    try:
        gpu = gpu_guard()
        if gpu["free_mib"] < RESERVE_MIB + 4096: raise RuntimeError("GPU 1 cannot retain reserve before fidelity suite")
        result["gpu"] = gpu; env = cuda_env(run, gpu["uuid"])
        (run / "environment.json").write_text(json.dumps({k: env[k] for k in ("CUDA_VISIBLE_DEVICES", "CUDA_HOME", "CUDACXX", "CC", "CXX", "CUDAHOSTCXX", "NVCC_CCBIN", "SPCONV_ALGO", "PHYSX_TILE_ENABLE", "PHYSX_OUTPUT_TILE_ENABLE", "PHYSX_STREAMING_GROUPNORM_ENABLE", "PHYSX_STREAMING_GROUPNORM_CHUNK_ROWS", "PHYSX_GPU_RESERVE_MIB", "PYTHONPATH")}, indent=2) + "\n")
        probe = run / "operation_metrics.json"
        result["operation_probe"] = monitored_child("01_operations", [PY, ADAPTER / "adapter_fidelity_worker.py", "operations", "--source", SRC, "--latent", LATENT, "--output", probe], {**env, "PHYSX_TILE_ENABLE": "0"}, run)
        single_output = run / "single_process_mesh"
        result["single_process_control"] = monitored_child("02_single_process", [PY, ADAPTER / "decode_cached_29354.py", "--latent", LATENT, "--source", SRC, "--output", single_output, "--report", run / "single_process_report.json"], env, run)
        intermediate = run / "physics_cache.pt"; split_output = run / "split_mesh"
        result["physics_child"] = monitored_child("03_physics_child", [PY, ADAPTER / "decode_cached_split.py", "physics", "--latent", LATENT, "--source", SRC, "--output", intermediate, "--report", run / "physics_report.json"], env, run)
        result["mesh_child"] = monitored_child("04_mesh_child", [PY, ADAPTER / "decode_cached_split.py", "mesh", "--latent", LATENT, "--physics-cache", intermediate, "--source", SRC, "--output", split_output, "--report", run / "mesh_report.json"], env, run)
        comparison = run / "child_process_comparison.json"
        result["child_process_comparison"] = monitored_child("05_compare", [PY, ADAPTER / "adapter_fidelity_worker.py", "compare-artifacts", "--source", SRC, "--reference", single_output / "mesh_physics_raw.pt", "--candidate", split_output / "mesh_physics_raw.pt", "--output", comparison], {**env, "CUDA_VISIBLE_DEVICES": ""}, run, timeout=300)
        result["coverage_after"] = coverage(); result["status"] = "success"; result["judgement"] = "locally_numerically_equivalent_on_tested_cases"
    except BaseException as exc:
        result["status"] = "failed"; result["judgement"] = "partially_verified"; result["reason"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        result["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (run / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"status": result["status"], "judgement": result["judgement"], "run": str(run)}, sort_keys=True), flush=True)


if __name__ == "__main__": main()
