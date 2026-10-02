"""29806 GT-only three-door PhysX drive via Isaac Warp tensors; never authors USD targets/transforms."""
import argparse, hashlib, json, math, traceback
from pathlib import Path
from isaacsim import SimulationApp

SETTLE_STEPS=30; RESET_STEPS=60; OUTSIDE_STEPS=60; FOLLOWER_TOL_RAD=0.10; ROOT_DRIFT_M=0.05

def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def vals(a): return a.numpy().tolist()
def flat(x):
 if isinstance(x,list):
  for y in x: yield from flat(y)
 else: yield float(x)
def finite(*arrays): return all(math.isfinite(v) for a in arrays for v in flat(vals(a)))
def in_targets(lo,hi):
 width=hi-lo
 return [lo+width*q for q in (.15,.325,.5,.675,.85)]
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); ap.add_argument('--input-usd',type=Path,required=True); ap.add_argument('--stage',type=Path,required=True); a=ap.parse_args(); a.stage.mkdir(parents=True,exist_ok=True)
 exp=a.root/'repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-02_IsaacSim_GPU_ArticulationTensor_ControlSmoke/isaac_gpu_articulation_tensor_smoke.kit'
 app=SimulationApp({'headless':True,'active_cuda_gpus':[0],'physics_gpu':0,'multi_gpu':False,'extra_args':['--/renderer/multiGpu/enabled=false','--/renderer/multiGpu/autoEnable=false']},experience=str(exp))
 print('GT_TENSOR_DRIVE_29806_APP_READY',flush=True)
 try:
  import omni.usd, warp as wp
  from isaacsim.core.simulation_manager import PhysxScene,SimulationManager
  from pxr import Gf,Sdf,Usd,UsdPhysics
  ctx=omni.usd.get_context(); ctx.open_stage(str(a.input_usd)); app.update(); app.update(); stage=ctx.get_stage()
  root=stage.GetDefaultPrim(); vs=root.GetVariantSets().GetVariantSet('Physics'); vs.SetVariantSelection('physx'); app.update()
  old=stage.GetEditTarget(); session=stage.GetSessionLayer(); stage.SetEditTarget(Usd.EditTarget(session))
  runtime_rigid=[p for p in stage.Traverse() if p.HasAPI(UsdPhysics.RigidBodyAPI)]
  for body in runtime_rigid:
   mass=UsdPhysics.MassAPI.Apply(body); mass.CreateMassAttr().Set(1.0); mass.CreateDiagonalInertiaAttr().Set(Gf.Vec3f(.1,.1,.1)); mass.CreatePrincipalAxesAttr().Set(Gf.Quatf(1.0,Gf.Vec3f(0,0,0)))
  scene=PhysxScene('/World/GTOnlyRuntimePhysicsScene'); scene.set_gravity((0,0,-9.81)); scene.set_dt(1/60); stage.SetEditTarget(old); app.update()
  if not session.GetPrimAtPath(Sdf.Path(scene.path)): raise RuntimeError('session PhysicsScene missing')
  SimulationManager.setup_simulation(dt=1/60,device='cuda:0'); SimulationManager.initialize_physics()
  before=SimulationManager.get_num_physics_steps(); SimulationManager.step(steps=1,update_fabric=False); app.update(); after=SimulationManager.get_num_physics_steps()
  if after<=before: raise RuntimeError('PhysicsScene did not advance')
  pred=Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate); prims=list(Usd.PrimRange(stage.GetPseudoRoot(),pred))
  rev=[p for p in prims if p.IsA(UsdPhysics.RevoluteJoint)]; arts=[p for p in prims if p.HasAPI(UsdPhysics.ArticulationRootAPI)]; rigid=[p for p in prims if p.HasAPI(UsdPhysics.RigidBodyAPI)]; coll=[p for p in prims if p.HasAPI(UsdPhysics.CollisionAPI)]
  if len(rev)!=3 or len(arts)!=1 or not rigid or not coll: raise RuntimeError(f'preflight rev={len(rev)} art={len(arts)} rigid={len(rigid)} collider={len(coll)}')
  view=SimulationManager.get_physics_simulation_view()
  if view is None: raise RuntimeError('initialized Warp simulation view unavailable')
  av=view.create_articulation_view([str(arts[0].GetPath())])
  if av.count!=1 or av.max_dofs!=3: raise RuntimeError(f'articulation count/dof {av.count}/{av.max_dofs}')
  meta=av.get_metatype(0)
  if meta.dof_count!=3: raise RuntimeError(f'dof count {meta.dof_count}')
  names=list(meta.dof_names); indices=[meta.dof_indices[n] for n in names]
  if len(set(indices))!=3: raise RuntimeError(f'nonunique dof indices {indices}')
  limits_all=vals(av.get_dof_limits())[0]; limits={n:[float(x) for x in limits_all[i]] for n,i in zip(names,indices)}
  if not all(lo<hi and math.isfinite(lo) and math.isfinite(hi) for lo,hi in limits.values()): raise RuntimeError(f'invalid limits {limits}')
  drive_by_joint={}
  for joint in rev:
   d=UsdPhysics.DriveAPI.Get(joint,'angular'); drive_by_joint[joint.GetName()]={'stiffness':d.GetStiffnessAttr().Get(),'damping':d.GetDampingAttr().Get(),'max_force':d.GetMaxForceAttr().Get()}
  if not all(math.isfinite(float(v)) for d in drive_by_joint.values() for v in d.values()): raise RuntimeError('nonfinite imported drive setting')
  neutral={n:(limits[n][0]+limits[n][1])/2 for n in names}
  report={'scope':'29806 GT-only controlled-material three-door joint drive; not AI prediction. Tensor position targets only: no USD PhysicsDrive target writes or transform/keyframe authoring.','input_usd':str(a.input_usd),'input_sha256':digest(a.input_usd),'variant':vs.GetVariantSelection(),'runtime_scene':scene.path,'physics_device':SimulationManager.get_physics_sim_device(),'preflight':{'revolute':len(rev),'revolute_paths':[str(x.GetPath()) for x in rev],'articulation_root':str(arts[0].GetPath()),'rigid_bodies':len(rigid),'colliders':len(coll),'dof_names':names,'dof_indices':indices,'limits_rad':limits},'drive_settings_from_imported_usd':drive_by_joint,'controlled_material_settings':'Session-layer-only controlled experimental override before physics initialization: every rigid body mass=1.0 kg, diagonal inertia=(0.1,0.1,0.1) kg*m^2, principal axes identity. Existing imported colliders and finite drive settings retained; no generated output used.','success_criteria':f'finite every-step DOF/link state; steps advance; all positions within limits ±0.05 rad; active response >=0.05 rad; non-active DOF drift <= {FOLLOWER_TOL_RAD} rad after neutral settling; root translation drift <= {ROOT_DRIFT_M} m; out-of-range requests separately recorded.','contact':'No intentional contact pair. Collider API presence and finite/bounded link transforms are checked; contact-force telemetry is not asserted.','joints':{},'all_records':[]}
  def set_targets(target_map):
   current=vals(av.get_dof_position_targets()); target_values=current[0]
   for n,target in target_map.items(): target_values[meta.dof_indices[n]]=target
   target_arr=wp.array([target_values],dtype=wp.float32,device=av.get_dof_position_targets().device); idxarr=wp.array([0],dtype=wp.uint32,device=target_arr.device); av.set_dof_position_targets(target_arr,idxarr)
   read=vals(av.get_dof_position_targets())[0]
   for n,target in target_map.items():
    if abs(float(read[meta.dof_indices[n]])-target)>1e-5: raise RuntimeError(f'target readback mismatch {n}')
   return {n:float(read[meta.dof_indices[n]]) for n in names}
  def step_record(phase,active,target,steps,baseline_pos=None,baseline_links=None):
   read=set_targets({**neutral,active:target})
   rows=[]
   for k in range(steps):
    b=SimulationManager.get_num_physics_steps(); SimulationManager.step(steps=1,update_fabric=False); c=SimulationManager.get_num_physics_steps(); pos=av.get_dof_positions(); vel=av.get_dof_velocities(); links=av.get_link_transforms()
    if c<=b or not finite(pos,vel,links): raise RuntimeError('non-finite/no-step state')
    lv=vals(links)
    if any(abs(v)>100 for v in flat(lv)): raise RuntimeError('link transform divergence')
    pv=vals(pos)[0]; vv=vals(vel)[0]
    row={'phase':phase,'active_dof':active,'requested_target_rad':target,'target_readback_rad':read[active],'step':k,'manager_steps':[b,c],'positions_rad':{n:float(pv[meta.dof_indices[n]]) for n in names},'velocities_rad_s':{n:float(vv[meta.dof_indices[n]]) for n in names},'link_transforms':lv}
    rows.append(row); report['all_records'].append(row)
   return rows
  for active in names:
   joint_report={'dof':active,'limits_rad':limits[active],'in_range_targets_rad':in_targets(*limits[active]),'initializations':[],'roundtrips':[],'out_of_range':None}
   # Re-establish a common neutral state before every independently driven door.
   for init in range(3): joint_report['initializations'].extend(step_record(f'{active}:initialization_{init}',active,neutral[active],RESET_STEPS))
   baseline_pos=joint_report['initializations'][-1]['positions_rad']; baseline_links=joint_report['initializations'][-1]['link_transforms']
   cycle=joint_report['in_range_targets_rad']+joint_report['in_range_targets_rad'][-2:0:-1]
    # Keep all actual trace rows, with each commanded target distinct.
   joint_report['roundtrips']=[]
   for trip in range(10):
    for target in cycle: joint_report['roundtrips'].extend(step_record(f'{active}:in_range_roundtrip_{trip}',active,target,SETTLE_STEPS,baseline_pos,baseline_links))
   hi=limits[active][1]; joint_report['out_of_range']=step_record(f'{active}:out_of_range',active,hi+.2,OUTSIDE_STEPS,baseline_pos,baseline_links)
   inrows=joint_report['roundtrips']; active_vals=[r['positions_rad'][active] for r in inrows]; other=[n for n in names if n!=active]
   follower={n:max(abs(r['positions_rad'][n]-baseline_pos[n]) for r in inrows) for n in other}
   root_translation_drift=max(math.dist(r['link_transforms'][0][0][:3],baseline_links[0][0][:3]) for r in inrows) if baseline_links and inrows else float('inf')
   allrows=joint_report['initializations']+inrows+joint_report['out_of_range']; lo,upper=limits[active]
   checks={'in_range_record_count':len(inrows),'initialization_record_count':len(joint_report['initializations']),'out_of_range_record_count':len(joint_report['out_of_range']),'active_response_span_rad':max(active_vals)-min(active_vals),'all_dof_within_own_limit_plus_0.05':all(limits[n][0]-.05<=r['positions_rad'][n]<=limits[n][1]+.05 for r in allrows for n in names),'non_active_dof_max_delta_from_settled_neutral_rad':follower,'non_active_dof_within_follower_tolerance':all(x<=FOLLOWER_TOL_RAD for x in follower.values()),'root_link_max_translation_drift_m':root_translation_drift,'root_within_drift_tolerance':root_translation_drift<=ROOT_DRIFT_M,'out_of_range_final_position_rad':joint_report['out_of_range'][-1]['positions_rad'][active],'finite':True}
   joint_report['checks']=checks
   if checks['active_response_span_rad']<.05: raise RuntimeError(f'{active}: no observable response')
   if not checks['all_dof_within_own_limit_plus_0.05']: raise RuntimeError(f'{active}: range escape')
   if not checks['non_active_dof_within_follower_tolerance']: raise RuntimeError(f'{active}: follower drift {follower}')
   if not checks['root_within_drift_tolerance']: raise RuntimeError(f'{active}: root drift {root_translation_drift}')
   report['joints'][active]=joint_report
  report['checks']={'joint_count':len(report['joints']),'all_joint_trials_passed':len(report['joints'])==3,'finite':True,'control_mode':'Warp omni.physics.tensors articulation position target (not USD DriveAPI authoring)'}
  (a.stage/'physics_drive_report.json').write_text(json.dumps(report,indent=2)+'\n'); print('GT_TENSOR_DRIVE_29806=PASS',flush=True); return 0
 except BaseException:
  traceback.print_exc(); raise
 finally: app.close()
if __name__=='__main__': raise SystemExit(main())
