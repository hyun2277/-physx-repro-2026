import argparse,json,math,hashlib
from pathlib import Path
from isaacsim import SimulationApp
p=argparse.ArgumentParser();p.add_argument('--root',type=Path);p.add_argument('--usd',type=Path);p.add_argument('--out',type=Path);a=p.parse_args();app=SimulationApp({'headless':True,'active_cuda_gpus':[0],'physics_gpu':0,'multi_gpu':False},experience=str(a.root/'repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-02_IsaacSim_GPU_ArticulationTensor_ControlSmoke/isaac_gpu_articulation_tensor_smoke.kit'))
try:
 import omni.usd
 from isaacsim.core.simulation_manager import PhysxScene,SimulationManager
 from pxr import Usd,UsdPhysics,Sdf
 c=omni.usd.get_context();c.open_stage(str(a.usd));[app.update() for _ in range(3)];st=c.get_stage();v=st.GetDefaultPrim().GetVariantSets().GetVariantSet('Physics');v.SetVariantSelection('physics');app.update();pr=list(Usd.PrimRange(st.GetPseudoRoot(),Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate)));rev=[x for x in pr if x.IsA(UsdPhysics.RevoluteJoint)];pri=[x for x in pr if x.IsA(UsdPhysics.PrismaticJoint)];art=[x for x in pr if x.HasAPI(UsdPhysics.ArticulationRootAPI)];rig=[x for x in pr if x.HasAPI(UsdPhysics.RigidBodyAPI)];col=[x for x in pr if x.HasAPI(UsdPhysics.CollisionAPI)];fix=[x for x in pr if x.IsA(UsdPhysics.FixedJoint)]
 if rev or pri or not art or not rig or not col:raise RuntimeError(f'preflight rev={len(rev)} pri={len(pri)} art={len(art)} rigid={len(rig)} col={len(col)}')
 old=st.GetEditTarget();se=st.GetSessionLayer();st.SetEditTarget(Usd.EditTarget(se));sc=PhysxScene('/World/GTOnlyRuntimePhysicsScene');sc.set_gravity((0,0,-9.81));sc.set_dt(1/60);st.SetEditTarget(old);SimulationManager.setup_simulation(dt=1/60,device='cuda:0');SimulationManager.initialize_physics();view=SimulationManager.get_physics_simulation_view();av=view.create_articulation_view([str(art[0].GetPath())]);
 if av.max_dofs!=0:raise RuntimeError(f'dof={av.max_dofs}')
 base=None;rows=[]
 for phase in range(3):
  for k in range(60):
   b=SimulationManager.get_num_physics_steps();SimulationManager.step(steps=1,update_fabric=False);pos=av.get_link_transforms().numpy().tolist();after=SimulationManager.get_num_physics_steps();flat=[float(z) for x in pos for y in x for z in y]
   if not all(math.isfinite(z) for z in flat) or after<=b:raise RuntimeError('nonfinite/no step')
   if base is None:base=pos
   drift=max(math.dist(x[0][:3],y[0][:3]) for x,y in zip(pos,base));rows.append({'phase':phase,'step':k,'manager':[b,after],'max_link_translation_drift_m':drift})
 d={'status':'PASS','scope':'29354 GT-only fixed passive PhysX control; not AI prediction; no joint target used.','variant':v.GetVariantSelection(),'preflight':{'revolute':len(rev),'prismatic':len(pri),'fixed_joints':len(fix),'articulation_roots':len(art),'rigid_bodies':len(rig),'colliders':len(col),'dof':av.max_dofs},'passive_steps':len(rows),'finite':True,'max_observed_link_translation_drift_m':max(x['max_link_translation_drift_m'] for x in rows),'anomaly':'none observed','records':rows};a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(d,indent=2));print('GT_FIXED_29354=PASS')
finally:app.close()
