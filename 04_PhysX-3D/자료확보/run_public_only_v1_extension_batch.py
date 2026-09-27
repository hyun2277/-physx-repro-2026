#!/usr/bin/env python3
"""Sequential six-object public-only v1 extension batch.

The selected objects all have directly verified source OBJ/MTL/texture members
inside the already present 04379243 archive.  Sampling is performed first; a
decoder is invoked only after the measured latent gate approves it.  Each
object owns a timestamped sampling and decoder run; object-local failures do
not prevent the next object from being attempted.
"""
from __future__ import annotations

import argparse
import fcntl
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
import run_articulated_sampling_candidates as sampling

ROOT, PY = common.ROOT, common.PY
DECODER = HERE / "run_public_only_cached_decoder.py"
SELECTION = (
    {"object_id":"21356", "movement_type":"fixed", "purpose":"public-only-v1 fixed candidate"},
    {"object_id":"27703", "movement_type":"fixed", "purpose":"public-only-v1 fixed candidate"},
    {"object_id":"30719", "movement_type":"fixed", "purpose":"public-only-v1 fixed candidate"},
    {"object_id":"21314", "movement_type":"fixed", "purpose":"public-only-v1 fixed candidate"},
    {"object_id":"32980", "movement_type":"fixed", "purpose":"public-only-v1 fixed candidate"},
    {"object_id":"23787", "movement_type":"C", "purpose":"public-only-v1 rotation candidate"},
)
EXCLUDED = {"27281": "only B-translation NEEDS_CONDITIONING candidate; existing N=73,024 mesh-decoder OOM evidence exceeds the preserved 28,000 MiB/4,607 MiB policy"}


def now(): return datetime.now(timezone.utc).isoformat()
def write_json(path, value): common.write_json(Path(path), value)


def selection_record():
    """Verify current ZIP members before any write or GPU work."""
    rows = []
    for config in SELECTION:
        official, model = sampling.mapping(config["object_id"])
        parts = sampling.part_members(config["object_id"])
        textures = sampling.texture_members(model)
        rows.append({**config, "finalindex":official, "shapenet_model_id":model,
                     "part_obj_count":len(parts)-1, "shape_texture_member_count":len(textures)-2,
                     "physx_members":common.zip_inventory(sampling.PHYSX_ZIP, parts),
                     "shapenet_members":common.zip_inventory(sampling.SHAPE_ZIP, textures),
                     "selection_reason":"verified current 04379243 ZIP OBJ/MTL/referenced textures; no prior unsafe decoder evidence"})
    return {"protocol":"public-materials-independent-evaluation-v1", "paper_equivalent":False,
            "selection":rows, "excluded":EXCLUDED,
            "balance_note":"no additional safe B-translation candidate exists in the current NEEDS_CONDITIONING manifest; 27281 is excluded by observed unsafe memory evidence; five fixed and one C-rotation candidate remain.",
            "memory_policy":{"hard_limit_mib":28000,"reserve_mib":4607,"decision":"per-object measured sampling latent gate; no decoder begins without approval"}}


def run_child(batch_step: Path, args):
    batch_step.mkdir(parents=True, exist_ok=True)
    (batch_step / "command.json").write_text(json.dumps({"argv":[str(a) for a in args]}, indent=2)+"\n")
    with open(batch_step / "stdout.log", "w") as out, open(batch_step / "stderr.log", "w") as err:
        result = subprocess.run([str(a) for a in args], stdout=out, stderr=err, text=True)
    (batch_step / "exit_code.txt").write_text(f"{result.returncode}\n")
    return result.returncode


def sampling_result_from_output(object_id, before):
    roots = sorted((ROOT / "logs/articulated-sampling-only" / object_id).glob("*/result.json"), key=lambda p:p.stat().st_mtime)
    new = [p for p in roots if str(p.parent) not in before]
    if len(new) != 1: raise RuntimeError(f"could not identify exactly one new sampling run for {object_id}: {new}")
    result = json.loads(new[0].read_text())
    return result, new[0].parent


