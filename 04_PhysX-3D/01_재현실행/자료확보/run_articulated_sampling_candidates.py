#!/usr/bin/env python3
"""Fail-closed sampling-only preparation for small articulated PhysXNet samples.

This runner intentionally stops after official sampling.  It never invokes a decoder.
"""
from __future__ import annotations
import argparse, csv, fcntl, hashlib, json, os, re, subprocess, sys, uuid, zipfile
from datetime import datetime, timezone
from pathlib import Path

# Reuse the hardened 27281 runner's source/checkpoint/GPU/overlay/marker helpers.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_27281_articulated_pipeline as common

ROOT, SRC, TOOLS, ADAPTER, PY = common.ROOT, common.SRC, common.TOOLS, common.ADAPTER, common.PY
PHYSX_ZIP, SHAPE_ZIP, BLENDER, MANIFEST = common.PHYSX_ZIP, common.SHAPE_ZIP, common.BLENDER, common.MANIFEST
HEAD, MAX_GPU_MIB, RESERVE_MIB = common.HEAD, common.MAX_GPU_MIB, common.RESERVE_MIB
CANDIDATES = (
    {"object_id":"24566", "movement_type":"B", "purpose":"translation"},
    {"object_id":"29806", "movement_type":"C", "purpose":"rotation"},
)


def now(): return datetime.now(timezone.utc).isoformat()
def sha(p): return common.sha(Path(p))
def write_json(p, v): common.write_json(Path(p), v)

def fingerprint(*items):
    h=hashlib.sha256()
    for item in items: h.update(str(item).encode()); h.update(b"\0")
    return h.hexdigest()

def part_members(object_id):
    prefix=f"version_1/partseg/{object_id}/objs/"
    with zipfile.ZipFile(PHYSX_ZIP) as z:
        found=sorted(x for x in z.namelist() if x.startswith(prefix) and x.endswith('.obj'))
    if not found: raise RuntimeError(f"no part OBJ members for {object_id}")
    # Only numbered direct children are accepted: no unexpected member traversal.
    if any(not re.fullmatch(re.escape(prefix)+r"[0-9]+\.obj", x) for x in found):
        raise RuntimeError(f"unexpected part member path for {object_id}: {found}")
    return [f"version_1/finaljson/{object_id}.json", *found]

def mapping(object_id):
    value=json.loads((SRC/'tools/finalindex.json').read_text()).get(object_id)
    # finalindex contains one verified 31-character hexadecimal ShapeNet model
    # identifier (21356) in addition to the usual 32-character identifiers.
    # Accept only those two archive-safe forms; ZIP member inventory still
    # proves the exact path before extraction.
    m=re.fullmatch(r"shapenet/([0-9]{8})/([0-9a-f]{31,32})", str(value))
    if not m: raise RuntimeError(f"official finalindex lacks safe ShapeNet mapping for {object_id}: {value!r}")
    return value, m.group(2)

def mapping_category(official):
    m=re.fullmatch(r"shapenet/([0-9]{8})/[0-9a-f]{31,32}", str(official))
    if not m: raise RuntimeError(f"invalid official ShapeNet mapping: {official!r}")
    return m.group(1)

def shape_archive(category):
    archive=ROOT/'data/shapenetcore/raw'/f'{category}.zip'
    if not archive.is_file(): raise RuntimeError(f'verified ShapeNet category archive missing: {archive}')
    return archive

def texture_members(shape, category='04379243'):
    obj=f"{category}/{shape}/models/model_normalized.obj"
    mtl=f"{category}/{shape}/models/model_normalized.mtl"
    with zipfile.ZipFile(shape_archive(category)) as z:
        text=z.read(mtl).decode('utf-8','replace')
        refs=[]
        for line in text.splitlines():
            if line.strip().startswith('map_Kd '):
                ref=line.strip().split(maxsplit=1)[1]
                # The official ShapeNet archive keeps retrieval textures one directory up in images/.
                # Reject any other MTL traversal rather than extracting an arbitrary archive member.
                if not re.fullmatch(r"\.\./images/[^/]+", ref): raise RuntimeError(f"unsafe MTL texture ref: {ref}")
                expected=f"{category}/{shape}/images/{Path(ref).name}"
                z.getinfo(expected); refs.append(expected)
    if not refs: raise RuntimeError(f"no map_Kd texture references in {mtl}")
    return [obj,mtl,*sorted(set(refs))]

def extract_members(archive, members, work, archive_kind):
    inventory=common.zip_inventory(archive,members); out=[]
    with zipfile.ZipFile(archive) as z:
        for member in members:
            if archive_kind=='physx': target=work/'physxnet'/member.removeprefix('version_1/')
            else: target=work/'shapenet'/member
            out.append(common.extract_member(z,member,target))
    return inventory,out

