#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/minsujo/Desktop/SH/PHYSx
REPO="$ROOT/repro-records"
ISAAC="$ROOT/tools/isaac-sim"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-gt-only-control"
LOG="$ROOT/logs/gt-only-isaac-control/$RUN_ID"
STAGE="$ROOT/staging/gt-only-isaac-control-$RUN_ID"
mkdir -p "$LOG" "$STAGE"
exec > >(tee "$LOG/runner.stdout.log") 2> >(tee "$LOG/runner.stderr.log" >&2)
printf 'run_id=%s\n' "$RUN_ID"
python3 - <<PY
import hashlib,json,os
root='$ROOT'; stage='$STAGE'; log='$LOG'
items={'10163':'staging/articulated-sampling-10163-20260927T154942Z-fc8c4d6127dc/work/physxnet','29806':'staging/articulated-sampling-29806-20260926T220010Z-ac2c1dfab94d/work/physxnet','29354':'staging/merge-29354-20260925T180423Z/physxnet'}
out={}
for oid,rel in items.items():
 p=os.path.join(root,rel); files=[os.path.join(p,'finaljson',oid+'.json')]+[os.path.join(p,'partseg',oid,'objs',x) for x in sorted(os.listdir(os.path.join(p,'partseg',oid,'objs'))) if x.endswith('.obj')]
 out[oid]=[{'path':x,'bytes':os.path.getsize(x),'sha256':hashlib.sha256(open(x,'rb').read()).hexdigest()} for x in files]