def execute(batch: Path, only=None, resume_sampling_run=None):
    # These conditions are global.  Their failure deliberately stops the batch.
    global_guard = {"source":common.source_guard(), "checkpoints":common.checkpoint_guard(), "gpu":common.gpu_guard()}
    env_probe = common.cuda_env(batch)
    write_json(batch / "selection_and_preflight.json", {"selection":selection_record(), "global_guard":global_guard,
                                                          "cuda_overlay":env_probe.get("CUDA_HOME"), "started_utc":now()})
    results = []
    configs = [c for c in SELECTION if only in (None, c["object_id"])]
    resume_object = None
    if resume_sampling_run is not None:
        resume_result = json.loads((resume_sampling_run / "result.json").read_text())
        resume_object = str(resume_result.get("object_id", ""))
        if resume_object not in {c["object_id"] for c in configs}:
            raise RuntimeError("resumed sampling run does not belong to the selected batch objects")
    for sequence, config in enumerate(configs, 1):
        object_id = config["object_id"]
        row = {"object_id":object_id, "sequence":sequence, "selection":config, "status":"not_run"}
        object_dir = batch / "objects" / object_id
        object_dir.mkdir(parents=True, exist_ok=True)
        before = {str(p.parent) for p in (ROOT / "logs/articulated-sampling-only" / object_id).glob("*/result.json")}
        try:
            # Reuse the proven stage 1-6 implementation in-process, preserving its independent timestamp paths.
            sample_paths = sampling.run_one(config, resume=resume_sampling_run if object_id == resume_object else None)
            sampling_run = Path(sample_paths["run_dir"])
            sample_result = json.loads((sampling_run / "result.json").read_text())
            row.update(sampling_run=str(sampling_run), sampling_staging=sample_paths["staging_dir"], sampling_status=sample_result["status"])
            gate_path = sampling_run / "steps/06_sampling_only_and_decoder_gate/decoder_eligibility.json"
            gate = json.loads(gate_path.read_text())
        except BaseException as exc:
            # If run_one raises after making a run, retain that exact run location when discoverable.
            try:
                sample_result, sampling_run = sampling_result_from_output(object_id, before)
                row.update(sampling_run=str(sampling_run), sampling_staging=sample_result.get("staging_dir"), sampling_status=sample_result.get("status"))
            except BaseException:
                pass
            row.update(status="failed", reason=f"sampling/preprocessing: {type(exc).__name__}: {exc}")
            results.append(row); write_json(object_dir / "result.json", row); continue
        if not gate.get("decoder_eligible_under_current_policy"):
            row.update(status="blocked", reason="measured decoder memory gate rejected latent", decoder_gate=gate)
            results.append(row); write_json(object_dir / "result.json", row); continue
        row["decoder_gate"] = gate
        decoder_step = object_dir / "decoder"
        code = run_child(decoder_step, [PY, DECODER, "--source-run", sampling_run])
        stdout = (decoder_step / "stdout.log").read_text(errors="replace")
        if code == 0:
            lines = [line for line in stdout.splitlines() if line.strip().startswith("{")]
            try: decoder_result = json.loads(lines[-1])
            except Exception as exc: raise RuntimeError(f"decoder succeeded but did not return result JSON: {exc}")
            row.update(status="success", decoder_run=decoder_result["run_dir"], decoder_staging=decoder_result["staging_dir"])
        else:
            row.update(status="failed", reason=f"decoder exit {code}", decoder_stderr_tail=(decoder_step / "stderr.log").read_text(errors="replace")[-4000:])
        results.append(row); write_json(object_dir / "result.json", row)
    summary = {"status":"success" if all(r["status"]=="success" for r in results) else "partial_failure",
               "paper_equivalent":False, "finished_utc":now(), "results":results}
    write_json(batch / "batch_result.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--object", choices=[x["object_id"] for x in SELECTION])
    parser.add_argument("--resume-sampling-run", type=Path, help="explicitly resume one unfinished sampling run, then continue remaining selected objects")
    args = parser.parse_args()
    if args.plan:
        print(json.dumps(selection_record(), indent=2)); return
    parent = ROOT / "logs/public-only-v1-extension"; parent.mkdir(parents=True, exist_ok=True)
    with open(parent / ".runner.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
        batch = parent / rid; batch.mkdir()
        try:
            result = execute(batch, args.object, args.resume_sampling_run.resolve() if args.resume_sampling_run else None)
        except BaseException as exc:
            write_json(batch / "batch_result.json", {"status":"failed", "reason":f"{type(exc).__name__}: {exc}", "finished_utc":now()})
            raise
        print(json.dumps({"batch":str(batch), "status":result["status"]}, ensure_ascii=False))
        if result["status"] != "success": raise SystemExit("one or more object-local stages failed or were blocked")


if __name__ == "__main__": main()
