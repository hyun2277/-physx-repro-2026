#!/usr/bin/env python3
"""Download only verified ShapeNetCore laptop archive 03642806.zip."""
from __future__ import annotations
import hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
import requests
from huggingface_hub import HfApi
from huggingface_hub.utils import get_token

ROOT=Path('/home/minsujo/Desktop/SH/PHYSx'); RAW=ROOT/'data/shapenetcore/raw'; LOGS=ROOT/'logs/shapenet-laptop-download'
REPO='ShapeNet/ShapeNetCore'; NAME='03642806.zip'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def main():
 RAW.mkdir(parents=True,exist_ok=True);LOGS.mkdir(parents=True,exist_ok=True)
 run=LOGS/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));run.mkdir()
 info=HfApi().dataset_info(REPO,files_metadata=True,token=True)
 x=[s for s in info.siblings if s.rfilename==NAME]
 if len(x)!=1: raise RuntimeError('official metadata has no unique laptop archive')
 exp={'revision':info.sha,'bytes':x[0].size,'sha256':x[0].lfs.sha256}
 (run/'official_metadata.json').write_text(json.dumps(exp,indent=2)+'\n')
 target=RAW/NAME; part=RAW/(NAME+'.download-'+run.name+'.part')
 if target.exists():
  got={'bytes':target.stat().st_size,'sha256':sha(target)}
  if got != {k:exp[k] for k in ('bytes','sha256')}: raise RuntimeError(f'existing final archive mismatches official metadata: {got}')
  print(json.dumps({'status':'already_verified','target':str(target),**got}));return
 token=get_token()
 if not token: raise RuntimeError('Hugging Face authentication token unavailable')
 url=f'https://huggingface.co/datasets/{REPO}/resolve/{info.sha}/{NAME}?download=true'
 with requests.get(url,headers={'Authorization':f'Bearer {token}'},stream=True,timeout=(30,120)) as response:
  if response.status_code!=200: raise RuntimeError(f'HTTP status {response.status_code}')
  with part.open('xb') as out:
   for block in response.iter_content(8*1024*1024):
    if block: out.write(block)
 got={'bytes':part.stat().st_size,'sha256':sha(part)}
 (run/'download_result.json').write_text(json.dumps({'expected':exp,'actual':got,'part':str(part)},indent=2)+'\n')
 if got != {k:exp[k] for k in ('bytes','sha256')}: raise RuntimeError(f'archive verification mismatch; preserving {part}')
 os.replace(part,target);print(json.dumps({'status':'downloaded_verified','target':str(target),**got}))
if __name__=='__main__':main()
