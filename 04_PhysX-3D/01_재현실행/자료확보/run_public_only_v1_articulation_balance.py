#!/usr/bin/env python3
"""Frozen public-only v1 B/C balance extension; no fixed candidate is runnable."""
from __future__ import annotations
import argparse, fcntl, hashlib, json, subprocess, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import run_27281_articulated_pipeline as common
import run_articulated_sampling_candidates as sampling
ROOT,PY=common.ROOT,common.PY; DECODER=HERE/'run_public_only_cached_decoder.py'
EXPECTED={'02933112':('432747631','f36bea3c118cb4818e751c8a6bdc8fd9202ed0dca5ce873251b068bc9b5dc5cd'),'03636649':('745318964','1ad7f8dc315d88cfd5bfdde7850e3b1880d88a15b2dd5ef2e16bfea86888adbb')}
# Ordered by smallest confirmed part count; later entries are backups only.
CANDIDATES=(
 {'object_id':'45443','tier':'B_translation','purpose':'B translation balance','part_count':3},
 {'object_id':'45645','tier':'B_translation','purpose':'B translation balance','part_count':7},
 {'object_id':'46323','tier':'B_translation','purpose':'B translation backup','part_count':5},
 {'object_id':'15896','tier':'C_rotation','purpose':'C rotation balance','part_count':2},
 {'object_id':'13737','tier':'C_rotation','purpose':'C rotation balance','part_count':4},
 {'object_id':'16693','tier':'C_rotation','purpose':'C rotation balance','part_count':4},
 {'object_id':'15146','tier':'C_rotation','purpose':'C rotation backup','part_count':4},
)
EXCLUDED={'23787':'non-finite retrieval output','27281':'decoder OOM under frozen policy','14567':'MTL lacks map_Kd texture','27370':'non-finite retrieval output'}
REJECTED={'15714':'03636649 MTL has no map_Kd texture','13348':'03636649 MTL has no map_Kd texture'}
def now():return datetime.now(timezone.utc).isoformat()
def write(p,v):common.write_json(Path(p),v)
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def preflight():
 rows=[]
 for category,(size,digest) in EXPECTED.items():
  p=sampling.shape_archive(category); actual={'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p),'expected_bytes':int(size),'expected_sha256':digest}
  if actual['bytes']!=int(size) or actual['sha256']!=digest:raise RuntimeError(f'archive verification failed: {actual}')
  rows.append(actual)
 cand=[]
 for c in CANDIDATES:
  official,model=sampling.mapping(c['object_id']);cat=sampling.mapping_category(official)
  parts=sampling.part_members(c['object_id']);tex=sampling.texture_members(model,cat)
  if cat not in EXPECTED:raise RuntimeError(f'unexpected category {cat}')
  cand.append({**c,'mapping':official,'category':cat,'physx_members':common.zip_inventory(sampling.PHYSX_ZIP,parts),'shapenet_members':common.zip_inventory(sampling.shape_archive(cat),tex)})
 return {'scope':'public-only-v1 balance extension, not paper Table 2','frozen_policy':{'gpu':1,'seed':1,'spconv':'native','hard_limit_mib':28000,'reserve_mib':4607,'adapter':'unchanged'},'archives':rows,'candidates':cand,'excluded':EXCLUDED,'preflight_rejected':REJECTED,'quotas':{'B_translation':2,'C_rotation':3}}
def child(d,args):
 d.mkdir(parents=True,exist_ok=True);write(d/'command.json',{'argv':[str(x) for x in args]})
 with open(d/'stdout.log','w') as o,open(d/'stderr.log','w') as e:r=subprocess.run([str(x) for x in args],stdout=o,stderr=e,text=True)
 (d/'exit_code.txt').write_text(f'{r.returncode}\n');return r.returncode
def run(batch):
 plan=preflight(); shared={'source':common.source_guard(),'checkpoints':common.checkpoint_guard(),'gpu':common.gpu_guard(),'cuda_overlay':common.cuda_env(batch).get('CUDA_HOME')};write(batch/'selection_and_preflight.json',{'started_utc':now(),'plan':plan,'shared':shared})
 count={'B_translation':0,'C_rotation':0};rows=[]
 for seq,c in enumerate(CANDIDATES,1):
  d=batch/'objects'/c['object_id'];d.mkdir(parents=True);row={'object_id':c['object_id'],'tier':c['tier'],'sequence':seq,'status':'not_run'}
  if count[c['tier']]>=plan['quotas'][c['tier']]:row.update(status='not_started_quota_reached',reason=f'{c["tier"]} quota reached');rows.append(row);write(d/'result.json',row);continue
  try:
   s=sampling.run_one({'object_id':c['object_id'],'movement_type':'B' if c['tier']=='B_translation' else 'C','purpose':c['purpose']});sr=Path(s['run_dir']);gate=json.loads((sr/'steps/06_sampling_only_and_decoder_gate/decoder_eligibility.json').read_text());row.update(sampling_run=str(sr),sampling_staging=s['staging_dir'],decoder_gate=gate)
   if not gate.get('decoder_eligible_under_current_policy'):row.update(status='blocked',reason='frozen decoder memory gate rejected latent')
   else:
    rc=child(d/'decoder',[PY,DECODER,'--source-run',sr])
    if rc:row.update(status='failed',reason=f'decoder exit {rc}',stderr_tail=(d/'decoder/stderr.log').read_text(errors='replace')[-4000:])
    else:
     lines=[x for x in (d/'decoder/stdout.log').read_text(errors='replace').splitlines() if x.startswith('{')];x=json.loads(lines[-1]);row.update(status='success',decoder_run=x['run_dir'],decoder_staging=x['staging_dir']);count[c['tier']]+=1
  except BaseException as e:row.update(status='failed',reason=f'{type(e).__name__}: {e}')
  rows.append(row);write(d/'result.json',row)
 result={'finished_utc':now(),'paper_equivalent':False,'quota':plan['quotas'],'successes':count,'goal_reached':count==plan['quotas'],'results':rows};write(batch/'batch_result.json',result);return result
def main():
 a=argparse.ArgumentParser();a.add_argument('--plan',action='store_true');x=a.parse_args()
 if x.plan:print(json.dumps(preflight(),indent=2));return
 parent=ROOT/'logs/public-only-v1-articulation-balance';parent.mkdir(parents=True,exist_ok=True)
 with open(parent/'.runner.lock','w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);rid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:12];b=parent/rid;b.mkdir();r=run(b);print(json.dumps({'batch':str(b),**r},ensure_ascii=False))
if __name__=='__main__':main()