def latent_schema_and_estimate(latent, output):
    """CPU-only post-sampling size gate; it does not run a decoder."""
    import torch
    d=torch.load(latent,map_location='cpu',weights_only=True)
    required=('slat_coords','slat_feats','phy_coords','phy_feats')
    if set(required)-set(d): raise RuntimeError(f"latent keys missing: {set(required)-set(d)}")
    sc,sf,pc,pf=(d[x] for x in required)
    if sc.ndim!=2 or pc.ndim!=2 or sc.shape[1]!=4 or pc.shape[1]!=4: raise RuntimeError('invalid sparse coordinate schema')
    if sf.ndim!=2 or pf.ndim!=2 or sf.shape[1]!=8 or pf.shape[1]!=8: raise RuntimeError('invalid sparse feature schema')
    if sc.shape!=pc.shape or sf.shape!=pf.shape or not torch.equal(sc,pc): raise RuntimeError('slat/physics coordinate schema mismatch')
    if not torch.isfinite(sf).all() or not torch.isfinite(pf).all(): raise RuntimeError('non-finite latent feature')
    n=int(sc.shape[0]); q=n*64  # two SparseSubdivideBlock3d stages; each SparseSubdivide is 2^3.
    # Empirical envelope, deliberately a lower-bound estimate: 29354 completed at 17,731.954 MiB
    # (N=33,886); 27281 had 29.94 GiB PyTorch allocated at mesh OOM (N=73,024).
    p0_n,p0_mib=33886,17731.954
    p1_n,p1_mib=73024,29.94*1024
    slope=(p1_mib-p0_mib)/(p1_n-p0_n); intercept=p0_mib-slope*p0_n
    lower_peak=intercept+slope*n
    uncertainty=max(1024.0,lower_peak*0.10)
    gate_mib=lower_peak+uncertainty
    eligible=gate_mib<=MAX_GPU_MIB
    report={
      'status':'sampling_only_decoder_gate', 'latent_sha256':sha(latent), 'rows_N':n,
      'maximum_subdivision_points_N_x_64':q,
      'evidence':{'29354':{'N':p0_n,'torch_max_allocated_mib':p0_mib},
                  '27281':{'N':p1_n,'torch_allocated_at_mesh_oom_mib':p1_mib}},
      'linear_lower_bound_peak_mib':round(lower_peak,3), 'measurement_uncertainty_mib':round(uncertainty,3),
      'gate_peak_with_uncertainty_mib':round(gate_mib,3), 'hard_limit_mib':MAX_GPU_MIB,
      'reserve_mib':RESERVE_MIB, 'decoder_eligible_under_current_policy':eligible,
      'decision':('candidate may be considered for a separate decoder runner only after review' if eligible else
                  'decoder prohibited: observed lower-bound envelope plus uncertainty exceeds current limit'),
      'schema':{'coordinate_shape':list(sc.shape),'feature_shape':list(sf.shape),
                'coordinate_dtype':str(sc.dtype),'feature_dtype':str(sf.dtype),'finite':True,'coordinate_equal':True}}
    write_json(output,report); return report

