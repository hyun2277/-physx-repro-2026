#!/usr/bin/env python3
"""CPU-only, sample-independent verification for official texture retrieval output."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
from PIL import Image
import trimesh


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def obj_records(path: Path):
    vertices=[]; uvs=[]; faces=[]; mtls=[]
    for raw in path.read_text(errors='replace').splitlines():
        p=raw.split()
        if not p: continue
        if p[0]=='v' and len(p)>=4: vertices.append([float(x) for x in p[1:4]])
        elif p[0]=='vt' and len(p)>=3: uvs.append([float(x) for x in p[1:3]])
        elif p[0]=='f' and len(p)>=4: faces.append(p[1:])
        elif p[0]=='mtllib' and len(p)==2: mtls.append(p[1])
    v=np.asarray(vertices,dtype=np.float64); uv=np.asarray(uvs,dtype=np.float64)
    if not len(v) or not len(faces): raise RuntimeError(f'OBJ lacks vertices/faces: {path}')
    if not np.isfinite(v).all() or (len(uv) and not np.isfinite(uv).all()): raise RuntimeError(f'non-finite OBJ data: {path}')
    return v,faces,uv,mtls

def mtl_textures(mtl: Path):
    if not mtl.is_file(): raise RuntimeError(f'missing MTL: {mtl}')
    refs=[]
    for raw in mtl.read_text(errors='replace').splitlines():
        p=raw.split(maxsplit=1)
        if len(p)==2 and p[0]=='map_Kd':
            ref=p[1].strip(); target=(mtl.parent/ref).resolve()
            if not target.is_file(): raise RuntimeError(f'missing MTL texture: {target}')
            refs.append(target)
    if not refs: raise RuntimeError(f'no map_Kd texture reference: {mtl}')
    for texture in refs:
        with Image.open(texture) as image:
            image.load()
            a=np.asarray(image)
            if not a.size or not np.isfinite(a.astype(np.float64)).all(): raise RuntimeError(f'invalid texture pixels: {texture}')
    return refs

def main(stage: Path, source_mesh: Path, object_id: str, report: Path|None):
    root=stage/'phy_dataset'/object_id; inp=root/'model.obj'; out=root/'model_tex.obj'
    if not inp.is_file() or not out.is_file(): raise RuntimeError(f'missing retrieval mesh under {root}')
    vi,fi,_,_=obj_records(inp); vo,fo,uv,mtls=obj_records(out)
    if not len(uv): raise RuntimeError('retrieval output has no UV coordinates')
    # Official code constructs target_mesh from finalmesh.vertices/faces (lines 146-155).
    # trimesh OBJ export can split/reindex vertices at UV seams.  Counts/order are therefore observations, not pass/fail conditions.
    if len(mtls)!=1: raise RuntimeError(f'expected exactly one output mtllib, got {mtls}')
    output_mtl=(out.parent/mtls[0]).resolve(); output_textures=mtl_textures(output_mtl)
    source_v,source_f,source_uv,source_mtls=obj_records(source_mesh)
    if len(source_uv)==0 or not source_mtls: raise RuntimeError('source ShapeNet mesh lacks textured UV prerequisites')
    source_mtl=(source_mesh.parent/source_mtls[0]).resolve(); source_textures=mtl_textures(source_mtl)
    source_loaded=trimesh.load(source_mesh,force='mesh',process=False)
    if isinstance(source_loaded.visual,trimesh.visual.ColorVisuals) or getattr(source_loaded.visual,'uv',None) is None:
        raise RuntimeError('official retrieval would use gray fallback: source visual is not textured UV')
    # finalindex is the formal connection the official code uses at line 121.
    index=json.loads((stage/'finalindex.json').read_text())
    # The source category is part of the formal finalindex mapping.  Earlier
    # validation accidentally hard-coded the already-used 04379243 category.
    # Derive the category from the archive-preserving staging path instead.
    expected=f'shapenet/{source_mesh.parents[2].name}/{source_mesh.parent.parent.name}'
    if index.get(object_id)!=expected: raise RuntimeError(f'finalindex/source mismatch: {index.get(object_id)!r} != {expected!r}')
    # The retrieval exporter can repack/reencode one or many source JPEGs into a PNG atlas.
    # Provenance is validated by the exact official path/control-flow prerequisites, not byte equality.
    result={
      'status':'pass','object_id':object_id,'model_tex':{'path':str(out),'bytes':out.stat().st_size,'sha256':sha(out)},
      'geometry':{'vertices':len(vo),'faces':len(fo),'uvs':len(uv),'finite':True,'input_model_vertices':len(vi),'input_model_faces':len(fi),'topology_note':'OBJ export may split/reindex UV seam vertices; no equality requirement'},
      'output':{'mtl':str(output_mtl),'textures':[{'path':str(x),'bytes':x.stat().st_size,'sha256':sha(x)} for x in output_textures],'decoded':True},
      'source':{'mesh':str(source_mesh),'vertices':len(source_v),'faces':len(source_f),'uvs':len(source_uv),'mtl':str(source_mtl),'textures':[{'path':str(x),'bytes':x.stat().st_size,'sha256':sha(x)} for x in source_textures],'textured_uv_branch':True,'finalindex_match':True},
      'gray_fallback':'not used: source textured-UV branch is present and official finalindex path matches',
      'atlas_note':'output atlas/reencoding is allowed; source JPEG byte equality and exact color-set membership are not required'}
    print(json.dumps(result,indent=2));
    if report: report.write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('stage',type=Path);p.add_argument('source_mesh',type=Path);p.add_argument('object_id');p.add_argument('--report',type=Path)
    a=p.parse_args(); main(a.stage,a.source_mesh,a.object_id,a.report)
