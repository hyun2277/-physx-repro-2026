#!/usr/bin/env python3
"""Verified two-file ShapeNetCore downloader for the public-only v1 extension."""
from __future__ import annotations
import hashlib, json, os, re, shutil, sys
from datetime import datetime, timezone
from pathlib import Path
import requests
from huggingface_hub import HfApi
from huggingface_hub.utils import get_token

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
RAW = ROOT / 'data/shapenetcore/raw'
LOGS = ROOT / 'logs/shapenet-extension-download'
REPO = 'ShapeNet/ShapeNetCore'
FILES = ('02933112.zip','03636649.zip')

def now(): return datetime.now(timezone.utc).isoformat()
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def metadata():
    info=HfApi().dataset_info(REPO, files_metadata=True, token=True)
    found={s.rfilename:{'bytes':s.size,'sha256':s.lfs.sha256,'lfs_bytes':s.lfs.size} for s in info.siblings if s.rfilename in FILES}
    if set(found)!=set(FILES): raise RuntimeError(f'official metadata missing requested archives: {found}')
    return found

def download(name, expected, log):
    target=RAW/name; part=RAW/(name+'.part')
    if target.exists():
        actual={'bytes':target.stat().st_size,'sha256':digest(target)}
        if actual['bytes']==expected['bytes'] and actual['sha256']==expected['sha256']:
            return {'status':'already_verified',**actual,'target':str(target)}
        raise RuntimeError(f'existing final archive does not match official metadata: {target}')
    offset=part.stat().st_size if part.exists() else 0
    if offset>expected['bytes']: raise RuntimeError(f'.part is larger than official file; preserving it: {part}')
    token=get_token()
    if not token: raise RuntimeError('existing Hugging Face token unavailable; authentication refresh forbidden')
    headers={'Authorization':f'Bearer {token}'}
    if offset: headers['Range']=f'bytes={offset}-'
    url=f'https://huggingface.co/datasets/{REPO}/resolve/main/{name}?download=true'
    with requests.get(url,headers=headers,stream=True,allow_redirects=True,timeout=(30,120)) as response:
        if offset:
            content_range=response.headers.get('Content-Range','')
            match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',content_range)
            if response.status_code != 206 or not match or int(match.group(1)) != offset or int(match.group(3)) != expected['bytes']:
                raise RuntimeError(f'unsafe resume response status={response.status_code} content_range={content_range!r}; preserving .part without replacement')
        if not offset and response.status_code != 200: response.raise_for_status()
        with part.open('ab') as out:
            for block in response.iter_content(chunk_size=8*1024*1024):
                if block: out.write(block)
    actual={'bytes':part.stat().st_size,'sha256':digest(part)}
    if actual['bytes']!=expected['bytes'] or actual['sha256']!=expected['sha256']:
        raise RuntimeError(f'completed .part verification mismatch; preserving {part}: {actual}')
    os.replace(part,target)
    return {'status':'downloaded_verified',**actual,'target':str(target)}

def main():
    RAW.mkdir(parents=True,exist_ok=True); LOGS.mkdir(parents=True,exist_ok=True)
    run=LOGS/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    run.mkdir()
    try:
        meta=metadata(); total=sum(x['bytes'] for x in meta.values()); free=shutil.disk_usage(ROOT).free
        # Reserve the archives plus 8 GiB for four independent minimum staging trees.
        required=total+8*1024**3
        plan={'started_utc':now(),'repository':REPO,'metadata':meta,'free_before_bytes':free,'required_free_bytes':required,'space_pass':free>=required}
        (run/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
        if not plan['space_pass']: raise RuntimeError('insufficient free disk space before download')
        results={}
        for name in FILES:
            try: results[name]=download(name,meta[name],run)
            except Exception as exc:
                results[name]={'status':'failed','reason':f'{type(exc).__name__}: {exc}','part_path':str(RAW/(name+'.part'))}
        result={'finished_utc':now(),'metadata':meta,'results':results}
        (run/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        if any(v['status']=='failed' for v in results.values()): raise SystemExit(1)
        print(json.dumps(result,indent=2))
    except BaseException as exc:
        (run/'failure.json').write_text(json.dumps({'finished_utc':now(),'reason':f'{type(exc).__name__}: {exc}'},indent=2)+'\n')
        raise
if __name__=='__main__': main()
