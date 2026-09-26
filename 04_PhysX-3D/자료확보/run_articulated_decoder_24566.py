#!/usr/bin/env python3
"""Guarded one-shot cached decoder runner for selected articulated sample 24566."""
from __future__ import annotations
import argparse, fcntl, hashlib, json, os, subprocess, sys, uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import run_27281_articulated_pipeline as common

ROOT, SRC, PY, ADAPTER = common.ROOT, common.SRC, common.PY, common.ADAPTER
OBJECT = "24566"
SOURCE_RUN = ROOT / "logs/articulated-sampling-only/24566/20260926T213719Z-83a8565c7136"
SOURCE_STAGE = ROOT / "staging/articulated-sampling-24566-20260926T213719Z-83a8565c7136"
LATENT = SOURCE_STAGE / "sampling/sampled_latents.pt"
GT = SOURCE_STAGE / "work/physxnet/finaljson/24566.json"
EXPECTED_LATENT_SHA = "ac83737ad1f8c78f5dae1b8e054037d8acd9fbb6e9c9f0e5f27cc88e65f908a5"
EXPECTED_N = 27089; EXPECTED_GATE_MIB = 17035.724
HARD_LIMIT_MIB = 28000; RESERVE_MIB = 4607


def sha(path): return common.sha(Path(path))
def write_json(path, data): common.write_json(Path(path), data)
def fingerprint(*values):
    h=hashlib.sha256()
    for value in values: h.update(str(value).encode()); h.update(b"\0")
    return h.hexdigest()


def verify_source_run():
    result=json.loads((SOURCE_RUN/"result.json").read_text())
    if result.get("status")!="success" or result.get("object_id")!=OBJECT: raise RuntimeError("sampling result is not successful 24566")
    checked=[]
    for number in range(1,7):
        matches=list((SOURCE_RUN/"steps").glob(f"{number:02d}_*/SUCCESS.json"))
        if len(matches)!=1: raise RuntimeError(f"stage {number} SUCCESS marker missing/ambiguous")
        marker=json.loads(matches[0].read_text())
        for row in marker.get("outputs",[]):
            path=Path(row["path"])
            if not path.is_file() or path.stat().st_size!=row["bytes"] or sha(path)!=row["sha256"]:
                raise RuntimeError(f"stage {number} output hash mismatch: {path}")
        checked.append({"stage":number,"marker":str(matches[0]),"input_fingerprint":marker["input_fingerprint"],"outputs":len(marker["outputs"])})
    gate=json.loads((SOURCE_RUN/"steps/06_sampling_only_and_decoder_gate/decoder_eligibility.json").read_text())
    if gate.get("rows_N")!=EXPECTED_N or gate.get("gate_peak_with_uncertainty_mib")!=EXPECTED_GATE_MIB or not gate.get("decoder_eligible_under_current_policy"):
        raise RuntimeError(f"decoder gate changed: {gate}")
    if sha(LATENT)!=EXPECTED_LATENT_SHA: raise RuntimeError("latent hash mismatch")
    return {"source_result":result,"verified_stages":checked,"gate":gate,"latent_sha256":sha(LATENT),"gt_sha256":sha(GT)}


def proactive_guard(gpu, gate):
    required=gate["gate_peak_with_uncertainty_mib"]+RESERVE_MIB
    report={"physical_gpu":gpu,"expected_peak_with_uncertainty_mib":gate["gate_peak_with_uncertainty_mib"],
            "hard_limit_mib":HARD_LIMIT_MIB,"reserve_mib":RESERVE_MIB,
            "required_free_before_mib":required,"free_before_mib":gpu["free_mib"],
            "pass":gate["gate_peak_with_uncertainty_mib"]<=HARD_LIMIT_MIB and gpu["free_mib"]>=required}
    if not report["pass"]: raise RuntimeError(f"proactive decoder memory guard failed: {report}")
    return report


