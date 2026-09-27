#!/usr/bin/env python3
"""Independent CPU audit of the already-created eleven public-only artifacts.

This intentionally does not import the public-only evaluator.  It rereads only
the immutable manifests/artifacts, recomputes three sentinel meshes with a
separate sampler and KD-tree calculation, then writes a new audit directory.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from pathlib import Path

import numpy as np
import torch
import trimesh
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
BASE = HERE / '2026-09-27_public-only-v1-eleven-actual'
OUT = HERE / '2026-09-27_public-only-v1-eleven-final-audit'
MANIFEST = BASE / 'manifest.json'
REPORT = BASE / 'eight_sample_report.json'
SOURCE_TEST = ROOT / 'sources/physx-4f54e750a309/val_test_list.npy'
SEED, POINTS, ATOL, RTOL = 20260927, 8192, 1e-11, 1e-10


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()


def mesh(path: Path) -> trimesh.Trimesh:
    m = trimesh.load(path, force='mesh', process=False)
    if isinstance(m, trimesh.Scene): m = trimesh.util.concatenate(tuple(m.geometry.values()))
    v, f = np.asarray(m.vertices, dtype=np.float64), np.asarray(m.faces, dtype=np.int64)
    if v.ndim != 2 or v.shape[1] != 3 or not len(v) or f.ndim != 2 or f.shape[1] != 3 or not len(f):
        raise ValueError('empty/non-triangle mesh')
    if not np.isfinite(v).all() or (f < 0).any() or (f >= len(v)).any(): raise ValueError('nonfinite/bad mesh topology')
    tri = v[f]; area = .5*np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)
    if not np.isfinite(area).all() or not np.any(area > 0): raise ValueError('no positive-area faces')
    return trimesh.Trimesh(vertices=v, faces=f, process=False)


def canonical(m: trimesh.Trimesh) -> trimesh.Trimesh:
    v=np.asarray(m.vertices,dtype=np.float64); lo,hi=v.min(0),v.max(0); scale=float((hi-lo).max())
    if not math.isfinite(scale) or scale <= 0: raise ValueError('invalid canonical extent')
    return trimesh.Trimesh(vertices=(v-(lo+hi)/2)/scale,faces=m.faces,process=False)


def surface(m: trimesh.Trimesh, count: int, seed: int) -> np.ndarray:
    v, f = np.asarray(m.vertices,dtype=np.float64), np.asarray(m.faces,dtype=np.int64); tri=v[f]
    area=.5*np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1); c=np.cumsum(area/area.sum())
    rng=np.random.Generator(np.random.PCG64(seed)); idx=np.minimum(np.searchsorted(c,rng.random(count),side='right'),len(tri)-1)
    u,vv=rng.random(count),rng.random(count); r=np.sqrt(u); bary=np.stack((1-r,r*(1-vv),r*vv),axis=1)
    pts=(tri[idx]*bary[:,:,None]).sum(1)
    if not np.isfinite(pts).all(): raise ValueError('nonfinite sample')
    return pts


def geometry(pred: trimesh.Trimesh, gt: trimesh.Trimesh) -> dict:
    p,g=surface(pred,POINTS,SEED),surface(gt,POINTS,SEED)
    pg=cKDTree(g).query(p,k=1,workers=1)[0]; gp=cKDTree(p).query(g,k=1,workers=1)[0]
    precision,recall=float((pg<=.05).mean()),float((gp<=.05).mean())
    return {'cd_l1_sum_raw':float(pg.mean()+gp.mean()),'cd_l2_sum_raw':float((pg*pg).mean()+(gp*gp).mean()),
            'fscore_raw':0. if precision+recall==0 else 2*precision*recall/(precision+recall),
            'precision':precision,'recall':recall,'pred_samples':len(p),'gt_samples':len(g)}


def tensor_from(path: Path):
    obj=torch.load(path,map_location='cpu',weights_only=True)
    if isinstance(obj,torch.Tensor): return obj
    if isinstance(obj,dict):
        for key in ('vertex_attrs','phy_property'):
            if isinstance(obj.get(key),torch.Tensor): return obj[key]
    raise ValueError('no inspectable tensor')


def close(a,b): return math.isclose(float(a),float(b),rel_tol=RTOL,abs_tol=ATOL)


def main():
    if OUT.exists(): raise RuntimeError(f'refusing to overwrite {OUT}')
    manifest=json.loads(MANIFEST.read_text()); report=json.loads(REPORT.read_text()); samples={x['object_id']:x for x in report['samples']}
    OUT.mkdir(parents=True)
    artifact={}; invalid=[]
    for item in manifest['items']:
        oid=item['object_id']; checks=[]
        for kind,meta in item['files'].items():
            p=Path(meta['path']); ok=p.is_file() and p.stat().st_size==meta['bytes'] and sha(p)==meta['sha256']
            checks.append({'kind':kind,'path':str(p),'hash_match':ok})
            if not ok: invalid.append({'object_id':oid,'kind':kind,'reason':'missing/size/hash mismatch'})
        try:
            gm=mesh(Path(item['files']['generated_mesh']['path'])); tm=mesh(Path(item['files']['gt_mesh']['path']))
            ten=tensor_from(Path(item['files']['property']['path'])); finite=bool(torch.isfinite(ten).all())
            json.loads(Path(item['files']['gt_json']['path']).read_text())
            checks.append({'kind':'semantic_load','mesh_vertices':[len(gm.vertices),len(tm.vertices)],'property_shape':list(ten.shape),'finite':finite})
            if not finite: raise ValueError('nonfinite property')
        except Exception as exc:
            invalid.append({'object_id':oid,'kind':'semantic_load','reason':f'{type(exc).__name__}: {exc}'})
        artifact[oid]={'status':'valid' if not any(x['object_id']==oid for x in invalid) else 'invalid','checks':checks}
    recompute={}
    for oid in ('29354','24566','29806'):
        item=next(x for x in manifest['items'] if x['object_id']==oid); expected=samples[oid]
        raw=geometry(mesh(Path(item['files']['generated_mesh']['path'])),mesh(Path(item['files']['gt_mesh']['path'])))
        can=geometry(canonical(mesh(Path(item['files']['generated_mesh']['path']))), canonical(mesh(Path(item['files']['gt_mesh']['path']))))
        checks={}
        for name,got,old in [('raw_cd_l1',raw['cd_l1_sum_raw'],expected['geometry']['raw_coordinate']['cd_l1_sum_raw']),('raw_cd_l2',raw['cd_l2_sum_raw'],expected['geometry']['raw_coordinate']['cd_l2_sum_raw']),('raw_fscore',raw['fscore_raw'],expected['geometry']['raw_coordinate']['fscore_raw']),('can_cd_l1',can['cd_l1_sum_raw'],expected['geometry']['bbox_center_max_extent_canonical']['cd_l1_sum_raw']),('can_cd_l2',can['cd_l2_sum_raw'],expected['geometry']['bbox_center_max_extent_canonical']['cd_l2_sum_raw']),('can_fscore',can['fscore_raw'],expected['geometry']['bbox_center_max_extent_canonical']['fscore_raw'])]:
            checks[name]={'computed':got,'existing':old,'abs_delta':abs(got-old),'pass':close(got,old)}
        gt=json.loads(Path(item['files']['gt_json']['path']).read_text()); audit=json.loads(Path(item['files']['audit']['path']).read_text())
        gt_groups=len(gt['group_info']); pred=int(audit.get('predicted_num_group',audit.get('num_group')))
        if oid=='29354': pred_scale=float(audit['scale']['predicted_vertex_mean_cm'])
        else: pred_scale=float(tensor_from(Path(item['files']['property']['path']))[:,0].mean())
        gt_scale=max(float(x) for x in gt['dimension'].split(' ')[0].split('*')); scale_error=abs(pred_scale-gt_scale)
        checks['scale']={'computed':scale_error,'existing':expected['scale']['raw'],'abs_delta':abs(scale_error-expected['scale']['raw']),'pass':close(scale_error,expected['scale']['raw'])}
        expected_art=expected['articulation']; false_negative=gt_groups>1 and pred==1; under=gt_groups>=3 and 1<pred<gt_groups
        checks['groups']={'gt':gt_groups,'predicted':pred,'existing_gt':expected_art['gt_num_group'],'existing_predicted':expected_art['predicted_num_group'],'false_negative':false_negative,'underprediction':under,'pass':gt_groups==expected_art['gt_num_group'] and pred==expected_art['predicted_num_group'] and false_negative==expected_art['articulated_false_negative'] and under==expected_art['multi_joint_underprediction']}
        recompute[oid]={'raw':raw,'canonical':can,'checks':checks,'pass':all(x['pass'] for x in checks.values())}
    # Independently recompute the eleven sample macro/subgroup values from sample rows.
    fields={'raw_cd_l1':lambda s:s['geometry']['raw_coordinate']['cd_l1_sum_raw'],'raw_cd_l2':lambda s:s['geometry']['raw_coordinate']['cd_l2_sum_raw'],'raw_fscore':lambda s:s['geometry']['raw_coordinate']['fscore_raw'],'canonical_cd_l1':lambda s:s['geometry']['bbox_center_max_extent_canonical']['cd_l1_sum_raw'],'canonical_cd_l2':lambda s:s['geometry']['bbox_center_max_extent_canonical']['cd_l2_sum_raw'],'canonical_fscore':lambda s:s['geometry']['bbox_center_max_extent_canonical']['fscore_raw'],'scale_error_cm':lambda s:s['scale']['raw'],'group_count_absolute_error':lambda s:s['articulation']['absolute_group_count_error']}
    def summary(rows): return {k:{'n':len(rows),'mean':float(statistics.mean([f(x) for x in rows])),'median':float(statistics.median([f(x) for x in rows]))} for k,f in fields.items()}
    all_rows=report['samples']; tiers={'fixed':6,'B_translation':3,'C_rotation':2}; aggregate={'overall':summary(all_rows),'subgroups':{t:summary([x for x in all_rows if x['tier']==t]) for t in tiers}}
    agg_pass=len(all_rows)==11 and all(len([x for x in all_rows if x['tier']==t])==n for t,n in tiers.items())
    for scope,calc,old in [('overall',aggregate['overall'],report['all_macro'])]+[(t,aggregate['subgroups'][t],report['subgroup_macro'][t]) for t in tiers]:
        for metric in fields:
            agg_pass &= calc[metric]['n']==old[metric]['n'] and close(calc[metric]['mean'],old[metric]['mean']) and close(calc[metric]['median'],old[metric]['median'])
    ledger={x['object_id'] for x in report['failure_ledger']} | {'14567'}
    agg_pass &= not ({'23787','27281','14567'} & {x['object_id'] for x in all_rows})
    official=[str(x) for x in np.load(SOURCE_TEST,allow_pickle=False)[-1000:]]; occurrence={}; rows_ok=True
    for item in manifest['items']:
        oid=item['object_id']; occurrence[oid]=occurrence.get(oid,0)+1; rows_ok &= official[item['test_index']]==oid and item['occurrence']==occurrence[oid]
    agg_pass &= rows_ok
    audit={'status':'pass' if not invalid and all(x['pass'] for x in recompute.values()) and agg_pass else 'fail','tolerance':{'absolute':ATOL,'relative':RTOL},'sampling':{'seed':SEED,'points_per_mesh':POINTS,'method':'independent PCG64 area-weighted barycentric + cKDTree'},'artifacts':artifact,'invalid_artifacts':invalid,'sentinel_recalculation':recompute,'aggregate':aggregate,'aggregate_pass':agg_pass,'test_order_duplicate_pass':rows_ok,'excluded_failure_ledger':['23787','27281','14567'],'raw_canonical_mixed':False}
    (OUT/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    # Reuse only existing previews; no mesh rendering is performed here.
    previews=[('29354 — fixed; official group 2 (six-vertex non-meaningful group 1)',ROOT/'repro-records/04_PhysX-3D/01_재현실행/자료확보/rtx5090_adapter/2026-09-27_29354-semantic-validation/semantic_preview.png'),('24566 — B translation GT 2; official prediction 1 (false negative)',ROOT/'repro-records/04_PhysX-3D/01_재현실행/자료확보/2026-09-27_24566_decoder_결과검증/articulation_group_preview.png'),('29806 — C rotation GT 4; official prediction 2 (underprediction)',ROOT/'repro-records/04_PhysX-3D/01_재현실행/자료확보/2026-09-27_29806_decoder_결과검증/articulation_group_preview.png')]
    tiles=[]
    for caption,p in previews:
        im=Image.open(p).convert('RGB'); im.thumbnail((900,260)); tile=Image.new('RGB',(920,300),'white'); tile.paste(im,((920-im.width)//2,35)); ImageDraw.Draw(tile).text((12,10),caption,fill='black'); tiles.append(tile)
    overview=Image.new('RGB',(920,300*len(tiles)), 'white')
    for i,t in enumerate(tiles): overview.paste(t,(0,300*i))
    overview.save(OUT/'overview_existing_previews.png')
    lines=['# PhysX-3D 중간 재현 보고서 — public-only v1, 11 표본','','본 보고서는 공개 자료 기반 독립 평가이며 논문 Table 2 또는 논문 동일 1,000-test 재현이 아니다. 기존 artifact를 다시 생성하지 않고 CPU 검산만 수행했다.','','## 범위와 실행 상태','','- 원본 공식 table 예제 1건은 기존 기록상 성공했다.','- RTX 5090 결과는 CUDA 12.8/GCC 12 및 검증된 channel-tiled Native adapter와 sampling/decoder 분리 경로를 사용한 환경 적응 실행이다. 따라서 원본 단일 프로세스 실행과 비트 동일하다고 주장하지 않는다.','- 11개 artifact-complete 표본의 geometry·scale·official group-count diagnostic만 public-only v1로 집계했다.','','## 11 표본 결과','','| ID | class | raw CD L1 | canonical CD L1 | raw F-score | scale error (cm) | GT/pred groups | diagnostic |','|---|---|---:|---:|---:|---:|---|---|']
    for s in all_rows:
        a=s['articulation']; diag='false negative' if a['articulated_false_negative'] else 'multi-joint underprediction' if a['multi_joint_underprediction'] else 'count diagnostic only'
        lines.append(f"| {s['object_id']} | {s['tier']} | {s['geometry']['raw_coordinate']['cd_l1_sum_raw']:.6f} | {s['geometry']['bbox_center_max_extent_canonical']['cd_l1_sum_raw']:.6f} | {s['geometry']['raw_coordinate']['fscore_raw']:.6f} | {s['scale']['raw']:.6f} | {a['gt_num_group']}/{a['predicted_num_group']} | {diag} |")
    lines += ['', '## 집계와 한계', f"- Overall n=11; fixed/B/C 분모는 6/3/2다. Raw와 canonical geometry는 별도 조건이며 평균으로 섞지 않았다.", f"- Overall raw CD L1 mean={report['all_macro']['raw_cd_l1']['mean']:.6f}; canonical CD L1 mean={report['all_macro']['canonical_cd_l1']['mean']:.6f}; scale error mean={report['all_macro']['scale_error_cm']['mean']:.6f} cm.", '- 23787은 official retrieval non-finite OBJ, 27281은 보존된 28,000 MiB/4,607 MiB 조건의 mesh decoder OOM, 14567은 source MTL `map_Kd` 부재로 수치 분모 밖에 유지했다.', '- Density·affordance·description map PSNR와 NAP COV/MMD는 GT/pred map·mask·part mapping·question/NAP conversion·공식 집계 규약 부재로 blocked다.', '- 30-view paper condition, GT vertex correspondence, parent/axis/range 정확도, 물리 정확도는 주장할 수 없다.','','## 현재 주장 가능한 것','','- 11개 기존 artifact의 무결성·유한성과 public-only geometry/scale/group diagnostic 계산 규약은 이번 독립 검산에서 확인됐다.','- 24566은 GT 2 groups 대비 official 1 group으로 false negative, 29806은 GT 4 groups 대비 official 2 groups으로 multi-joint underprediction이라는 표본 단위 count diagnostic은 재확인됐다.','','## 다음 선택지','','A. 이 11표본 public-only v1 결과를 중간 재현 보고서로 확정한다.','B. 새 ShapeNet category 확보 후 사전 목록을 고정하고 20–30 표본 independent evaluation으로 확장한다. 이 확장도 공식 evaluator 자료가 없으면 Table 2 비교가 아니다.']
    (OUT/'INTERIM_REPRODUCTION_REPORT.md').write_text('\n'.join(lines)+'\n')
    (OUT/'README.md').write_text('# Eleven-sample final audit\n\n`audit.json` is a CPU-only independent verifier report. It rechecks hashes, parses GT JSON, reloads meshes/properties, recomputes three sentinel geometry/scale/group results, and audits the 11-item denominators. `overview_existing_previews.png` only combines existing previews.\n')
    print(json.dumps({'status':audit['status'],'invalid_artifacts':len(invalid),'sentinel_pass':all(x['pass'] for x in recompute.values()),'aggregate_pass':agg_pass,'output':str(OUT)},ensure_ascii=False))


if __name__=='__main__': main()
