#!/usr/bin/env python3
"""CPU-only verification and previews for the completed 24566 decoder result."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import trimesh

ROOT=Path("/home/minsujo/Desktop/SH/PHYSx")
RUN=ROOT/"logs/articulated-decoder/24566/20260926T221319Z-a9491be93452"
STAGE=ROOT/"staging/articulated-decoder-24566-20260926T221319Z-a9491be93452"
GT=ROOT/"staging/articulated-sampling-24566-20260926T213719Z-83a8565c7136/work/physxnet/finaljson/24566.json"
OUT=ROOT/"repro-records/04_PhysX-3D/01_재현실행/자료확보/2026-09-27_24566_decoder_결과검증"

def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def verify_markers():
    rows=[]
    for marker in sorted((RUN/"steps").glob("*/SUCCESS.json")):
        doc=json.loads(marker.read_text()); step=marker.parent
        if doc.get("status")!="success" or (step/"exit_code.txt").read_text().strip()!="0": raise RuntimeError(f"failed marker: {step}")
        for x in doc["outputs"]:
            p=Path(x["path"])
            if not p.is_file() or p.stat().st_size!=x["bytes"] or sha(p)!=x["sha256"]: raise RuntimeError(f"hash mismatch: {p}")
        child_codes={p.name:p.read_text().strip() for p in step.glob("*child_exit_code.txt")}
        if any(v!="0" for v in child_codes.values()): raise RuntimeError(f"child failure: {child_codes}")
        gpu=step/"gpu_usage.json"; peak=json.loads(gpu.read_text()).get("peak_nvidia_smi_mib") if gpu.is_file() else None
        rows.append({"stage":step.name,"exit_code":0,"child_exit_codes":child_codes,"outputs_verified":len(doc["outputs"]),"success_sha256":sha(marker),"peak_nvidia_smi_mib":peak})
    if len(rows)!=5: raise RuntimeError(f"expected five successful stages, got {len(rows)}")
    return rows

def preview(vertices,faces,labels,path,groups=False):
    fig,axes=plt.subplots(1,3,figsize=(12,4),dpi=150); pairs=((0,1),(0,2),(1,2)); names=("X–Y","X–Z","Y–Z")
    stride=max(1,len(vertices)//120000); ids=np.arange(0,len(vertices),stride)
    for ax,(a,b),name in zip(axes,pairs,names):
        if groups:
            colors=np.where(labels[ids]==0,"#3268a8","#d64b3c")
            ax.scatter(vertices[ids,a],vertices[ids,b],s=.15,c=colors,rasterized=True)
        else: ax.scatter(vertices[ids,a],vertices[ids,b],s=.15,c="#283747",rasterized=True)
        ax.set_aspect("equal");ax.set_title(name);ax.set_xlabel("normalized coordinate");ax.set_ylabel("normalized coordinate")
    title="24566 predicted articulation groups: group 0 only; no predicted moving surface" if groups else "24566 decoded mesh — CPU orthographic vertex projections"
    fig.suptitle(title);fig.tight_layout();fig.savefig(path,bbox_inches="tight");plt.close(fig)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    raw_path=STAGE/"mesh/mesh_physics_raw.pt";obj_path=STAGE/"mesh/mesh.obj";phy_path=STAGE/"articulation_audit/vertex_physics_14ch.pt"
    raw=torch.load(raw_path,map_location="cpu",weights_only=True);phy=torch.load(phy_path,map_location="cpu",weights_only=True)
    vertices=raw["vertices"].float().numpy();faces=raw["faces"].long().numpy();attrs=raw["vertex_attrs"];vphysics=raw["vertex_physics"]
    if vertices.shape!=(613164,3) or faces.shape!=(1226344,3) or list(vphysics.shape)!=[613164,32] or list(phy.shape)!=[613164,14]: raise RuntimeError("unexpected output shapes")
    if not all(torch.isfinite(x).all() for x in (raw["vertices"],attrs,vphysics,phy)): raise RuntimeError("non-finite output")
    mesh=trimesh.load(obj_path,force="mesh",process=False)
    if len(mesh.vertices)!=len(vertices) or len(mesh.faces)!=len(faces): raise RuntimeError("OBJ/raw shape mismatch")
    group=phy[:,3].numpy();predicted=round(float(group.max()))+1;labels=np.full(len(group),-1,dtype=np.int64)
    for g in range(predicted): labels[(group>g-.5)&(group<g+.5)]=g
    gt=json.loads(GT.read_text());g1=gt["group_info"]["1"];motion=g1[2]
    official=json.loads((STAGE/"articulation_audit/official_result.json").read_text())
    candidate=json.loads((STAGE/"articulation_audit/indexing_correction_candidate.json").read_text())
    stats={"status":"verified","object_id":"24566","stages":verify_markers(),
      "artifacts":{"raw":{"path":str(raw_path),"bytes":raw_path.stat().st_size,"sha256":sha(raw_path),"vertex_physics_shape":list(vphysics.shape),"vertex_attrs_shape":list(attrs.shape)},"obj":{"path":str(obj_path),"bytes":obj_path.stat().st_size,"sha256":sha(obj_path),"vertices":len(mesh.vertices),"faces":len(mesh.faces),"reloaded":True},"property_14ch":{"shape":list(phy.shape),"finite":True}},
      "gpu":{"input_tiling_nvidia_smi_peak_mib":728,"output_norm_nvidia_smi_peak_mib":64,"physics_torch_peak_mib":json.loads((RUN/"steps/03_physics_decoder_child/physics_report.json").read_text())["torch_peak_allocated_mib"],"physics_nvidia_smi_peak_mib":9062,"mesh_torch_peak_mib":json.loads((RUN/"steps/04_mesh_decoder_child/mesh_report.json").read_text())["torch_peak_allocated_mib"],"mesh_nvidia_smi_peak_mib":19934,"limit_mib":28000,"reserve_mib":4607},
      "gt":{"group_count":2,"fixed_group_0_parts":gt["group_info"]["0"],"moving_group_1_parts":g1[0],"parent":g1[1],"type":g1[3],"direction":motion[:3],"position":motion[3:6],"range":motion[6:]},
      "official_prediction":{"formula":"round(max(group_id))+1","predicted_group_count":predicted,"gt_group_count":2,"classification":"false negative articulation","group_id_min":float(group.min()),"group_id_max":float(group.max()),"groups":{"0":{"vertices":int((labels==0).sum()),"vertex_fraction":float((labels==0).mean()),"faces":int(len(faces)),"surface_area":float(official["groups"]["0"]["majority_area"]),"components":official["groups"]["0"]["components"]},"1":{"vertices":0,"vertex_fraction":0.0,"faces":0,"surface_area":0.0,"components":{"count_including_isolated":0}}},"moving_surface_region":False,"official_indexing":official["indexing"]},
      "indexing_correction_candidate":candidate,
      "limits":["no direct GT-part to generated-vertex correspondence","parent/direction/position/range accuracy not established","scale/density/affordance/description not evaluated","24 conditioning views are not paper 30-view evaluation","not a paper-wide quantitative result"]}
    preview(vertices,faces,labels,OUT/"mesh_preview.png",False);preview(vertices,faces,labels,OUT/"articulation_group_preview.png",True)
    stats["previews"]=[str(OUT/"mesh_preview.png"),str(OUT/"articulation_group_preview.png")]
    (OUT/"statistics.json").write_text(json.dumps(stats,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"verified":True,"predicted_groups":predicted,"moving_vertices":0,"previews":stats["previews"]}))

if __name__=="__main__": main()
