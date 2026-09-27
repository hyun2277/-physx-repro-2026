#!/usr/bin/env python3
"""CPU-only validation and previews for completed 29806 decoder output."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch,trimesh

ROOT=Path("/home/minsujo/Desktop/SH/PHYSx")
RUN=ROOT/"logs/articulated-decoder/29806/20260927T050730Z-8271ccb5f82b"
STAGE=ROOT/"staging/articulated-decoder-29806-20260927T050730Z-8271ccb5f82b"
GT=ROOT/"staging/articulated-sampling-29806-20260926T220010Z-ac2c1dfab94d/work/physxnet/finaljson/29806.json"
OUT=ROOT/"repro-records/04_PhysX-3D/자료확보/2026-09-27_29806_decoder_결과검증"

def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()

def stages():
 rows=[]
 for marker in sorted((RUN/"steps").glob("*/SUCCESS.json")):
  d=json.loads(marker.read_text());step=marker.parent
  if d.get("status")!="success" or (step/"exit_code.txt").read_text().strip()!="0":raise RuntimeError(f"failed {step}")
  for x in d["outputs"]:
   p=Path(x["path"])
   if not p.is_file() or p.stat().st_size!=x["bytes"] or sha(p)!=x["sha256"]:raise RuntimeError(f"hash mismatch {p}")
  child={p.name:p.read_text().strip() for p in step.glob("*child_exit_code.txt")}
  if any(x!="0" for x in child.values()):raise RuntimeError(f"child failure {child}")
  rows.append({"stage":step.name,"exit_code":0,"child_exit_codes":child,"outputs_verified":len(d["outputs"]),"success_sha256":sha(marker)})
 if len(rows)!=5:raise RuntimeError("expected 5 stage markers")
 return rows

def preview(v,labels,path,group):
 fig,axs=plt.subplots(1,3,figsize=(12,4),dpi=150);pairs=((0,1),(0,2),(1,2));names=("X–Y","X–Z","Y–Z");ids=np.arange(0,len(v),max(1,len(v)//120000))
 for ax,(a,b),name in zip(axs,pairs,names):
  if group:ax.scatter(v[ids,a],v[ids,b],s=.2,c=np.where(labels[ids]==0,"#3268a8","#d64b3c"),rasterized=True)
  else:ax.scatter(v[ids,a],v[ids,b],s=.2,c="#283747",rasterized=True)
  ax.set_aspect("equal");ax.set_title(name);ax.set_xlabel("normalized coordinate");ax.set_ylabel("normalized coordinate")
 fig.suptitle("29806 predicted groups: 0 fixed / 1 moving" if group else "29806 decoded mesh — CPU orthographic vertex projections");fig.tight_layout();fig.savefig(path,bbox_inches="tight");plt.close(fig)

def main():
 OUT.mkdir(parents=True,exist_ok=True);rawp=STAGE/"mesh/mesh_physics_raw.pt";objp=STAGE/"mesh/mesh.obj";prop=STAGE/"articulation_audit/vertex_physics_14ch.pt"
 raw=torch.load(rawp,map_location="cpu",weights_only=True);p14=torch.load(prop,map_location="cpu",weights_only=True);v=raw["vertices"].float().numpy();f=raw["faces"].long().numpy();vp=raw["vertex_physics"]
 if v.shape!=(180260,3) or f.shape!=(360512,3) or list(vp.shape)!=[180260,32] or list(p14.shape)!=[180260,14]:raise RuntimeError("unexpected shape")
 if not all(torch.isfinite(x).all() for x in (raw["vertices"],raw["vertex_attrs"],vp,p14)):raise RuntimeError("nonfinite output")
 mesh=trimesh.load(objp,force="mesh",process=False)
 if len(mesh.vertices)!=len(v) or len(mesh.faces)!=len(f):raise RuntimeError("OBJ reload mismatch")
 official=json.loads((STAGE/"articulation_audit/official_result.json").read_text());candidate=json.loads((STAGE/"articulation_audit/indexing_correction_candidate.json").read_text());gt=json.loads(GT.read_text())
 gid=p14[:,3].numpy();count=round(float(gid.max()))+1;labels=np.full(len(gid),-1,dtype=np.int64)
 for n in range(count):labels[(gid>n-.5)&(gid<n+.5)]=n
 stats={"status":"verified","object_id":"29806","stages":stages(),"artifacts":{"raw":{"path":str(rawp),"bytes":rawp.stat().st_size,"sha256":sha(rawp),"vertex_physics_shape":list(vp.shape),"vertex_attrs_shape":list(raw["vertex_attrs"].shape)},"obj":{"path":str(objp),"bytes":objp.stat().st_size,"sha256":sha(objp),"vertices":len(mesh.vertices),"faces":len(mesh.faces),"reloaded":True},"property_14ch":{"shape":list(p14.shape),"finite":True}},"gpu":{"physics_torch_peak_mib":2234.963,"physics_nvidia_smi_peak_mib":4298,"mesh_torch_peak_mib":12587.484,"mesh_nvidia_smi_peak_mib":3526,"limit_mib":28000,"reserve_mib":4607},"gt":{"group_count":4,"group_info":gt["group_info"]},"official_prediction":{"formula":"round(max(group_id))+1","predicted_group_count":count,"gt_group_count":4,"classification":"articulation surface present but group-count underprediction","group_id_min":float(gid.min()),"group_id_max":float(gid.max()),"groups":official["groups"],"moving_surface_region":bool((labels==1).any()),"official_indexing":official["indexing"]},"indexing_correction_candidate":candidate,"limits":["no direct GT-part to generated-vertex correspondence","parent/direction/position/range accuracy not established","does not establish correspondence of predicted group 1 to any GT door","not a 30-view or paper-wide quantitative evaluation"]}
 preview(v,labels,OUT/"mesh_preview.png",False);preview(v,labels,OUT/"articulation_group_preview.png",True);stats["previews"]=[str(OUT/"mesh_preview.png"),str(OUT/"articulation_group_preview.png")]
 (OUT/"statistics.json").write_text(json.dumps(stats,indent=2,ensure_ascii=False)+"\n");print(json.dumps({"verified":True,"groups":count,"moving_vertices":int((labels==1).sum())}))

if __name__=="__main__":main()