json.dump(out,open(os.path.join(stage,'gt_input_hashes.json'),'w'),indent=2)
PY
cat > "$STAGE/gt_only_control.py" <<'PY'
import argparse, json, math, os, xml.etree.ElementTree as ET
from pathlib import Path
from isaacsim import SimulationApp
p=argparse.ArgumentParser(); p.add_argument('--stage',required=True); p.add_argument('--root',required=True); a=p.parse_args()
EXP=f'{a.root}/repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-02_IsaacSim_Importer_API_진단/isaac_minimal_urdf_importer.kit'
app=SimulationApp({'headless':True,'active_gpu':1,'physics_gpu':1,'multi_gpu':False,'extra_args':['--/renderer/multiGpu/enabled=false','--/renderer/multiGpu/autoEnable=false']},experience=EXP)
try:
 import omni.usd, omni.timeline
 from pxr import Usd, UsdPhysics
 from isaacsim.asset.importer.urdf import URDFImporter, URDFImporterConfig
 cases={'10163':'staging/articulated-sampling-10163-20260927T154942Z-fc8c4d6127dc/work/physxnet','29806':'staging/articulated-sampling-29806-20260926T220010Z-ac2c1dfab94d/work/physxnet','29354':'staging/merge-29354-20260925T180423Z/physxnet'}
 out={}
 for oid,rel in cases.items():
  src=Path(a.root)/rel; d=json.loads((src/'finaljson'/f'{oid}.json').read_text()); mov=d['group_info']; od=Path(a.stage)/oid; od.mkdir(parents=True,exist_ok=True); robot=ET.Element('robot',name=f'gt_{oid}')
  def link(part):
   e=ET.SubElement(robot,'link',name=f'l_{part}'); it=ET.SubElement(e,'inertial'); ET.SubElement(it,'mass',value='1.0'); ET.SubElement(it,'inertia',ixx='1.0',ixy='0',ixz='0',iyy='1.0',iyz='0',izz='1.0')
   mesh=str((src/'partseg'/oid/'objs'/f'{part}.obj').resolve())
   for tag in ('visual','collision'):
    x=ET.SubElement(e,tag); g=ET.SubElement(x,'geometry'); ET.SubElement(g,'mesh',filename=mesh,scale='1 1 1')
  for part in sorted({x for v in mov.values() for x in (v if isinstance(v[0],int) else v[0]) if isinstance(x,int)}): link(part)
  base=mov['0']; world=ET.SubElement(robot,'link',name='world'); ET.SubElement(world,'inertial');
  def joint(name,typ,parent,child,xyz='0 0 0',axis=None,lim=None):
   j=ET.SubElement(robot,'joint',name=name,type=typ); ET.SubElement(j,'parent',link=parent); ET.SubElement(j,'child',link=child); ET.SubElement(j,'origin',xyz=xyz,rpy='0 0 0')
   if axis: ET.SubElement(j,'axis',xyz=' '.join(map(str,axis)))
   if lim: ET.SubElement(j,'limit',lower=str(lim[0]),upper=str(lim[1]),effort='2000',velocity='2')
  joint('world_fixed','fixed','world',f'l_{base[0]}')
  for x,y in zip(base,base[1:]): joint(f'fixed_{x}_{y}','fixed',f'l_{x}',f'l_{y}')
  for gid in sorted(k for k in mov if k!='0'):
   v=mov[gid]; parts=v[0]; parent=mov[v[1]][0]; axis=v[-2][:3]; point=v[-2][3:6]; lim=[v[-2][-2]*math.pi,v[-2][-1]*math.pi]
   absn=f'abstract_{gid}'; ae=ET.SubElement(robot,'link',name=absn); ET.SubElement(ae,'inertial'); joint(f'fixed_abs_{gid}','fixed',absn,f'l_{parts[0]}',xyz=' '.join(map(str,[-q for q in point])))
   joint(f'gt_C_{gid}','revolute',f'l_{parent}',absn,xyz=' '.join(map(str,point)),axis=axis,lim=lim)
  urdf=od/f'gt_{oid}.urdf'; ET.ElementTree(robot).write(urdf,encoding='utf-8',xml_declaration=True)
  cfg=URDFImporterConfig(urdf_path=str(urdf),usd_path=str(od),fix_base=True,collision_from_visuals=True,collision_type='Convex Hull',joint_drive_type='force',joint_target_type='position',override_joint_stiffness=100.0,override_joint_damping=10.0)
  usd=URDFImporter(cfg).import_urdf(); omni.usd.get_context().open_stage(usd); app.update(); st=omni.usd.get_context().get_stage(); joints=[x for x in Usd.PrimRange(st.GetPseudoRoot()) if x.IsA(UsdPhysics.RevoluteJoint)]
  # Drive targets only; no transform writes. Five in-range targets plus one out-of-range target per revolute joint.
  trial=[]; timeline=omni.timeline.get_timeline_interface(); timeline.play()
  for j in joints:
   lo,hi=UsdPhysics.RevoluteJoint(j).GetLowerLimitAttr().Get(),UsdPhysics.RevoluteJoint(j).GetUpperLimitAttr().Get(); drive=UsdPhysics.DriveAPI.Get(j,'angular'); targets=[lo+(hi-lo)*i/4 for i in range(5)]+[hi+abs(hi-lo)*0.1]
   for target in targets:
    drive.GetTargetPositionAttr().Set(target)
    for _ in range(30): app.update()
    trial.append({'joint':str(j.GetPath()),'target':target,'lower':lo,'upper':hi})
  timeline.stop(); app.update()
  expected_revolute = len(mov) - 1
  if len(joints) != expected_revolute:
   raise RuntimeError(f'USD physics-joint visibility failure for {oid}: expected {expected_revolute} revolute joints, found {len(joints)}')
  out[oid]={'urdf':str(urdf),'usd':str(usd),'revolute_joint_count':len(joints),'trials':trial,'controlled_settings':{'mass_kg_per_link':1.0,'diagonal_inertia_kg_m2':[1,1,1],'drive_stiffness':100.0,'drive_damping':10.0,'collision':'URDF collision mesh plus importer Convex Hull'}}
 json.dump(out,open(Path(a.stage)/'result.json','w'),indent=2)
 print('GT_ONLY_CONTROL=PASS')
finally: app.close()
PY
env -u CUDA_VISIBLE_DEVICES -u CONDA_PREFIX -u CONDA_DEFAULT_ENV HOME="$ISAAC/runtime-home" XDG_CACHE_HOME="$ISAAC/runtime-home/cache" XDG_CONFIG_HOME="$ISAAC/runtime-home/config" XDG_DATA_HOME="$ISAAC/runtime-home/data" "$ISAAC/python.sh" "$STAGE/gt_only_control.py" --stage "$STAGE" --root "$ROOT" >"$LOG/child.stdout.log" 2>"$LOG/child.stderr.log" || rc=$?
rc=${rc:-0}; printf '%s\n' "$rc" > "$LOG/exit_code.txt"; [ "$rc" -eq 0 ] && rg -qx 'GT_ONLY_CONTROL=PASS' "$LOG/child.stdout.log"
