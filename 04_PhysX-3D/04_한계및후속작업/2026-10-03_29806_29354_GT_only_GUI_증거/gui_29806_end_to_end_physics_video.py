"""GPU-0 GUI preflight for 29806 GT-only three-door physics capture.

Diagnostic visual meshes are authored once before physics initialization as
children of the real rigid bodies.  No clone transform, USD drive target, or
keyframe is authored after simulation begins.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import signal
import subprocess
import time
import traceback
from collections import deque
from pathlib import Path

from isaacsim import SimulationApp


INPUT_SHA256 = "5da6eb5823de2a8da1d7896ad047c8a73b2f25c79b60bd606afe912dd1b0891a"
URDF_SHA256 = "99ee19188ec969488e63ae2504f3ecf04f7de73071e523ec9e4f231fb68855c6"
# Fractions of each runtime-reported GT range: closed, middle, open, middle, closed.
TARGET_FRACTIONS = (0.10, 0.50, 0.90, 0.50, 0.10)
STEPS_PER_PRETEST_TARGET = 60
STEPS_PER_CAPTURE_TARGET = 90


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def nested_values(array):
    return array.numpy().tolist()


def flatten(value):
    if isinstance(value, list):
        for child in value:
            yield from flatten(child)
    else:
        yield float(value)


def finite_array(array) -> bool:
    return all(math.isfinite(value) for value in flatten(nested_values(array)))


def pose_delta(a, b):
    translation = math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))
    dot = abs(sum(float(a[3 + i]) * float(b[3 + i]) for i in range(4)))
    angle = 2.0 * math.acos(max(-1.0, min(1.0, dot)))
    return translation, angle


def matrix_values(value):
    return [[float(value[row][column]) for column in range(4)] for row in range(4)]


def transform7_matrix(value, Gf):
    x, y, z, qx, qy, qz, qw = [float(v) for v in value]
    result = Gf.Matrix4d(1.0)
    result.SetRotate(Gf.Quatd(qw, Gf.Vec3d(qx, qy, qz)))
    result.SetTranslateOnly(Gf.Vec3d(x, y, z))
    return matrix_values(result)


def authored_clone_xforms(clone_prims):
    result = {}
    for prim in clone_prims:
        result[str(prim.GetPath())] = {
            name: str(prim.GetAttribute(name).Get())
            for name in prim.GetPropertyNames()
            if name == "xformOpOrder" or name.startswith("xformOp:")
        }
    return result


def clone_time_samples(clone_prims):
    return sum(len(attr.GetTimeSamples()) for prim in clone_prims for attr in prim.GetAttributes())


def one_target(prim, relationship):
    values = prim.GetRelationship(relationship).GetTargets()
    if len(values) != 1:
        raise RuntimeError(f"{prim.GetPath()} {relationship} targets={list(map(str, values))}")
    return values[0]


def connected(graph, start, goal):
    queue, seen = deque([start]), {start}
    while queue:
        current = queue.popleft()
        if current == goal:
            return True
        for adjacent in graph.get(current, []):
            if adjacent not in seen:
                seen.add(adjacent); queue.append(adjacent)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--input-usd", type=Path, required=True)
    parser.add_argument("--input-urdf", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--capture-size", required=True)
    parser.add_argument("--capture-offset", default="0,0")
    parser.add_argument("--static-mapping-gate", action="store_true")
    args = parser.parse_args()
    args.run_dir.mkdir(parents=True, exist_ok=True)

    experience = args.root / (
        "repro-records/04_PhysX-3D/04_한계및후속작업/"
        "2026-10-03_29806_29354_GT_only_GUI_증거/"
        "isaac_gui_29806_gpu0_tensor_physics.kit"
    )
    app = SimulationApp(
        {
            "headless": False,
            "active_cuda_gpus": [0],
            "physics_gpu": 0,
            "multi_gpu": False,
            "extra_args": [
                "--/renderer/activeGpu=0",
                "--/physics/cudaDevice=0",
                "--/renderer/multiGpu/enabled=false",
                "--/renderer/multiGpu/autoEnable=false",
            ],
        },
        experience=str(experience),
    )
    report = {
        "scope": "29806 GT-only three-door GUI physics control; not AI prediction",
        "status": "RUNNING",
        "input_usd": str(args.input_usd),
        "physics_gpu": 0,
        "renderer_gpu": 0,
        "multi_gpu": False,
        "p2p_used": False,
        "usd_drive_target_authored_during_run": False,
        "transform_or_keyframe_animation_used": False,
        "pretest": {"records": []},
        "capture": {"records": []},
    }
    ffmpeg_process = None
    try:
        import omni.kit.app
        import omni.timeline
        import omni.usd
        import warp as wp
        from isaacsim.core.simulation_manager import PhysxScene, SimulationManager
        from omni.kit.viewport.utility import frame_viewport_prims, get_active_viewport
        from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade

        actual_hash = digest(args.input_usd)
        if actual_hash != INPUT_SHA256:
            raise RuntimeError(f"input USD hash mismatch: {actual_hash}")
        report["input_sha256"] = actual_hash

        urdf_hash = digest(args.input_urdf)
        if urdf_hash != URDF_SHA256:
            raise RuntimeError(f"input URDF hash mismatch: {urdf_hash}")
        report["input_urdf"] = str(args.input_urdf)
        report["input_urdf_sha256"] = urdf_hash

        # Use the verified GT USD directly; no generated output and no re-import.
        selected_usd = args.input_usd
        report["visual_route"] = "RELATIONSHIP_DERIVED_BODY_LOCAL_CLONES"

        context = omni.usd.get_context()
        context.open_stage(str(selected_usd))
        for _ in range(3):
            app.update()
        stage = context.get_stage()
        root = stage.GetDefaultPrim()
        variant = root.GetVariantSet("Physics")
        if variant.IsValid() and "physx" in variant.GetVariantNames():
            variant.SetVariantSelection("physx")
        for _ in range(3):
            app.update()

        predicate = Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate)
        prims = list(Usd.PrimRange(stage.GetPseudoRoot(), predicate))
        meshes = [prim for prim in prims if prim.IsA(UsdGeom.Mesh)]
        revolute = [prim for prim in prims if prim.IsA(UsdPhysics.RevoluteJoint)]
        articulations = [prim for prim in prims if prim.HasAPI(UsdPhysics.ArticulationRootAPI)]
        rigid = [prim for prim in prims if prim.HasAPI(UsdPhysics.RigidBodyAPI)]
        colliders = [prim for prim in prims if prim.HasAPI(UsdPhysics.CollisionAPI)]
        structure_ok = len(meshes) >= 4 and len(revolute) == 3 and len(articulations) == 1 and len(rigid) == 11 and len(colliders) == 8
        if not structure_ok:
            raise RuntimeError(
                f"schema preflight mesh={len(meshes)} rev={len(revolute)} art={len(articulations)} "
                f"rigid={len(rigid)} collider={len(colliders)}"
            )

        original_target = stage.GetEditTarget()
        session = stage.GetSessionLayer()
        stage.SetEditTarget(Usd.EditTarget(session))
        joint_bodies = {str(j.GetPath()): {"body0": str(one_target(j, "physics:body0")), "body1": str(one_target(j, "physics:body1"))} for j in revolute}
        if sorted(Path(p).name for p in joint_bodies) != ["gt_C_1", "gt_C_2", "gt_C_3"]:
            raise RuntimeError(f"unexpected revolute joints: {list(joint_bodies)}")
        fixed_graph = {}
        for fixed_joint in [p for p in prims if p.IsA(UsdPhysics.FixedJoint)]:
            left = str(one_target(fixed_joint, "physics:body0")); right = str(one_target(fixed_joint, "physics:body1"))
            fixed_graph.setdefault(left, []).append(right); fixed_graph.setdefault(right, []).append(left)
        rigid_body_paths = []
        nearest_rigid_paths = []
        for source_prim in meshes:
            body = source_prim.GetParent()
            while body.IsValid() and not body.HasAPI(UsdPhysics.RigidBodyAPI):
                body = body.GetParent()
            if not body.IsValid():
                raise RuntimeError(f"no rigid-body ancestor for {source_prim.GetPath()}")
            nearest = str(body.GetPath())
            nearest_rigid_paths.append(nearest)
            candidates = set()
            for relation in joint_bodies.values():
                for side in ("body0", "body1"):
                    endpoint = relation[side]
                    if nearest == endpoint or connected(fixed_graph, nearest, endpoint):
                        candidates.add(endpoint)
            # All three joints share the same body0 component.  A door component
            # contains exactly one body1.  Collapse same-component endpoints.
            components = []
            for candidate in sorted(candidates):
                if not any(candidate == prior or connected(fixed_graph, candidate, prior) for prior in components):
                    components.append(candidate)
            if len(components) != 1:
                raise RuntimeError(f"relationship mapping ambiguous: mesh={source_prim.GetPath()} nearest={nearest} candidates={components}")
            rigid_body_paths.append(stage.GetPrimAtPath(components[0]).GetPath())

        # Route B never edits/de-instances source proxies.  The relationship
        # chain establishes the body mapping; points are transformed once into
        # that body's local space.  Route A uses the same display clone policy
        # so both routes have identical presentation and runtime invariants.
        deinstanced_rigid_bodies = []

        colors = {None:(0.72,0.72,0.76), "gt_C_1":(0.88,0.20,0.18), "gt_C_2":(0.16,0.70,0.26), "gt_C_3":(0.15,0.35,0.92)}
        materials = {}
        for label,color in colors.items():
            token = label or "BASE"
            material = UsdShade.Material.Define(stage, f"/__PhysXGuiDiagnostic/Material_{token}")
            shader = UsdShade.Shader.Define(stage, f"/__PhysXGuiDiagnostic/Material_{token}/PreviewSurface")
            shader.CreateIdAttr("UsdPreviewSurface"); shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color)); shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0); shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface"); materials[label]=material

        xforms = UsdGeom.XformCache(Usd.TimeCode.Default())
        clone_prims = []
        clone_specs = []
        for index, (source_prim, nearest_path, body_path) in enumerate(zip(meshes, nearest_rigid_paths, rigid_body_paths)):
            body = stage.GetPrimAtPath(body_path)
            source_mesh = UsdGeom.Mesh(source_prim)
            source_world = xforms.GetLocalToWorldTransform(source_prim)
            body_world_inverse = xforms.GetLocalToWorldTransform(body).GetInverse()
            body_local_points = []; source_world_points = []; reconstructed_world_points = []
            reconstruction_error = 0.0
            body_world = xforms.GetLocalToWorldTransform(body)
            for point in (source_mesh.GetPointsAttr().Get() or []):
                world = source_world.Transform(Gf.Vec3d(float(point[0]), float(point[1]), float(point[2])))
                local = body_world_inverse.Transform(world)
                reconstructed = body_world.Transform(local)
                reconstruction_error = max(reconstruction_error, (reconstructed - world).GetLength())
                source_world_points.append(world); reconstructed_world_points.append(reconstructed)
                body_local_points.append(Gf.Vec3f(local))
            if reconstruction_error > 1.0e-6:
                raise RuntimeError(f"body-local round trip failed: {source_prim.GetPath()} error={reconstruction_error}")
            counts = list(source_mesh.GetFaceVertexCountsAttr().Get() or [])
            indices = list(source_mesh.GetFaceVertexIndicesAttr().Get() or [])
            clone_path = body.GetPath().AppendChild(f"__GuiDiagnosticMesh_{index}")
            clone = UsdGeom.Mesh.Define(stage, clone_path)
            clone.CreatePointsAttr(body_local_points)
            clone.CreateFaceVertexCountsAttr(counts)
            clone.CreateFaceVertexIndicesAttr(indices)
            clone.CreateOrientationAttr(UsdGeom.Tokens.rightHanded)
            clone.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
            clone.CreateDoubleSidedAttr(True)
            clone.CreateVisibilityAttr(UsdGeom.Tokens.inherited)
            door_joint = next((Path(path).name for path,rel in joint_bodies.items() if rel["body1"] == str(body_path) or connected(fixed_graph, rel["body1"], str(body_path))), None)
            clone.CreateDisplayColorPrimvar(UsdGeom.Tokens.constant).Set([Gf.Vec3f(*colors[door_joint])])
            clone.CreateDisplayOpacityPrimvar(UsdGeom.Tokens.constant).Set([1.0])
            UsdShade.MaterialBindingAPI.Apply(clone.GetPrim()).Bind(materials[door_joint])
            direct_targets = [
                str(path) for path in clone.GetPrim().GetRelationship("material:binding").GetTargets()
            ]
            if direct_targets != [str(materials[door_joint].GetPath())]:
                raise RuntimeError(f"clone material binding failed: {clone_path} -> {direct_targets}")
            # Re-read the authored prim from the composed stage.  This is
            # deliberately independent of the pre-authoring round-trip above.
            authored_mesh=UsdGeom.Mesh(stage.GetPrimAtPath(clone_path)); authored_points=list(authored_mesh.GetPointsAttr().Get() or [])
            authored_world=UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(authored_mesh.GetPrim())
            actual_world_points=[authored_world.Transform(Gf.Vec3d(float(p[0]),float(p[1]),float(p[2]))) for p in authored_points]
            if len(actual_world_points)!=len(source_world_points): raise RuntimeError(f"authored clone point count mismatch {clone_path}")
            actual_vertex_error=max((a-b).GetLength() for a,b in zip(actual_world_points,source_world_points))
            if actual_vertex_error>1e-6: raise RuntimeError(f"actual authored clone mismatch {clone_path}: {actual_vertex_error}")
            clone_prims.append(clone.GetPrim())
            clone_specs.append(
                {
                    "source_mesh": str(source_prim.GetPath()),
                    "original_rigid_body_ancestor": nearest_path,
                    "presentation_mode": "relationship_derived_body_local_clone",
                    "clone_mesh": str(clone_path),
                    "rigid_body_parent": str(body.GetPath()),
                    "component_label": door_joint or "BASE",
                    "display_color_rgb": list(colors[door_joint]),
                    "points": len(body_local_points),
                    "triangles": sum(max(0, int(count) - 2) for count in counts),
                    "direct_material_binding_targets": direct_targets,
                    "double_sided": True,
                    "visibility": "inherited",
                    "initial_world_roundtrip_max_error_m": reconstruction_error,
                    "source_world_bounds": {"min":[min(float(p[i]) for p in source_world_points) for i in range(3)],"max":[max(float(p[i]) for p in source_world_points) for i in range(3)]},
                    "reconstructed_world_bounds": {"min":[min(float(p[i]) for p in reconstructed_world_points) for i in range(3)],"max":[max(float(p[i]) for p in reconstructed_world_points) for i in range(3)]},
                    "actual_authored_clone_world_bounds": {"min":[min(float(p[i]) for p in actual_world_points) for i in range(3)],"max":[max(float(p[i]) for p in actual_world_points) for i in range(3)]},
                    "actual_authored_clone_vertex_max_error_stage_units":actual_vertex_error,
                    "actual_authored_clone_vertex_max_error_m":actual_vertex_error*UsdGeom.GetStageMetersPerUnit(stage),
                    "clone_parent_is_instance_proxy":body.IsInstanceProxy(),
                }
            )

        key_light = UsdLux.DistantLight.Define(stage, "/__PhysXGuiDiagnostic/KeyLight")
        key_light.CreateIntensityAttr(3000.0)
        fill_light = UsdLux.SphereLight.Define(stage, "/__PhysXGuiDiagnostic/FillLight")
        fill_light.CreateIntensityAttr(30000.0)
        fill_light.CreateRadiusAttr(0.5)
        UsdGeom.Xformable(fill_light).AddTranslateOp().Set(Gf.Vec3d(2.0, -2.0, 3.0))

        scene = None
        if not args.static_mapping_gate:
            for body in rigid:
                mass = UsdPhysics.MassAPI.Apply(body)
                mass.CreateMassAttr().Set(1.0)
                mass.CreateDiagonalInertiaAttr().Set(Gf.Vec3f(0.1, 0.1, 0.1))
                mass.CreatePrincipalAxesAttr().Set(Gf.Quatf(1.0, Gf.Vec3f(0.0, 0.0, 0.0)))
            scene = PhysxScene("/World/GTOnlyRuntimePhysicsScene")
            scene.set_gravity((0.0, 0.0, -9.81))
            scene.set_dt(1.0 / 60.0)
        clone_xforms_before = authored_clone_xforms(clone_prims)
        clone_time_samples_before = clone_time_samples(clone_prims)
        report["selected_visual_route"] = "RELATIONSHIP_DERIVED_BODY_LOCAL_CLONES"
        stage.SetEditTarget(original_target)
        for _ in range(3):
            app.update()

        viewport = get_active_viewport()
        clone_paths = [str(prim.GetPath()) for prim in clone_prims]
        if viewport is None or not frame_viewport_prims(viewport, prims=clone_paths):
            raise RuntimeError("failed to frame GUI diagnostic cabinet meshes")
        if args.static_mapping_gate:
            mins=[min(spec["source_world_bounds"]["min"][i] for spec in clone_specs) for i in range(3)]
            maxs=[max(spec["source_world_bounds"]["max"][i] for spec in clone_specs) for i in range(3)]
            center=Gf.Vec3d(*[(a+b)*0.5 for a,b in zip(mins,maxs)]); sizes=[b-a for a,b in zip(mins,maxs)]
            up_token=str(UsdGeom.GetStageUpAxis(stage)); front_index=min(range(3),key=lambda i:sizes[i])
            distance=max(sizes)*2.2
            cube=UsdGeom.Cube.Define(stage,"/__PhysXGuiDiagnostic/ReferenceCube"); cube.CreateSizeAttr(max(sizes)*0.08); cube.CreateDisplayColorPrimvar(UsdGeom.Tokens.constant).Set([Gf.Vec3f(1.0,0.55,0.05)])
            UsdGeom.Xformable(cube).AddTranslateOp().Set(Gf.Vec3d(maxs[0]+max(sizes)*0.12,maxs[1],maxs[2]))
            progress_path=args.run_dir/"static_capture_progress.json"
            def save_progress(status, current=None, error=None):
                progress_path.write_text(json.dumps({"status":status,"current_camera":current,"physics_started":False,"simulation_steps":0,"external_capture_started":False,"error":error},indent=2)+"\n")
            save_progress("CAMERA_SETUP")
            eye_values=list(center); eye_values[front_index]+=distance
            up_index=1 if front_index==2 else 2; up_values=[0.0,0.0,0.0]; up_values[up_index]=1.0
            camera=UsdGeom.Camera.Define(stage,"/__PhysXGuiDiagnostic/Camera_front")
            view=Gf.Matrix4d(1.0); view.SetLookAt(Gf.Vec3d(*eye_values),center,Gf.Vec3d(*up_values))
            UsdGeom.Xformable(camera).AddTransformOp().Set(view.GetInverse()); camera.CreateFocalLengthAttr(45.0); camera.CreateClippingRangeAttr(Gf.Vec2f(0.01,max(1000.0,distance*10)))
            viewport.set_active_camera(str(camera.GetPath()))
            for _ in range(20): app.update()
            report["static_camera"]={"bounds":{"min":mins,"max":maxs,"size":sizes},"center":list(center),"stage_up_axis":up_token,"thin_axis_index":front_index,"selection_basis":"smallest aggregate source/clone extent; stage up is not excluded because doors may lie in a plane normal to it","eye":eye_values,"target":list(center),"screen_up":up_values,"camera":str(camera.GetPath()),"reference_cube":"/__PhysXGuiDiagnostic/ReferenceCube","external_capture_started":False}
            save_progress("FRONT_GUI_READY", "front")
        context.get_selection().set_selected_prim_paths([str(revolute[0].GetPath())], True)

        joint_frames={}
        for joint in revolute:
            schema=UsdPhysics.RevoluteJoint(joint)
            def value(name):
                raw=joint.GetAttribute(name).Get()
                if raw is None:return None
                try:return [float(x) for x in raw]
                except TypeError:
                    try:return float(raw)
                    except (TypeError,ValueError):return str(raw)
            joint_frames[str(joint.GetPath())]={"body0":str(one_target(joint,"physics:body0")),"body1":str(one_target(joint,"physics:body1")),"axis":str(schema.GetAxisAttr().Get()),"local_pos0":value("physics:localPos0"),"local_pos1":value("physics:localPos1"),"local_rot0":value("physics:localRot0"),"local_rot1":value("physics:localRot1"),"lower_limit_degrees":value("physics:lowerLimit"),"upper_limit_degrees":value("physics:upperLimit")}
        static_mapping = {
            "status":"AUTOMATION_STATIC_MAPPING_READY_HUMAN_CHECK_REQUIRED",
            "physics_started":False,"simulation_steps":0,"variant":variant.GetVariantSelection(),
            "meters_per_unit":UsdGeom.GetStageMetersPerUnit(stage),"up_axis":str(UsdGeom.GetStageUpAxis(stage)),
            "joint_relationships":joint_bodies,"joint_frames":joint_frames,"fixed_joint_graph":fixed_graph,"mesh_mapping":clone_specs,"camera":report.get("static_camera"),
            "color_legend":{"BASE":list(colors[None]),"gt_C_1":list(colors["gt_C_1"]),"gt_C_2":list(colors["gt_C_2"]),"gt_C_3":list(colors["gt_C_3"])},
        }
        (args.run_dir / "static_mapping_gate.json").write_text(json.dumps(static_mapping,indent=2)+"\n")
        if args.static_mapping_gate:
            (args.run_dir / "runner_phase.txt").write_text("STATIC_MAPPING_HUMAN_REVIEW\n")
            started=time.monotonic()
            save_progress("HUMAN_REVIEW_WINDOW")
            while time.monotonic()-started < 30.0:
                app.update(); time.sleep(0.01)
            save_progress("COMPLETE")
            print("STATIC_MAPPING_GATE=AUTOMATION_READY_HUMAN_CHECK_REQUIRED",flush=True)
            return 0

        SimulationManager.setup_simulation(dt=1.0 / 60.0, device="cuda:0")
        SimulationManager.initialize_physics()
        first_step = SimulationManager.get_num_physics_steps()
        SimulationManager.step(steps=1, update_fabric=True)
        app.update()
        if SimulationManager.get_num_physics_steps() <= first_step:
            raise RuntimeError("PhysicsScene did not advance")
        view = SimulationManager.get_physics_simulation_view()
        articulation = view.create_articulation_view([str(articulations[0].GetPath())])
        if articulation.count != 1 or articulation.max_dofs != 3:
            raise RuntimeError(f"articulation count/dof={articulation.count}/{articulation.max_dofs}")
        meta = articulation.get_metatype(0)
        dof_names = list(meta.dof_names)
        if sorted(dof_names) != ["gt_C_1", "gt_C_2", "gt_C_3"]:
            raise RuntimeError(f"unexpected DOFs {dof_names}")
        dof_indices = {name: int(meta.dof_indices[name]) for name in dof_names}
        link_names = list(meta.link_names)
        link_indices = {name: int(meta.link_indices[name]) for name in link_names}
        raw_limits = nested_values(articulation.get_dof_limits())[0]
        limits = {name: [float(raw_limits[index][0]), float(raw_limits[index][1])] for name,index in dof_indices.items()}
        for name, (lower, upper) in limits.items():
            if not lower < upper:
                raise RuntimeError(f"invalid joint limits {name}: {lower, upper}")
        for spec in clone_specs:
            body_name = Path(spec["rigid_body_parent"]).name
            if body_name not in link_indices:
                raise RuntimeError(f"rigid body {body_name} absent from articulation links {link_names}")
            spec["link_name"] = body_name
            spec["link_index"] = link_indices[body_name]
            spec["door_joint"] = next((Path(path).name for path,rel in joint_bodies.items() if rel["body1"] == spec["rigid_body_parent"] or connected(fixed_graph, rel["body1"], spec["rigid_body_parent"])), None)

        neutral = {name: limits[name][1] - 0.10*(limits[name][1]-limits[name][0]) for name in dof_names}
        sequences = {name: [limits[name][1]-(limits[name][1]-limits[name][0])*f for f in TARGET_FRACTIONS] for name in dof_names}
        report["preflight"] = {
            "variant": variant.GetVariantSelection() if variant.IsValid() else None,
            "revolute_joints": sorted(str(j.GetPath()) for j in revolute),
            "joint_relationships": joint_bodies, "fixed_joint_graph": fixed_graph,
            "articulation_root": str(articulations[0].GetPath()),
            "rigid_body_count": len(rigid), "collider_count": len(colliders),
            "dof_names": dof_names, "dof_indices": dof_indices,
            "joint_limits_rad": limits, "target_sequences_rad": sequences,
            "runtime_physics_scene": scene.path, "clone_meshes": clone_specs,
            "source_instance_proxies_modified": False,
            "clone_xforms_before_simulation": clone_xforms_before,
            "clone_time_samples_before_simulation": clone_time_samples_before,
            "controlled_material_settings": {"mass_kg":1.0,"diagonal_inertia_kg_m2":[0.1,0.1,0.1],"principal_axes":[1.0,0.0,0.0,0.0],"source":"session-layer controlled experimental setting"},
        }

        async def command_target(phase, active_name, target, steps, destination):
            current = articulation.get_dof_position_targets(); values = nested_values(current)
            for name,index in dof_indices.items(): values[0][index] = target if name == active_name else neutral[name]
            targets = wp.array(values, dtype=wp.float32, device=current.device)
            articulation.set_dof_position_targets(targets, wp.array([0], dtype=wp.uint32, device=targets.device))
            readback_all = nested_values(articulation.get_dof_position_targets())[0]
            if abs(float(readback_all[dof_indices[active_name]])-target) > 1e-5: raise RuntimeError("target readback mismatch")
            for local_step in range(steps):
                before=SimulationManager.get_num_physics_steps(); SimulationManager.step(steps=1,update_fabric=True)
                await omni.kit.app.get_app().next_update_async(); after=SimulationManager.get_num_physics_steps()
                positions=articulation.get_dof_positions(); velocities=articulation.get_dof_velocities(); links=articulation.get_link_transforms()
                if after<=before or not all(finite_array(x) for x in (positions,velocities,links)): raise RuntimeError("non-finite state or physics step did not advance")
                link_values=nested_values(links)[0]; pos=nested_values(positions)[0]; vel=nested_values(velocities)[0]
                destination.append({"phase":phase,"active_joint":active_name,"wall_monotonic_s":time.monotonic(),"requested_target_rad":target,"target_readback_rad":float(readback_all[dof_indices[active_name]]),"local_step":local_step,"manager_steps":[before,after],"positions_rad":{n:float(pos[i]) for n,i in dof_indices.items()},"velocities_rad_s":{n:float(vel[i]) for n,i in dof_indices.items()},"rigid_body_link_transforms_xyzw":link_values,"clone_world_transforms_from_physics_body":{spec["clone_mesh"]:transform7_matrix(link_values[spec["link_index"]],Gf) for spec in clone_specs}})
        heartbeat_path = args.run_dir / "gui_heartbeat.json"
        update_count = 0
        def run_responsive(coroutine, phase, minimum_wall_s=0.0, pace_s=0.005):
            nonlocal update_count
            task = asyncio.ensure_future(coroutine)
            started = time.monotonic(); last_heartbeat = 0.0
            while not task.done() or time.monotonic() - started < minimum_wall_s:
                app.update(); update_count += 1
                now = time.monotonic()
                if now - last_heartbeat >= 1.0:
                    heartbeat_path.write_text(json.dumps({"phase": phase, "wall_monotonic_s": now, "elapsed_s": now-started, "update_callback_count": update_count, "physics_step_count": SimulationManager.get_num_physics_steps()}) + "\n")
                    last_heartbeat = now
                time.sleep(pace_s)
            return task.result()

        async def idle_updates(seconds):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                await omni.kit.app.get_app().next_update_async()

        async def drive_all(phase, steps, destination):
            for name in sorted(dof_names):
                for target in sequences[name]:
                    await command_target(phase, name, target, steps, destination)

        (args.run_dir / "runner_phase.txt").write_text("STATIC_PREFLIGHT\n")
        run_responsive(idle_updates(3.0), "STATIC_PREFLIGHT", minimum_wall_s=3.0, pace_s=0.01)
        (args.run_dir / "marker_structure_mapping.json").write_text(json.dumps(report["preflight"],indent=2)+"\n")
        (args.run_dir / "runner_phase.txt").write_text("PHYSICS_PRETEST\n")
        run_responsive(drive_all("pretest_each_door", 30, report["pretest"]["records"]), "PHYSICS_PRETEST", pace_s=0.01)
        rows=report["pretest"]["records"]
        checks={"record_count":len(rows),"joint_spans_rad":{},"nonactive_max_drift_rad":{},"door_body_rotation_span_rad":{}}
        for active in sorted(dof_names):
            subset=[r for r in rows if r["active_joint"]==active]
            checks["joint_spans_rad"][active]=max(r["positions_rad"][active] for r in subset)-min(r["positions_rad"][active] for r in subset)
            checks["nonactive_max_drift_rad"][active]=max(abs(r["positions_rad"][other]-neutral[other]) for r in subset for other in dof_names if other!=active)
            body1=joint_bodies[next(p for p in joint_bodies if Path(p).name==active)]["body1"]
            link=Path(body1).name; idx=link_indices[link]; first=subset[0]["rigid_body_link_transforms_xyzw"][idx]
            checks["door_body_rotation_span_rad"][active]=max(pose_delta(first,r["rigid_body_link_transforms_xyzw"][idx])[1] for r in subset)
        clone_after=authored_clone_xforms(clone_prims); samples_after=clone_time_samples(clone_prims)
        checks["clone_xform_authoring_after_start"]=clone_after!=clone_xforms_before
        checks["clone_time_sample_authoring_after_start"]=samples_after-clone_time_samples_before
        if min(checks["joint_spans_rad"].values())<0.5 or min(checks["door_body_rotation_span_rad"].values())<0.5: raise RuntimeError(f"door response invariant failed {checks}")
        if checks["clone_xform_authoring_after_start"] or checks["clone_time_sample_authoring_after_start"]: raise RuntimeError("visual transform/keyframe authored after start")
        report["pretest"]["checks"]=checks
        (args.run_dir / "marker_pretest_pass.json").write_text(json.dumps(checks,indent=2)+"\n")

        display = os.environ.get("DISPLAY")
        if not display:
            raise RuntimeError("DISPLAY is empty")
        video_path = args.run_dir / "29806_gt_only_gpu0_gui_physics.mp4"
        ffmpeg_command = [
            "ffmpeg", "-y", "-f", "x11grab", "-draw_mouse", "0", "-framerate", "30",
            "-video_size", args.capture_size, "-i", f"{display}+{args.capture_offset}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            str(video_path),
        ]
        report["capture"]["ffmpeg_command"] = ffmpeg_command
        report["capture"]["video"] = str(video_path)
        video_start_monotonic = time.monotonic()
        ffmpeg_process = subprocess.Popen(
            ffmpeg_command,
            stdout=(args.run_dir / "ffmpeg.stdout.log").open("wb"),
            stderr=(args.run_dir / "ffmpeg.stderr.log").open("wb"),
        )
        run_responsive(idle_updates(1.0), "CAPTURE_STATIC_START", minimum_wall_s=1.0, pace_s=0.01)
        capture_process_error = None
        if ffmpeg_process.poll() is not None:
            capture_process_error = f"ffmpeg exited before capture: {ffmpeg_process.returncode}"
            ffmpeg_process = None
        capture_start_step = SimulationManager.get_num_physics_steps()
        capture_wall_start = time.monotonic()
        (args.run_dir / "runner_phase.txt").write_text("PHYSICS_CAPTURE\n")
        run_responsive(drive_all("capture_each_door_closed_mid_open_mid_closed", 60, report["capture"]["records"]), "PHYSICS_CAPTURE", pace_s=1.0/30.0)
        capture_end_step = SimulationManager.get_num_physics_steps()
        run_responsive(idle_updates(2.0), "CAPTURE_STATIC_END", minimum_wall_s=2.0, pace_s=0.01)
        ffmpeg_rc = None
        if ffmpeg_process is not None:
            ffmpeg_process.send_signal(signal.SIGINT)
            ffmpeg_rc = ffmpeg_process.wait(timeout=20)
            ffmpeg_process = None
            if ffmpeg_rc not in (0, 255) or not video_path.is_file() or video_path.stat().st_size == 0:
                capture_process_error = f"ffmpeg capture failed rc={ffmpeg_rc}"
        report["capture"].update(
            {
                "simulation_step_range": [capture_start_step, capture_end_step],
                "record_count": len(report["capture"]["records"]), "capture_wall_start_monotonic": capture_wall_start,
                "video_start_monotonic": video_start_monotonic,
                "video_bytes": video_path.stat().st_size if video_path.is_file() else 0,
                "video_sha256": digest(video_path) if video_path.is_file() else None,
                "capture_process_error": capture_process_error,
            }
        )
        if capture_process_error:
            raise RuntimeError(capture_process_error + "; physics sequence completed and was preserved")
        report["status"] = "AUTOMATED_PRETEST_AND_CAPTURE_COMPLETE_HUMAN_VIEWPORT_REVIEW_REQUIRED"
        (args.run_dir / "runner_phase.txt").write_text("COMPLETE\n")
        (args.run_dir / "physics_gui_report.json").write_text(json.dumps(report, indent=2) + "\n")
        print("GT_GUI_TENSOR_PHYSICS_CAPTURE=AUTOMATED_PASS_HUMAN_REVIEW_REQUIRED", flush=True)
        return 0
    except BaseException as exc:
        report["status"] = "FAIL"
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        (args.run_dir / "physics_gui_report.json").write_text(json.dumps(report, indent=2) + "\n")
        traceback.print_exc()
        raise
    finally:
        if ffmpeg_process is not None and ffmpeg_process.poll() is None:
            ffmpeg_process.send_signal(signal.SIGINT)
            try:
                ffmpeg_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                ffmpeg_process.kill()
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
