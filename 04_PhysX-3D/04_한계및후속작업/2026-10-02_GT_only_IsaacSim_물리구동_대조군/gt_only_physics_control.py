"""Drive existing GT-only USD variants; it never converts URDF or uses predictions."""
import argparse, hashlib, json, math
from pathlib import Path
from isaacsim import SimulationApp

print("GT_ONLY_PHYSICS_SCRIPT_IMPORTED", flush=True)

CASES = {"10163": ("physx", 1), "29806": ("physx", 3), "29354": ("physics", 0)}
FRAMES, RESETS, ROUND_TRIPS = 30, 3, 10
FOLLOWER_TOLERANCE_DEG, RANGE_TOLERANCE_DEG = 1.0, 2.0

def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for data in iter(lambda: source.read(1 << 20), b""): digest.update(data)
    return digest.hexdigest()

def finite(value):
    try: return all(math.isfinite(float(x)) for x in value)
    except TypeError: return value is not None and math.isfinite(float(value))

def update(app, n):
    for _ in range(n): app.update()

def advance_physics(app, manager, frames):
    """Advance PhysX through the Isaac 6.1 manager; never authors a transform."""
    before = manager.get_num_physics_steps()
    manager.step(steps=frames, update_fabric=False)
    update(app, 1)
    after = manager.get_num_physics_steps()
    if after <= before:
        raise RuntimeError(f"physics step did not advance ({before}->{after})")
    return before, after

