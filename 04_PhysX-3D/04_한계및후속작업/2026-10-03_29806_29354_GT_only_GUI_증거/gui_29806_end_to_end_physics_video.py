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
from gui_29806_common import atomic_json, corners, diffuse_pixel_decision, execution_plan, internal_exit_payload, validate_modes

from isaacsim import SimulationApp


INPUT_SHA256 = "5da6eb5823de2a8da1d7896ad047c8a73b2f25c79b60bd606afe912dd1b0891a"
URDF_SHA256 = "99ee19188ec969488e63ae2504f3ecf04f7de73071e523ec9e4f231fb68855c6"
MAX_CLOSED_TARGET_ABSOLUTE_ERROR_RAD = 0.01
MAX_INACTIVE_EXCURSION_RAD = 0.002
MAX_ROOT_TRANSLATION_DRIFT_M = 0.0001
MAX_ROOT_ORIENTATION_DRIFT_RAD = 0.002
MIN_ACTIVE_RESPONSE_SPAN_RAD = 0.50
POSITION_SETTLE_RAD = MAX_CLOSED_TARGET_ABSOLUTE_ERROR_RAD
VELOCITY_SETTLE_RAD_S = 0.05
SETTLE_CONSECUTIVE_STEPS = 30
SETTLE_TIMEOUT_STEPS = 300
RECOVERY_TIMEOUT_STEPS = 300
TRANSIENT_PIXEL_RATIO = 0.20
TRANSIENT_CENTER_SHIFT_PX = 40.0
FINAL_DOOR_PIXEL_RATIO = 0.70
FINAL_BASE_PIXEL_RATIO = 0.80
FINAL_DOOR_BBOX_IOU = 0.65
FINAL_JOINT_VELOCITY_RAD_S = 0.01
FINAL_MAX_PAIRWISE_DOOR_BBOX_IOU = 0.10
FINAL_MIN_DOOR_CENTER_SEPARATION_PX = 10.0


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


def bbox_iou(a, b):
    if not a or not b:
        return 0.0
    left=max(a[0],b[0]);top=max(a[1],b[1]);right=min(a[2],b[2]);bottom=min(a[3],b[3])
    intersection=max(0,right-left+1)*max(0,bottom-top+1)
    area_a=max(0,a[2]-a[0]+1)*max(0,a[3]-a[1]+1)
    area_b=max(0,b[2]-b[0]+1)*max(0,b[3]-b[1]+1)
    return intersection/max(1,area_a+area_b-intersection)


