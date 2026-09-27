#!/usr/bin/env python3
"""One-pass, fail-isolated expansion using the already verified 04379243 ZIP.

This orchestrator deliberately imports the frozen preprocessing, native-adapter,
memory-gate, sampling, and split-decoder runners.  It contains no alternative
math, retry loop, or evaluator implementation.
"""
from __future__ import annotations
import argparse, fcntl, json, subprocess, sys, uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_27281_articulated_pipeline as common
import run_articulated_sampling_candidates as sampling

ROOT, PY = common.ROOT, common.PY
DECODER = HERE / "run_public_only_cached_decoder.py"
ELIGIBILITY = ROOT / "repro-records/04_PhysX-3D/03_평가및최종보고서/evaluation/2026-09-27_public-only-v1-eligibility/eligibility_manifest.json"
BASELINE = {"29354","21356","24566","27703","30719","21314","32980","48419","38882","15821","29806"}
EXCLUDED = {"23787":"official texture retrieval output non-finite OBJ", "27281":"preserved decoder-OOM ledger", "14567":"MTL lacks map_Kd texture"}
# All are unique, 2-part, fixed rows with direct 04379243 OBJ/MTL/map_Kd members.
# The stale eligibility snapshot has no remaining B-translation or C-rotation row
# after the above exclusions; that limitation is recorded rather than hidden.
SELECTED_IDS = ("19661","25862","27370","31114","22738","24163","27499","25598","19335","34676","26121","18778")

def now(): return datetime.now(timezone.utc).isoformat()
def write(path, value): common.write_json(Path(path), value)

def _rows():
    return {str(row["object_id"]): row for row in json.loads(ELIGIBILITY.read_text())["rows"]}

def selection_record():
    rows = _rows(); selected=[]
    for oid in SELECTED_IDS:
        row=rows.get(oid)
        if row is None: raise RuntimeError(f"candidate missing from eligibility manifest: {oid}")
        m=row.get("mapping") or {}; s=row.get("shapenet") or {}; p=row.get("physxnet") or {}
        if (row.get("eligibility"),m.get("category"),p.get("source_ok"),s.get("available")) != ("NEEDS_CONDITIONING","04379243",True,True):
            raise RuntimeError(f"candidate no longer meets frozen selection contract: {oid}: {row}")
        # ``run_one`` re-opens both ZIP central directories immediately before
        # extraction.  Here we retain the eligibility audit's member paths so a
        # no-GPU plan does not repeatedly scan a 1.6-GB archive twelve times.
        official, model=sampling.mapping(oid); part_count=int(p["part_obj_count"])
        selected.append({"object_id":oid,"test_row":row["test_index"],"tier":row["group_profile"]["tier"],
          "group_count":row["group_profile"]["group_count"],"movement_types":row["group_profile"]["motion_classes"],
          "mapping":official,"part_obj_count":part_count,"texture_member_count":len(s.get("raw_texture_members",[])),
          "physxnet_members_from_eligibility_audit":[p.get("json_member"), *[f"version_1/partseg/{oid}/objs/{i}.obj" for i in range(part_count)]],
          "shapenet_members_from_eligibility_audit":[s.get("raw_obj_member"),s.get("raw_mtl_member"),*s.get("raw_texture_members",[])],
          "selection_reason":"NEEDS_CONDITIONING; eligibility audit directly recorded 04379243 OBJ/MTL/referenced texture members. run_one re-verifies current ZIP central-directory entries before extraction; selected among the smallest two-part fixed candidates."})
    return {"protocol":"public-materials-independent-evaluation-v1","paper_equivalent":False,
      "selection":selected,"excluded":EXCLUDED,
      "selection_constraints":{"baseline_artifacts_excluded":sorted(BASELINE),"target_new_artifact_complete":9,
        "available_remaining_tiers":{"fixed":222,"B_translation":0,"C_rotation":0,"other_articulated":5},
        "balance_note":"No eligible B/C row remains in current 04379243 NEEDS_CONDITIONING set; selected fixed rows are the only safe small candidates under the frozen exclusions."},
      "frozen_execution":{"physical_gpu":1,"seed":1,"spconv_algo":"native","hard_limit_mib":28000,"reserve_mib":4607,
       "adapter":"existing channel/output tiling plus memory-bounded GroupNorm; not modified","per_object":"separate timestamped sampling and decoder children"}}

