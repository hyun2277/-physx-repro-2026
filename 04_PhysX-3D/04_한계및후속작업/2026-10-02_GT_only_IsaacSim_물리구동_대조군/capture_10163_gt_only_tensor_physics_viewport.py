"""10163 GT-only PhysX drive via Isaac's initialized Warp tensor view; never authors USD targets/transforms."""
import argparse, hashlib, json, math, traceback
from pathlib import Path
from isaacsim import SimulationApp

TARGETS=(-1.2,-0.6,0.0,0.6,1.2); SETTLE_STEPS=30; RESET_STEPS=60; OUTSIDE_STEPS=60

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
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); ap.add_argument('--input-usd',type=Path,required=True); ap.add_argument('--stage',type=Path,required=True); ap.add_argument('--frames',type=Path,required=True); a=ap.parse_args(); a.stage.mkdir(parents=True,exist_ok=True); a.frames.mkdir(parents=True,exist_ok=True)
 exp=a.root/'repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-02_IsaacSim_GPU_ArticulationTensor_ControlSmoke/isaac_gpu_articulation_tensor_smoke.kit'
 app=SimulationApp({'headless':True,'active_cuda_gpus':[0],'physics_gpu':0,'multi_gpu':False,'extra_args':['--/renderer/multiGpu/enabled=false','--/renderer/multiGpu/autoEnable=false']},experience=str(exp))
 print('GT_TENSOR_DRIVE_APP_READY',flush=True)
 try:
  import omni.usd, warp as wp, omni.kit.app
  from isaacsim.core.simulation_manager import PhysxScene,SimulationManager
  from pxr import Gf,Sdf,Usd,UsdPhysics
  ctx=omni.usd.get_context(); ctx.open_stage(str(a.input_usd)); app.update();app.update();
  mgr=omni.kit.app.get_app().get_extension_manager(); mgr.set_extension_enabled_immediate('omni.kit.renderer.capture',True); [app.update() for _ in range(8)]
  import omni.kit.renderer_capture
  capture_iface=omni.kit.renderer_capture.acquire_renderer_capture_interface(); capture_count=0; stage=ctx.get_stage(); root=stage.GetDefaultPrim(); vs=root.GetVariantSets().GetVariantSet('Physics'); vs.SetVariantSelection('physx'); app.update()
  old=stage.GetEditTarget(); session=stage.GetSessionLayer();stage.SetEditTarget(Usd.EditTarget(session))
  # Runtime-only controlled material settings: ensure all dynamic links have finite positive mass/inertia.
  runtime_rigid=[p for p in stage.Traverse() if p.HasAPI(UsdPhysics.RigidBodyAPI)]
  for body in runtime_rigid:
   mass=UsdPhysics.MassAPI.Apply(body);mass.CreateMassAttr().Set(1.0);mass.CreateDiagonalInertiaAttr().Set(Gf.Vec3f(0.1,0.1,0.1));mass.CreatePrincipalAxesAttr().Set(Gf.Quatf(1.0,Gf.Vec3f(0,0,0)))
  scene=PhysxScene('/World/GTOnlyRuntimePhysicsScene');scene.set_gravity((0,0,-9.81));scene.set_dt(1/60);stage.SetEditTarget(old);app.update()
  if not session.GetPrimAtPath(Sdf.Path(scene.path)):raise RuntimeError('session PhysicsScene missing')
  SimulationManager.setup_simulation(dt=1/60,device='cuda:0');SimulationManager.initialize_physics(); b=SimulationManager.get_num_physics_steps();SimulationManager.step(steps=1,update_fabric=False);app.update(); c=SimulationManager.get_num_physics_steps()
  if c<=b:raise RuntimeError('PhysicsScene did not advance')
  pred=Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate);prims=list(Usd.PrimRange(stage.GetPseudoRoot(),pred)); rev=[p for p in prims if p.IsA(UsdPhysics.RevoluteJoint)];arts=[p for p in prims if p.HasAPI(UsdPhysics.ArticulationRootAPI)];rigid=[p for p in prims if p.HasAPI(UsdPhysics.RigidBodyAPI)];coll=[p for p in prims if p.HasAPI(UsdPhysics.CollisionAPI)]
  if len(rev)!=1 or len(arts)!=1 or not rigid or not coll:raise RuntimeError(f'preflight rev={len(rev)} art={len(arts)} rigid={len(rigid)} collider={len(coll)}')
  view=SimulationManager.get_physics_simulation_view()
  if view is None:raise RuntimeError('initialized Warp simulation view unavailable')
  av=view.create_articulation_view([str(arts[0].GetPath())])
  if av.count!=1 or av.max_dofs!=1:raise RuntimeError(f'articulation count/dof {av.count}/{av.max_dofs}')
  meta=av.get_metatype(0)
  if meta.dof_count!=1:raise RuntimeError(f'dof count {meta.dof_count}')
  name=meta.dof_names[0];idx=meta.dof_indices[name];limits=av.get_dof_limits();lo,hi=[float(x) for x in vals(limits)[0][idx]]
  drive=UsdPhysics.DriveAPI.Get(rev[0],'angular');settings={'stiffness':drive.GetStiffnessAttr().Get(),'damping':drive.GetDampingAttr().Get(),'max_force':drive.GetMaxForceAttr().Get()}
  if not all(math.isfinite(float(v)) for v in settings.values()) or not (lo<min(TARGETS)<max(TARGETS)<hi):raise RuntimeError('finite drive or target range precondition failed')
  report={'scope':'10163 GT-only controlled-material joint drive; not AI prediction. Tensor target control only: no USD target writes or transform/keyframe authoring.','input_usd':str(a.input_usd),'input_sha256':digest(a.input_usd),'variant':vs.GetVariantSelection(),'runtime_scene':scene.path,'physics_device':SimulationManager.get_physics_sim_device(),'preflight':{'revolute':len(rev),'articulation_root':str(arts[0].GetPath()),'rigid_bodies':len(rigid),'colliders':len(coll),'dof_name':name,'dof_index':idx,'limits_rad':[lo,hi]},'drive_settings_from_imported_usd':settings,'controlled_material_settings':'Session-layer-only experimental override before physics initialization: every rigid body mass=1.0 kg, diagonal inertia=(0.1,0.1,0.1) kg*m^2, principal axes identity. Existing imported colliders and finite drive settings are retained; no generated output used.','success_criteria':'finite every-step DOF/link state; step counters advance; all in-range positions remain within limits; observable in-range response; fixed-base link stays bounded; out-of-range request separately recorded.','failure_criteria':'missing composed schema, no step advance, non-finite state/link, range escape, base/link divergence, or no observable in-range response.','records':[],'viewport_capture':'Renderer capture frames are taken only after actual Tensor-target PhysicsManager steps; no object transform/keyframe authoring.','contact':'No intentional contact pair. Collider API presence and finite link transforms are checked; contact force telemetry is not asserted.'}
  base_links=None
  nonlocal_capture=[0]
  def command(label,target,steps):
   nonlocal base_links
   current=av.get_dof_position_targets(); tv=vals(current);tv[0][idx]=target;targets=wp.array(tv,dtype=wp.float32,device=current.device);indices=wp.array([0],dtype=wp.uint32,device=targets.device);av.set_dof_position_targets(targets,indices);readback=float(vals(av.get_dof_position_targets())[0][idx]);
   if abs(readback-target)>1e-5:raise RuntimeError(f'target readback mismatch {readback} vs {target}')
   for step in range(steps):
    before=SimulationManager.get_num_physics_steps();SimulationManager.step(steps=1,update_fabric=False);app.update();after=SimulationManager.get_num_physics_steps();pos=av.get_dof_positions();vel=av.get_dof_velocities();links=av.get_link_transforms()
    if after<=before or not finite(pos,vel,links):raise RuntimeError('non-finite/no-step state')
    lv=vals(links)
    if base_links is None:base_links=lv
    if any(abs(v)>100 for v in flat(lv)):raise RuntimeError('link transform divergence')
    report['records'].append({'phase':label,'requested_target_rad':target,'target_readback_rad':readback,'step':step,'manager_steps':[before,after],'position_rad':float(vals(pos)[0][idx]),'velocity_rad_s':float(vals(vel)[0][idx]),'link_transforms':lv})
   if step==steps-1 and (label.startswith('initialization') or label.startswith('in_range_roundtrip_') and label.endswith(('_0','_4','_9'))):
    nonlocal_capture[0]+=1; capture_iface.capture_next_frame_swapchain(str(a.frames/f'frame_{nonlocal_capture[0]:03d}.png')); [app.update() for _ in range(4)]
  for n in range(3):command(f'initialization_{n}',0.0,RESET_STEPS)
  cycle=list(TARGETS)+list(TARGETS[-2:0:-1])
  for trip in range(10):
   for t in cycle:command(f'in_range_roundtrip_{trip}',t,SETTLE_STEPS)
  command('out_of_range',hi+0.2,OUTSIDE_STEPS)
  ins=[r for r in report['records'] if r['phase'].startswith('in_range')];out=[r for r in report['records'] if r['phase']=='out_of_range'];positions=[r['position_rad'] for r in ins];span=max(positions)-min(positions);allpos=[r['position_rad'] for r in report['records']];report['checks']={'in_range_count':len(ins),'initialization_count':sum(r['phase'].startswith('initialization') for r in report['records']),'out_of_range_count':len(out),'in_range_response_span_rad':span,'all_positions_within_limit_plus_0.05':min(allpos)>=lo-.05 and max(allpos)<=hi+.05,'out_of_range_final_position_rad':out[-1]['position_rad'],'finite':True,'control_mode':'tensor position target (not USD DriveAPI authoring)'}
  if span<0.05:raise RuntimeError(f'no observable drive response span={span}')
  if not report['checks']['all_positions_within_limit_plus_0.05']:raise RuntimeError('joint position escaped range tolerance')
  (a.stage/'physics_drive_report.json').write_text(json.dumps(report,indent=2)+'\n');print('GT_TENSOR_DRIVE=PASS',flush=True);return 0
 except BaseException:
  traceback.print_exc();raise
 finally: app.close()
if __name__=='__main__':raise SystemExit(main())
