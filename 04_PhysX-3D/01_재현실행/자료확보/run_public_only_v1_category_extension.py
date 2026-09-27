#!/usr/bin/env python3
"""Four-object category extension after both verified ShapeNet archives exist."""
from __future__ import annotations
import argparse, fcntl, json, subprocess, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import run_27281_articulated_pipeline as common
import run_articulated_sampling_candidates as sampling
ROOT,PY=common.ROOT,common.PY; DECODER=HERE/'run_public_only_cached_decoder.py'
CANDIDATES=({'object_id':'48419','movement_type':'B','purpose':'public-only v1 B translation'}, {'object_id':'38882','movement_type':'B','purpose':'public-only v1 B translation'}, {'object_id':'14567','movement_type':'C','purpose':'public-only v1 C rotation'}, {'object_id':'15821','movement_type':'C','purpose':'public-only v1 C rotation'})
def now():return datetime.now(timezone.utc).isoformat()
def write(p,v):common.write_json(Path(p),v)
def child(d,args):
 d.mkdir(parents=True,exist_ok=True);write(d/'command.json',{'argv':[str(x) for x in args]})
 with open(d/'stdout.log','w') as o,open(d/'stderr.log','w') as e:r=subprocess.run([str(x) for x in args],stdout=o,stderr=e)
 (d/'exit_code.txt').write_text(f'{r.returncode}\n');return r.returncode
def plan():
 rows=[]
 for c in CANDIDATES:
  official,model=sampling.mapping(c['object_id']);category=sampling.mapping_category(official)
  rows.append({**c,'finalindex':official,'category_archive':str(sampling.shape_archive(category)),'part_obj_members':len(sampling.part_members(c['object_id']))-1,'texture_members':'checked per object during guarded minimal extraction'})
 return {'paper_equivalent':False,'requires_both_verified_archives':True,'candidates':rows,'policy':{'gpu':1,'seed':1,'hard_limit_mib':28000,'reserve_mib':4607,'independent_failures_continue':True}}
def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');p.add_argument('--object',choices=[x['object_id'] for x in CANDIDATES]);p.add_argument('--resume-sampling-run',type=Path);a=p.parse_args()
 if a.plan:print(json.dumps(plan(),indent=2));return
 # shared fail-closed conditions before any object staging / GPU work
 verified=plan();common.source_guard();common.checkpoint_guard();common.gpu_guard()
 parent=ROOT/'logs/public-only-v1-category-extension';parent.mkdir(parents=True,exist_ok=True)
 with open(parent/'.runner.lock','w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);rid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:12];run=parent/rid;run.mkdir();write(run/'plan.json',verified)
  rows=[]
  resume_object=None
  if a.resume_sampling_run:
   resume_object=str(json.loads((a.resume_sampling_run/'result.json').read_text()).get('object_id',''))
   if resume_object not in {x['object_id'] for x in CANDIDATES}:raise RuntimeError('resume run is not a category-extension object')
  for c in [x for x in CANDIDATES if a.object in (None,x['object_id'])]:
   d=run/'objects'/c['object_id'];d.mkdir(parents=True);row={'object_id':c['object_id'],'status':'not_run'}
   try:
    s=sampling.run_one(c,resume=a.resume_sampling_run if c['object_id']==resume_object else None);sr=Path(s['run_dir']);gate=json.loads((sr/'steps/06_sampling_only_and_decoder_gate/decoder_eligibility.json').read_text());row.update(sampling_run=str(sr),sampling_staging=s['staging_dir'],decoder_gate=gate)
    if not gate.get('decoder_eligible_under_current_policy'):
     row.update(status='blocked',reason='measured decoder memory gate rejected latent');write(d/'result.json',row);rows.append(row);continue
    rc=child(d/'decoder',[PY,DECODER,'--source-run',sr])
    if rc:
     row.update(status='failed',reason=f'decoder exit {rc}',stderr_tail=(d/'decoder/stderr.log').read_text(errors='replace')[-4000:])
    else:
     lines=[x for x in (d/'decoder/stdout.log').read_text().splitlines() if x.startswith('{')];out=json.loads(lines[-1]);row.update(status='success',decoder_run=out['run_dir'],decoder_staging=out['staging_dir'])
   except Exception as e:row.update(status='failed',reason=f'{type(e).__name__}: {e}')
   write(d/'result.json',row);rows.append(row)
  result={'finished_utc':now(),'paper_equivalent':False,'results':rows};write(run/'batch_result.json',result);print(json.dumps({'run':str(run),**result},ensure_ascii=False))
  if not all(x['status']=='success' for x in rows):raise SystemExit(1)
if __name__=='__main__':main()