def run_child(directory, argv):
    directory.mkdir(parents=True,exist_ok=True)
    write(directory/"command.json",{"argv":[str(x) for x in argv]})
    with open(directory/"stdout.log","w") as out, open(directory/"stderr.log","w") as err:
        cp=subprocess.run([str(x) for x in argv],stdout=out,stderr=err,text=True)
    (directory/"exit_code.txt").write_text(str(cp.returncode)+"\n")
    return cp.returncode

def run_batch(batch):
    # Only these shared guard failures terminate the batch before object work.
    guard={"source":common.source_guard(),"checkpoints":common.checkpoint_guard(),"gpu":common.gpu_guard(),"cuda_overlay":common.cuda_env(batch).get("CUDA_HOME")}
    record=selection_record(); write(batch/"selection_and_preflight.json",{"started_utc":now(),"global_guard":guard,**record})
    results=[]; successful=0
    for sequence, oid in enumerate(SELECTED_IDS,1):
        row={"object_id":oid,"sequence":sequence,"status":"not_run"}; out=batch/"objects"/oid; out.mkdir(parents=True,exist_ok=True)
        if successful>=9:
            row.update(status="not_started_goal_reached",reason="baseline 11 plus 9 new successes reaches 20; no further candidate run")
            results.append(row); write(out/"result.json",row); continue
        cfg={"object_id":oid,"movement_type":"fixed","purpose":"public-only-v1 04379243 fixed expansion"}
        try:
            sample=sampling.run_one(cfg)
            srun=Path(sample["run_dir"]); sresult=json.loads((srun/"result.json").read_text())
            gate=json.loads((srun/"steps/06_sampling_only_and_decoder_gate/decoder_eligibility.json").read_text())
            row.update(sampling_run=str(srun),sampling_staging=sample["staging_dir"],sampling_status=sresult["status"],decoder_gate=gate)
            if not gate.get("decoder_eligible_under_current_policy"):
                row.update(status="blocked",reason="measured frozen decoder memory gate rejected latent")
            else:
                rc=run_child(out/"decoder",[PY,DECODER,"--source-run",srun])
                if rc:
                    row.update(status="failed",reason=f"decoder exit {rc}",decoder_stderr_tail=(out/"decoder/stderr.log").read_text(errors="replace")[-4000:])
                else:
                    lines=[x for x in (out/"decoder/stdout.log").read_text(errors="replace").splitlines() if x.startswith("{")]
                    decoded=json.loads(lines[-1])
                    row.update(status="success",decoder_run=decoded["run_dir"],decoder_staging=decoded["staging_dir"]); successful+=1
        except BaseException as exc:
            row.update(status="failed",reason=f"{type(exc).__name__}: {exc}")
        results.append(row); write(out/"result.json",row)
    summary={"status":"goal_reached" if successful>=9 else "completed_below_goal","paper_equivalent":False,"baseline_artifact_complete":11,"new_artifact_complete":successful,"artifact_complete_total":11+successful,"finished_utc":now(),"results":results}
    write(batch/"batch_result.json",summary); return summary

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--plan",action="store_true"); a=ap.parse_args()
    if a.plan: print(json.dumps(selection_record(),indent=2)); return
    parent=ROOT/"logs/public-only-v1-04379243-12-batch"; parent.mkdir(parents=True,exist_ok=True)
    with open(parent/".runner.lock","w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        rid=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:12]
        batch=parent/rid; batch.mkdir(); result=run_batch(batch)
        print(json.dumps({"batch":str(batch),"status":result["status"],"artifact_complete_total":result["artifact_complete_total"]}))

if __name__=="__main__": main()