def run_one(config, resume=None):
    object_id=config['object_id']; official,shape=mapping(object_id); category=mapping_category(official); sarchive=shape_archive(category); members=part_members(object_id); smembers=texture_members(shape,category)
    if resume:
        run=Path(resume).resolve(); prior=json.loads((run/'result.json').read_text()); stage=Path(prior['staging_dir'])
        if prior.get('status') not in ('failed','interrupted','not_run'): raise RuntimeError('resume only accepts an unfinished run')
    else:
        rid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:12]
        run=ROOT/'logs/articulated-sampling-only'/object_id/rid; stage=ROOT/f'staging/articulated-sampling-{object_id}-{rid}'
    r=common.Runner(run,stage,bool(resume)); work=stage/'work'; renders=stage/f'datasets/PhysXNet/renders_cond/{object_id}_'
    r.result.update(object_id=object_id, purpose=config['purpose'], movement_type=config['movement_type'], decoder_scope='prohibited: sampling-only'); r.save()
    try:
      guard={'source':common.source_guard(),'checkpoints':common.checkpoint_guard()}
      def s1(d):
        a,ea=extract_members(PHYSX_ZIP,members,work,'physx'); b,eb=extract_members(sarchive,smembers,work,'shape')
        write_json(work/'finalindex.json',{object_id:official})
        write_json(d/'inventory.json',{'physx_central_directory':a,'shapenet_central_directory':b,'extracted':ea+eb,'source':guard['source'],'checkpoints':guard['checkpoints'],'mapping':official})
        outs=[Path(x['target']) for x in ea+eb]+[work/'finalindex.json',MANIFEST,SRC/'dataset_toolkits/merge_property.py',SRC/'dataset_toolkits/retrieval_texture_example.py',SRC/'dataset_toolkits/render_cond.py']+[Path(x['path']) for x in guard['checkpoints']]
        return outs,{'part_obj_count':len(members)-1,'shape_mapping':official,'texture_members':smembers[2:]}
      r.step(1,'guards_and_minimal_extract',fingerprint(sha(PHYSX_ZIP),sha(SHAPE_ZIP),HEAD,object_id,official,*members,*smembers),s1)
      def s2(d):
        gpu=common.gpu_guard(); write_json(d/'gpu_preflight.json',gpu); env=common.cuda_env(run)
        r.child(d,[PY,SRC/'dataset_toolkits/merge_property.py','--index','0','--range','1','--datapath',work/'physxnet'],env=env,cwd=work,gpu=True)
        root=work/f'phy_dataset/{object_id}'; outs=[root/x for x in ('model.obj','clip.npy','clip_ind_new.npy','otherproperty.npy')]
        if not all(x.is_file() and x.stat().st_size for x in outs): raise RuntimeError('merge output missing')
        return outs,{'gpu':gpu}
      r.step(2,'official_merge_property',fingerprint(sha(work/f'physxnet/finaljson/{object_id}.json'),sha(SRC/'dataset_toolkits/merge_property.py'),sha(MANIFEST)),s2)
      def s3(d):
        env=os.environ.copy(); env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
        root=work/f'phy_dataset/{object_id}'; obj=root/'model_tex.obj'; source_mesh=work/f'shapenet/{category}/{shape}/models/model_normalized.obj'
        reused=None
        if obj.is_file():
            reused={'official_retrieval':'not re-run; existing output is verified on explicit resume','model_tex_sha256':sha(obj)}
            write_json(d/'retrieval_reused.json',reused)
        else:
            r.child(d,[PY,SRC/'dataset_toolkits/retrieval_texture_example.py','--index','0','--range','1'],env=env,cwd=work)
        with open(d/'verification.log','w') as f: subprocess.run([PY,TOOLS/'verify_retrieval_output.py',work,source_mesh,object_id,'--report',d/'verification.json'],check=True,stdout=f,stderr=subprocess.STDOUT,env=env)
        refs=[root/x.split(maxsplit=1)[1] for x in obj.read_text(errors='replace').splitlines() if x.startswith('mtllib ')]
        if len(refs)!=1 or not refs[0].is_file(): raise RuntimeError('OBJ->MTL reference invalid')
        texrefs=[refs[0].parent/x.split(maxsplit=1)[1] for x in refs[0].read_text(errors='replace').splitlines() if x.startswith('map_Kd ')]
        if not texrefs or not all(x.is_file() for x in texrefs): raise RuntimeError('MTL->texture reference invalid')
        return [obj,*refs,*texrefs,d/'verification.json',*([d/'retrieval_reused.json'] if reused else [])],{'gray_fallback':'not used (official retrieval verifier passed)','official_retrieval_reused':bool(reused)}
      r.step(3,'official_texture_retrieval',fingerprint(sha(work/f'phy_dataset/{object_id}/model.obj'),sha(work/'finalindex.json'),sha(SRC/'dataset_toolkits/retrieval_texture_example.py'),sha(TOOLS/'verify_retrieval_output.py'),*[sha(work/'shapenet'/x) for x in smembers]),s3)
      def s4(d):
        if not BLENDER.is_file(): raise RuntimeError('portable Blender missing')
        data=stage/'datasets/PhysXNet'; data.mkdir(parents=True,exist_ok=True); meta=data/'metadata.csv'
        with open(meta,'w',newline='') as f:
          fields=['sha256','file_identifier','aesthetic_score','captions','rendered','voxelized','num_voxels','cond_rendered','local_path']; w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerow({'sha256':object_id+'_','file_identifier':'0','aesthetic_score':'10','captions':'0','rendered':'False','voxelized':'False','num_voxels':'0','cond_rendered':'False','local_path':str(work/f'phy_dataset/{object_id}/model_tex.obj')})
        env=os.environ.copy(); env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
        r.child(d,[PY,TOOLS/'render_cond_29354_portable.py','--source-dir',SRC/'dataset_toolkits','--blender',BLENDER,'--model',work/f'phy_dataset/{object_id}/model_tex.obj','--output',data,'--num-views','24','--object-id',object_id],env=env,cwd=work)
        trans=renders/'transforms.json'; doc=json.loads(trans.read_text()); frames=doc.get('frames',[])
        if len(frames)!=24: raise RuntimeError(f'expected 24 frames, got {len(frames)}')
        images=[(renders/f['file_path']).resolve() for f in frames]
        if not all(x.is_file() for x in images): raise RuntimeError('transform references missing image')
        selected=sorted(images,key=lambda p:p.name)[0]
        if selected.name!='000.png': raise RuntimeError('lowest valid frame is not 000.png')
        write_json(d/'selected_input.json',{'path':str(selected),'sha256':sha(selected),'frame':[f for f in frames if (renders/f['file_path']).resolve()==selected][0],'transforms_sha256':sha(trans),'camera_note':'official default 24-view conditioning render; not paper 30-view evaluation camera'})
        return [meta,trans,*images],{'image_count':24,'selected':str(selected)}
      r.step(4,'conditioning_render_24view',fingerprint(sha(work/f'phy_dataset/{object_id}/model_tex.obj'),sha(SRC/'dataset_toolkits/render_cond.py'),sha(TOOLS/'render_cond_29354_portable.py')),s4)
      env=common.cuda_env(run); selected=renders/'000.png'
      def s5(d):
        gpu=common.gpu_guard(); write_json(d/'gpu_preflight.json',gpu)
        for mode in ('cpu','cpu_spconv','boundary'): r.child(d,[PY,ADAPTER/'validate_candidate.py',mode],env={**env,'PHYSX_TILE_ENABLE':'0'},log_prefix=f'validate_{mode}')
        r.child(d,[PY,ADAPTER/'validate_candidate.py','gpu'],env={**env,'PHYSX_TILE_ENABLE':'0'},gpu=True,log_prefix='validate_gpu_equivalence')
        probe='import json,trellis,spconv,cumm;from trellis.modules.sparse import conv;print("PHYSX_RESULT_JSON="+json.dumps({"trellis":trellis.__file__,"spconv":spconv.__file__,"cumm":cumm.__file__,"algo":conv.SPCONV_ALGO},sort_keys=True))'
        r.child(d,[PY,'-c',probe],env=env,gpu=True,log_prefix='import_probe'); actual=common.parse_result_marker((d/'import_probe.stdout.log').read_text(),{'trellis':str,'spconv':str,'cumm':str,'algo':str})
        if actual['algo']!='native' or not actual['trellis'].startswith(str(SRC)): raise RuntimeError(f'import/algo mismatch: {actual}')
        write_json(d/'imports.json',actual); return [d/'imports.json'],{'gpu':gpu,'equivalence':'passed'}
      r.step(5,'native_adapter_equivalence',fingerprint(sha(ADAPTER/'channel_tiled_spconv.py'),sha(ADAPTER/'sitecustomize.py'),sha(ADAPTER/'validate_candidate.py'),sha(selected)),s5)
      sampling=stage/'sampling'
      def s6(d):
        gpu=common.gpu_guard(); write_json(d/'gpu_preflight.json',gpu)
        r.child(d,[PY,ADAPTER/'sample_latents_only.py','--source',SRC,'--input',selected,'--output',sampling,'--report',d/'sampling_report.json','--seed','1'],env=env,cwd=SRC,gpu=True)
        latent=sampling/'sampled_latents.pt'
        if not latent.is_file(): raise RuntimeError('sampling latent missing')
        estimate=latent_schema_and_estimate(latent,d/'decoder_eligibility.json')
        return [latent,sampling/'preprocessed.png',d/'sampling_report.json',d/'decoder_eligibility.json'],{'seed':1,'latent_sha256':sha(latent),'decoder_eligible_under_current_policy':estimate['decoder_eligible_under_current_policy']}
      r.step(6,'sampling_only_and_decoder_gate',fingerprint(sha(selected),'seed=1',HEAD,sha(ADAPTER/'sample_latents_only.py'),sha(MANIFEST)),s6)
      r.result.update(status='success',reason='sampling-only complete; decoder deliberately not invoked',stage='complete',child_exit_code=0); r.save()
    except KeyboardInterrupt:
      r.result.update(status='interrupted',reason='Ctrl+C');r.save();raise
    except BaseException as exc:
      r.result.update(status='failed',reason=f'{type(exc).__name__}: {exc}');r.save();print(f'FAILED object={object_id} stage={r.result["stage"]} log={run}',file=sys.stderr);raise
    print(f'SUCCESS object={object_id} sampling-only log={run} staging={stage}')
    # Callers that orchestrate a decoder in a separate process need the exact
    # timestamped locations; returning them does not change CLI behavior.
    return {'object_id': object_id, 'run_dir': str(run), 'staging_dir': str(stage)}

