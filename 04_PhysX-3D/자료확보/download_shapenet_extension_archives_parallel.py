#!/usr/bin/env python3
"""Fresh exact-range downloader used only after invalid partial quarantine."""
from __future__ import annotations
import concurrent.futures, hashlib, json, os, re, shutil, uuid
from datetime import datetime, timezone
from pathlib import Path
import requests
from huggingface_hub import HfApi
from huggingface_hub.utils import get_token

ROOT=Path('/home/minsujo/Desktop/SH/PHYSx'); RAW=ROOT/'data/shapenetcore/raw'; LOGS=ROOT/'logs/shapenet-extension-recovery'
REPO='ShapeNet/ShapeNetCore'; FILES=('02933112.zip','03636649.zip'); CHUNK=64*1024*1024
def now(): return datetime.now(timezone.utc).isoformat()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def meta():
 i=HfApi().dataset_info(REPO,files_metadata=True,token=True)
 d={x.rfilename:{'bytes':x.size,'sha256':x.lfs.sha256,'revision':i.sha,'url':f'https://huggingface.co/datasets/{REPO}/resolve/{i.sha}/{x.rfilename}'} for x in i.siblings if x.rfilename in FILES}
 if set(d)!=set(FILES):raise RuntimeError('official metadata incomplete')
 return d
def get_range(name, expected, start, end, fd, token):
 url=expected['url']+f'?download=true&cachebust={uuid.uuid4().hex}'
 r=requests.get(url,headers={'Authorization':f'Bearer {token}','Range':f'bytes={start}-{end}'},stream=True,allow_redirects=True,timeout=(30,180))
 m=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',r.headers.get('Content-Range',''))
 if r.status_code!=206 or not m or (int(m.group(1)),int(m.group(2)),int(m.group(3)))!=(start,end,expected['bytes']):
  r.close();raise RuntimeError(f'unsafe range response status={r.status_code} content_range={r.headers.get("Content-Range")!r}')
 pos=start; count=0
 for block in r.iter_content(8*1024*1024):
  if block: os.pwrite(fd,block,pos);pos+=len(block);count+=len(block)
 r.close()
 if pos!=end+1:raise RuntimeError(f'incomplete range {start}-{end}: wrote {count}')
 return {'start':start,'end':end,'bytes':count}
def fetch(name, expected, run, token):
 final=RAW/name
 if final.exists():
  a={'bytes':final.stat().st_size,'sha256':sha(final)}
  if a=={'bytes':expected['bytes'],'sha256':expected['sha256']}:return {'status':'already_verified','actual':a,'path':str(final)}
  raise RuntimeError(f'final destination exists but is not official: {final}')
 part=RAW/f'{name}.download-{run.name}.part'
 if part.exists():raise RuntimeError(f'unique temporary path unexpectedly exists: {part}')
 fd=os.open(part,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600)
 try:
  os.ftruncate(fd,expected['bytes'])
  ranges=[(a,min(a+CHUNK-1,expected['bytes']-1)) for a in range(0,expected['bytes'],CHUNK)]
  with concurrent.futures.ThreadPoolExecutor(max_workers=min(8,len(ranges))) as pool:
   pieces=list(pool.map(lambda x:get_range(name,expected,x[0],x[1],fd,token),ranges))
  os.fsync(fd)
 finally:os.close(fd)
 actual={'bytes':part.stat().st_size,'sha256':sha(part)}
 if actual['bytes']!=expected['bytes'] or actual['sha256']!=expected['sha256']:
  return {'status':'failed_verification','expected':expected,'actual':actual,'retained_part_path':str(part)}
 os.replace(part,final)
 return {'status':'verified','expected':expected,'actual':actual,'verified_path':str(final),'ranges':pieces}
def main():
 run=LOGS/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-parallel-'+os.urandom(5).hex());run.mkdir(parents=True)
 m=meta();free=shutil.disk_usage(ROOT).free;need=sum(v['bytes'] for v in m.values())+8*1024**3
 plan={'started_utc':now(),'metadata':m,'free_before_bytes':free,'required_free_bytes':need,'space_pass':free>=need,'method':'fresh unique sparse .part plus independently content-range-verified chunks; no invalid partial reuse'};(run/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
 if not plan['space_pass']:raise RuntimeError('disk preflight failed')
 token=get_token()
 if not token:raise RuntimeError('existing login unavailable; refresh forbidden')
 results={}
 for name in FILES:
  try:results[name]=fetch(name,m[name],run,token)
  except Exception as e:results[name]={'status':'failed_download','reason':f'{type(e).__name__}: {e}'}
 result={'finished_utc':now(),'results':results,'both_verified':all(v['status'] in ('verified','already_verified') for v in results.values())};(run/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
 if not result['both_verified']:raise SystemExit(1)
if __name__=='__main__':main()