def rigid_transforms(prims, xformable, time_code):
    result = {}
    for prim in prims:
        matrix = xformable(prim).ComputeLocalToWorldTransform(time_code)
        values = [float(matrix[row][col]) for row in range(4) for col in range(4)]
        if not finite(values):
            raise RuntimeError(f"non-finite rigid transform: {prim.GetPath()}")
        result[str(prim.GetPath())] = values
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--input-stage", type=Path, required=True)
    p.add_argument("--stage", type=Path, required=True)
    p.add_argument("--case", choices=sorted(CASES), help="Run one GT control case only.")
    a = p.parse_args(); a.stage.mkdir(parents=True, exist_ok=True)
    exp = a.root / "repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-02_IsaacSim_PhysicsScene_등록Smoke/isaac_physics_scene_smoke.kit"
    app = SimulationApp({"headless":True, "active_cuda_gpus":[0], "physics_gpu":0, "multi_gpu":False,
                         "extra_args":["--/renderer/multiGpu/enabled=false","--/renderer/multiGpu/autoEnable=false"]}, experience=str(exp))
    print("GT_ONLY_PHYSICS_APP_READY", flush=True)
    try:
        import omni.timeline, omni.usd
        from isaacsim.core.simulation_manager import PhysxScene, SimulationManager
        from pxr import Gf, PhysxSchema, Usd, UsdGeom, UsdPhysics
        report = {"scope":"GT-only converter/simulator control; not an AI prediction result",
          "settings":{"gpu":1,"multi_gpu":False,"frames_per_target":FRAMES,"resets":RESETS,"round_trips":ROUND_TRIPS,
          "follower_tolerance_deg":FOLLOWER_TOLERANCE_DEG,"range_tolerance_deg":RANGE_TOLERANCE_DEG,
          "mass_inertia_friction":"controlled experimental settings from existing importer output; no generated-output property used",
          "drive_source":"existing importer USD position/force drive with finite authored stiffness, damping, effort",
          "success_criteria":"runtime PhysicsScene registration, composed-schema preflight, finite joint/rigid states, manager step advance, nonzero in-range joint response, and a finite separately recorded out-of-range trial",
          "failure_criteria":"missing composed schema, absent runtime scene/step advance, non-finite state/transform, no observable in-range response, or child exception"},
          "cases":{}}
        timeline = omni.timeline.get_timeline_interface()
        selected_cases = {a.case: CASES[a.case]} if a.case else CASES
        for oid, (choice, expected) in selected_cases.items():
            print(f"GT_ONLY_PHYSICS_CASE_START={oid}", flush=True)
            usd = a.input_stage / oid / f"gt_{oid}" / f"gt_{oid}.usda"
            ctx = omni.usd.get_context(); ctx.open_stage(str(usd)); update(app, 2)
            print(f"GT_ONLY_PHYSICS_STAGE_OPENED={oid}", flush=True)
            stage = ctx.get_stage(); root = stage.GetDefaultPrim()
            variants = root.GetVariantSets().GetVariantSet("Physics")
            if not variants.IsValid() or choice not in variants.GetVariantNames(): raise RuntimeError(f"{oid}: missing Physics={choice}")
            variants.SetVariantSelection(choice); update(app, 2)
            print(f"GT_ONLY_PHYSICS_VARIANT_SELECTED={oid}:{choice}", flush=True)
            old_target = stage.GetEditTarget()
            stage.SetEditTarget(Usd.EditTarget(stage.GetSessionLayer()))
            runtime_scene = PhysxScene("/World/GTOnlyRuntimePhysicsScene")
            runtime_scene.set_gravity((0.0, 0.0, -9.81))
            runtime_scene.set_dt(1.0 / 60.0)
            stage.SetEditTarget(old_target)
            update(app, 1)
            SimulationManager.setup_simulation(dt=1.0 / 60.0, device="cuda:0")
            SimulationManager.initialize_physics()
            physics_steps_before = SimulationManager.get_num_physics_steps()
            SimulationManager.step(steps=1, update_fabric=False)
            update(app, 1)
            physics_steps_after = SimulationManager.get_num_physics_steps()
            if physics_steps_after <= physics_steps_before:
                raise RuntimeError(f"{oid}: runtime PhysicsScene did not advance manager step counter")
            print(f"GT_ONLY_PHYSICS_RUNTIME_SCENE_READY={oid}:{physics_steps_before}->{physics_steps_after}", flush=True)
            pred = Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate)
            prims = list(Usd.PrimRange(stage.GetPseudoRoot(), pred))
            print(f"GT_ONLY_PHYSICS_TRAVERSED={oid}", flush=True)
            revolute = [x for x in prims if x.IsA(UsdPhysics.RevoluteJoint)]
            generic = [x for x in prims if x.IsA(UsdPhysics.Joint)]
            art = [x for x in prims if x.HasAPI(UsdPhysics.ArticulationRootAPI)]
            rigid = [x for x in prims if x.HasAPI(UsdPhysics.RigidBodyAPI)]
            collider = [x for x in prims if x.HasAPI(UsdPhysics.CollisionAPI)]
            print(f"GT_ONLY_PHYSICS_COUNTS={oid}:rev={len(revolute)},art={len(art)},rigid={len(rigid)},collider={len(collider)}", flush=True)
            preflight_ok = len(revolute) == expected and bool(art) and bool(rigid) and bool(collider)
            print(f"GT_ONLY_PHYSICS_PREFLIGHT={oid}:{preflight_ok}", flush=True)
            if not preflight_ok:
                raise RuntimeError(f"{oid}: stage preflight rev={len(revolute)} expected={expected} art={len(art)} rigid={len(rigid)} collider={len(collider)}")
            print(f"GT_ONLY_PHYSICS_PRE_CASE={oid}", flush=True)
            case = {"usd":str(usd),"usd_sha256":sha256(usd),"variant":choice,
              "preflight":{"revolute":len(revolute),"generic_joints":len(generic),"articulation_roots":len(art),"rigid_bodies":len(rigid),
              "colliders_including_instance_proxies":len(collider),"collider_paths":[str(x.GetPath()) for x in collider],
              "contact":"No intentional contact pair; collider API presence and per-step rigid-body transforms recorded. Contact force telemetry is not asserted."}}
            case["runtime_physics_scene"]={"path":runtime_scene.path,"layer":"session (not saved to imported USD)","step_counter_before":physics_steps_before,"step_counter_after":physics_steps_after}
            physics_device = str(SimulationManager.get_physics_sim_device())
            case["control_backend"] = {
                "physics_device": physics_device,
                "usd_drive_target_authoring": "not_started",
            }
            print(f"GT_ONLY_PHYSICS_CASE_READY={oid}", flush=True)
            if not revolute:
                timeline.play(); update(app, FRAMES * 3); timeline.stop(); update(app, 1)
                case["fixed_control"]={"no_revolute_joint":True,"physics_frames":FRAMES*3}
                report["cases"][oid]=case; continue
            if physics_device.startswith("cuda"):
                # Isaac/PhysX direct GPU API rejects authoring a USD DriveAPI target while
                # the scene is running.  Refuse to repeat that invalid control path; a
                # separately audited tensor ArticulationView controller is required.
                case["control_backend"]["block_reason"] = (
                    "GPU direct API forbids runtime USD PhysicsDriveAPI target authoring; "
                    "do not issue DriveAPI.Set(target) in this runner"
                )
                report["cases"][oid] = case
                (a.stage/"physics_drive_report.json").write_text(json.dumps(report,indent=2,default=str)+"\\n")
                raise RuntimeError(
                    f"{oid}: blocked before drive command: GPU direct API requires an "
                    "audited tensor ArticulationView control path"
                )
            trials = {}
            for joint in revolute:
                print(f"GT_ONLY_PHYSICS_JOINT_START={oid}:{joint.GetName()}", flush=True)
                name = joint.GetName(); drive = UsdPhysics.DriveAPI.Get(joint,"angular")
                print(f"GT_ONLY_PHYSICS_DRIVE_READY={oid}:{name}", flush=True)
                state = PhysxSchema.JointStateAPI.Apply(joint,"angular")
                print(f"GT_ONLY_PHYSICS_DRIVE_STATE_READY={oid}:{name}", flush=True)
                lo, hi = UsdPhysics.RevoluteJoint(joint).GetLowerLimitAttr().Get(), UsdPhysics.RevoluteJoint(joint).GetUpperLimitAttr().Get()
                stiffness, damping, effort = drive.GetStiffnessAttr().Get(), drive.GetDampingAttr().Get(), drive.GetMaxForceAttr().Get()
                if not all(finite(x) for x in (lo,hi,stiffness,damping,effort)) or hi <= lo: raise RuntimeError(f"{oid}/{name}: invalid finite drive")
                resets=[]
                for reset_index in range(RESETS):
                    drive.GetTargetPositionAttr().Set(0.0)
                    step_before, step_after = advance_physics(app, SimulationManager, FRAMES)
                    resets.append({"reset_index":reset_index,"position_deg":state.GetPositionAttr().Get(),"velocity_deg_s":state.GetVelocityAttr().Get(),"step_before":step_before,"step_after":step_after,
                                   "rigid_body_world_transforms":rigid_transforms(rigid, UsdGeom.Xformable, Usd.TimeCode.Default())})
                target5=[lo+(hi-lo)*i/4 for i in range(5)]
                commands=(target5+target5[-2::-1])*ROUND_TRIPS
                samples=[]
                for command_index, target in enumerate(commands):
                    drive.GetTargetPositionAttr().Set(target)
                    step_before, step_after = advance_physics(app, SimulationManager, FRAMES)
                    pos,vel=state.GetPositionAttr().Get(),state.GetVelocityAttr().Get()
                    other={x.GetName():PhysxSchema.JointStateAPI.Apply(x,"angular").GetPositionAttr().Get() for x in revolute if x != joint}
                    if not finite(pos) or not finite(vel) or not all(finite(v) for v in other.values()): raise RuntimeError(f"{oid}/{name}: non-finite state")
                    samples.append({"command_index":command_index,"target_deg":target,"position_deg":pos,"velocity_deg_s":vel,"other_joint_positions_deg":other,"step_before":step_before,"step_after":step_after,
                                    "rigid_body_world_transforms":rigid_transforms(rigid, UsdGeom.Xformable, Usd.TimeCode.Default())})
                outside=hi+abs(hi-lo)*.1; drive.GetTargetPositionAttr().Set(outside)
                outside_step_before, outside_step_after = advance_physics(app, SimulationManager, FRAMES)
                outside_pos=state.GetPositionAttr().Get()
                if not finite(outside_pos): raise RuntimeError(f"{oid}/{name}: non-finite out-of-range state")
                follower=max((abs(float(v)) for row in samples for v in row["other_joint_positions_deg"].values()),default=0.0)
                response_span=max(float(row["position_deg"]) for row in samples)-min(float(row["position_deg"]) for row in samples)
                if abs(response_span) < 1.0:
                    raise RuntimeError(f"{oid}/{name}: no observable in-range joint response (span={response_span} deg)")
                trials[name]={"path":str(joint.GetPath()),"axis":str(UsdPhysics.RevoluteJoint(joint).GetAxisAttr().Get()),
                    "limits_deg":[lo,hi],"drive":{"stiffness":stiffness,"damping":damping,"max_force":effort},
                    "initializations":resets,"in_range_targets_deg":target5,"round_trips":ROUND_TRIPS,"samples":samples,
                    "out_of_range":{"target_deg":outside,"position_deg":outside_pos,"step_before":outside_step_before,"step_after":outside_step_after,"within_limit_plus_tolerance":outside_pos<=hi+RANGE_TOLERANCE_DEG},
                    "response_span_deg":response_span,
                    "other_joint_max_abs_position_deg":follower,"other_joint_within_tolerance":follower<=FOLLOWER_TOLERANCE_DEG}
            case["joint_trials"]=trials; report["cases"][oid]=case
        (a.stage/"physics_drive_report.json").write_text(json.dumps(report,indent=2,default=str)+"\n")
        print("GT_ONLY_PHYSICS_CONTROL=PASS")
    finally: app.close()

if __name__ == "__main__":
    import traceback
    print("GT_ONLY_PHYSICS_MAIN_ENTERED", flush=True)
    try:
        raise SystemExit(main())
    except BaseException:
        traceback.print_exc()
        raise