def plan():
    rows=[]
    for c in CANDIDATES:
        official,shape=mapping(c['object_id']); pm=part_members(c['object_id']); sm=texture_members(shape)
        category=mapping_category(official); rows.append({**c,'finalindex':official,'part_obj_count':len(pm)-1,'texture_member_count':len(sm)-2,'physx_inventory':common.zip_inventory(PHYSX_ZIP,pm),'shapenet_inventory':common.zip_inventory(shape_archive(category),sm)})
    return {'scope':'sequential candidate preparation through sampling only; no decoder', 'candidates':rows,'policy':{'physical_gpu':1,'max_gpu_mib':MAX_GPU_MIB,'reserve_mib':RESERVE_MIB,'decoder':'never executed by this runner'},'subdivision_basis':'two mesh decoder SparseSubdivideBlock3d stages; SparseSubdivide factor=2^3 each, hence N*64'}

def self_test():
    import tempfile
    with tempfile.TemporaryDirectory(dir=ROOT/'logs') as tmp:
      tmp=Path(tmp); import torch
      latent=tmp/'sampled_latents.pt'; coords=torch.tensor([[0,0,0,0],[0,1,0,0]],dtype=torch.int32); feats=torch.ones((2,8))
      torch.save({'slat_coords':coords,'slat_feats':feats,'phy_coords':coords.clone(),'phy_feats':feats.clone()},latent)
      out=tmp/'gate.json'; r=latent_schema_and_estimate(latent,out)
      if r['maximum_subdivision_points_N_x_64']!=128 or not out.is_file(): raise RuntimeError('N*64 gate mock failed')
      try:
        torch.save({'slat_coords':coords},tmp/'bad.pt');latent_schema_and_estimate(tmp/'bad.pt',tmp/'bad.json')
      except RuntimeError: pass
      else: raise RuntimeError('bad latent mock accepted')
    return {'cpu_latent_schema_mock':'PASS','N_x_64_estimator_mock':'PASS','missing_key_rejected':'PASS'}

