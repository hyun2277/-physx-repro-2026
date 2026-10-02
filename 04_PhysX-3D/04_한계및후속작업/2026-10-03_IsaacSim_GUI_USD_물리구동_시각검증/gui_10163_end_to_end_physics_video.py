"""GPU-0 GUI preflight for 10163 GT-only physics and viewport capture.

Diagnostic visual meshes are authored once before physics initialization as
children of the real rigid bodies.  No clone transform, USD drive target, or
keyframe is authored after simulation begins.
"""

from __future__ import annotations

import argparse
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


INPUT_SHA256 = "72cee88ff5ac563e89c34e4028a9a3fe3d8b839d40f88fed4ef048e3f4fab23b"
URDF_SHA256 = "b3cdc38a849033c623411a049d049181c7a1cec13fbb22f3cf95de4d73ce8723"
PRETEST_TARGETS = (0.0, -0.6, -1.2, 0.0)
CAPTURE_TARGETS = (0.0, -0.6, -1.2, -0.6, 0.0)
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
    args = parser.parse_args()
    args.run_dir.mkdir(parents=True, exist_ok=True)

    experience = args.root / (
        "repro-records/04_PhysX-3D/04_한계및후속작업/"
        "2026-10-03_IsaacSim_GUI_USD_물리구동_시각검증/"
        "isaac_gui_10163_gpu0_tensor_physics.kit"
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
        "scope": "10163 GT-only GUI physics control; not AI prediction",
        "status": "RUNNING",
        "input_usd": str(args.input_usd),
        "physics_gpu": 0,
        "renderer_gpu": 0,
        "multi_gpu": False,
        "p2p_used": False,
        "usd_drive_target_authored_during_run": False,
        "transform_or_keyframe_animation_used": False,
        "pretest": {"targets_rad": list(PRETEST_TARGETS), "records": []},
        "capture": {"targets_rad": list(CAPTURE_TARGETS), "records": []},
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

        # Route A: the installed 6.1 API has no make_instanceable switch.  Its
        # documented direct-output route is run_asset_transformer=False.  Try
        # it in this run's staging only; accept it only after schema and mesh
        # invariants below.  Any failure is preserved before route B is used.
        route_a = {"attempted": True, "config": {"run_asset_transformer": False}}
        selected_usd = args.input_usd
        try:
            from isaacsim.asset.importer.urdf import URDFImporter, URDFImporterConfig
            out_dir = args.run_dir / "route_a_non_instanceable_import"
            config = URDFImporterConfig(
                urdf_path=str(args.input_urdf), usd_path=str(out_dir),
                merge_fixed_joints=False, merge_mesh=False,
                collision_from_visuals=False, fix_base=None,
                run_asset_transformer=False, run_multi_physics_conversion=True,
            )
            imported = Path(URDFImporter().import_urdf(config))
            if not imported.is_file():
                raise RuntimeError(f"importer returned missing file: {imported}")
            route_a.update({"output": str(imported), "sha256": digest(imported)})
            selected_usd = imported
        except BaseException as exc:
            route_a.update({"status": "UNAVAILABLE", "error_type": type(exc).__name__, "error": str(exc)})
        report["route_a"] = route_a

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
        structure_ok = len(meshes) == 2 and len(revolute) == 1 and len(articulations) == 1 and len(rigid) == 3 and len(colliders) == 2
        route_a_mesh_ok = selected_usd != args.input_usd and structure_ok and all(not p.IsInstanceProxy() for p in meshes)
        if selected_usd != args.input_usd and not route_a_mesh_ok:
            route_a.update({"status": "REJECTED_BY_INVARIANTS", "counts": {"mesh": len(meshes), "revolute": len(revolute), "articulation": len(articulations), "rigid": len(rigid), "collider": len(colliders)}, "instance_proxy": [p.IsInstanceProxy() for p in meshes]})
            selected_usd = args.input_usd
            context.open_stage(str(selected_usd))
            for _ in range(3): app.update()
            stage = context.get_stage(); root = stage.GetDefaultPrim(); variant = root.GetVariantSet("Physics"); variant.SetVariantSelection("physx")
            for _ in range(3): app.update()
            prims = list(Usd.PrimRange(stage.GetPseudoRoot(), Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate)))
            meshes = [p for p in prims if p.IsA(UsdGeom.Mesh)]; revolute = [p for p in prims if p.IsA(UsdPhysics.RevoluteJoint)]
            articulations = [p for p in prims if p.HasAPI(UsdPhysics.ArticulationRootAPI)]; rigid = [p for p in prims if p.HasAPI(UsdPhysics.RigidBodyAPI)]; colliders = [p for p in prims if p.HasAPI(UsdPhysics.CollisionAPI)]
            structure_ok = len(meshes) == 2 and len(revolute) == 1 and len(articulations) == 1 and len(rigid) == 3 and len(colliders) == 2
        elif route_a_mesh_ok:
            route_a["status"] = "SELECTED"
        if not structure_ok:
            raise RuntimeError(
                f"schema preflight mesh={len(meshes)} rev={len(revolute)} art={len(articulations)} "
                f"rigid={len(rigid)} collider={len(colliders)}"
            )

        original_target = stage.GetEditTarget()
        session = stage.GetSessionLayer()
        stage.SetEditTarget(Usd.EditTarget(session))
        joint_body0 = str(one_target(revolute[0], "physics:body0"))
        joint_body1 = str(one_target(revolute[0], "physics:body1"))
        fixed_graph = {}
        for fixed_joint in [p for p in prims if p.IsA(UsdPhysics.FixedJoint)]:
            left = str(one_target(fixed_joint, "physics:body0")); right = str(one_target(fixed_joint, "physics:body1"))
            fixed_graph.setdefault(left, []).append(right); fixed_graph.setdefault(right, []).append(left)
        rigid_body_paths = []
        for source_prim in meshes:
            body = source_prim.GetParent()
            while body.IsValid() and not body.HasAPI(UsdPhysics.RigidBodyAPI):
                body = body.GetParent()
            if not body.IsValid():
                raise RuntimeError(f"no rigid-body ancestor for {source_prim.GetPath()}")
            nearest = str(body.GetPath())
            side0 = nearest == joint_body0 or connected(fixed_graph, nearest, joint_body0)
            side1 = nearest == joint_body1 or connected(fixed_graph, nearest, joint_body1)
            if side0 == side1:
                raise RuntimeError(f"relationship mapping ambiguous: mesh={source_prim.GetPath()} nearest={nearest}")
            rigid_body_paths.append(stage.GetPrimAtPath(joint_body0 if side0 else joint_body1).GetPath())

        # Route B never edits/de-instances source proxies.  The relationship
        # chain establishes the body mapping; points are transformed once into
        # that body's local space.  Route A uses the same display clone policy
        # so both routes have identical presentation and runtime invariants.
        deinstanced_rigid_bodies = []

        material = UsdShade.Material.Define(stage, "/__PhysXGuiDiagnostic/Material")
        shader = UsdShade.Shader.Define(stage, "/__PhysXGuiDiagnostic/Material/PreviewSurface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.12, 0.68, 0.92))
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)
        shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

        xforms = UsdGeom.XformCache(Usd.TimeCode.Default())
        clone_prims = []
        clone_specs = []
        for index, (source_prim, body_path) in enumerate(zip(meshes, rigid_body_paths)):
            body = stage.GetPrimAtPath(body_path)
            source_mesh = UsdGeom.Mesh(source_prim)
            source_world = xforms.GetLocalToWorldTransform(source_prim)
            body_world_inverse = xforms.GetLocalToWorldTransform(body).GetInverse()
            body_local_points = []
            reconstruction_error = 0.0
            body_world = xforms.GetLocalToWorldTransform(body)
            for point in (source_mesh.GetPointsAttr().Get() or []):
                world = source_world.Transform(Gf.Vec3d(float(point[0]), float(point[1]), float(point[2])))
                local = body_world_inverse.Transform(world)
                reconstruction_error = max(reconstruction_error, (body_world.Transform(local) - world).GetLength())
                body_local_points.append(Gf.Vec3f(local))
            if reconstruction_error > 1.0e-6:
                raise RuntimeError(f"body-local round trip failed: {source_prim.GetPath()} error={reconstruction_error}")
            counts = list(source_mesh.GetFaceVertexCountsAttr().Get() or [])
            indices = list(source_mesh.GetFaceVertexIndicesAttr().Get() or [])
            if route_a_mesh_ok:
                clone = source_mesh
                clone_path = source_prim.GetPath()
            else:
                clone_path = body.GetPath().AppendChild(f"__GuiDiagnosticMesh_{index}")
                clone = UsdGeom.Mesh.Define(stage, clone_path)
                clone.CreatePointsAttr(body_local_points)
                clone.CreateFaceVertexCountsAttr(counts)
                clone.CreateFaceVertexIndicesAttr(indices)
                clone.CreateOrientationAttr(UsdGeom.Tokens.rightHanded)
                clone.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
                clone.CreateDoubleSidedAttr(True)
                clone.CreateVisibilityAttr(UsdGeom.Tokens.inherited)
            clone.CreateDisplayColorPrimvar(UsdGeom.Tokens.constant).Set([Gf.Vec3f(0.12, 0.68, 0.92)])
            clone.CreateDisplayOpacityPrimvar(UsdGeom.Tokens.constant).Set([1.0])
            UsdShade.MaterialBindingAPI.Apply(clone.GetPrim()).Bind(material)
            direct_targets = [
                str(path) for path in clone.GetPrim().GetRelationship("material:binding").GetTargets()
            ]
            if direct_targets != [str(material.GetPath())]:
                raise RuntimeError(f"clone material binding failed: {clone_path} -> {direct_targets}")
            clone_prims.append(clone.GetPrim())
            clone_specs.append(
                {
                    "source_mesh": str(source_prim.GetPath()),
                    "presentation_mode": "route_a_direct_mesh" if route_a_mesh_ok else "route_b_body_local_clone",
                    "clone_mesh": str(clone_path),
                    "rigid_body_parent": str(body.GetPath()),
                    "points": len(body_local_points),
                    "triangles": sum(max(0, int(count) - 2) for count in counts),
                    "direct_material_binding_targets": direct_targets,
                    "double_sided": True,
                    "visibility": "inherited",
                    "initial_world_roundtrip_max_error_m": reconstruction_error,
                }
            )

        key_light = UsdLux.DistantLight.Define(stage, "/__PhysXGuiDiagnostic/KeyLight")
        key_light.CreateIntensityAttr(3000.0)
        fill_light = UsdLux.SphereLight.Define(stage, "/__PhysXGuiDiagnostic/FillLight")
        fill_light.CreateIntensityAttr(30000.0)
        fill_light.CreateRadiusAttr(0.5)
        UsdGeom.Xformable(fill_light).AddTranslateOp().Set(Gf.Vec3d(2.0, -2.0, 3.0))

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
        report["selected_visual_route"] = "A_DIRECT_IMPORT" if route_a_mesh_ok else "B_RELATIONSHIP_LINKED_CLONE"
        stage.SetEditTarget(original_target)
        for _ in range(3):
            app.update()

        viewport = get_active_viewport()
        clone_paths = [str(prim.GetPath()) for prim in clone_prims]
        if viewport is None or not frame_viewport_prims(viewport, prims=clone_paths):
            raise RuntimeError("failed to frame GUI diagnostic laptop meshes")
        context.get_selection().set_selected_prim_paths([str(revolute[0].GetPath())], True)

        SimulationManager.setup_simulation(dt=1.0 / 60.0, device="cuda:0")
        SimulationManager.initialize_physics()
        first_step = SimulationManager.get_num_physics_steps()
        SimulationManager.step(steps=1, update_fabric=True)
        app.update()
        if SimulationManager.get_num_physics_steps() <= first_step:
            raise RuntimeError("PhysicsScene did not advance")
        view = SimulationManager.get_physics_simulation_view()
        articulation = view.create_articulation_view([str(articulations[0].GetPath())])
        if articulation.count != 1 or articulation.max_dofs != 1:
            raise RuntimeError(f"articulation count/dof={articulation.count}/{articulation.max_dofs}")
        meta = articulation.get_metatype(0)
        dof_name = meta.dof_names[0]
        dof_index = meta.dof_indices[dof_name]
        link_names = list(meta.link_names)
        link_indices = {name: int(meta.link_indices[name]) for name in link_names}
        limits = nested_values(articulation.get_dof_limits())[0][dof_index]
        lower, upper = float(limits[0]), float(limits[1])
        if not (lower < min(PRETEST_TARGETS) and max(PRETEST_TARGETS) < upper):
            raise RuntimeError(f"pretest target outside limits {lower, upper}")
        for spec in clone_specs:
            body_name = Path(spec["rigid_body_parent"]).name
            if body_name not in link_indices:
                raise RuntimeError(f"rigid body {body_name} absent from articulation links {link_names}")
            spec["link_name"] = body_name
            spec["link_index"] = link_indices[body_name]

        report["preflight"] = {
            "variant": variant.GetVariantSelection() if variant.IsValid() else None,
            "revolute_joint": str(revolute[0].GetPath()),
            "articulation_root": str(articulations[0].GetPath()),
            "rigid_body_count": len(rigid),
            "collider_count": len(colliders),
            "dof_name": dof_name,
            "dof_index": dof_index,
            "joint_limits_rad": [lower, upper],
            "runtime_physics_scene": scene.path,
            "clone_meshes": clone_specs,
            "session_deinstanced_rigid_bodies": deinstanced_rigid_bodies,
            "source_instance_proxies_modified": False,
            "clone_xforms_before_simulation": clone_xforms_before,
            "clone_time_samples_before_simulation": clone_time_samples_before,
            "clone_xform_authoring_after_start": False,
            "controlled_material_settings": {
                "mass_kg": 1.0,
                "diagonal_inertia_kg_m2": [0.1, 0.1, 0.1],
                "principal_axes": [1.0, 0.0, 0.0, 0.0],
                "source": "session-layer controlled experimental setting",
            },
        }

        def command_target(phase, target, steps, destination, wall_delay=0.0):
            current = articulation.get_dof_position_targets()
            values = nested_values(current)
            values[0][dof_index] = target
            targets = wp.array(values, dtype=wp.float32, device=current.device)
            articulation.set_dof_position_targets(
                targets, wp.array([0], dtype=wp.uint32, device=targets.device)
            )
            readback = float(nested_values(articulation.get_dof_position_targets())[0][dof_index])
            if abs(readback - target) > 1.0e-5:
                raise RuntimeError(f"target readback mismatch {readback} != {target}")
            for local_step in range(steps):
                before = SimulationManager.get_num_physics_steps()
                SimulationManager.step(steps=1, update_fabric=True)
                app.update()
                after = SimulationManager.get_num_physics_steps()
                positions = articulation.get_dof_positions()
                velocities = articulation.get_dof_velocities()
                links = articulation.get_link_transforms()
                if after <= before or not all(
                    finite_array(array) for array in (positions, velocities, links)
                ):
                    raise RuntimeError("non-finite state or physics step did not advance")
                link_values = nested_values(links)[0]
                clone_world = {
                    spec["clone_mesh"]: transform7_matrix(link_values[spec["link_index"]], Gf)
                    for spec in clone_specs
                }
                destination.append(
                    {
                        "phase": phase,
                        "wall_monotonic_s": time.monotonic(),
                        "requested_target_rad": target,
                        "target_readback_rad": readback,
                        "local_step": local_step,
                        "manager_steps": [before, after],
                        "position_rad": float(nested_values(positions)[0][dof_index]),
                        "velocity_rad_s": float(nested_values(velocities)[0][dof_index]),
                        "rigid_body_link_transforms_xyzw": link_values,
                        "clone_world_transforms_from_physics_body": clone_world,
                        "clone_world_transform_source": (
                            "tensor rigid-body transform; clone local xform is unauthored identity"
                        ),
                    }
                )
                if wall_delay:
                    time.sleep(wall_delay)

        for target in PRETEST_TARGETS:
            command_target(
                "pretest_closed_mid_open_closed", target, STEPS_PER_PRETEST_TARGET, report["pretest"]["records"]
            )
        pretest_positions = [record["position_rad"] for record in report["pretest"]["records"]]
        clone_xforms_after_pretest = authored_clone_xforms(clone_prims)
        clone_time_samples_after_pretest = clone_time_samples(clone_prims)
        report["pretest"]["checks"] = {
            "finite": True,
            "record_count": len(report["pretest"]["records"]),
            "physics_step_advanced": True,
            "measured_position_span_rad": max(pretest_positions) - min(pretest_positions),
            "clone_xforms_after_pretest": clone_xforms_after_pretest,
            "clone_xform_authoring_after_start": clone_xforms_after_pretest != clone_xforms_before,
            "clone_time_sample_authoring_after_start": clone_time_samples_after_pretest - clone_time_samples_before,
            "all_positions_inside_joint_limits": min(pretest_positions) >= lower and max(pretest_positions) <= upper,
        }
        first_links = report["pretest"]["records"][0]["rigid_body_link_transforms_xyzw"]
        body_deltas = {}
        for name, index in link_indices.items():
            deltas = [pose_delta(first_links[index], row["rigid_body_link_transforms_xyzw"][index]) for row in report["pretest"]["records"]]
            body_deltas[name] = {"max_translation_m": max(x[0] for x in deltas), "max_rotation_rad": max(x[1] for x in deltas)}
        report["pretest"]["checks"]["rigid_body_pose_deltas"] = body_deltas
        moving_names = [Path(spec["rigid_body_parent"]).name for spec in clone_specs if str(spec["rigid_body_parent"]) == joint_body1]
        if not moving_names or max(body_deltas[name]["max_rotation_rad"] for name in moving_names) < 0.5:
            raise RuntimeError("body1 tensor transform did not show hinge rotation")
        if report["pretest"]["checks"]["measured_position_span_rad"] < 0.5:
            raise RuntimeError("pretest measured joint response span below 0.5 rad")
        if report["pretest"]["checks"]["clone_xform_authoring_after_start"]:
            raise RuntimeError("clone xform property was authored after simulation start")
        if report["pretest"]["checks"]["clone_time_sample_authoring_after_start"] != 0:
            raise RuntimeError("clone time sample was authored after simulation start")
        if not report["pretest"]["checks"]["all_positions_inside_joint_limits"]:
            raise RuntimeError("pretest position left GT joint limits")
        if max(pretest_positions) - min(pretest_positions) < 0.5:
            raise RuntimeError("measured state did not follow the requested range")
        (args.run_dir / "marker_pretest_pass.json").write_text(
            json.dumps(report["pretest"]["checks"], indent=2) + "\n"
        )

        display = os.environ.get("DISPLAY")
        if not display:
            raise RuntimeError("DISPLAY is empty")
        video_path = args.run_dir / "10163_gt_only_gpu0_gui_physics.mp4"
        ffmpeg_command = [
            "ffmpeg", "-y", "-f", "x11grab", "-draw_mouse", "0", "-framerate", "30",
            "-video_size", args.capture_size, "-i", f"{display}+{args.capture_offset}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            str(video_path),
        ]
        report["capture"]["ffmpeg_command"] = ffmpeg_command
        report["capture"]["video"] = str(video_path)
        ffmpeg_process = subprocess.Popen(
            ffmpeg_command,
            stdout=(args.run_dir / "ffmpeg.stdout.log").open("wb"),
            stderr=(args.run_dir / "ffmpeg.stderr.log").open("wb"),
        )
        for _ in range(90):
            app.update(); time.sleep(1.0 / 30.0)
        if ffmpeg_process.poll() is not None:
            raise RuntimeError(f"ffmpeg exited before capture: {ffmpeg_process.returncode}")
        capture_start_step = SimulationManager.get_num_physics_steps()
        capture_wall_start = time.monotonic()
        for target in (0.0, -0.6, -1.2, -0.6, 0.0):
            command_target(
                "capture_closed_open_closed", target, STEPS_PER_CAPTURE_TARGET,
                report["capture"]["records"], wall_delay=1.0 / 30.0,
            )
        capture_end_step = SimulationManager.get_num_physics_steps()
        for _ in range(60):
            app.update(); time.sleep(1.0 / 30.0)
        ffmpeg_process.send_signal(signal.SIGINT)
        ffmpeg_rc = ffmpeg_process.wait(timeout=20)
        ffmpeg_process = None
        if ffmpeg_rc not in (0, 255) or not video_path.is_file() or video_path.stat().st_size == 0:
            raise RuntimeError(f"ffmpeg capture failed rc={ffmpeg_rc}")
        report["capture"].update(
            {
                "simulation_step_range": [capture_start_step, capture_end_step],
                "record_count": len(report["capture"]["records"]), "capture_wall_start_monotonic": capture_wall_start,
                "video_bytes": video_path.stat().st_size,
                "video_sha256": digest(video_path),
            }
        )
        report["status"] = "AUTOMATED_PRETEST_AND_CAPTURE_COMPLETE_HUMAN_VIEWPORT_REVIEW_REQUIRED"
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
