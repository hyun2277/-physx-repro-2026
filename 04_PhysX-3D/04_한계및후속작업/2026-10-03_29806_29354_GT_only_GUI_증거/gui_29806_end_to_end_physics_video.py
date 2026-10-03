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
MAX_INACTIVE_DOF_DRIFT_RAD = 0.02
MAX_ROOT_TRANSLATION_DRIFT_M = 0.001
MAX_ROOT_ORIENTATION_DRIFT_RAD = 0.01
MIN_ACTIVE_RESPONSE_SPAN_RAD = 0.50


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
        materials = {}
        for label,color in colors.items():
            token = label or "BASE"
            material = UsdShade.Material.Define(stage, f"/__PhysXGuiDiagnostic/Material_{token}")
            shader = UsdShade.Shader.Define(stage, f"/__PhysXGuiDiagnostic/Material_{token}/PreviewSurface")
            shader.CreateIdAttr("UsdPreviewSurface"); shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color)); shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color)); shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0); shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
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

            def corners(bounds):
                lo,hi=bounds["min"],bounds["max"]
                return [[x,y,z] for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])]
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
            return 0

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
        for _ in range(30): app.update()

        # Pre-physics rendered-pixel gate: this validates the body-local linked
        # clones, not the world-space clones used by the approved static gate.
        from omni.kit.viewport.utility import capture_viewport_to_file, next_viewport_frame_async
        from PIL import Image
        import numpy as np
        from scipy import ndimage
        async def capture_viewport_png(path):
            for _ in range(30): await next_viewport_frame_async(viewport)
            handle=capture_viewport_to_file(viewport,file_path=str(path),is_hdr=False)
            return await asyncio.wait_for(handle.wait_for_result(completion_frames=30),timeout=15.0)
        masks_factory=lambda h,sat,val:{"BASE_GRAY":(sat<=65)&(val>=55)&(val<=245),"gt_C_1_RED":((h<=12)|(h>=247))&(sat>=85)&(val>=55),"gt_C_2_GREEN":(h>=60)&(h<=112)&(sat>=70)&(val>=50),"gt_C_3_BLUE":(h>=138)&(h<=190)&(sat>=70)&(val>=50)}
        def capture_pixel_gate(label,relative_step,baseline=None):
            path=args.run_dir/f"visual_continuity_{label}.png";task=asyncio.ensure_future(capture_viewport_png(path));started=time.monotonic()
            while not task.done():
                before=time.monotonic();app.update();after=time.monotonic()
                if after-before>5.0 or after-started>15.0:task.cancel();raise RuntimeError(f"visual continuity capture watchdog failed: {label}")
                time.sleep(0.01)
            if not task.result() or not path.is_file() or path.stat().st_size==0:raise RuntimeError(f"visual continuity capture missing: {label}")
            image=Image.open(path).convert("RGB");hsv=np.asarray(image.convert("HSV"));masks=masks_factory(hsv[:,:,0],hsv[:,:,1],hsv[:,:,2]);components={}
            for name,raw in masks.items():
                labels,_=ndimage.label(raw);sizes_cc=np.bincount(labels.ravel());sizes_cc[0]=0;chosen=labels==int(sizes_cc.argmax()) if sizes_cc.max()>0 else np.zeros_like(raw,dtype=bool)
                ys,xs=np.where(chosen);count=int(chosen.sum());components[name]={"pixel_count":count,"bbox_xyxy":[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if count else None,"center_xy":[float(xs.mean()),float(ys.mean())] if count else None}
            missing=[name for name,row in components.items() if row["pixel_count"]<30];continuity={}
            if baseline:
                for name,row in components.items():
                    prior=baseline[name];ratio=row["pixel_count"]/max(1,prior["pixel_count"]);shift=math.dist(row["center_xy"],prior["center_xy"]) if row["center_xy"] and prior["center_xy"] else float("inf")
                    continuity[name]={"pixel_ratio_to_prephysics":ratio,"center_shift_px":shift,"pass":ratio>=0.20 and shift<=40.0}
            status="PASS" if not missing and all(x["pass"] for x in continuity.values()) else "FAIL"
            result={"label":label,"status":status,"relative_physics_step":relative_step,"manager_step":SimulationManager.get_num_physics_steps() if relative_step is not None else None,"capture_path":str(path),"capture_sha256":digest(path),"components":components,"missing":missing,"continuity":continuity}
            if status!="PASS":raise RuntimeError(f"VISUAL_CONTINUITY_GATE_FAIL {result}")
            return result
        prephysics_gate=capture_pixel_gate("prephysics",None)
        prephysics_gate.update({"physics_steps":0,"camera":{"path":str(camera.GetPath()),"eye":eye,"target":center,"selection":"minus-Z derived 3/4; +X/+Y offset exposes Y-axis door depth"},"linked_clone_max_roundtrip_error_m":max(spec["actual_authored_clone_vertex_max_error_m"] for spec in clone_specs)})
        (args.run_dir/"prephysics_pixel_gate.json").write_text(json.dumps(prephysics_gate,indent=2)+"\n")
        report["prephysics_pixel_gate"]=prephysics_gate
        stage.SetEditTarget(original_target)

        SimulationManager.setup_simulation(dt=1.0 / 60.0, device="cuda:0")
        SimulationManager.initialize_physics()
        continuity=[capture_pixel_gate("after_initialize",0,prephysics_gate["components"])]
        for relative_step in range(1,11):
            before=SimulationManager.get_num_physics_steps();SimulationManager.step(steps=1,update_fabric=True);app.update()
            if SimulationManager.get_num_physics_steps()<=before:raise RuntimeError("PhysicsScene did not advance")
            if relative_step in (1,2,5,10):continuity.append(capture_pixel_gate(f"step_{relative_step}",relative_step,prephysics_gate["components"]))
        (args.run_dir/"visual_continuity_gate.json").write_text(json.dumps({"status":"PASS","captures":continuity},indent=2)+"\n")
        report["visual_continuity_gate"]={"status":"PASS","captures":continuity}
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

        closed = {name: limits[name][1] - 0.08*(limits[name][1]-limits[name][0]) for name in dof_names}
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
            "joint_limits_rad": limits, "closed_targets_rad":closed,"open_targets_rad":opened,"target_derivation":{"closed":"upper - 0.08*(upper-lower)","open":"upper - 0.42*(upper-lower)"},"authored_drive_and_limit_properties":joint_authored_properties,
            "thresholds_declared_before_drive":{"minimum_active_response_span_rad":MIN_ACTIVE_RESPONSE_SPAN_RAD,"maximum_inactive_dof_drift_rad":MAX_INACTIVE_DOF_DRIFT_RAD,"maximum_root_translation_drift_m":MAX_ROOT_TRANSLATION_DRIFT_M,"maximum_root_orientation_drift_rad":MAX_ROOT_ORIENTATION_DRIFT_RAD,"settle_position_error_rad":0.03,"settle_velocity_rad_s":0.05,"settle_consecutive_steps":30,"visual_component_min_pixels":30,"visual_continuity_min_pixel_ratio":0.20,"visual_continuity_max_center_shift_px":40.0,"minimum_wall_duration_fraction":0.90},
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
                app.update(); update_count += 1
                now = time.monotonic()
                if now - last_heartbeat >= 1.0:
                    heartbeat_path.write_text(json.dumps({"phase": phase, "wall_monotonic_s": now, "elapsed_s": now-started, "update_callback_count": update_count, "physics_step_count": SimulationManager.get_num_physics_steps()}) + "\n")
                    last_heartbeat = now
            return task.result()

        async def idle_updates(seconds):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                await omni.kit.app.get_app().next_update_async()

        SIM_HZ=60.0;POSITION_SETTLE_RAD=0.03;VELOCITY_SETTLE_RAD_S=0.05;SETTLE_CONSECUTIVE_STEPS=30
        schedule={"simulation_hz":SIM_HZ,"per_door":{"closed_hold_s":1.5,"open_ramp_s":3.0,"open_hold_s":1.5,"close_ramp_s":3.0,"closed_settle_s":3.0},"per_door_s":12.0,"three_doors_s":36.0,"capture_static_start_s":1.0,"capture_static_end_s":2.0,"expected_video_s":39.0,"maximum_shortfall_fraction":0.10,"trajectory":"smoothstep u*u*(3-2*u)"}
        report["schedule"]=schedule

        def target_array(target_vector):
            current=articulation.get_dof_position_targets();values=nested_values(current)
            for name,index in dof_indices.items():values[0][index]=float(target_vector[name])
            targets=wp.array(values,dtype=wp.float32,device=current.device);articulation.set_dof_position_targets(targets,wp.array([0],dtype=wp.uint32,device=targets.device))
            return {name:float(nested_values(articulation.get_dof_position_targets())[0][index]) for name,index in dof_indices.items()}

        async def paced_segment(active_name,segment,start_targets,end_targets,steps,destination,sequence_start):
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
                destination.append({"phase":"capture","segment":segment,"active_joint":active_name,"wall_monotonic_s":time.monotonic(),"sequence_wall_elapsed_s":time.monotonic()-sequence_start,"segment_wall_elapsed_s":time.monotonic()-segment_start,"planned_segment_elapsed_s":(local_step+1)/SIM_HZ,"target_vector_rad":vector,"target_readback_vector_rad":readback,"requested_target_rad":vector.get(active_name),"target_readback_rad":readback.get(active_name),"local_step":local_step,"manager_steps":[before,after],"positions_rad":{n:float(pos[i]) for n,i in dof_indices.items()},"velocities_rad_s":{n:float(vel[i]) for n,i in dof_indices.items()},"rigid_body_link_transforms_xyzw":link_values,"clone_world_transforms_from_physics_body":{spec["clone_mesh"]:transform7_matrix(link_values[spec["link_index"]],Gf) for spec in clone_specs}})
            actual=time.monotonic()-segment_start;planned=steps/SIM_HZ
            if actual<planned*0.90:raise RuntimeError(f"wall-time segment too short {segment}: {actual} < {planned*0.90}")
            return {"segment":segment,"planned_s":planned,"actual_s":actual}

        async def establish_closed():
            positions=nested_values(articulation.get_dof_positions())[0];initial={name:float(positions[index]) for name,index in dof_indices.items()};sink=[];start=time.monotonic()
            await paced_segment("ALL","initial_close_ramp",initial,closed,60,sink,start)
            consecutive=0
            for local_step in range(180):
                target_array(closed);before=SimulationManager.get_num_physics_steps();SimulationManager.step(steps=1,update_fabric=True);after=SimulationManager.get_num_physics_steps()
                deadline=start+1.0+(local_step+1)/SIM_HZ
                while time.monotonic()<deadline:await omni.kit.app.get_app().next_update_async()
                pos=nested_values(articulation.get_dof_positions())[0];vel=nested_values(articulation.get_dof_velocities())[0]
                stable=all(abs(float(pos[i])-closed[name])<=POSITION_SETTLE_RAD and abs(float(vel[i]))<=VELOCITY_SETTLE_RAD_S for name,i in dof_indices.items())
                consecutive=consecutive+1 if stable else 0
                if consecutive>=SETTLE_CONSECUTIVE_STEPS:return {"status":"PASS","steps":local_step+1,"wall_s":time.monotonic()-start,"position_error_rad":{name:abs(float(pos[i])-closed[name]) for name,i in dof_indices.items()},"velocity_rad_s":{name:float(vel[i]) for name,i in dof_indices.items()}}
            raise RuntimeError("closed settle timeout")

        async def drive_scheduled(destination):
            sequence_start=time.monotonic();phase_times=[]
            for active in sorted(dof_names):
                baseline_pos=nested_values(articulation.get_dof_positions())[0]
                baseline={name:float(baseline_pos[index]) for name,index in dof_indices.items()}
                hold_closed=dict(closed);open_vector=dict(closed);open_vector[active]=opened[active]
                phase_times.append(await paced_segment(active,"closed_hold",hold_closed,hold_closed,90,destination,sequence_start))
                phase_times.append(await paced_segment(active,"opening_smoothstep",hold_closed,open_vector,180,destination,sequence_start))
                phase_times.append(await paced_segment(active,"open_hold",open_vector,open_vector,90,destination,sequence_start))
                phase_times.append(await paced_segment(active,"closing_smoothstep",open_vector,hold_closed,180,destination,sequence_start))
                phase_times.append(await paced_segment(active,"closed_settle",hold_closed,hold_closed,180,destination,sequence_start))
                settled=destination[-SETTLE_CONSECUTIVE_STEPS:]
                if not all(all(abs(row["positions_rad"][name]-closed[name])<=POSITION_SETTLE_RAD and abs(row["velocities_rad_s"][name])<=VELOCITY_SETTLE_RAD_S for name in dof_names) for row in settled):raise RuntimeError(f"per-door closed settle failed: {active}")
                # Drift baseline belongs to this active-door interval only and
                # is captured after the preceding door has settled closed.
                for row in destination[-720:]:row["inactive_baseline_rad"]={name:baseline[name] for name in dof_names if name!=active}
            return {"sequence_wall_s":time.monotonic()-sequence_start,"phase_times":phase_times}

        (args.run_dir / "runner_phase.txt").write_text("STATIC_PREFLIGHT\n")
        run_responsive(idle_updates(3.0), "STATIC_PREFLIGHT", minimum_wall_s=3.0, pace_s=0.01)
        (args.run_dir / "marker_structure_mapping.json").write_text(json.dumps(report["preflight"],indent=2)+"\n")
        (args.run_dir / "runner_phase.txt").write_text("CLOSED_SETTLE_PREFLIGHT\n")
        report["pretest"]["closed_settle"]=run_responsive(establish_closed(),"CLOSED_SETTLE_PREFLIGHT",pace_s=0.0)
        (args.run_dir / "marker_pretest_pass.json").write_text(json.dumps({"status":"PASS","scope":"visual continuity plus closed settle; no fast door sweep", "closed_settle":report["pretest"]["closed_settle"]},indent=2)+"\n")

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
        report["capture"]["schedule_result"]=run_responsive(drive_scheduled(report["capture"]["records"]),"PHYSICS_CAPTURE",pace_s=0.0)
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
        capture_checks={"joint_spans_rad":{},"door_body_rotation_span_rad":{},"nonactive_max_drift_rad":{},"root_translation_drift_m":{},"root_orientation_drift_rad":{},"finite":True,"expected_record_count":3*720,"minimum_sequence_wall_s":schedule["three_doors_s"]*0.90}
        for active in sorted(dof_names):
            subset=[r for r in capture_rows if r["active_joint"]==active]
            capture_checks["joint_spans_rad"][active]=max(r["positions_rad"][active] for r in subset)-min(r["positions_rad"][active] for r in subset)
            capture_checks["nonactive_max_drift_rad"][active]=max(abs(r["positions_rad"][other]-r["inactive_baseline_rad"][other]) for r in subset for other in dof_names if other!=active)
            body1=joint_bodies[next(p for p in joint_bodies if Path(p).name==active)]["body1"];body_index=link_indices[Path(body1).name];body_first=subset[0]["rigid_body_link_transforms_xyzw"][body_index]
            capture_checks["door_body_rotation_span_rad"][active]=max(pose_delta(body_first,r["rigid_body_link_transforms_xyzw"][body_index])[1] for r in subset)
            root_first=subset[0]["rigid_body_link_transforms_xyzw"][root_link_index]
            root_deltas=[pose_delta(root_first,r["rigid_body_link_transforms_xyzw"][root_link_index]) for r in subset]
            capture_checks["root_translation_drift_m"][active]=max(x[0] for x in root_deltas);capture_checks["root_orientation_drift_rad"][active]=max(x[1] for x in root_deltas)
        capture_checks["clone_xform_authoring_after_start"]=authored_clone_xforms(clone_prims)!=clone_xforms_before
        capture_checks["clone_time_sample_authoring_after_start"]=clone_time_samples(clone_prims)-clone_time_samples_before
        report["capture"]["checks"]=capture_checks
        with (args.run_dir/"physics_records.jsonl").open("w") as stream:
            for row in capture_rows: stream.write(json.dumps(row,separators=(",",":"))+"\n")
        if len(capture_rows)!=capture_checks["expected_record_count"]: raise RuntimeError(f"capture record count mismatch {capture_checks}")
        if min(capture_checks["joint_spans_rad"].values())<MIN_ACTIVE_RESPONSE_SPAN_RAD: raise RuntimeError(f"capture active response failed {capture_checks}")
        if min(capture_checks["door_body_rotation_span_rad"].values())<MIN_ACTIVE_RESPONSE_SPAN_RAD: raise RuntimeError(f"capture door body response failed {capture_checks}")
        if max(capture_checks["nonactive_max_drift_rad"].values())>MAX_INACTIVE_DOF_DRIFT_RAD: raise RuntimeError(f"capture inactive drift failed {capture_checks}")
        if max(capture_checks["root_translation_drift_m"].values())>MAX_ROOT_TRANSLATION_DRIFT_M or max(capture_checks["root_orientation_drift_rad"].values())>MAX_ROOT_ORIENTATION_DRIFT_RAD: raise RuntimeError(f"capture root drift failed {capture_checks}")
        if capture_checks["clone_xform_authoring_after_start"] or capture_checks["clone_time_sample_authoring_after_start"]: raise RuntimeError(f"capture visual authoring invariant failed {capture_checks}")
        if report["capture"]["schedule_result"]["sequence_wall_s"]<capture_checks["minimum_sequence_wall_s"]: raise RuntimeError(f"capture wall schedule too short {report['capture']['schedule_result']}")
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