def main():
  p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');p.add_argument('--self-test',action='store_true');p.add_argument('--candidate',choices=[x['object_id'] for x in CANDIDATES]);p.add_argument('--resume',type=Path);p.add_argument('--resume-first',type=Path,help='resume the first candidate, then start remaining candidates once')
  a=p.parse_args()
  if a.plan: print(json.dumps(plan(),indent=2));return
  if a.self_test: print(json.dumps(self_test(),indent=2));return
  chosen=[x for x in CANDIDATES if a.candidate in (None,x['object_id'])]
  if a.resume and a.resume_first: raise SystemExit('--resume and --resume-first are mutually exclusive')
  if a.resume and len(chosen)!=1: raise SystemExit('--resume requires --candidate')
  if a.resume_first:
    prior=json.loads((a.resume_first.resolve()/'result.json').read_text())
    if prior.get('object_id') != chosen[0]['object_id']: raise SystemExit('--resume-first must name the first selected candidate')
  parent=ROOT/'logs/articulated-sampling-only';parent.mkdir(parents=True,exist_ok=True)
  with open(parent/'.runner.lock','w') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    failures=[]
    fatal_terms=('source HEAD mismatch','non-pyc tracked source changes','bad checkpoint manifest','checkpoint manifest missing','physical GPU index 1 unavailable','GPU 1 already has a compute process','GPU total memory does not preserve configured reserve','CUDA overlay is incomplete','existing CLIP cache missing')
    for index,c in enumerate(chosen):
      try:
        run_one(c,a.resume if a.resume else (a.resume_first if index==0 else None))
      except BaseException as exc:
        # An object-local retrieval/render/sampling failure is recorded by run_one and does not hide the next candidate.
        # Source/checkpoint/GPU/overlay preconditions are shared and fail closed for the whole batch.
        text=str(exc); failures.append({'object_id':c['object_id'],'error':f'{type(exc).__name__}: {text}'})
        if any(term in text for term in fatal_terms):
          write_json(parent/'batch_result.json',{'status':'failed','reason':'shared precondition failure','failures':failures,'finished_utc':now()})
          raise
    write_json(parent/'batch_result.json',{'status':'success' if not failures else 'partial_failure','failures':failures,'finished_utc':now()})
    if failures: raise SystemExit('one or more object-local stages failed; later candidates were attempted')
if __name__=='__main__': main()
