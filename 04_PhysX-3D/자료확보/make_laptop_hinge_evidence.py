#!/usr/bin/env python3
"""CPU-only small preview/summary for one generated hinge-candidate result."""
from __future__ import annotations
import argparse, hashlib, json, shutil
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import torch

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def draw(ax,v,color,title):
 n=min(50000,len(v)); idx=np.linspace(0,len(v)-1,n,dtype=np.int64)
 point_color=color if isinstance(color,str) else color[idx]
 ax.scatter(v[idx,0],v[idx,2],c=point_color,s=.15,linewidths=0,rasterized=True)
 ax.set_aspect('equal');ax.set_title(title);ax.set_xlabel('x');ax.set_ylabel('z')
def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--raw',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--gt',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise RuntimeError('output must be new')
 a.output.mkdir(parents=True);shutil.copy2(a.input,a.output/'conditioning_000.png')
 raw=torch.load(a.raw,map_location='cpu',weights_only=True);v=raw['vertices'].numpy(); phy=raw['vertex_physics'].numpy()
 audit=json.loads(a.audit.read_text());gt=json.loads(a.gt.read_text());
 # Official audit applies this head, then group round/window logic; recreate only group colors for a preview.
 head=torch.load('/home/minsujo/Desktop/SH/PHYSx/sources/physx-4f54e750a309/pretrain/diffusion/ckpts_new/property_output_step0100000.pt',map_location='cpu',weights_only=True)
 p14=torch.from_numpy(phy[:,-16:]).float()@head['output_layer_phy.weight'][:,:,1,1].float().T+head['output_layer_phy.bias'].float(); gid=p14[:,3].numpy();groups=np.full(len(gid),-1)
 for g in range(audit['predicted_num_group']):groups[(gid>g-.5)&(gid<g+.5)]=g
 fig,ax=plt.subplots(figsize=(7,5),dpi=140);draw(ax,v,'#4472c4','Generated mesh: x-z vertex projection');fig.tight_layout();fig.savefig(a.output/'mesh_preview.png');plt.close(fig)
 palette=np.where(groups==1,'#d62728','#377eb8');fig,ax=plt.subplots(figsize=(7,5),dpi=140);draw(ax,v,palette,'Official predicted group window: group 1 red');fig.tight_layout();fig.savefig(a.output/'predicted_group_preview.png');plt.close(fig)
 result={'object_id':a.gt.stem,'conditioning_sha256':sha(a.input),'raw_sha256':sha(a.raw),'audit_sha256':sha(a.audit),'gt_sha256':sha(a.gt),'mesh':{'vertices':len(v),'faces':len(raw['faces']),'finite':bool(np.isfinite(v).all() and np.isfinite(phy).all())},'gt_group_info':gt['group_info'],'predicted_num_group':audit['predicted_num_group'],'groups':audit['groups'],'scope':'CPU previews only; no simulation, joint parameter accuracy, or GT-to-generated correspondence claim'}
 (a.output/'result_summary.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