def bbox_diagonal(bbox):
    return math.hypot(bbox[2]-bbox[0]+1,bbox[3]-bbox[1]+1) if bbox else 0.0


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
    parser.add_argument("--initialization-diagnostic", action="store_true")
    parser.add_argument("--initialization-isolation-diagnostic", action="store_true")
    parser.add_argument("--diffuse-only-material-diagnostic", action="store_true")
    parser.add_argument("--gated-recovery-end-to-end", action="store_true")
    args = parser.parse_args()
    mode = validate_modes(static_mapping_gate=args.static_mapping_gate,
                          initialization_diagnostic=args.initialization_diagnostic,
                          initialization_isolation_diagnostic=args.initialization_isolation_diagnostic,
                          gated_recovery_end_to_end=args.gated_recovery_end_to_end,
                          diffuse_only_material_diagnostic=args.diffuse_only_material_diagnostic)
    args.run_dir.mkdir(parents=True, exist_ok=True)

    experience = args.root / (
        "repro-records/04_PhysX-3D/04_한계및후속작업/"
        "2026-10-03_29806_29354_GT_only_GUI_증거/"
        "isaac_gui_29806_gpu0_tensor_physics.kit"
    )
    plan = execution_plan(mode, diffuse_only=args.diffuse_only_material_diagnostic)
    try:
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
    except BaseException as exc:
        atomic_json(args.run_dir/"runner_internal_exit.json",internal_exit_payload(
            status="ISAAC_APP_STARTUP_ERROR",code=1,mode=mode,plan=plan,completed=[],asset_pass=False,
            error={"type":type(exc).__name__,"message":str(exc)},last_phase="ISAAC_APP_STARTUP"))
        traceback.print_exc()
        return 1
    report = {
        "scope": "29806 GT-only three-door GUI physics control; not AI prediction",
        "status": "RUNNING",
        "mode": mode,
        "execution_plan": plan,
        "input_usd": str(args.input_usd),
        "physics_gpu": 0,
        "renderer_gpu": 0,
        "multi_gpu": False,
        "p2p_used": False,
        "usd_drive_target_authored_during_run": False,
        "transform_or_keyframe_animation_used": False,
        "pretest": {"records": []},
        "capture": {"records": []},
        "completed_phases": [],
    }
    def finish(code, status, *, asset_pass=False):
        atomic_json(args.run_dir/"runner_internal_exit.json",internal_exit_payload(status=status,code=code,mode=mode,plan=report["execution_plan"],completed=report["completed_phases"],asset_pass=asset_pass))
        return code
    def set_phase(name, completed=None):
        (args.run_dir/"runner_phase.txt").write_text(name+"\n")
        if completed and completed not in report["completed_phases"]:
            report["completed_phases"].append(completed)
        atomic_json(args.run_dir/"runner_phase_state.json",{"phase":name,"wall_time":time.time(),"wall_monotonic":time.monotonic(),"completed_phases":report["completed_phases"],"mode":mode})
    ffmpeg_process = None
    try:
        set_phase("APP_STARTED")
        import carb
        import omni.kit.app
        import omni.timeline
        import omni.usd
        import warp as wp
        from isaacsim.core.simulation_manager import PhysxScene, SimulationManager
        from omni.kit.viewport.utility import frame_viewport_prims, get_active_viewport
        from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade
        settings=carb.settings.get_settings()

        marker_path=args.run_dir/"static_gate_markers.jsonl"
        def marker(name, **values):
            record={"marker":name,"wall_time":time.time(),"physics_steps":0};record.update(values)
            with marker_path.open("a") as stream: stream.write(json.dumps(record,sort_keys=True)+"\n")
            print(f"STATIC_GATE_MARKER_{name}="+json.dumps(record,sort_keys=True),flush=True)
        if args.static_mapping_gate:
            settings.set("/app/window/title", "GT-only static mapping gate — physics not started | 29806")
            settings.set("/persistent/app/usd/muteUsdDiagnostics", False)
            marker("APP_READY",headless=False,usd_diagnostics_muted=False)
        else:
            settings.set("/app/window/title", "GT-only physics control — not AI prediction | 29806")
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
        set_phase("STAGE_LOADED",completed="stage")
        root = stage.GetDefaultPrim()
        if args.static_mapping_gate: marker("STAGE_LOADED",stage=str(selected_usd),default_prim=str(root.GetPath()))
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
        if args.diffuse_only_material_diagnostic:
            colors = {label:(0.12,0.68,0.92) for label in colors}
        materials = {}
        for label,color in colors.items():
            token = label or "BASE"
            material = UsdShade.Material.Define(stage, f"/__PhysXGuiDiagnostic/Material_{token}")
            shader = UsdShade.Shader.Define(stage, f"/__PhysXGuiDiagnostic/Material_{token}/PreviewSurface")
            shader.CreateIdAttr("UsdPreviewSurface"); shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
            if not args.diffuse_only_material_diagnostic:
                shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
            shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0); shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface"); materials[label]=material
        # Exact material pattern used by the successful 10163 route-B runner:
        # diffuse + opacity, no emissive input.  Isolation phases bind this
        # material temporarily to distinguish material from geometry/Fabric.
        notebook_control_material=UsdShade.Material.Define(stage,"/__PhysXGuiDiagnostic/Material_10163StyleControl")
        notebook_control_shader=UsdShade.Shader.Define(stage,"/__PhysXGuiDiagnostic/Material_10163StyleControl/PreviewSurface")
        notebook_control_shader.CreateIdAttr("UsdPreviewSurface")
        notebook_control_shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.12,0.68,0.92))
        notebook_control_shader.CreateInput("opacity",Sdf.ValueTypeNames.Float).Set(1.0)
        notebook_control_shader.CreateOutput("surface",Sdf.ValueTypeNames.Token)
        notebook_control_material.CreateSurfaceOutput().ConnectToSource(notebook_control_shader.ConnectableAPI(),"surface")

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
            if args.static_mapping_gate:
                clone_path = Sdf.Path("/__PhysXGuiStatic").AppendChild(f"CloneMesh_{index}")
                authored_clone_points = [Gf.Vec3f(point) for point in source_world_points]
            else:
                clone_path = body.GetPath().AppendChild(f"__GuiDiagnosticMesh_{index}")
                authored_clone_points = body_local_points
            clone = UsdGeom.Mesh.Define(stage, clone_path)
            clone.CreatePointsAttr(authored_clone_points)
            clone.CreateFaceVertexCountsAttr(counts)
            clone.CreateFaceVertexIndicesAttr(indices)
            clone.CreateOrientationAttr(UsdGeom.Tokens.rightHanded)
            clone.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
            clone.CreateDoubleSidedAttr(True)
            clone.CreateVisibilityAttr(UsdGeom.Tokens.inherited)
            clone.CreatePurposeAttr(UsdGeom.Tokens.default_)
            clone.CreateExtentAttr([Gf.Vec3f(*[min(float(p[i]) for p in authored_clone_points) for i in range(3)]),Gf.Vec3f(*[max(float(p[i]) for p in authored_clone_points) for i in range(3)])])
            door_joint = next((Path(path).name for path,rel in joint_bodies.items() if rel["body1"] == str(body_path) or connected(fixed_graph, rel["body1"], str(body_path))), None)
            clone.CreateDisplayColorPrimvar(UsdGeom.Tokens.constant).Set([Gf.Vec3f(*colors[door_joint])])
            clone.CreateDisplayOpacityPrimvar(UsdGeom.Tokens.constant).Set([1.0])
            binding_api = UsdShade.MaterialBindingAPI.Apply(clone.GetPrim())
            binding_api.Bind(materials[door_joint])
            direct_targets = [str(path) for path in clone.GetPrim().GetRelationship("material:binding").GetTargets()]
            computed_material, _ = binding_api.ComputeBoundMaterial()
            computed_target = str(computed_material.GetPath()) if computed_material else None
            expected_material = str(materials[door_joint].GetPath())
            if direct_targets != [expected_material] or computed_target != expected_material:
                raise RuntimeError(f"clone material binding failed: {clone_path} direct={direct_targets} computed={computed_target}")
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
                    "target_rigid_body": str(body.GetPath()),
                    "component_label": door_joint or "BASE",
                    "display_color_rgb": list(colors[door_joint]),
                    "points": len(body_local_points),
                    "triangles": sum(max(0, int(count) - 2) for count in counts),
                    "direct_material_binding_targets": direct_targets,
                    "computed_material_target": computed_target,
                    "shader_surface_connected": bool(materials[door_joint].GetSurfaceOutput().HasConnectedSource()),
                    "shader_diffuse_color": list(colors[door_joint]),
                    "shader_emissive_color": list(colors[door_joint]),
                    "display_color": list(colors[door_joint]),
                    "display_opacity": 1.0,
                    "double_sided": True,
                    "visibility": "inherited",
                    "purpose": str(UsdGeom.Imageable(source_prim).GetPurposeAttr().Get() or UsdGeom.Tokens.default_),
                    "source_active": source_prim.IsActive(),
                    "source_loaded": source_prim.IsLoaded(),
                    "source_visibility": str(UsdGeom.Imageable(source_prim).ComputeVisibility()),
                    "source_instance_proxy": source_prim.IsInstanceProxy(),
                    "source_local_xform_ops": {name:str(source_prim.GetAttribute(name).Get()) for name in source_prim.GetPropertyNames() if name=="xformOpOrder" or name.startswith("xformOp:")},
                    "source_orientation": str(source_mesh.GetOrientationAttr().Get()),
                    "source_subdivision_scheme": str(source_mesh.GetSubdivisionSchemeAttr().Get()),
                    "source_extent": [[float(v) for v in row] for row in (source_mesh.GetExtentAttr().Get() or [])],
                    "source_local_bounds": {"min":[min(float(p[i]) for p in (source_mesh.GetPointsAttr().Get() or [])) for i in range(3)],"max":[max(float(p[i]) for p in (source_mesh.GetPointsAttr().Get() or [])) for i in range(3)]},
                    "source_world_transform": matrix_values(source_world),
                    "source_world_transform_determinant": float(source_world.GetDeterminant()),
                    "source_world_transform_finite": all(math.isfinite(v) for row in matrix_values(source_world) for v in row),
                    "target_body_world_transform": matrix_values(body_world),
                    "clone_parent_prim": str(clone.GetPrim().GetParent().GetPath()),
                    "visual_authoring_space": "world" if args.static_mapping_gate else "rigid_body_local",
                    "clone_local_transform": matrix_values(Gf.Matrix4d(1.0)),
                    "clone_world_transform": matrix_values(authored_world),
                    "clone_world_transform_determinant": float(authored_world.GetDeterminant()),
                    "clone_world_transform_finite": all(math.isfinite(v) for row in matrix_values(authored_world) for v in row),
                    "source_clone_world_bounds_max_error_m": max(abs(float(a)-float(b))*UsdGeom.GetStageMetersPerUnit(stage) for key in ("min","max") for a,b in zip({"min":[min(float(p[i]) for p in source_world_points) for i in range(3)],"max":[max(float(p[i]) for p in source_world_points) for i in range(3)]}[key],{"min":[min(float(p[i]) for p in actual_world_points) for i in range(3)],"max":[max(float(p[i]) for p in actual_world_points) for i in range(3)]}[key])),
                    "initial_world_roundtrip_max_error_m": reconstruction_error,
                    "source_world_bounds": {"min":[min(float(p[i]) for p in source_world_points) for i in range(3)],"max":[max(float(p[i]) for p in source_world_points) for i in range(3)]},
                    "reconstructed_world_bounds": {"min":[min(float(p[i]) for p in reconstructed_world_points) for i in range(3)],"max":[max(float(p[i]) for p in reconstructed_world_points) for i in range(3)]},
                    "actual_authored_clone_world_bounds": {"min":[min(float(p[i]) for p in actual_world_points) for i in range(3)],"max":[max(float(p[i]) for p in actual_world_points) for i in range(3)]},
                    "actual_authored_clone_vertex_max_error_stage_units":actual_vertex_error,
                    "actual_authored_clone_vertex_max_error_m":actual_vertex_error*UsdGeom.GetStageMetersPerUnit(stage),
                    "clone_parent_is_instance_proxy":body.IsInstanceProxy(),
                }
            )

        if args.static_mapping_gate:
            marker("CLONES_AND_MATERIALS_RESOLVED",clone_count=len(clone_specs),components=[spec["component_label"] for spec in clone_specs])
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
        set_phase("LINKED_CLONES_CREATED",completed="linked_clones")
        stage.SetEditTarget(original_target)
        for _ in range(3):
            app.update()

        viewport = get_active_viewport()
        if viewport is not None:
            # Installed Kit 110 per-viewport settings. Hide presentation guides
            # without changing any USD joint or physics relationship.
            settings.set(f"/persistent/app/viewport/{viewport.id}/guide/axis/visible", False)
            settings.set(f"/persistent/app/viewport/{viewport.id}/guide/grid/visible", False)
            settings.set(f"/persistent/app/viewport/{viewport.id}/guide/selection/visible", False)
        clone_paths = [str(prim.GetPath()) for prim in clone_prims]
        if viewport is None or not frame_viewport_prims(viewport, prims=clone_paths):
            raise RuntimeError("failed to frame GUI diagnostic cabinet meshes")
        mins=[min(spec["source_world_bounds"]["min"][i] for spec in clone_specs) for i in range(3)]
        maxs=[max(spec["source_world_bounds"]["max"][i] for spec in clone_specs) for i in range(3)]
        center=[(a+b)*0.5 for a,b in zip(mins,maxs)]; sizes=[b-a for a,b in zip(mins,maxs)]
        asset_scale=max(sizes); distance=asset_scale*3.2
        if args.static_mapping_gate:
            cube_size=asset_scale*0.055
            def diagnostic_material(name,color):
                material=UsdShade.Material.Define(stage,f"/__PhysXGuiStatic/Material_{name}")
                shader=UsdShade.Shader.Define(stage,f"/__PhysXGuiStatic/Material_{name}/PreviewSurface")
                shader.CreateIdAttr("UsdPreviewSurface");shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color));shader.CreateInput("emissiveColor",Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color));shader.CreateInput("opacity",Sdf.ValueTypeNames.Float).Set(1.0);shader.CreateOutput("surface",Sdf.ValueTypeNames.Token);material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),"surface");return material
            def control_cube(path,size,position,color,material):
                item=UsdGeom.Cube.Define(stage,path);item.CreateSizeAttr(size);item.CreateDisplayColorPrimvar(UsdGeom.Tokens.constant).Set([Gf.Vec3f(*color)]);item.CreateDisplayOpacityPrimvar(UsdGeom.Tokens.constant).Set([1.0]);item.CreateDoubleSidedAttr(True);UsdGeom.Xformable(item).AddTranslateOp().Set(Gf.Vec3d(*position));UsdShade.MaterialBindingAPI.Apply(item.GetPrim()).Bind(material);return item
            orange=(1.0,0.45,0.02);magenta=(1.0,0.02,0.85);cyan=(0.02,0.95,1.0)
            cube=control_cube("/__PhysXGuiStatic/ReferenceCube",cube_size,[maxs[0]+asset_scale*0.10,center[1],mins[2]-cube_size],orange,diagnostic_material("ORANGE",orange))
            control_a=control_cube("/__PhysXGuiStatic/ControlCube",cube_size*0.65,[maxs[0]+asset_scale*0.10,mins[1]-asset_scale*0.08,mins[2]-cube_size],magenta,diagnostic_material("MAGENTA",magenta))
            control_b=control_cube("/__PhysXGuiStatic/ControlThinCube",cube_size*0.65,[maxs[0]+asset_scale*0.10,maxs[1]+asset_scale*0.08,mins[2]-cube_size],cyan,diagnostic_material("CYAN",cyan))
            control_b.CreateExtentAttr([Gf.Vec3f(-cube_size*0.325,-cube_size*0.08,-cube_size*0.325),Gf.Vec3f(cube_size*0.325,cube_size*0.08,cube_size*0.325)])
            UsdGeom.Xformable(control_b).AddScaleOp().Set(Gf.Vec3f(1.0,0.25,1.0))
            progress_path=args.run_dir/"static_capture_progress.json"
            heartbeat_path=args.run_dir/"gui_heartbeat.json"
            def save_progress(status, current=None, error=None, **extra):
                payload={"status":status,"current_camera":current,"physics_started":False,"simulation_steps":0,"external_capture_started":False,"error":error};payload.update(extra)
                progress_path.write_text(json.dumps(payload,indent=2)+"\n")
            save_progress("SOURCE_AND_CLONE_AUDIT_COMPLETE")

            def norm(v):
                n=math.sqrt(sum(x*x for x in v));return [x/n for x in v]
            def dot(a,b):return sum(x*y for x,y in zip(a,b))
            def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
            directions={"plus_X":[1,0,0],"minus_X":[-1,0,0],"plus_Y":[0,1,0],"minus_Y":[0,-1,0],"plus_Z":[0,0,1],"minus_Z":[0,0,-1],"diag_minusZ_plusX":[0.28,-0.12,-1],"diag_minusZ_minusX":[-0.28,-0.12,-1]}
            camera_candidates=[]
            for label,raw_direction in directions.items():
                direction=norm(raw_direction); eye=[center[i]+direction[i]*distance for i in range(3)]; forward=norm([center[i]-eye[i] for i in range(3)])
                up_hint=[0,1,0] if abs(forward[2])>0.85 else [0,0,1]
                right=norm(cross(forward,up_hint)); screen_up=norm(cross(right,forward))
                rows=[]
                for spec in clone_specs:
                    projected=[]; depths=[]
                    for point in corners(spec["actual_authored_clone_world_bounds"]):
                        relative=[point[i]-eye[i] for i in range(3)]; depth=dot(relative,forward);depths.append(depth)
                        projected.append([dot(relative,right)/depth,dot(relative,screen_up)/depth])
                    rect=[min(p[0] for p in projected),max(p[0] for p in projected),min(p[1] for p in projected),max(p[1] for p in projected)]
                    rows.append({"component":spec["component_label"],"clone":spec["clone_mesh"],"rect":rect,"projected_width":rect[1]-rect[0],"projected_height":rect[3]-rect[2],"depth_min":min(depths),"depth_max":max(depths)})
                doors=[row for row in rows if row["component"].startswith("gt_C_")]; bases=[row for row in rows if row["component"]=="BASE"]
                blockers=0
                for door in doors:
                    dc=(door["depth_min"]+door["depth_max"])*0.5
                    for base in bases:
                        overlap=max(0,min(door["rect"][1],base["rect"][1])-max(door["rect"][0],base["rect"][0]))*max(0,min(door["rect"][3],base["rect"][3])-max(door["rect"][2],base["rect"][2]))
                        door_area=max(1e-15,door["projected_width"]*door["projected_height"])
                        if overlap/door_area>0.5 and base["depth_min"]<dc: blockers+=1
                centers2=[[0.5*(d["rect"][0]+d["rect"][1]),0.5*(d["rect"][2]+d["rect"][3])] for d in doors]
                separation=min(math.dist(a,b) for i,a in enumerate(centers2) for b in centers2[i+1:])
                door_area=sum(d["projected_width"]*d["projected_height"] for d in doors)
                edge_on=sum(1 for d in doors if min(d["projected_width"],d["projected_height"])/max(d["projected_width"],d["projected_height"])<0.02)
                margin=max(max(abs(v) for v in row["rect"]) for row in rows)
                score=door_area+separation*0.5-blockers*10-edge_on*5-margin*0.01
                camera_candidates.append({"label":label,"eye":eye,"target":center,"screen_up":screen_up,"forward":forward,"component_projections":rows,"door_center_min_separation":separation,"door_projected_area_sum":door_area,"edge_on_door_count":edge_on,"base_occlusion_risk_count":blockers,"max_tangent_extent":margin,"score":score})
            preferred=max(camera_candidates,key=lambda row:row["score"])
            camera=UsdGeom.Camera.Define(stage,"/__PhysXGuiDiagnostic/Camera_front")
            view=Gf.Matrix4d(1.0); view.SetLookAt(Gf.Vec3d(*preferred["eye"]),Gf.Vec3d(*preferred["target"]),Gf.Vec3d(*preferred["screen_up"]))
            UsdGeom.Xformable(camera).AddTransformOp().Set(view.GetInverse()); camera.CreateFocalLengthAttr(35.0); camera.CreateClippingRangeAttr(Gf.Vec2f(max(0.01,distance-asset_scale*2),distance+asset_scale*2))
            viewport.set_active_camera(str(camera.GetPath()))
            for _ in range(20): app.update()
            sentinel=3.0e38
            sentinel_extent_present=any(abs(v)>=sentinel for spec in clone_specs for key in ("source_world_bounds","actual_authored_clone_world_bounds") for side in ("min","max") for v in spec[key][side])
            report["static_camera"]={"asset_bounds":{"min":mins,"max":maxs,"size":sizes},"center":center,"stage_up_axis":str(UsdGeom.GetStageUpAxis(stage)),"selection_basis":"numeric perspective projection of authored clone bounds; maximize door area/separation and penalize edge-on/base occlusion","preferred":preferred,"candidates":camera_candidates,"focal_length_mm":35.0,"clipping_range":[max(0.01,distance-asset_scale*2),distance+asset_scale*2],"reference_cube":{"path":"/__PhysXGuiStatic/ReferenceCube","size":cube_size},"control_geometry":["/__PhysXGuiStatic/ControlCube","/__PhysXGuiStatic/ControlThinCube"],"sentinel_extent_present":sentinel_extent_present,"external_capture_started":False}
            save_progress("CAMERA_ACTIVE_GUI_READY",preferred["label"],camera_path=str(camera.GetPath()),physics_steps=0)
            marker("CAMERA_ACTIVE",camera=str(camera.GetPath()),candidate=preferred["label"],eye=preferred["eye"],target=preferred["target"])
        context.get_selection().set_selected_prim_paths([], True)

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
            "mapping_invariants":{"mesh_count":len(clone_specs),"component_counts":{label:sum(1 for spec in clone_specs if spec["component_label"]==label) for label in ("BASE","gt_C_1","gt_C_2","gt_C_3")},"duplicate_source_meshes":len({spec["source_mesh"] for spec in clone_specs})!=len(clone_specs),"missing_door_components":[label for label in ("gt_C_1","gt_C_2","gt_C_3") if not any(spec["component_label"]==label for spec in clone_specs)],"max_actual_clone_vertex_error_m":max(spec["actual_authored_clone_vertex_max_error_m"] for spec in clone_specs)},
            "color_legend":{"BASE":list(colors[None]),"gt_C_1":list(colors["gt_C_1"]),"gt_C_2":list(colors["gt_C_2"]),"gt_C_3":list(colors["gt_C_3"])},
        }
        (args.run_dir / "static_mapping_gate.json").write_text(json.dumps(static_mapping,indent=2)+"\n")
        if args.static_mapping_gate:
            session_path=args.run_dir/"static_mapping_session_layer.usda"
            if not session.Export(str(session_path)): raise RuntimeError("session layer export failed")
            (args.run_dir / "runner_phase.txt").write_text("STATIC_RENDER_PIXEL_CAPTURE\n")
            from omni.kit.viewport.utility import capture_viewport_to_file, next_viewport_frame_async
            capture_path=args.run_dir/"viewport_render_pixel_gate.png"
            async def capture_active_viewport():
                for _ in range(30): await next_viewport_frame_async(viewport)
                capture=capture_viewport_to_file(viewport,file_path=str(capture_path),is_hdr=False)
                return await asyncio.wait_for(capture.wait_for_result(completion_frames=30),timeout=15.0)
            capture_task=asyncio.ensure_future(capture_active_viewport());capture_started=time.monotonic();capture_updates=0
            while not capture_task.done():
                before=time.monotonic();app.update();after=time.monotonic();capture_updates+=1
                if after-before>5.0 or after-capture_started>15.0:
                    capture_task.cancel();raise RuntimeError(f"internal viewport capture watchdog failed elapsed={after-capture_started:.3f}s update={after-before:.3f}s")
                time.sleep(0.01)
            if not capture_task.result() or not capture_path.is_file() or capture_path.stat().st_size==0: raise RuntimeError("internal viewport capture did not create PNG")
            marker("INTERNAL_VIEWPORT_CAPTURE_CREATED",path=str(capture_path),bytes=capture_path.stat().st_size,viewport_id=str(viewport.id),camera=str(viewport.camera_path),capture_updates=capture_updates)
            from PIL import Image
            import numpy as np
            from scipy import ndimage
            image=Image.open(capture_path).convert("RGB");rgb=np.asarray(image);hsv=np.asarray(image.convert("HSV"));h=hsv[:,:,0];sat=hsv[:,:,1];val=hsv[:,:,2]
            masks={
                "BASE_GRAY":(sat<=65)&(val>=55)&(val<=245),
                "gt_C_1_RED":((h<=12)|(h>=247))&(sat>=85)&(val>=55),
                "gt_C_2_GREEN":(h>=60)&(h<=112)&(sat>=70)&(val>=50),
                "gt_C_3_BLUE":(h>=138)&(h<=190)&(sat>=70)&(val>=50),
                "REFERENCE_ORANGE":(h>=12)&(h<=38)&(sat>=90)&(val>=60),
                "CONTROL_MAGENTA":(h>=205)&(h<=242)&(sat>=90)&(val>=60),
                "CONTROL_CYAN":(h>=115)&(h<=140)&(sat>=90)&(val>=60),
            }
            pixel_rows={}
            for name,raw_mask in masks.items():
                labels,component_count=ndimage.label(raw_mask)
                sizes=np.bincount(labels.ravel())
                if sizes.size: sizes[0]=0
                largest_label=int(sizes.argmax()) if sizes.size and sizes.max()>0 else 0
                mask=labels==largest_label if largest_label else np.zeros_like(raw_mask,dtype=bool)
                ys,xs=np.where(mask);count=int(mask.sum())
                pixel_rows[name]={"raw_pixel_count":int(raw_mask.sum()),"connected_component_count":int(component_count),"pixel_count":count,"bbox_xyxy":[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if count else None,"center_xy":[float(xs.mean()),float(ys.mean())] if count else None,"screen_fraction":count/float(mask.size),"mean_rgb":[float(x) for x in rgb[mask].mean(axis=0)] if count else None,"selection":"largest_4_connected_component"}
            required=("BASE_GRAY","gt_C_1_RED","gt_C_2_GREEN","gt_C_3_BLUE","REFERENCE_ORANGE","CONTROL_MAGENTA","CONTROL_CYAN")
            minimum_pixels=30;missing=[name for name in required if pixel_rows[name]["pixel_count"]<minimum_pixels]
            door_centers=[pixel_rows[name]["center_xy"] for name in ("gt_C_1_RED","gt_C_2_GREEN","gt_C_3_BLUE") if pixel_rows[name]["center_xy"]]
            min_door_center_distance=min((math.dist(a,b) for i,a in enumerate(door_centers) for b in door_centers[i+1:]),default=0.0)
            pixel_report={"status":"AUTOMATION_RENDER_PIXEL_GATE_PASS_HUMAN_CHECK_REQUIRED" if not missing and min_door_center_distance>=10.0 else "RENDER_PIXEL_GATE_FAIL","capture_path":str(capture_path),"capture_sha256":digest(capture_path),"width":image.width,"height":image.height,"nonblack_pixel_ratio":float((rgb.max(axis=2)>10).mean()),"minimum_pixels":minimum_pixels,"components":pixel_rows,"missing_or_too_small":missing,"door_center_min_distance_pixels":min_door_center_distance,"active_viewport_id":str(viewport.id),"active_camera":str(viewport.camera_path),"physics_steps":0}
            (args.run_dir/"render_pixel_gate.json").write_text(json.dumps(pixel_report,indent=2)+"\n")
            marker("RENDER_PIXEL_GATE",status=pixel_report["status"],missing=missing,door_center_min_distance_pixels=min_door_center_distance)
            if pixel_report["status"]!="AUTOMATION_RENDER_PIXEL_GATE_PASS_HUMAN_CHECK_REQUIRED": raise RuntimeError(f"render pixel gate failed: missing={missing} door_center_distance={min_door_center_distance}")
            (args.run_dir / "runner_phase.txt").write_text("STATIC_MAPPING_HUMAN_REVIEW\n")
            started=time.monotonic(); last_heartbeat=started; update_count=0; heartbeat_count=0
            save_progress("HUMAN_REVIEW_WINDOW", report["static_camera"]["preferred"]["label"],internal_capture=str(capture_path))
            marker("GUI_SHOWN_HUMAN_CHECK_REQUIRED",duration_s=45.0,camera=report["static_camera"]["preferred"]["label"])
            while time.monotonic()-started < 45.0:
                before=time.monotonic(); app.update(); after=time.monotonic(); update_count+=1
                if after-before>5.0: raise RuntimeError(f"GUI update watchdog exceeded 5 seconds: {after-before:.3f}s")
                if after-last_heartbeat>=1.0:
                    heartbeat_count+=1; last_heartbeat=after
                    heartbeat_path.write_text(json.dumps({"status":"RESPONSIVE","elapsed_s":after-started,"update_count":update_count,"heartbeat_count":heartbeat_count,"physics_steps":0},indent=2)+"\n")
                time.sleep(0.01)
            save_progress("COMPLETE_HUMAN_CHECK_REQUIRED", report["static_camera"]["preferred"]["label"],update_count=update_count,heartbeat_count=heartbeat_count)
            print("STATIC_MAPPING_GATE=AUTOMATION_READY_HUMAN_CHECK_REQUIRED",flush=True)
            report["completed_phases"].extend(["stage","linked_clones","static_pixel_gate","human_review_window"])
            return finish(0,"DIAGNOSTIC_COMPLETE_HUMAN_CHECK_REQUIRED",asset_pass=False)

        # The physics camera is a slight 3/4 view derived from the verified
        # minus-Z mapping view.  It preserves all three door panels while
        # exposing depth change around their Y axes.
        stage.SetEditTarget(Usd.EditTarget(session))
        camera=UsdGeom.Camera.Define(stage,"/__PhysXGuiDiagnostic/Camera_physics")
        eye=[center[0]+asset_scale*0.42,center[1]+asset_scale*0.10,center[2]-distance]
        view_matrix=Gf.Matrix4d(1.0);view_matrix.SetLookAt(Gf.Vec3d(*eye),Gf.Vec3d(*center),Gf.Vec3d(0.0,1.0,0.0))
        UsdGeom.Xformable(camera).AddTransformOp().Set(view_matrix.GetInverse())
        camera.CreateFocalLengthAttr(35.0);camera.CreateClippingRangeAttr(Gf.Vec2f(max(0.01,distance-asset_scale*2),distance+asset_scale*2))
        viewport.set_active_camera(str(camera.GetPath()))
        context.get_selection().set_selected_prim_paths([],True)
        diagnostic_controls=[]
        if args.diffuse_only_material_diagnostic:
            # Both controls use the same camera and light. Keep them outside
            # the asset bounds so their pixels cannot satisfy a door region.
            stage.SetEditTarget(Usd.EditTarget(session))
            for name,color,emissive,y in (
                ("DiffuseControl",(0.12,0.68,0.92),False,center[1]-asset_scale*0.10),
                ("EmissiveControl",(0.92,0.12,0.72),True,center[1]+asset_scale*0.10),
            ):
                path=f"/__PhysXGuiDiagnostic/{name}"
                cube=UsdGeom.Cube.Define(stage,path);cube.CreateSizeAttr(asset_scale*0.055)
                cube.CreateDisplayColorPrimvar(UsdGeom.Tokens.constant).Set([Gf.Vec3f(*color)])
                UsdGeom.Xformable(cube).AddTranslateOp().Set(Gf.Vec3d(maxs[0]+asset_scale*0.12,y,center[2]))
                material=UsdShade.Material.Define(stage,path+"Material")
                shader=UsdShade.Shader.Define(stage,path+"Material/PreviewSurface")
                shader.CreateIdAttr("UsdPreviewSurface")
                shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
                if emissive:shader.CreateInput("emissiveColor",Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
                shader.CreateInput("opacity",Sdf.ValueTypeNames.Float).Set(1.0)
                shader.CreateOutput("surface",Sdf.ValueTypeNames.Token)
                material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),"surface")
                UsdShade.MaterialBindingAPI.Apply(cube.GetPrim()).Bind(material)
                diagnostic_controls.append({"name":name,"prim":path,"material":str(material.GetPath()),"position":[maxs[0]+asset_scale*0.12,y,center[2]],"size":asset_scale*0.055,"emissive":emissive})
            stage.SetEditTarget(original_target)
        for _ in range(30): app.update()

        # Pre-physics rendered-pixel gate: this validates the body-local linked
        # clones, not the world-space clones used by the approved static gate.
        from omni.kit.viewport.utility import capture_viewport_to_file, next_viewport_frame_async
        from PIL import Image
        import numpy as np
        from scipy import ndimage
        from capture_file_stability import wait_for_stable_png
        async def capture_viewport_png(path, fast=False):
            for _ in range(1 if fast else 30): await next_viewport_frame_async(viewport)
            handle=capture_viewport_to_file(viewport,file_path=str(path),is_hdr=False)
            completed=await asyncio.wait_for(handle.wait_for_result(completion_frames=1 if fast else 30),timeout=15.0)
            if not completed:return False
            stable=await wait_for_stable_png(path,omni.kit.app.get_app().next_update_async,timeout_s=15.0,stable_observations=2)
            return stable.get("status")=="CAPTURE_OK"

        async def capture_viewport_png_stable(label, fast=True, timeout_s=15.0):
            """Wait for renderer flush, stable size, PNG header, and decode."""
            path=(args.run_dir/f"visual_continuity_{label}.png").resolve()
            path.parent.mkdir(parents=True,exist_ok=True)
            marker_dir=args.run_dir/"capture_markers";marker_dir.mkdir(parents=True,exist_ok=True)
            request={"label":label,"status":"CAPTURE_REQUESTED","path":str(path),"wall_time":time.time()}
            request_path=marker_dir/f"{label}.request.json";tmp=request_path.with_suffix(".json.tmp");tmp.write_text(json.dumps(request,indent=2)+"\n");os.replace(tmp,request_path)
            result={**request,"status":"CAPTURE_FAILED","timeout_s":timeout_s}
            try:
                for _ in range(2 if fast else 30):await next_viewport_frame_async(viewport)
                handle=capture_viewport_to_file(viewport,file_path=str(path),is_hdr=False)
                result["capture_api_result"]=bool(await asyncio.wait_for(handle.wait_for_result(completion_frames=2 if fast else 30),timeout=timeout_s))
                try:
                    import omni.kit.renderer_capture
                    omni.kit.renderer_capture.acquire_renderer_capture_interface().wait_async_capture()
                    result["renderer_capture_flush"]="CALLED"
                except BaseException as flush_error:
                    result["renderer_capture_flush"]="UNAVAILABLE_OR_FAILED";result["renderer_capture_flush_error"]=repr(flush_error)
                file_result=await wait_for_stable_png(path,omni.kit.app.get_app().next_update_async,timeout_s=timeout_s,stable_observations=2)
                result.update(file_result)
            except BaseException as error:result.update({"reason":"CAPTURE_API_EXCEPTION","exception":repr(error)})
            result["completed_wall_time"]=time.time()
            done=marker_dir/f"{label}.result.json";tmp=done.with_suffix(".json.tmp");tmp.write_text(json.dumps(result,indent=2)+"\n");os.replace(tmp,done)
            return result
        masks_factory=lambda h,sat,val:{"BASE_GRAY":(sat<=65)&(val>=55)&(val<=245),"gt_C_1_RED":((h<=12)|(h>=247))&(sat>=85)&(val>=55),"gt_C_2_GREEN":(h>=60)&(h<=112)&(sat>=70)&(val>=50),"gt_C_3_BLUE":(h>=138)&(h<=190)&(sat>=70)&(val>=50)}
        def analyze_diffuse_only(path,label,relative_step):
            image=Image.open(path).convert("RGB");rgb=np.asarray(image);hsv=np.asarray(image.convert("HSV"));h,sat,val=hsv[:,:,0],hsv[:,:,1],hsv[:,:,2]
            cyan=(h>=115)&(h<=155)&(sat>=70)&(val>=35);magenta=(h>=195)&(h<=240)&(sat>=70)&(val>=35);nonblack=rgb.max(axis=2)>10
            labels,_=ndimage.label(cyan);sizes_cc=np.bincount(labels.ravel());sizes_cc[0]=0
            selected=labels==int(sizes_cc.argmax()) if sizes_cc.max()>0 else np.zeros_like(cyan,dtype=bool);ys,xs=np.where(selected);cyan_count=int(selected.sum())
            camera_world=UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(camera.GetPrim());world_to_camera=camera_world.GetInverse()
            focal=float(camera.GetFocalLengthAttr().Get());hap=float(camera.GetHorizontalApertureAttr().Get());vap=float(camera.GetVerticalApertureAttr().Get());projected={}
            for component in ("BASE","gt_C_1","gt_C_2","gt_C_3"):
                points=[]
                for spec in clone_specs:
                    if spec["component_label"]!=component:continue
                    for point in corners(spec["actual_authored_clone_world_bounds"]):
                        pc=world_to_camera.Transform(Gf.Vec3d(*point));depth=-float(pc[2])
                        if depth>0:
                            nx=float(pc[0])/depth*focal/(hap*0.5);ny=float(pc[1])/depth*focal/(vap*0.5);points.append(((nx+1)*0.5*image.width,(1-ny)*0.5*image.height))
                if not points:projected[component]={"in_front":False,"intersects_frame":False,"bbox_xyxy":None,"cyan_pixels":0,"nonblack_ratio":0.0};continue
                x0=max(0,int(math.floor(min(x for x,_ in points))));x1=min(image.width-1,int(math.ceil(max(x for x,_ in points))));y0=max(0,int(math.floor(min(y for _,y in points))));y1=min(image.height-1,int(math.ceil(max(y for _,y in points))));inside=x1>=x0 and y1>=y0
                region_cyan=cyan[y0:y1+1,x0:x1+1] if inside else np.zeros((0,0),bool);region_nonblack=nonblack[y0:y1+1,x0:x1+1] if inside else np.zeros((0,0),bool)
                projected[component]={"in_front":True,"intersects_frame":inside,"bbox_xyxy":[x0,y0,x1,y1] if inside else None,"cyan_pixels":int(region_cyan.sum()),"nonblack_ratio":float(region_nonblack.mean()) if region_nonblack.size else 0.0}
            control_rows={}
            for control in diagnostic_controls:
                half=control["size"]*0.5;position=control["position"]
                bounds={"min":[position[i]-half for i in range(3)],"max":[position[i]+half for i in range(3)]};points=[]
                for point in corners(bounds):
                    pc=world_to_camera.Transform(Gf.Vec3d(*point));depth=-float(pc[2])
                    if depth>0:
                        nx=float(pc[0])/depth*focal/(hap*0.5);ny=float(pc[1])/depth*focal/(vap*0.5);points.append(((nx+1)*0.5*image.width,(1-ny)*0.5*image.height))
                if not points:control_rows[control["name"]]={"bbox_xyxy":None,"color_pixels":0,"nonblack_ratio":0.0};continue
                x0=max(0,int(math.floor(min(x for x,_ in points))));x1=min(image.width-1,int(math.ceil(max(x for x,_ in points))));y0=max(0,int(math.floor(min(y for _,y in points))));y1=min(image.height-1,int(math.ceil(max(y for _,y in points))));inside=x1>=x0 and y1>=y0
                color_mask=magenta if control["emissive"] else cyan;region=color_mask[y0:y1+1,x0:x1+1] if inside else np.zeros((0,0),bool);region_nonblack=nonblack[y0:y1+1,x0:x1+1] if inside else np.zeros((0,0),bool)
                control_rows[control["name"]]={"bbox_xyxy":[x0,y0,x1,y1] if inside else None,"color_pixels":int(region.sum()),"nonblack_ratio":float(region_nonblack.mean()) if region_nonblack.size else 0.0,"emissive":control["emissive"]}
            regions_pass=all(row["intersects_frame"] and row["cyan_pixels"]>=5 and row["nonblack_ratio"]>=0.001 for row in projected.values())
            status="PASS" if diffuse_pixel_decision(cyan_count,float(nonblack.mean()),projected) else "FAIL"
            diffuse_visible=control_rows.get("DiffuseControl",{}).get("color_pixels",0)>=5;emissive_visible=control_rows.get("EmissiveControl",{}).get("color_pixels",0)>=5
            interpretation="ASSET_AND_CONTROLS_REQUIRE_HOST_RESULT"
            if emissive_visible and not diffuse_visible:interpretation="DIFFUSE_LIGHTING_OR_MATERIAL_PATH_SUSPECT"
            elif diffuse_visible and not regions_pass:interpretation="ASSET_GEOMETRY_NORMALS_OR_RENDER_POPULATION_SUSPECT"
            elif not diffuse_visible and not emissive_visible:interpretation="CAMERA_RENDER_SYNC_OR_SHARED_PRESENTATION_SUSPECT"
            return {"label":label,"status":status,"status_scope":"DIFFUSE_ONLY_CYAN_BOUNDARY","relative_physics_step":relative_step,"manager_step":SimulationManager.get_num_physics_steps() if relative_step is not None else None,"capture_path":str(path),"capture_sha256":digest(path),"resolution":[image.width,image.height],"cyan_pixel_count":cyan_count,"cyan_bbox_xyxy":[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if cyan_count else None,"nonblack_pixel_count":int(nonblack.sum()),"nonblack_pixel_ratio":float(nonblack.mean()),"components":projected,"controls":control_rows,"interpretation":interpretation,"missing":[name for name,row in projected.items() if not (row["intersects_frame"] and row["cyan_pixels"]>=5 and row["nonblack_ratio"]>=0.001)],"threshold_basis":"10163-style diffuseColor=(0.12,0.68,0.92); HSV 115..155, saturation>=70, value>=35; whole connected cyan>=30/nonblack>=0.001; each projected component cyan>=5/nonblack>=0.001; controls are outside asset regions"}
        def capture_pixel_gate(label,relative_step,baseline=None,raise_on_fail=True,fast=False,captured_path=None):
            path=captured_path or args.run_dir/f"visual_continuity_{label}.png"
            if captured_path is None:
                task=asyncio.ensure_future(capture_viewport_png(path,fast=fast));started=time.monotonic()
                last_capture_heartbeat=0.0
                while not task.done():
                    before=time.monotonic();app.update();after=time.monotonic()
                    if after-last_capture_heartbeat>=1.0:
                        (args.run_dir/"gui_heartbeat.json").write_text(json.dumps({"phase":f"VIEWPORT_CAPTURE_{label}","wall_monotonic_s":after,"elapsed_s":after-started,"physics_step_count":SimulationManager.get_num_physics_steps()})+"\n")
                        last_capture_heartbeat=after
                    if after-before>5.0 or after-started>15.0:task.cancel();raise RuntimeError(f"visual continuity capture watchdog failed: {label}")
                    time.sleep(0.01)
                if not task.result():raise RuntimeError(f"visual continuity capture API failed: {label}")
            if not path.is_file() or path.stat().st_size==0:raise RuntimeError(f"visual continuity capture missing: {label}")
            if args.diffuse_only_material_diagnostic:
                result=analyze_diffuse_only(path,label,relative_step)
                if result["status"]!="PASS" and raise_on_fail:raise RuntimeError(f"DIFFUSE_ONLY_PIXEL_GATE_FAIL {result}")
                return result
            image=Image.open(path).convert("RGB");hsv=np.asarray(image.convert("HSV"));masks=masks_factory(hsv[:,:,0],hsv[:,:,1],hsv[:,:,2]);components={}
            for name,raw in masks.items():
                labels,_=ndimage.label(raw);sizes_cc=np.bincount(labels.ravel());sizes_cc[0]=0;chosen=labels==int(sizes_cc.argmax()) if sizes_cc.max()>0 else np.zeros_like(raw,dtype=bool)
                ys,xs=np.where(chosen);count=int(chosen.sum());components[name]={"pixel_count":count,"bbox_xyxy":[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if count else None,"center_xy":[float(xs.mean()),float(ys.mean())] if count else None}
            missing=[name for name,row in components.items() if row["pixel_count"]<30];continuity={};final_recovery=None
            if baseline:
                for name,row in components.items():
                    prior=baseline[name];ratio=row["pixel_count"]/max(1,prior["pixel_count"]);shift=math.dist(row["center_xy"],prior["center_xy"]) if row["center_xy"] and prior["center_xy"] else float("inf")
                    continuity[name]={"pixel_ratio_to_prephysics":ratio,"center_shift_px":shift,"bbox_iou_to_prephysics":bbox_iou(row["bbox_xyxy"],prior["bbox_xyxy"]),"transient_monitor_pass":ratio>=TRANSIENT_PIXEL_RATIO and shift<=TRANSIENT_CENTER_SHIFT_PX}
                doors=("gt_C_1_RED","gt_C_2_GREEN","gt_C_3_BLUE")
                door_checks={}
                for name in doors:
                    prior=baseline[name];metric=continuity[name];center_limit=max(10.0,0.05*bbox_diagonal(prior["bbox_xyxy"]))
                    door_checks[name]={"pixel_ratio":metric["pixel_ratio_to_prephysics"],"bbox_iou":metric["bbox_iou_to_prephysics"],"center_shift_px":metric["center_shift_px"],"center_shift_limit_px":center_limit,"pass":components[name]["pixel_count"]>=30 and metric["pixel_ratio_to_prephysics"]>=FINAL_DOOR_PIXEL_RATIO and metric["bbox_iou_to_prephysics"]>=FINAL_DOOR_BBOX_IOU and metric["center_shift_px"]<=center_limit}
                pairwise=[]
                for index,left in enumerate(doors):
                    for right in doors[index+1:]:
                        distance=math.dist(components[left]["center_xy"],components[right]["center_xy"]) if components[left]["center_xy"] and components[right]["center_xy"] else 0.0
                        overlap=bbox_iou(components[left]["bbox_xyxy"],components[right]["bbox_xyxy"])
                        pairwise.append({"left":left,"right":right,"center_distance_px":distance,"bbox_iou":overlap,"separated":distance>=FINAL_MIN_DOOR_CENTER_SEPARATION_PX,"not_merged":overlap<=FINAL_MAX_PAIRWISE_DOOR_BBOX_IOU})
                base_ratio=continuity["BASE_GRAY"]["pixel_ratio_to_prephysics"]
                final_recovery={"door_checks":door_checks,"base_pixel_ratio":base_ratio,"base_pass":components["BASE_GRAY"]["pixel_count"]>=30 and base_ratio>=FINAL_BASE_PIXEL_RATIO,"pairwise_doors":pairwise}
                final_recovery["pass"]=all(row["pass"] for row in door_checks.values()) and final_recovery["base_pass"] and all(row["separated"] and row["not_merged"] for row in pairwise)
            status="PASS" if not missing and all(x["transient_monitor_pass"] for x in continuity.values()) else "FAIL"
            result={"label":label,"status":status,"status_scope":"TRANSIENT_MONITOR_ONLY" if baseline else "STATIC_BASELINE","relative_physics_step":relative_step,"manager_step":SimulationManager.get_num_physics_steps() if relative_step is not None else None,"capture_path":str(path),"capture_sha256":digest(path),"components":components,"missing":missing,"continuity":continuity,"final_recovery_visual_gate":final_recovery}
            if status!="PASS" and raise_on_fail:raise RuntimeError(f"VISUAL_CONTINUITY_GATE_FAIL {result}")
            return result
        async def capture_pixel_gate_async(label,relative_step,baseline=None,raise_on_fail=True,fast=False):
            """Capture inside an existing Kit task without nested app.update()."""
            path=args.run_dir/f"visual_continuity_{label}.png"
            if not await capture_viewport_png(path,fast=fast):
                raise RuntimeError(f"visual continuity capture API failed: {label}")
            return capture_pixel_gate(label,relative_step,baseline,raise_on_fail,fast,captured_path=path)
        def material_binding_audit():
            rows=[]
            for spec,prim in zip(clone_specs,clone_prims):
                binding=UsdShade.MaterialBindingAPI(prim);material,_=binding.ComputeBoundMaterial()
                shader=UsdShade.Shader(stage.GetPrimAtPath(str(material.GetPath())+"/PreviewSurface")) if material else None
                def shader_input(name):
                    value=shader.GetInput(name).Get() if shader and shader.GetInput(name) else None
                    return [float(x) for x in value] if value is not None and hasattr(value,"__iter__") else value
                rows.append({
                    "clone":str(prim.GetPath()),"component":spec["component_label"],
                    "visibility":str(UsdGeom.Imageable(prim).ComputeVisibility()),"purpose":str(UsdGeom.Imageable(prim).ComputePurpose()),
                    "points":len(UsdGeom.Mesh(prim).GetPointsAttr().Get() or []),"face_counts":len(UsdGeom.Mesh(prim).GetFaceVertexCountsAttr().Get() or []),
                    "face_indices":len(UsdGeom.Mesh(prim).GetFaceVertexIndicesAttr().Get() or []),"extent":str(UsdGeom.Mesh(prim).GetExtentAttr().Get()),
                    "normals":len(UsdGeom.Mesh(prim).GetNormalsAttr().Get() or []),"normals_interpolation":str(UsdGeom.Mesh(prim).GetNormalsInterpolation()),
                    "orientation":str(UsdGeom.Mesh(prim).GetOrientationAttr().Get()),"subdivision_scheme":str(UsdGeom.Mesh(prim).GetSubdivisionSchemeAttr().Get()),"double_sided":bool(UsdGeom.Mesh(prim).GetDoubleSidedAttr().Get()),
                    "xform_op_order":str(prim.GetAttribute("xformOpOrder").Get()),
                    "direct_material_targets":[str(x) for x in prim.GetRelationship("material:binding").GetTargets()],
                    "computed_material":str(material.GetPath()) if material else None,"shader":str(shader.GetPath()) if shader else None,
                    "diffuseColor":shader_input("diffuseColor"),"emissiveColor":shader_input("emissiveColor"),"opacity":shader_input("opacity"),
                    "displayColor":str(prim.GetAttribute("primvars:displayColor").Get()),"displayColor_interpolation":str(UsdGeom.Mesh(prim).GetDisplayColorPrimvar().GetInterpolation()),
                    "displayOpacity":str(prim.GetAttribute("primvars:displayOpacity").Get()),"displayOpacity_interpolation":str(UsdGeom.Mesh(prim).GetDisplayOpacityPrimvar().GetInterpolation()),
                    "prim_spec_layers":[spec.layer.identifier for spec in prim.GetPrimStack()],
                    "material_spec_layers":[spec.layer.identifier for spec in material.GetPrim().GetPrimStack()] if material else [],
                    "world_bounds":spec["actual_authored_clone_world_bounds"],
                })
            return {"mode":"DIFFUSE_ONLY_CYAN" if args.diffuse_only_material_diagnostic else "DEFAULT_RGB","session_layer":session.identifier,"edit_target":stage.GetEditTarget().GetLayer().identifier,"renderer_warmup":{"synchronous_app_updates_before_camera_capture":30,"capture_completion_frames":30,"renderer_sync_verified_by_pixels":False},"controls":diagnostic_controls,"clones":rows}
        material_audit=material_binding_audit()
        set_phase("PREPHYSICS_MATERIAL_AUDIT")
        material_audit["binding_pass"]=all(row["direct_material_targets"]==[row["computed_material"]] and row["shader"] and row["diffuseColor"] is not None and row["opacity"]==1.0 for row in material_audit["clones"])
        atomic_json(args.run_dir/"prephysics_material_binding_audit.json",material_audit)
        atomic_json(args.run_dir/"renderer_material_sync_marker.json",{"status":"MATERIAL_BINDINGS_RESOLVED_RENDER_SYNC_NOT_YET_VERIFIED" if material_audit["binding_pass"] else "MATERIAL_BINDING_INVALID","binding_pass":material_audit["binding_pass"],"app_updates_after_camera_activation":30,"capture_completion_frames":30,"physics_initialized":False})
        if not material_audit["binding_pass"]:
            report["status"]="DIFFUSE_ONLY_PREPHYSICS_INVALID" if args.diffuse_only_material_diagnostic else "PREPHYSICS_MATERIAL_BINDING_INVALID"
            report["material_audit"]=material_audit;atomic_json(args.run_dir/"physics_gui_report.json",report);(args.run_dir/"runner_phase.txt").write_text(report["status"]+"\n");return finish(21,report["status"],asset_pass=False)

        prephysics_gate=capture_pixel_gate("prephysics",None,raise_on_fail=not args.diffuse_only_material_diagnostic)
        set_phase("PREPHYSICS_CAPTURED",completed="prephysics_gate")
        if args.diffuse_only_material_diagnostic:
            cyan_report={**prephysics_gate,"status":"PASS" if prephysics_gate["status"]=="PASS" else "DIFFUSE_ONLY_PREPHYSICS_INVALID","legacy_rgb_gate_status":"NOT_RUN","legacy_rgb_gate_is_decisive":False,"material_audit_path":str(args.run_dir/"prephysics_material_binding_audit.json"),"physics_initialized":False,"active_schedule_started":False,"recorder_started":False}
            atomic_json(args.run_dir/"diffuse_only_prephysics_gate.json",cyan_report)
            print("DIFFUSE_ONLY_PREPHYSICS_GATE="+cyan_report["status"],flush=True)
            if cyan_report["status"]!="PASS":
                report["status"]="DIFFUSE_ONLY_PREPHYSICS_INVALID_OBSERVATION";report["diffuse_only_prephysics_gate"]=cyan_report
                atomic_json(args.run_dir/"physics_gui_report.json",report)
                (args.run_dir/"runner_phase.txt").write_text("DIFFUSE_ONLY_PREPHYSICS_INVALID\n")
                # Isolation mode is bounded to closed targets and ten steps.
                # Preserve the visual failure and continue collecting the safe
                # API/Fabric boundary evidence. Active motion and recording stay disabled.
            prephysics_gate={**prephysics_gate,"mode":"DIFFUSE_ONLY_CYAN","cyan_gate":cyan_report}
        prephysics_gate.update({"physics_steps":0,"camera":{"path":str(camera.GetPath()),"eye":eye,"target":center,"selection":"minus-Z derived 3/4; +X/+Y offset exposes Y-axis door depth"},"linked_clone_max_roundtrip_error_m":max(spec["actual_authored_clone_vertex_max_error_m"] for spec in clone_specs)})
        (args.run_dir/"prephysics_pixel_gate.json").write_text(json.dumps(prephysics_gate,indent=2)+"\n")
        report["prephysics_pixel_gate"]=prephysics_gate
        prephysics_smokes=[]
        if args.initialization_isolation_diagnostic:
            print("DIAGNOSTIC_ONLY_ACTIVE_DOOR_MOTION_NOT_EXPECTED",flush=True)
            for smoke_label in ("prephysics_smoke_1","prephysics_smoke_2"):
                task=asyncio.ensure_future(capture_viewport_png_stable(smoke_label));started=time.monotonic()
                while not task.done():
                    app.update()
                    if time.monotonic()-started>20.0:task.cancel();break
                    time.sleep(0.005)
                prephysics_smokes.append(task.result() if task.done() and not task.cancelled() else {"label":smoke_label,"status":"CAPTURE_FAILED","reason":"OUTER_PUMP_TIMEOUT"})
            report["prephysics_capture_smokes"]=prephysics_smokes
        stage.SetEditTarget(original_target)

        diagnostic_marker_path=args.run_dir/"initialization_diagnostic_markers.jsonl"
        def diagnostic_marker(name,**values):
            try:manager_step=SimulationManager.get_num_physics_steps()
            except BaseException:manager_step=None
            row={"marker":name,"wall_time":time.time(),"manager_step":manager_step};row.update(values)
            with diagnostic_marker_path.open("a") as stream:stream.write(json.dumps(row,sort_keys=True)+"\n")
            print("INITIALIZATION_DIAGNOSTIC_MARKER_"+name+"="+json.dumps(row,sort_keys=True),flush=True)
        def usd_prim_state(path):
            prim=stage.GetPrimAtPath(path);cache=UsdGeom.XformCache(Usd.TimeCode.Default());matrix=cache.GetLocalToWorldTransform(prim);rotation=matrix.ExtractRotationQuat();bbox=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render,UsdGeom.Tokens.proxy]).ComputeWorldBound(prim).ComputeAlignedRange()
            imageable=UsdGeom.Imageable(prim);material=UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
            return {"path":path,"active":prim.IsActive(),"loaded":prim.IsLoaded(),"visibility":str(imageable.ComputeVisibility()) if imageable else None,"purpose":str(imageable.ComputePurpose()) if imageable else None,"parent":str(prim.GetParent().GetPath()),"world_matrix":matrix_values(matrix),"translation":[float(x) for x in matrix.ExtractTranslation()],"quaternion_real_imag":[float(rotation.GetReal()),*[float(x) for x in rotation.GetImaginary()]],"world_bounds":{"min":[float(x) for x in bbox.GetMin()],"max":[float(x) for x in bbox.GetMax()]},"material":str(material.GetPath()) if material else None,"display_color":str(prim.GetAttribute("primvars:displayColor").Get()),"display_opacity":str(prim.GetAttribute("primvars:displayOpacity").Get())}
        tracked_paths=sorted({next(iter({value["body0"] for value in joint_bodies.values()})),*[value["body1"] for value in joint_bodies.values()],*[spec["source_mesh"] for spec in clone_specs],*[spec["clone_mesh"] for spec in clone_specs]})
        def usd_snapshot(label,pixel_gate):
            return {"label":label,"manager_step":SimulationManager.get_num_physics_steps(),"prims":{path:usd_prim_state(path) for path in tracked_paths},"joint_authored":joint_frames,"pixel_gate":pixel_gate,"object_id":{"status":"NOT_CAPTURED","reason":"No supported viewport prim-ID API was found in the installed Kit examples; semantic IDs would require a separate Replicator annotator path."},"depth":{"status":"AVAILABLE_INSTALLED_API_NOT_INVOKED","api":"isaacsim.test.utils.image_capture.capture_depth_data_async","reason":"Replicator render-product initialization is intentionally excluded from this minimal initialization diagnostic."}}
        report["initialization_diagnostic"]={"before_initialize":usd_snapshot("before_initialize",prephysics_gate)}
        diagnostic_marker("STAGE_LOADED");diagnostic_marker("LINKED_CLONES_CREATED",clone_count=len(clone_specs))
        diagnostic_marker("PREPHYSICS_PIXEL_GATE_PASS" if prephysics_gate["status"]=="PASS" else "PREPHYSICS_PIXEL_GATE_FAIL_OBSERVED",pixel_status=prephysics_gate["status"])
        diagnostic_marker("BEFORE_INITIALIZE_STATE_CAPTURED")

        SimulationManager.setup_simulation(dt=1.0 / 60.0, device="cuda:0")
        set_phase("FABRIC_SETUP_COMPLETE",completed="fabric_setup")
        if args.diffuse_only_material_diagnostic:
            fabric_setup_gate=capture_pixel_gate("after_setup_fabric_enabled_before_initialize",0,prephysics_gate["components"],raise_on_fail=False)
            report["initialization_diagnostic"]["after_setup_fabric_enabled_before_initialize"]={"usd":usd_snapshot("after_setup_fabric_enabled_before_initialize",fabric_setup_gate),"tensor":"NOT_CREATED_YET"}
            diagnostic_marker("FABRIC_ENABLED_BEFORE_INITIALIZE_CAPTURED",pixel_status=fabric_setup_gate["status"],api_evidence="SimulationManager.set_device(cuda:0) calls enable_fabric(True) in installed 6.1 runtime")
        SimulationManager.initialize_physics()
        set_phase("PHYSICS_INITIALIZED",completed="physics_initialize")
        diagnostic_marker("PHYSICS_INITIALIZED_NO_STEP_IF_API_ALLOWS",manager_step_observed=SimulationManager.get_num_physics_steps())
        if args.diffuse_only_material_diagnostic:
            before_tensor_gate=capture_pixel_gate("after_initialize_before_tensor",0,prephysics_gate["components"],raise_on_fail=False)
            report["initialization_diagnostic"]["after_initialize_before_tensor"]={"usd":usd_snapshot("after_initialize_before_tensor",before_tensor_gate),"tensor":"NOT_CREATED_YET"}
            diagnostic_marker("AFTER_INITIALIZE_BEFORE_TENSOR_CAPTURED",pixel_status=before_tensor_gate["status"])
        view = SimulationManager.get_physics_simulation_view()
        articulation = view.create_articulation_view([str(articulations[0].GetPath())])
        if articulation.count != 1 or articulation.max_dofs != 3:
            raise RuntimeError(f"articulation count/dof={articulation.count}/{articulation.max_dofs}")
        meta = articulation.get_metatype(0);diagnostic_marker("TENSOR_VIEW_CREATED",dof_names=list(meta.dof_names));diagnostic_marker("FABRIC_ALREADY_ENABLED",first_update_fabric_step_pending=True)
        set_phase("TENSOR_VIEW_CREATED",completed="tensor_view")
        runtime_dof_indices={name:int(meta.dof_indices[name]) for name in meta.dof_names}
        runtime_link_indices={name:int(meta.link_indices[name]) for name in meta.link_names}
        for spec in clone_specs:
            body_name=Path(spec["rigid_body_parent"]).name
            if body_name not in runtime_link_indices:raise RuntimeError(f"runtime body mapping missing {body_name}")
            spec["link_name"]=body_name;spec["link_index"]=runtime_link_indices[body_name]
        report["runtime_mapping"]={"dof_indices":runtime_dof_indices,"link_indices":runtime_link_indices,"clone_body_links":[{"source":s["source_mesh"],"clone":s["clone_mesh"],"component":s["component_label"],"body":s["rigid_body_parent"],"runtime_link":s["link_name"],"runtime_link_index":s["link_index"]} for s in clone_specs]}
        def tensor_state(label):
            positions=nested_values(articulation.get_dof_positions())[0];velocities=nested_values(articulation.get_dof_velocities())[0];links=nested_values(articulation.get_link_transforms())[0]
            return {"label":label,"dof_names":list(meta.dof_names),"positions_rad":{name:float(positions[index]) for name,index in meta.dof_indices.items()},"velocities_rad_s":{name:float(velocities[index]) for name,index in meta.dof_indices.items()},"link_names":list(meta.link_names),"link_transforms_xyzw":links}
        # Flush the tensor state before renderer capture so a capture failure
        # cannot erase the first post-initialize physics evidence.
        post_initialize_tensor=tensor_state("after_initialize_before_capture")
        temporary=args.run_dir/"after_initialize_tensor_state.json.tmp"
        temporary.write_text(json.dumps(post_initialize_tensor,indent=2)+"\n")
        os.replace(temporary,args.run_dir/"after_initialize_tensor_state.json")
        after_initialize=capture_pixel_gate(
            "after_initialize", 0, prephysics_gate["components"],
            raise_on_fail=not (args.initialization_diagnostic or args.initialization_isolation_diagnostic or args.gated_recovery_end_to_end),
        )
        continuity=[after_initialize]
        report["initialization_diagnostic"]["after_initialize"]={"usd":usd_snapshot("after_initialize",after_initialize),"tensor":tensor_state("after_initialize")};diagnostic_marker("AFTER_INITIALIZE_CAPTURED",pixel_status=after_initialize["status"])
        if args.initialization_diagnostic and after_initialize["status"]!="PASS":
            report["status"]="INITIALIZATION_DIAGNOSTIC_STOPPED_AT_AFTER_INITIALIZE_PIXEL_FAIL";report["initialization_diagnostic"]["physics_commands_sent"]=False;report["initialization_diagnostic"]["video_recorder_started"]=False
            (args.run_dir/"visual_continuity_gate.json").write_text(json.dumps({"status":"FAIL","captures":continuity},indent=2)+"\n")
            (args.run_dir/"initialization_diagnostic_report.json").write_text(json.dumps(report,indent=2)+"\n");(args.run_dir/"runner_phase.txt").write_text("INITIALIZATION_DIAGNOSTIC_PIXEL_FAIL_AFTER_INITIALIZE\n")
            return finish(20,"INITIALIZATION_DIAGNOSTIC_PIXEL_FAIL",asset_pass=False)
        # The gated runner deliberately does not issue these uncontrolled steps.
        # Its first post-initialize steps all carry the full closed-target vector.
        for relative_step in ([] if (args.gated_recovery_end_to_end or args.initialization_isolation_diagnostic) else range(1,11)):
            before=SimulationManager.get_num_physics_steps();SimulationManager.step(steps=1,update_fabric=True);app.update()
            if SimulationManager.get_num_physics_steps()<=before:raise RuntimeError("PhysicsScene did not advance")
            if relative_step in (1,2,5,10):
                gate=capture_pixel_gate(f"step_{relative_step}",relative_step,prephysics_gate["components"],raise_on_fail=not args.initialization_diagnostic);continuity.append(gate);report["initialization_diagnostic"][f"step_{relative_step}"]={"usd":usd_snapshot(f"step_{relative_step}",gate),"tensor":tensor_state(f"step_{relative_step}")};diagnostic_marker(f"STEP_{relative_step}_CAPTURED",pixel_status=gate["status"])
                if args.initialization_diagnostic and gate["status"]!="PASS":break
        continuity_status="PASS" if all(row["status"]=="PASS" for row in continuity) else "INITIALIZATION_TRANSIENT_REQUIRES_RECOVERY"
        (args.run_dir/"visual_continuity_gate.json").write_text(json.dumps({"status":continuity_status,"captures":continuity},indent=2)+"\n")
        report["visual_continuity_gate"]={"status":continuity_status,"captures":continuity}
        if args.initialization_diagnostic:
            report["status"]="INITIALIZATION_DIAGNOSTIC_COMPLETE";report["initialization_diagnostic"]["physics_commands_sent"]=False;report["initialization_diagnostic"]["video_recorder_started"]=False;diagnostic_marker("INITIALIZATION_DIAGNOSTIC_COMPLETE")
            (args.run_dir/"initialization_diagnostic_report.json").write_text(json.dumps(report,indent=2)+"\n");(args.run_dir/"initialization_diagnostic_complete.json").write_text(json.dumps({"status":report["status"],"manager_step":SimulationManager.get_num_physics_steps()},indent=2)+"\n")
            return finish(0,"INITIALIZATION_DIAGNOSTIC_COMPLETE_NOT_ASSET_PASS",asset_pass=False)
        dof_names = list(meta.dof_names)
        if sorted(dof_names) != ["gt_C_1", "gt_C_2", "gt_C_3"]:
            raise RuntimeError(f"unexpected DOFs {dof_names}")
        dof_indices = {name: int(meta.dof_indices[name]) for name in dof_names}
        link_names = list(meta.link_names)
        link_indices = {name: int(meta.link_indices[name]) for name in link_names}
        common_body0={value["body0"] for value in joint_bodies.values()}
        if len(common_body0)!=1: raise RuntimeError(f"joints do not share one fixed body0: {common_body0}")
        root_link_name=Path(next(iter(common_body0))).name
        if root_link_name not in link_indices: raise RuntimeError(f"root link {root_link_name} absent from {link_names}")
        root_link_index=link_indices[root_link_name]
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

        # URDF origin, identity USD joint frames, upper limit 0, authored body
        # transforms and the tensor radian convention all independently place
        # the authored closed geometry at q=0.  Abort rather than guessing if
        # this invariant changes in a future input.
        if any(abs(limits[name][1]) > 1.0e-6 for name in dof_names):
            raise RuntimeError(f"closed-target evidence no longer supports q=0: {limits}")
        closed = {name: 0.0 for name in dof_names}
        opened = {name: limits[name][1] - 0.42*(limits[name][1]-limits[name][0]) for name in dof_names}
        joint_authored_properties={str(joint.GetPath()):{name:str(joint.GetAttribute(name).Get()) for name in joint.GetPropertyNames() if any(token in name.lower() for token in ("drive","stiffness","damping","effort","velocity","limit"))} for joint in revolute}
        report["preflight"] = {
            "variant": variant.GetVariantSelection() if variant.IsValid() else None,
            "revolute_joints": sorted(str(j.GetPath()) for j in revolute),
            "joint_relationships": joint_bodies, "fixed_joint_graph": fixed_graph,
            "articulation_root": str(articulations[0].GetPath()),
            "rigid_body_count": len(rigid), "collider_count": len(colliders),
            "dof_names": dof_names, "dof_indices": dof_indices,
            "link_names":link_names,"root_link_name":root_link_name,"root_link_index":root_link_index,
            "joint_limits_rad": limits, "closed_targets_rad":closed,"open_targets_rad":opened,"target_derivation":{"closed":"0 rad: URDF origin + identity USD local rotations + authored body/localPos0 equality + upper limit 0 + tensor radians","open":"upper - 0.42*(upper-lower)"},"authored_drive_and_limit_properties":joint_authored_properties,
            "thresholds_declared_before_drive":{"minimum_active_response_span_rad":MIN_ACTIVE_RESPONSE_SPAN_RAD,"maximum_closed_target_absolute_error_rad":MAX_CLOSED_TARGET_ABSOLUTE_ERROR_RAD,"maximum_inactive_excursion_from_settled_baseline_rad":MAX_INACTIVE_EXCURSION_RAD,"maximum_root_translation_drift_m":MAX_ROOT_TRANSLATION_DRIFT_M,"maximum_root_orientation_drift_rad":MAX_ROOT_ORIENTATION_DRIFT_RAD,"root_threshold_scope":"conservative GUI smoke operating criteria; not an equivalence claim to previous headless values","previous_failed_run_root_observations":{"translation_max_m":3.9745080992257815e-05,"orientation_max_rad":0.0009765642395587193},"settle_position_error_rad":POSITION_SETTLE_RAD,"settle_velocity_rad_s":VELOCITY_SETTLE_RAD_S,"settle_consecutive_steps":SETTLE_CONSECUTIVE_STEPS,"settle_timeout_steps":SETTLE_TIMEOUT_STEPS,"recovery_timeout_steps":RECOVERY_TIMEOUT_STEPS,"visual_component_min_pixels":30,"transient_monitor":{"pixel_ratio":TRANSIENT_PIXEL_RATIO,"center_shift_px":TRANSIENT_CENTER_SHIFT_PX,"allows_recorder_start":False},"final_recovery":{"door_pixel_ratio":FINAL_DOOR_PIXEL_RATIO,"base_pixel_ratio":FINAL_BASE_PIXEL_RATIO,"door_bbox_iou":FINAL_DOOR_BBOX_IOU,"door_center_shift":"max(10 px, 5% static bbox diagonal)","minimum_door_center_separation_px":FINAL_MIN_DOOR_CENTER_SEPARATION_PX,"maximum_pairwise_door_bbox_iou":FINAL_MAX_PAIRWISE_DOOR_BBOX_IOU,"joint_velocity_rad_s":FINAL_JOINT_VELOCITY_RAD_S,"consecutive_steps":SETTLE_CONSECUTIVE_STEPS},"minimum_wall_duration_fraction":0.90},
            "runtime_physics_scene": scene.path, "clone_meshes": clone_specs,
            "source_instance_proxies_modified": False,
            "clone_xforms_before_simulation": clone_xforms_before,
            "clone_time_samples_before_simulation": clone_time_samples_before,
            "controlled_material_settings": {"mass_kg":1.0,"diagonal_inertia_kg_m2":[0.1,0.1,0.1],"principal_axes":[1.0,0.0,0.0,0.0],"source":"session-layer controlled experimental setting"},
        }

        heartbeat_path = args.run_dir / "gui_heartbeat.json"
        update_count = 0
        def run_responsive(coroutine, phase, minimum_wall_s=0.0, pace_s=0.005):
            nonlocal update_count
            task = asyncio.ensure_future(coroutine)
            started = time.monotonic(); last_heartbeat = 0.0
            while not task.done() or time.monotonic() - started < minimum_wall_s:
                before_update=time.monotonic();app.update(); update_count += 1
                now = time.monotonic()
                if now-before_update>5.0:
                    task.cancel()
                    raise RuntimeError(f"GUI update watchdog exceeded 5 seconds in {phase}: {now-before_update:.3f}s")
                if now - last_heartbeat >= 1.0:
                    heartbeat_path.write_text(json.dumps({"phase": phase, "wall_monotonic_s": now, "elapsed_s": now-started, "update_callback_count": update_count, "physics_step_count": SimulationManager.get_num_physics_steps()}) + "\n")
                    last_heartbeat = now
            return task.result()

        def runtime_geometry_state(label):
            positions=nested_values(articulation.get_dof_positions())[0]
            velocities=nested_values(articulation.get_dof_velocities())[0]
            links=nested_values(articulation.get_link_transforms())[0]
            items=[]
            for spec in clone_specs:
                clone=UsdGeom.Mesh(stage.GetPrimAtPath(spec["clone_mesh"]))
                points=list(clone.GetPointsAttr().Get() or [])
                link=links[spec["link_index"]]
                matrix=Gf.Matrix4d(1.0);matrix.SetRotate(Gf.Quatd(float(link[6]),Gf.Vec3d(*map(float,link[3:6]))));matrix.SetTranslateOnly(Gf.Vec3d(*map(float,link[:3])))
                predicted=[matrix.Transform(Gf.Vec3d(float(p[0]),float(p[1]),float(p[2]))) for p in points]
                source=stage.GetPrimAtPath(spec["source_mesh"]);source_imageable=UsdGeom.Imageable(source);clone_imageable=UsdGeom.Imageable(clone.GetPrim())
                items.append({"component":spec["component_label"],"source":spec["source_mesh"],"clone":spec["clone_mesh"],"body":spec["rigid_body_parent"],"link_name":spec["link_name"],"link_index":spec["link_index"],"source_instance_proxy":source.IsInstanceProxy(),"source_active":source.IsActive(),"source_loaded":source.IsLoaded(),"source_visibility":str(source_imageable.ComputeVisibility()),"source_purpose":str(source_imageable.ComputePurpose()),"source_points":spec["points"],"source_triangles":spec["triangles"],"source_world_bounds":spec["source_world_bounds"],"clone_visibility":str(clone_imageable.ComputeVisibility()),"clone_purpose":str(clone_imageable.ComputePurpose()),"clone_parent":str(clone.GetPrim().GetParent().GetPath()),"clone_local_points_space":"authored-body-local-derived-from-USD-body-transform","authored_body_world_transform":spec["target_body_world_transform"],"tensor_body_pose_xyzw":link,"predicted_fabric_clone_world_bounds":{"min":[min(float(p[i]) for p in predicted) for i in range(3)],"max":[max(float(p[i]) for p in predicted) for i in range(3)]},"material":str(UsdShade.MaterialBindingAPI(clone.GetPrim()).ComputeBoundMaterial()[0].GetPath()),"opacity":str(clone.GetDisplayOpacityPrimvar().Get()),"finite":all(math.isfinite(float(v)) for v in link)})
            return {"label":label,"manager_step":SimulationManager.get_num_physics_steps(),"positions_rad":{name:float(positions[index]) for name,index in runtime_dof_indices.items()},"velocities_rad_s":{name:float(velocities[index]) for name,index in runtime_dof_indices.items()},"links_xyzw":links,"meshes":items,"clone_xform_authoring":authored_clone_xforms(clone_prims),"clone_time_samples":clone_time_samples(clone_prims)}

        async def initialization_isolation_diagnostic():
            """Bounded diagnosis only: no active-door schedule and no recorder."""
            result={"status":"RUNNING","scope":"29806 initialization source/clone isolation; GT-only; no active schedule; no video recorder","manager_step_start":SimulationManager.get_num_physics_steps(),"phases":[],"isolation":[],"limitations":["Instance-proxy source prims are not edited or de-instanced; clone-only capture cannot be guaranteed. Source-only and source-plus-selected-clone captures are used to test overlap."],"physics_commands":{"closed_target_vector_rad":{"gt_C_1":0.0,"gt_C_2":0.0,"gt_C_3":0.0},"maximum_recovery_steps":10,"active_door_targets_sent":False}}
            out=args.run_dir/"initialization_isolation_diagnostic.json"
            atomic_json(out,result)
            result["prephysics_capture_smokes"]=prephysics_smokes;result["capture_failures"]=[]
            async def capture(label,baseline=None):
                capture_result=await capture_viewport_png_stable(label);gate=None
                if capture_result["status"]=="CAPTURE_OK":
                    try:
                        gate=capture_pixel_gate(label,SimulationManager.get_num_physics_steps()-2,baseline,raise_on_fail=False,fast=True,captured_path=Path(capture_result["path"]))
                        capture_status="CAPTURE_OK_PIXEL_PASS" if gate["status"]=="PASS" else "CAPTURE_OK_PIXEL_FAIL"
                    except BaseException as decode_error:
                        capture_result.update({"reason":"PIXEL_ANALYSIS_EXCEPTION","exception":repr(decode_error)});capture_status="CAPTURE_FAILED"
                else:capture_status="CAPTURE_FAILED"
                if capture_status=="CAPTURE_FAILED":result["capture_failures"].append({"label":label,"capture":capture_result})
                visible=[spec["clone_mesh"] for spec,prim in zip(clone_specs,clone_prims) if UsdGeom.Imageable(prim).ComputeVisibility()!=UsdGeom.Tokens.invisible]
                visible_sources=[spec["source_mesh"] for spec in clone_specs if UsdGeom.Imageable(stage.GetPrimAtPath(spec["source_mesh"])).ComputeVisibility()!=UsdGeom.Tokens.invisible]
                result["phases"].append({"label":label,"capture_status":capture_status,"capture":capture_result,"pixel_gate":gate,"visible_clone_prims":visible,"visible_source_prims":visible_sources,"state":runtime_geometry_state(label)})
                atomic_json(out,result);diagnostic_marker("ISOLATION_CAPTURED",label=label,capture_status=capture_status,pixel_status=gate["status"] if gate else None)
                return gate
            await capture("after_initialize_full_1",prephysics_gate["components"])
            await capture("after_initialize_full_2",prephysics_gate["components"])
            original_visibility={str(p.GetPath()):p.GetAttribute("visibility").Get() for p in clone_prims}
            isolation_edit_target_before=stage.GetEditTarget()
            stage.SetEditTarget(Usd.EditTarget(session))
            def set_clone_visibility(visible_labels):
                authored=[]
                with Sdf.ChangeBlock():
                    for spec,prim in zip(clone_specs,clone_prims):
                        requested=UsdGeom.Tokens.inherited if spec["component_label"] in visible_labels else UsdGeom.Tokens.invisible
                        success=bool(UsdGeom.Imageable(prim).GetVisibilityAttr().Set(requested))
                        authored.append({"clone":spec["clone_mesh"],"component":spec["component_label"],"requested":str(requested),"set_success":success})
                return authored
            modes=[("source_only",set()),("source_plus_red",{"gt_C_1"}),("source_plus_green",{"gt_C_2"}),("source_plus_blue",{"gt_C_3"}),("source_plus_base",{"BASE"}),("source_plus_all",{"BASE","gt_C_1","gt_C_2","gt_C_3"})]
            for mode,visible_labels in modes:
                visibility_authoring=set_clone_visibility(visible_labels)
                for _ in range(3):await omni.kit.app.get_app().next_update_async()
                gate=await capture("isolation_"+mode,None)
                composed={spec["clone_mesh"]:str(UsdGeom.Imageable(prim).ComputeVisibility()) for spec,prim in zip(clone_specs,clone_prims)}
                result["isolation"].append({"mode":mode,"requested_visible_clone_components":sorted(visible_labels),"visibility_authoring":visibility_authoring,"composed_clone_visibility":composed,"visibility_edit_layer":session.identifier,"source_instance_proxies_edited":False,"capture":gate})
                atomic_json(out,result)
            # Reuse the proven 10163 diffuse-only material on each door geometry
            # separately.  Geometry, body parent, points and physics stay fixed.
            for component in (() if args.diffuse_only_material_diagnostic else ("gt_C_1","gt_C_2","gt_C_3")):
                visibility_authoring=set_clone_visibility({component})
                selected=[(spec,prim) for spec,prim in zip(clone_specs,clone_prims) if spec["component_label"]==component]
                if len(selected)!=1:raise RuntimeError(f"material isolation requires one clone for {component}: {len(selected)}")
                spec,prim=selected[0];binding=UsdShade.MaterialBindingAPI.Apply(prim)
                binding.Bind(notebook_control_material)
                UsdGeom.Mesh(prim).CreateDisplayColorPrimvar(UsdGeom.Tokens.constant).Set([Gf.Vec3f(0.12,0.68,0.92)])
                for _ in range(3):await omni.kit.app.get_app().next_update_async()
                computed,_=binding.ComputeBoundMaterial()
                gate=await capture("isolation_10163_material_"+component,None)
                result["isolation"].append({"mode":"10163_material_"+component,"requested_visible_clone_components":[component],"visibility_authoring":visibility_authoring,"control_material":str(notebook_control_material.GetPath()),"computed_material":str(computed.GetPath()) if computed else None,"emissive_authored":False,"geometry_and_parent_unchanged":True,"capture":gate})
                native_joint=component
                binding.Bind(materials[native_joint])
                UsdGeom.Mesh(prim).CreateDisplayColorPrimvar(UsdGeom.Tokens.constant).Set([Gf.Vec3f(*colors[native_joint])])
            # Repeat source-only after all additive modes. This distinguishes a
            # stable differential from stale-frame or phase-order artifacts.
            repeat_authoring=set_clone_visibility(set())
            for _ in range(3):await omni.kit.app.get_app().next_update_async()
            repeated_source=await capture("isolation_source_only_repeat",None)
            result["isolation"].append({"mode":"source_only_repeat","requested_visible_clone_components":[],"visibility_authoring":repeat_authoring,"composed_clone_visibility":{spec["clone_mesh"]:str(UsdGeom.Imageable(prim).ComputeVisibility()) for spec,prim in zip(clone_specs,clone_prims)},"visibility_edit_layer":session.identifier,"source_instance_proxies_edited":False,"capture":repeated_source})
            atomic_json(out,result)
            with Sdf.ChangeBlock():
                for prim in clone_prims:
                    value=original_visibility[str(prim.GetPath())]
                    prim.GetAttribute("visibility").Set(value or UsdGeom.Tokens.inherited)
            for _ in range(3):await omni.kit.app.get_app().next_update_async()
            await capture("isolation_restored_full",prephysics_gate["components"])
            stage.SetEditTarget(isolation_edit_target_before)
            # Limited closed-target recovery diagnosis. All three targets are sent
            # each step; no active door target and no submission recording exists.
            checkpoints={1,2,5,10}
            for step in range(1,11):
                current=articulation.get_dof_position_targets();values=nested_values(current)
                for name,index in runtime_dof_indices.items():values[0][index]=0.0
                targets=wp.array(values,dtype=wp.float32,device=current.device)
                articulation.set_dof_position_targets(targets,wp.array([0],dtype=wp.uint32,device=targets.device))
                before=SimulationManager.get_num_physics_steps();SimulationManager.step(steps=1,update_fabric=True);after=SimulationManager.get_num_physics_steps()
                await omni.kit.app.get_app().next_update_async()
                state=runtime_geometry_state(f"closed_recovery_{step}");state["manager_steps"]=[before,after]
                result["phases"].append({"label":f"closed_recovery_{step}","state":state})
                atomic_json(out,result)
                if step in checkpoints:await capture(f"isolation_closed_recovery_{step}",prephysics_gate["components"])
            all_capture_failures=list(result["capture_failures"])+[x for x in prephysics_smokes if x.get("status")!="CAPTURE_OK"]
            any_pixel_fail=any(p.get("pixel_gate") and p["pixel_gate"].get("status")!="PASS" for p in result["phases"])
            result["status"]="DIAGNOSTIC_COMPLETED_WITH_CAPTURE_FAILURE" if all_capture_failures else ("DIAGNOSTIC_COMPLETED_VISUAL_FAIL" if any_pixel_fail else "DIAGNOSTIC_COMPLETED_CAPTURE_OK_ANALYSIS_REQUIRED")
            result["manager_step_end"]=SimulationManager.get_num_physics_steps();result["active_door_schedule_started"]=False;result["video_recorder_started"]=False
            result["clone_xform_authored_after_start"]=authored_clone_xforms(clone_prims)!=clone_xforms_before
            result["clone_time_samples_added"]=clone_time_samples(clone_prims)-clone_time_samples_before
            atomic_json(out,result)
            diagnostic_marker("INITIALIZATION_ISOLATION_DIAGNOSTIC_COMPLETE",manager_step_end=result["manager_step_end"],status=result["status"])
            return result

        if args.initialization_isolation_diagnostic:
            (args.run_dir/"runner_phase.txt").write_text("INITIALIZATION_ISOLATION_DIAGNOSTIC\n")
            isolation=run_responsive(initialization_isolation_diagnostic(),"INITIALIZATION_ISOLATION_DIAGNOSTIC",pace_s=0.0)
            report["initialization_isolation_diagnostic"]=isolation;report["status"]=isolation["status"]
            atomic_json(args.run_dir/"physics_gui_report.json",report)
            atomic_json(args.run_dir/"initialization_isolation_diagnostic_complete.json",{"status":isolation["status"],"manager_step":SimulationManager.get_num_physics_steps(),"physics_video_created":False,"active_door_schedule_started":False,"case_29354_executed":False})
            print("INITIALIZATION_ISOLATION_DIAGNOSTIC_COMPLETE",flush=True)
            print(f"DIAGNOSTIC_COMPLETE_NOT_A_PHYSICS_VIDEO_PASS status={isolation['status']}",flush=True)
            report["completed_phases"].extend(["stage","linked_clones","prephysics_gate","fabric_setup","physics_initialize","tensor_view","visibility_isolation","closed_steps_1_2_5_10"])
            return finish(0,"DIAGNOSTIC_COMPLETE_NOT_A_PHYSICS_VIDEO_PASS",asset_pass=False)

        async def idle_updates(seconds):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                await omni.kit.app.get_app().next_update_async()

        SIM_HZ=60.0
        schedule={"simulation_hz":SIM_HZ,"initialization_recovery":{"physics_step_range_s":[SETTLE_CONSECUTIVE_STEPS/SIM_HZ,RECOVERY_TIMEOUT_STEPS/SIM_HZ],"render_sample_each_step":True,"estimated_wall_s_at_30_render_samples_per_s":[SETTLE_CONSECUTIVE_STEPS/30.0,RECOVERY_TIMEOUT_STEPS/30.0],"actual_wall_time_is_host_renderer_dependent":True,"post_recovery_closed_hold_s":1.5,"post_hold_internal_pixel_gate":True,"recorder_starts_after_recovery":True},"per_door":{"closed_hold_s":1.5,"open_ramp_s":3.0,"open_hold_s":1.5,"close_ramp_s":3.0,"closed_settle_min_s":SETTLE_CONSECUTIVE_STEPS/SIM_HZ,"closed_settle_timeout_s":SETTLE_TIMEOUT_STEPS/SIM_HZ},"per_door_min_s":9.0+SETTLE_CONSECUTIVE_STEPS/SIM_HZ,"per_door_max_s":9.0+SETTLE_TIMEOUT_STEPS/SIM_HZ,"three_doors_min_s":3*(9.0+SETTLE_CONSECUTIVE_STEPS/SIM_HZ),"three_doors_max_s":3*(9.0+SETTLE_TIMEOUT_STEPS/SIM_HZ),"capture_static_start_s":1.0,"capture_static_end_s":2.0,"expected_video_range_s":[3.0+3*(9.0+SETTLE_CONSECUTIVE_STEPS/SIM_HZ),3.0+3*(9.0+SETTLE_TIMEOUT_STEPS/SIM_HZ)],"estimated_after_initialize_to_video_complete_s_at_30_render_samples_per_s":[SETTLE_CONSECUTIVE_STEPS/30.0+1.5+3.0+3*(9.0+SETTLE_CONSECUTIVE_STEPS/SIM_HZ),RECOVERY_TIMEOUT_STEPS/30.0+1.5+3.0+3*(9.0+SETTLE_TIMEOUT_STEPS/SIM_HZ)],"maximum_shortfall_fraction":0.10,"trajectory":"smoothstep u*u*(3-2*u)"}
        report["schedule"]=schedule

        def target_array(target_vector):
            current=articulation.get_dof_position_targets();values=nested_values(current)
            for name,index in dof_indices.items():values[0][index]=float(target_vector[name])
            targets=wp.array(values,dtype=wp.float32,device=current.device);articulation.set_dof_position_targets(targets,wp.array([0],dtype=wp.uint32,device=targets.device))
            return {name:float(nested_values(articulation.get_dof_position_targets())[0][index]) for name,index in dof_indices.items()}

        async def paced_segment(active_name,segment,start_targets,end_targets,steps,destination,sequence_start,inactive_baseline=None):
            segment_start=time.monotonic()
            for local_step in range(steps):
                u=(local_step+1)/steps;smooth=u*u*(3.0-2.0*u)
                vector={name:float(start_targets[name]+(end_targets[name]-start_targets[name])*smooth) for name in dof_names}
                readback=target_array(vector)
                if any(abs(readback[name]-vector[name])>1e-5 for name in dof_names):raise RuntimeError("full target vector readback mismatch")
                before=SimulationManager.get_num_physics_steps();SimulationManager.step(steps=1,update_fabric=True);after=SimulationManager.get_num_physics_steps()
                deadline=segment_start+(local_step+1)/SIM_HZ
                while time.monotonic()<deadline:await omni.kit.app.get_app().next_update_async()
                positions=articulation.get_dof_positions();velocities=articulation.get_dof_velocities();links=articulation.get_link_transforms()
                if after<=before or not all(finite_array(x) for x in (positions,velocities,links)):raise RuntimeError("non-finite state or physics step did not advance")
                link_values=nested_values(links)[0];pos=nested_values(positions)[0];vel=nested_values(velocities)[0]
                destination.append({"phase":"capture","segment":segment,"metric_scope":"inactive_excursion" if segment in ("opening_smoothstep","open_hold","closing_smoothstep") else "excluded_from_inactive_excursion","active_joint":active_name,"wall_monotonic_s":time.monotonic(),"sequence_wall_elapsed_s":time.monotonic()-sequence_start,"segment_wall_elapsed_s":time.monotonic()-segment_start,"planned_segment_elapsed_s":(local_step+1)/SIM_HZ,"target_vector_rad":vector,"target_readback_vector_rad":readback,"requested_target_rad":vector.get(active_name),"target_readback_rad":readback.get(active_name),"inactive_baseline_rad":inactive_baseline or {},"local_step":local_step,"manager_steps":[before,after],"positions_rad":{n:float(pos[i]) for n,i in dof_indices.items()},"velocities_rad_s":{n:float(vel[i]) for n,i in dof_indices.items()},"rigid_body_link_transforms_xyzw":link_values,"clone_world_transforms_from_physics_body":{spec["clone_mesh"]:transform7_matrix(link_values[spec["link_index"]],Gf) for spec in clone_specs}})
            actual=time.monotonic()-segment_start;planned=steps/SIM_HZ
            if actual<planned*0.90:raise RuntimeError(f"wall-time segment too short {segment}: {actual} < {planned*0.90}")
            return {"segment":segment,"planned_s":planned,"actual_s":actual}

        async def settle_closed(label,destination,sequence_start):
            settle_start=time.monotonic();consecutive=0;maximum_velocity={name:0.0 for name in dof_names}
            for local_step in range(SETTLE_TIMEOUT_STEPS):
                readback=target_array(closed);before=SimulationManager.get_num_physics_steps();SimulationManager.step(steps=1,update_fabric=True);after=SimulationManager.get_num_physics_steps()
                deadline=settle_start+(local_step+1)/SIM_HZ
                while time.monotonic()<deadline:await omni.kit.app.get_app().next_update_async()
                positions=articulation.get_dof_positions();velocities=articulation.get_dof_velocities();links=articulation.get_link_transforms()
                if after<=before or not all(finite_array(x) for x in (positions,velocities,links)):raise RuntimeError("non-finite settle state or physics step did not advance")
                pos=nested_values(positions)[0];vel=nested_values(velocities)[0];link_values=nested_values(links)[0]
                measured={name:float(pos[index]) for name,index in dof_indices.items()};velocity={name:float(vel[index]) for name,index in dof_indices.items()};errors={name:abs(measured[name]-closed[name]) for name in dof_names}
                maximum_velocity={name:max(maximum_velocity[name],abs(velocity[name])) for name in dof_names}
                stable=all(errors[name]<=MAX_CLOSED_TARGET_ABSOLUTE_ERROR_RAD and abs(velocity[name])<=VELOCITY_SETTLE_RAD_S for name in dof_names)
                consecutive=consecutive+1 if stable else 0
                destination.append({"phase":"capture","segment":"closed_settle","settle_label":label,"metric_scope":"excluded_from_inactive_excursion","active_joint":label,"wall_monotonic_s":time.monotonic(),"sequence_wall_elapsed_s":time.monotonic()-sequence_start,"segment_wall_elapsed_s":time.monotonic()-settle_start,"planned_segment_elapsed_s":None,"target_vector_rad":dict(closed),"target_readback_vector_rad":readback,"requested_target_rad":closed.get(label),"target_readback_rad":readback.get(label),"inactive_baseline_rad":{},"local_step":local_step,"manager_steps":[before,after],"positions_rad":measured,"velocities_rad_s":velocity,"rigid_body_link_transforms_xyzw":link_values,"clone_world_transforms_from_physics_body":{spec["clone_mesh"]:transform7_matrix(link_values[spec["link_index"]],Gf) for spec in clone_specs}})
                if consecutive>=SETTLE_CONSECUTIVE_STEPS:
                    return {"status":"PASS","label":label,"closed_target_rad":dict(closed),"settle_completed_measured_rad":measured,"closed_target_absolute_error_rad":errors,"settled_baseline_rad":dict(measured),"maximum_velocity_during_settle_rad_s":maximum_velocity,"settle_steps":local_step+1,"settle_wall_s":time.monotonic()-settle_start,"consecutive_stable_steps":consecutive,"thresholds":{"absolute_error_rad":MAX_CLOSED_TARGET_ABSOLUTE_ERROR_RAD,"velocity_rad_s":VELOCITY_SETTLE_RAD_S,"consecutive_steps":SETTLE_CONSECUTIVE_STEPS,"timeout_steps":SETTLE_TIMEOUT_STEPS}}
            raise RuntimeError(f"closed settle timeout {label}: errors={errors} velocities={velocity}")

        async def initialization_recovery():
            """Recover the authored closed pose before recorder/door schedule.

            Every recovery step sends all three closed targets.  A failed
            post-initialize image is evidence retained by the report, not an
            instruction to hide the transient or to start the active schedule.
            """
            recovery_path=args.run_dir/"initialization_recovery_report.json"
            checkpoint_steps={1,2,5,10,30,60,120,180,240,300}
            start=time.monotonic();records=[];captures=[];consecutive=0
            initial_links=nested_values(articulation.get_link_transforms())[0]
            root_reference=initial_links[root_link_index]
            status="INITIALIZATION_RECOVERY_FAIL"
            stable_result=None
            for local_step in range(1,RECOVERY_TIMEOUT_STEPS+1):
                readback=target_array(closed)
                before=SimulationManager.get_num_physics_steps()
                SimulationManager.step(steps=1,update_fabric=True)
                after=SimulationManager.get_num_physics_steps()
                deadline=start+local_step/SIM_HZ
                while time.monotonic()<deadline:
                    await omni.kit.app.get_app().next_update_async()
                positions=articulation.get_dof_positions();velocities=articulation.get_dof_velocities();links=articulation.get_link_transforms()
                if after<=before or not all(finite_array(x) for x in (positions,velocities,links)):
                    raise RuntimeError("INITIALIZATION_RECOVERY_FAIL nonfinite state or physics did not advance")
                pos=nested_values(positions)[0];vel=nested_values(velocities)[0];link_values=nested_values(links)[0]
                measured={name:float(pos[index]) for name,index in dof_indices.items()}
                velocity={name:float(vel[index]) for name,index in dof_indices.items()}
                errors={name:abs(measured[name]-closed[name]) for name in dof_names}
                root_translation,root_orientation=pose_delta(root_reference,link_values[root_link_index])
                max_link_distance=max(math.dist(link[:3],link_values[root_link_index][:3]) for link in link_values)
                if max_link_distance>asset_scale*4.0:
                    raise RuntimeError(f"INITIALIZATION_RECOVERY_FAIL body escaped asset bounds: {max_link_distance}")
                if root_translation>MAX_ROOT_TRANSLATION_DRIFT_M or root_orientation>MAX_ROOT_ORIENTATION_DRIFT_RAD:
                    raise RuntimeError(f"INITIALIZATION_RECOVERY_FAIL root drift: {root_translation}/{root_orientation}")
                # A real viewport sample is required for every candidate step;
                # the final counter therefore represents 30 consecutive physics
                # and rendered-image states, not 30 tensor-only states.
                gate=await capture_pixel_gate_async(f"recovery_monitor_{local_step}",local_step,prephysics_gate["components"],raise_on_fail=False,fast=True)
                if local_step in checkpoint_steps:
                    captures.append(gate)
                final_visual=gate["final_recovery_visual_gate"] or {"pass":False}
                clone_authoring_ok=authored_clone_xforms(clone_prims)==clone_xforms_before and clone_time_samples(clone_prims)==clone_time_samples_before
                body_clone_correspondence_ok=all(
                    spec["link_index"]<len(link_values)
                    and str(stage.GetPrimAtPath(spec["clone_mesh"]).GetParent().GetPath())==spec["rigid_body_parent"]
                    and spec["actual_authored_clone_vertex_max_error_m"]<=1.0e-6
                    and all(math.isfinite(v) for row in transform7_matrix(link_values[spec["link_index"]],Gf) for v in row)
                    for spec in clone_specs
                )
                final_step_pass=all(errors[name]<=MAX_CLOSED_TARGET_ABSOLUTE_ERROR_RAD and abs(velocity[name])<=FINAL_JOINT_VELOCITY_RAD_S for name in dof_names) and final_visual["pass"] and clone_authoring_ok and body_clone_correspondence_ok
                consecutive=consecutive+1 if final_step_pass else 0
                row={"recovery_step":local_step,"manager_steps":[before,after],"wall_elapsed_s":time.monotonic()-start,"target_vector_rad":dict(closed),"target_readback_vector_rad":readback,"positions_rad":measured,"velocities_rad_s":velocity,"closed_target_absolute_error_rad":errors,"root_translation_drift_m":root_translation,"root_orientation_drift_rad":root_orientation,"maximum_link_distance_from_root_m":max_link_distance,"finite":True,"constraint_explosion_proxy_pass":max_link_distance<=asset_scale*4.0 and root_translation<=MAX_ROOT_TRANSLATION_DRIFT_M and root_orientation<=MAX_ROOT_ORIENTATION_DRIFT_RAD,"contact_impulse_measurement":"NOT_AVAILABLE_IN_THIS_RUNNER; no-constraint-explosion uses finite/root/body-bounds proxies","transient_monitor_pass":gate["status"]=="PASS","final_visual_pass":final_visual["pass"],"final_step_pass":final_step_pass,"consecutive_final_stable_steps":consecutive,"body_clone_correspondence_ok":body_clone_correspondence_ok,"clone_authoring_ok":clone_authoring_ok,"pixel_metrics":gate,"rigid_body_link_transforms_xyzw":link_values,"clone_world_transforms_from_physics_body":{spec["clone_mesh"]:transform7_matrix(link_values[spec["link_index"]],Gf) for spec in clone_specs}}
                records.append(row)
                if consecutive>=SETTLE_CONSECUTIVE_STEPS:
                    status="INITIALIZATION_RECOVERY_PASS"
                    stable_result={"step":local_step,"manager_step":after,"measured_rad":measured,"velocity_rad_s":velocity,"closed_target_absolute_error_rad":errors,"settled_baseline_rad":dict(measured),"root_translation_drift_m":root_translation,"root_orientation_drift_rad":root_orientation,"pixel_gate":gate,"consecutive_final_stable_steps":consecutive}
                    break
            result={"status":status,"closed_targets_rad":dict(closed),"closed_target_evidence":report["preflight"]["target_derivation"]["closed"],"records":records,"checkpoint_captures":captures,"stable_result":stable_result,"thresholds":{"timeout_steps":RECOVERY_TIMEOUT_STEPS,"closed_target_absolute_error_rad":MAX_CLOSED_TARGET_ABSOLUTE_ERROR_RAD,"final_joint_velocity_rad_s":FINAL_JOINT_VELOCITY_RAD_S,"consecutive_steps":SETTLE_CONSECUTIVE_STEPS,"transient_monitor":{"pixel_ratio":TRANSIENT_PIXEL_RATIO,"center_shift_px":TRANSIENT_CENTER_SHIFT_PX,"allows_pass":False},"final_visual":{"door_pixel_ratio":FINAL_DOOR_PIXEL_RATIO,"base_pixel_ratio":FINAL_BASE_PIXEL_RATIO,"door_bbox_iou":FINAL_DOOR_BBOX_IOU,"center_shift":"max(10 px, static bbox diagonal * 0.05)","minimum_door_center_separation_px":FINAL_MIN_DOOR_CENTER_SEPARATION_PX,"maximum_pairwise_door_bbox_iou":FINAL_MAX_PAIRWISE_DOOR_BBOX_IOU},"root_translation_m":MAX_ROOT_TRANSLATION_DRIFT_M,"root_orientation_rad":MAX_ROOT_ORIENTATION_DRIFT_RAD,"body_escape_distance_m":asset_scale*4.0},"video_recorder_started":False,"active_door_schedule_started":False,"clone_xform_authored_after_start":authored_clone_xforms(clone_prims)!=clone_xforms_before,"clone_time_samples_added":clone_time_samples(clone_prims)-clone_time_samples_before}
            recovery_path.write_text(json.dumps(result,indent=2)+"\n")
            if status!="INITIALIZATION_RECOVERY_PASS":
                (args.run_dir/"runner_phase.txt").write_text("INITIALIZATION_RECOVERY_FAIL\n")
                raise RuntimeError("INITIALIZATION_RECOVERY_FAIL: 300 closed-target steps did not satisfy numeric and rendered-pixel gates")
            return result

        async def establish_closed():
            positions=nested_values(articulation.get_dof_positions())[0];initial={name:float(positions[index]) for name,index in dof_indices.items()};sink=[];start=time.monotonic()
            await paced_segment("ALL","initial_close_ramp",initial,closed,60,sink,start)
            result=await settle_closed("initial",sink,start)
            result["initial_close_ramp_s"]=1.0
            return result

        async def drive_scheduled(destination,initial_settle):
            sequence_start=time.monotonic();phase_times=[];settle_results=[];baseline=dict(initial_settle["settled_baseline_rad"])
            for active in sorted(dof_names):
                pre_errors={name:abs(baseline[name]-closed[name]) for name in dof_names}
                if any(value>MAX_CLOSED_TARGET_ABSOLUTE_ERROR_RAD for value in pre_errors.values()):raise RuntimeError(f"pre-door closed target absolute error failed {active}: {pre_errors}")
                hold_closed=dict(closed);open_vector=dict(closed);open_vector[active]=opened[active]
                phase_times.append(await paced_segment(active,"closed_hold",hold_closed,hold_closed,90,destination,sequence_start,baseline))
                phase_times.append(await paced_segment(active,"opening_smoothstep",hold_closed,open_vector,180,destination,sequence_start,baseline))
                phase_times.append(await paced_segment(active,"open_hold",open_vector,open_vector,90,destination,sequence_start,baseline))
                phase_times.append(await paced_segment(active,"closing_smoothstep",open_vector,hold_closed,180,destination,sequence_start,baseline))
                settled=await settle_closed(active,destination,sequence_start);settle_results.append(settled);baseline=dict(settled["settled_baseline_rad"])
            return {"sequence_wall_s":time.monotonic()-sequence_start,"phase_times":phase_times,"settle_results":settle_results}

        (args.run_dir / "runner_phase.txt").write_text("STATIC_PREFLIGHT\n")
        run_responsive(idle_updates(3.0), "STATIC_PREFLIGHT", minimum_wall_s=3.0, pace_s=0.01)
        (args.run_dir / "marker_structure_mapping.json").write_text(json.dumps(report["preflight"],indent=2)+"\n")
        if args.gated_recovery_end_to_end:
            (args.run_dir / "runner_phase.txt").write_text("INITIALIZATION_RECOVERY_DIAGNOSTIC\n")
            recovery=run_responsive(initialization_recovery(),"INITIALIZATION_RECOVERY_DIAGNOSTIC",pace_s=0.0)
            report["initialization_recovery"]=recovery
            report["pretest"]["closed_settle"]={"status":"PASS","label":"initialization_recovery","closed_target_rad":dict(closed),"settle_completed_measured_rad":recovery["stable_result"]["measured_rad"],"closed_target_absolute_error_rad":recovery["stable_result"]["closed_target_absolute_error_rad"],"settled_baseline_rad":recovery["stable_result"]["settled_baseline_rad"],"maximum_velocity_during_settle_rad_s":{name:max(abs(row["velocities_rad_s"][name]) for row in recovery["records"]) for name in dof_names},"settle_steps":recovery["stable_result"]["step"],"settle_wall_s":recovery["records"][-1]["wall_elapsed_s"],"consecutive_stable_steps":SETTLE_CONSECUTIVE_STEPS}
            # Keep the recovered closed pose visible for 1.5 real seconds while
            # continuing to send the complete closed vector. Recorder starts later.
            hold_sink=[];hold_start=time.monotonic()
            run_responsive(paced_segment("ALL","recovery_closed_hold",closed,closed,90,hold_sink,hold_start,recovery["stable_result"]["settled_baseline_rad"]),"RECOVERY_CLOSED_HOLD",pace_s=0.0)
            post_hold_gate=capture_pixel_gate("post_recovery_closed_hold",recovery["stable_result"]["step"]+90,prephysics_gate["components"],raise_on_fail=False)
            post_hold_positions=nested_values(articulation.get_dof_positions())[0];post_hold_velocities=nested_values(articulation.get_dof_velocities())[0]
            post_hold_numeric=all(abs(float(post_hold_positions[dof_indices[name]])-closed[name])<=MAX_CLOSED_TARGET_ABSOLUTE_ERROR_RAD and abs(float(post_hold_velocities[dof_indices[name]]))<=FINAL_JOINT_VELOCITY_RAD_S for name in dof_names)
            post_hold_pass=post_hold_numeric and bool(post_hold_gate["final_recovery_visual_gate"] and post_hold_gate["final_recovery_visual_gate"]["pass"])
            report["initialization_recovery"]["post_recovery_closed_hold"]={"planned_s":1.5,"actual_s":time.monotonic()-hold_start,"records":len(hold_sink),"numeric_pass":post_hold_numeric,"pixel_gate":post_hold_gate,"pass":post_hold_pass}
            (args.run_dir/"initialization_recovery_report.json").write_text(json.dumps(report["initialization_recovery"],indent=2)+"\n")
            if not post_hold_pass:
                (args.run_dir/"runner_phase.txt").write_text("POST_RECOVERY_HOLD_GATE_FAIL\n")
                raise RuntimeError("POST_RECOVERY_HOLD_GATE_FAIL: recorder and active schedule were not started")
        else:
            (args.run_dir / "runner_phase.txt").write_text("CLOSED_SETTLE_PREFLIGHT\n")
            report["pretest"]["closed_settle"]=run_responsive(establish_closed(),"CLOSED_SETTLE_PREFLIGHT",pace_s=0.0)
        (args.run_dir / "marker_pretest_pass.json").write_text(json.dumps({"status":"PASS","scope":"recovery plus closed settle; active schedule and recorder not yet started", "closed_settle":report["pretest"]["closed_settle"]},indent=2)+"\n")

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
        report["capture"]["schedule_result"]=run_responsive(drive_scheduled(report["capture"]["records"],report["pretest"]["closed_settle"]),"PHYSICS_CAPTURE",pace_s=0.0)
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
        capture_rows=report["capture"]["records"]
        capture_checks={"joint_spans_rad":{},"door_body_rotation_span_rad":{},"closed_target_absolute_error_rad":{},"settled_baseline_rad":{},"inactive_excursion_from_settled_baseline_rad":{},"maximum_velocity_rad_s":{},"settle_wall_s":{},"settle_steps":{},"root_translation_drift_m":{},"root_orientation_drift_rad":{},"finite":True,"record_count_range":[3*(540+SETTLE_CONSECUTIVE_STEPS),3*(540+SETTLE_TIMEOUT_STEPS)],"minimum_sequence_wall_s":schedule["three_doors_min_s"]*0.90}
        settle_by_joint={row["label"]:row for row in report["capture"]["schedule_result"]["settle_results"]}
        for active in sorted(dof_names):
            subset=[r for r in capture_rows if r["active_joint"]==active]
            capture_checks["joint_spans_rad"][active]=max(r["positions_rad"][active] for r in subset)-min(r["positions_rad"][active] for r in subset)
            capture_checks["closed_target_absolute_error_rad"][active]=settle_by_joint[active]["closed_target_absolute_error_rad"][active]
            capture_checks["settled_baseline_rad"][active]=settle_by_joint[active]["settled_baseline_rad"][active]
            inactive_rows=[r for r in capture_rows if r["metric_scope"]=="inactive_excursion" and r["active_joint"]!=active and active in r["inactive_baseline_rad"]]
            capture_checks["inactive_excursion_from_settled_baseline_rad"][active]=max(abs(r["positions_rad"][active]-r["inactive_baseline_rad"][active]) for r in inactive_rows)
            capture_checks["maximum_velocity_rad_s"][active]=max(abs(r["velocities_rad_s"][active]) for r in capture_rows)
            capture_checks["settle_wall_s"][active]=settle_by_joint[active]["settle_wall_s"]
            capture_checks["settle_steps"][active]=settle_by_joint[active]["settle_steps"]
            body1=joint_bodies[next(p for p in joint_bodies if Path(p).name==active)]["body1"];body_index=link_indices[Path(body1).name];body_first=subset[0]["rigid_body_link_transforms_xyzw"][body_index]
            capture_checks["door_body_rotation_span_rad"][active]=max(pose_delta(body_first,r["rigid_body_link_transforms_xyzw"][body_index])[1] for r in subset)
            root_first=subset[0]["rigid_body_link_transforms_xyzw"][root_link_index]
            root_deltas=[pose_delta(root_first,r["rigid_body_link_transforms_xyzw"][root_link_index]) for r in subset]
            capture_checks["root_translation_drift_m"][active]=max(x[0] for x in root_deltas);capture_checks["root_orientation_drift_rad"][active]=max(x[1] for x in root_deltas)
        capture_checks["per_door_metrics"]={active:{"closed_target_rad":closed[active],"settle_completed_measured_position_rad":settle_by_joint[active]["settle_completed_measured_rad"][active],"closed_target_absolute_error_rad":capture_checks["closed_target_absolute_error_rad"][active],"closed_target_absolute_error_pass":capture_checks["closed_target_absolute_error_rad"][active]<=MAX_CLOSED_TARGET_ABSOLUTE_ERROR_RAD,"settled_baseline_rad":capture_checks["settled_baseline_rad"][active],"inactive_excursion_from_settled_baseline_rad":capture_checks["inactive_excursion_from_settled_baseline_rad"][active],"inactive_excursion_pass":capture_checks["inactive_excursion_from_settled_baseline_rad"][active]<=MAX_INACTIVE_EXCURSION_RAD,"maximum_velocity_rad_s":capture_checks["maximum_velocity_rad_s"][active],"settle_wall_s":capture_checks["settle_wall_s"][active],"settle_steps":capture_checks["settle_steps"][active],"settle_pass":settle_by_joint[active]["status"]=="PASS"} for active in sorted(dof_names)}
        capture_checks["clone_xform_authoring_after_start"]=authored_clone_xforms(clone_prims)!=clone_xforms_before
        capture_checks["clone_time_sample_authoring_after_start"]=clone_time_samples(clone_prims)-clone_time_samples_before
        report["capture"]["checks"]=capture_checks
        with (args.run_dir/"physics_records.jsonl").open("w") as stream:
            for row in capture_rows: stream.write(json.dumps(row,separators=(",",":"))+"\n")
        if not capture_checks["record_count_range"][0]<=len(capture_rows)<=capture_checks["record_count_range"][1]: raise RuntimeError(f"capture record count outside adaptive settle range {capture_checks}")
        if min(capture_checks["joint_spans_rad"].values())<MIN_ACTIVE_RESPONSE_SPAN_RAD: raise RuntimeError(f"capture active response failed {capture_checks}")
        if min(capture_checks["door_body_rotation_span_rad"].values())<MIN_ACTIVE_RESPONSE_SPAN_RAD: raise RuntimeError(f"capture door body response failed {capture_checks}")
        if max(capture_checks["closed_target_absolute_error_rad"].values())>MAX_CLOSED_TARGET_ABSOLUTE_ERROR_RAD: raise RuntimeError(f"capture closed target absolute error failed {capture_checks}")
        if max(capture_checks["inactive_excursion_from_settled_baseline_rad"].values())>MAX_INACTIVE_EXCURSION_RAD: raise RuntimeError(f"capture inactive excursion failed {capture_checks}")
        if max(capture_checks["root_translation_drift_m"].values())>MAX_ROOT_TRANSLATION_DRIFT_M or max(capture_checks["root_orientation_drift_rad"].values())>MAX_ROOT_ORIENTATION_DRIFT_RAD: raise RuntimeError(f"capture root drift failed {capture_checks}")
        if capture_checks["clone_xform_authoring_after_start"] or capture_checks["clone_time_sample_authoring_after_start"]: raise RuntimeError(f"capture visual authoring invariant failed {capture_checks}")
        if report["capture"]["schedule_result"]["sequence_wall_s"]<capture_checks["minimum_sequence_wall_s"]: raise RuntimeError(f"capture wall schedule too short {report['capture']['schedule_result']}")
        if capture_process_error:
            raise RuntimeError(capture_process_error + "; physics sequence completed and was preserved")
        report["status"] = "AUTOMATED_PRETEST_AND_CAPTURE_COMPLETE_HUMAN_VIEWPORT_REVIEW_REQUIRED"
        (args.run_dir / "runner_phase.txt").write_text("COMPLETE\n")
        (args.run_dir / "physics_gui_report.json").write_text(json.dumps(report, indent=2) + "\n")
        print("GT_GUI_TENSOR_PHYSICS_CAPTURE=AUTOMATED_PASS_HUMAN_REVIEW_REQUIRED", flush=True)
        report["completed_phases"].extend(["stage","linked_clones","prephysics_gate","physics_initialize","tensor_view","recorder","three_door_schedule"])
        return finish(0,"AUTOMATION_PASS_HUMAN_VIDEO_REVIEW_REQUIRED",asset_pass=False)
    except BaseException as exc:
        report["status"] = "FAIL"
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        atomic_json(args.run_dir / "physics_gui_report.json", report)
        atomic_json(args.run_dir / "runner_internal_exit.json",internal_exit_payload(status="EXECUTION_OR_API_ERROR",code=1,mode=mode,plan=report["execution_plan"],completed=report["completed_phases"],asset_pass=False,error=report["error"],last_phase=(args.run_dir/"runner_phase.txt").read_text().strip() if (args.run_dir/"runner_phase.txt").exists() else "BEFORE_PHASE_MARKER"))
        traceback.print_exc()
        return 1
    finally:
        try:
            if ffmpeg_process is not None and ffmpeg_process.poll() is None:
                ffmpeg_process.send_signal(signal.SIGINT)
                try:
                    ffmpeg_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    ffmpeg_process.kill()
        except BaseException as cleanup_error:
            atomic_json(args.run_dir/"recorder_cleanup_error.json",{"type":type(cleanup_error).__name__,"message":str(cleanup_error)})
        try:
            app.close()
        except BaseException as cleanup_error:
            # Cleanup must not replace the primary failure recorded above.
            atomic_json(args.run_dir/"cleanup_error.json",{"type":type(cleanup_error).__name__,"message":str(cleanup_error)})


if __name__ == "__main__":
    raise SystemExit(main())