def execute(run, stage):
    r=common.Runner(run,stage); env=common.cuda_env(run)
    env.update(PHYSX_OUTPUT_TILE_ENABLE="1",PHYSX_STREAMING_GROUPNORM_ENABLE="1",
               PHYSX_STREAMING_GROUPNORM_CHUNK_ROWS="16384",PHYSX_GPU_RESERVE_MIB=str(RESERVE_MIB))
    try:
        manifest=verify_source_run()
        def s1(d):
            gpu=common.gpu_guard(); guard=proactive_guard(gpu,manifest["gate"])
            write_json(d/"source_run_manifest.json",manifest);write_json(d/"proactive_memory_guard.json",guard)
            return [d/"source_run_manifest.json",d/"proactive_memory_guard.json",LATENT,GT],{"stages_reused":[1,2,3,4,5,6],"gpu":gpu}
        r.step(1,"reuse_sampling_and_memory_gate",fingerprint(EXPECTED_LATENT_SHA,sha(GT),EXPECTED_GATE_MIB),s1)

        def s2(d):
            gpu=common.gpu_guard();write_json(d/"gpu_preflight.json",gpu);proactive_guard(gpu,manifest["gate"])
            r.child(d,[PY,ADAPTER/"validate_candidate.py","gpu"],env={**env,"PHYSX_TILE_ENABLE":"0"},gpu=True,log_prefix="input_tiling")
            r.child(d,[PY,ADAPTER/"validate_decoder_adapters.py"],env=env,gpu=True,log_prefix="output_norm")
            return [d/"input_tiling.stdout.log",d/"output_norm.stdout.log"],{"equivalence":"mandatory GPU checks passed"}
        r.step(2,"mandatory_small_gpu_equivalence",fingerprint(sha(ADAPTER/"validate_candidate.py"),sha(ADAPTER/"validate_decoder_adapters.py"),sha(ADAPTER/"channel_tiled_spconv.py"),sha(ADAPTER/"output_channel_tiled_spconv.py"),sha(ADAPTER/"memory_bounded_groupnorm.py")),s2)

        physics_cache=stage/"physics/physics_cache.pt"
        def s3(d):
            gpu=common.gpu_guard();write_json(d/"gpu_preflight.json",gpu);write_json(d/"proactive_memory_guard.json",proactive_guard(gpu,manifest["gate"]))
            physics_cache.parent.mkdir(parents=True,exist_ok=False)
            r.child(d,[PY,ADAPTER/"decode_cached_split.py","physics","--latent",LATENT,"--source",SRC,"--output",physics_cache,"--report",d/"physics_report.json"],env=env,cwd=SRC,gpu=True)
            if not physics_cache.is_file(): raise RuntimeError("physics cache missing")
            return [physics_cache,d/"physics_report.json"],{"separate_child":True}
        r.step(3,"physics_decoder_child",fingerprint(EXPECTED_LATENT_SHA,sha(SRC/"pretrain/diffusion/ckpts_new/property_decoder_step0100000.pt"),sha(ADAPTER/"decode_cached_split.py")),s3)

        mesh_out=stage/"mesh"
        def s4(d):
            gpu=common.gpu_guard();write_json(d/"gpu_preflight.json",gpu);write_json(d/"proactive_memory_guard.json",proactive_guard(gpu,manifest["gate"]))
            r.child(d,[PY,ADAPTER/"decode_cached_split.py","mesh","--latent",LATENT,"--physics-cache",physics_cache,"--source",SRC,"--output",mesh_out,"--report",d/"mesh_report.json"],env=env,cwd=SRC,gpu=True)
            raw=mesh_out/"mesh_physics_raw.pt";obj=mesh_out/"mesh.obj"
            if not raw.is_file() or not obj.is_file(): raise RuntimeError("mesh outputs missing")
            return [raw,obj,d/"mesh_report.json"],{"separate_child":True}
        r.step(4,"mesh_decoder_child",fingerprint(sha(physics_cache),sha(SRC/"pretrain/diffusion/ckpts_new/decoder_step0100000.pt"),sha(ADAPTER/"decode_cached_split.py")),s4)

        audit=stage/"articulation_audit"
        def s5(d):
            audit_env=os.environ.copy();audit_env.update(CUDA_VISIBLE_DEVICES="",PYTHONDONTWRITEBYTECODE="1")
            r.child(d,[PY,"-B",ADAPTER/"verify_articulated_output.py","--raw",mesh_out/"mesh_physics_raw.pt","--mesh",mesh_out/"mesh.obj","--gt",GT,"--head",SRC/"pretrain/diffusion/ckpts_new/property_output_step0100000.pt","--output",audit],env=audit_env)
            outputs=[audit/x for x in ("official_result.json","indexing_correction_candidate.json","gt_annotation.json","input_hashes.json","vertex_physics_14ch.pt")]
            return outputs,{"scope":"GT group/type/parent structural comparison only; no description, 30-view PSNR, density or affordance accuracy"}
        r.step(5,"cpu_gt_structure_audit",fingerprint(sha(mesh_out/"mesh_physics_raw.pt"),sha(GT),sha(ADAPTER/"verify_articulated_output.py")),s5)
        r.result.update(status="success",reason=None,stage="complete",child_exit_code=0);r.save()
    except BaseException as exc:
        r.result.update(status="failed",reason=f"{type(exc).__name__}: {exc}");r.save();raise
    print(f"SUCCESS object={OBJECT} log={run} staging={stage}")


def self_test():
    assert EXPECTED_N*64==1733696
    mock={"free_mib":32000,"total_mib":32607,"index":1,"uuid":"mock","name":"mock"}
    gate={"gate_peak_with_uncertainty_mib":EXPECTED_GATE_MIB}
    assert proactive_guard(mock,gate)["pass"]
    try: proactive_guard({**mock,"free_mib":20000},gate)
    except RuntimeError: pass
    else: raise RuntimeError("unsafe memory mock accepted")
    return {"N_x_64":"PASS","proactive_guard_pass":"PASS","unsafe_free_memory_rejected":"PASS"}


def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--plan",action="store_true");a=p.parse_args()
    if a.self_test: print(json.dumps(self_test(),indent=2));return
    if a.plan: print(json.dumps({"object_id":OBJECT,"source_run":str(SOURCE_RUN),"latent":str(LATENT),"N":EXPECTED_N,"N_x_64":EXPECTED_N*64,"gate_peak_mib":EXPECTED_GATE_MIB,"steps":["verify stage 1-6 hashes","mandatory GPU equivalence","physics child","mesh child","CPU GT structure audit"]},indent=2));return
    parent=ROOT/"logs/articulated-decoder/24566";parent.mkdir(parents=True,exist_ok=True)
    with open(parent/".runner.lock","w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        rid=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:12]
        execute(parent/rid,ROOT/f"staging/articulated-decoder-24566-{rid}")


if __name__=="__main__": main()
