#!/usr/bin/env python3
"""Clean, verified ShapeNet extension archive recovery without Range append."""
from __future__ import annotations
import hashlib, json, os, shutil, stat
from datetime import datetime, timezone
from pathlib import Path
from huggingface_hub import HfApi, hf_hub_download

ROOT=Path('/home/minsujo/Desktop/SH/PHYSx'); RAW=ROOT/'data/shapenetcore/raw'
LOG_ROOT=ROOT/'logs/shapenet-extension-recovery'; REPO='ShapeNet/ShapeNetCore'
NAMES=('02933112.zip','03636649.zip')
def now(): return datetime.now(timezone.utc).isoformat()
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def record_file(p):
    s=p.stat()
    return {'absolute_path':str(p),'bytes':s.st_size,'sha256':sha(p),'created_utc':datetime.fromtimestamp(s.st_ctime,timezone.utc).isoformat(),'modified_utc':datetime.fromtimestamp(s.st_mtime,timezone.utc).isoformat()}
def official_metadata():
    info=HfApi().dataset_info(REPO,files_metadata=True,token=True)
    found={x.rfilename:{'bytes':x.size,'sha256':x.lfs.sha256,'revision':info.sha,
                         'url':f'https://huggingface.co/datasets/{REPO}/resolve/{info.sha}/{x.rfilename}'}
           for x in info.siblings if x.rfilename in NAMES}
    if set(found)!=set(NAMES): raise RuntimeError(f'missing official metadata: {found}')
    return found
def main():
    runid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+os.urandom(6).hex()
    run=LOG_ROOT/runid; run.mkdir(parents=True); RAW.mkdir(parents=True,exist_ok=True)
    quarantine=RAW/'quarantine'/runid; quarantine.mkdir(parents=True)
    prior=[]
    for name in NAMES:
        old=RAW/(name+'.part')
        if old.exists():
            before=record_file(old); target=quarantine/old.name
            os.replace(old,target)
            prior.append({**before,'quarantine_path':str(target),'move':'atomic rename; preserved'})
    meta=official_metadata(); free=shutil.disk_usage(ROOT).free; needed=sum(x['bytes'] for x in meta.values())+8*1024**3
    plan={'run_id':runid,'started_utc':now(),'repository':REPO,'metadata':meta,'prior_invalid_partials':prior,
          'free_before_bytes':free,'required_free_bytes':needed,'space_pass':free>=needed,
          'download_method':'fresh hf_hub_download into unique local_dir; no direct HTTP Range append'}
    (run/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    if not plan['space_pass']: raise RuntimeError('disk preflight failed')
    result={}
    for name in NAMES:
        expected=meta[name]; tempdir=RAW/'recovery-downloads'/runid/name
        tempdir.mkdir(parents=True,exist_ok=False)
        unique_part=RAW/f'{name}.download-{runid}.part'
        try:
            downloaded=Path(hf_hub_download(REPO,name,repo_type='dataset',revision=expected['revision'],token=True,
                                             local_dir=tempdir,cache_dir=ROOT/'cache/huggingface/recovery-downloads',force_download=True))
            if downloaded.name != name or not downloaded.is_file(): raise RuntimeError(f'unexpected client download path: {downloaded}')
            os.replace(downloaded,unique_part)
            actual=record_file(unique_part)
            if actual['bytes']!=expected['bytes'] or actual['sha256']!=expected['sha256']:
                result[name]={'status':'failed_verification','expected':expected,'actual':actual,'retained_part_path':str(unique_part)}
                continue
            final=RAW/name
            if final.exists(): raise RuntimeError(f'verified destination already exists: {final}')
            os.replace(unique_part,final)
            result[name]={'status':'verified','expected':expected,'actual':record_file(final),'verified_path':str(final)}
        except Exception as exc:
            result[name]={'status':'failed_download','expected':expected,'reason':f'{type(exc).__name__}: {exc}',
                          'retained_part_path':str(unique_part) if unique_part.exists() else None}
    outcome={'finished_utc':now(),'run_id':runid,'prior_invalid_partials':prior,'results':result,
             'both_verified':all(x.get('status')=='verified' for x in result.values())}
    (run/'result.json').write_text(json.dumps(outcome,indent=2)+'\n')
    print(json.dumps(outcome,indent=2))
    if not outcome['both_verified']: raise SystemExit(1)
if __name__=='__main__': main()
