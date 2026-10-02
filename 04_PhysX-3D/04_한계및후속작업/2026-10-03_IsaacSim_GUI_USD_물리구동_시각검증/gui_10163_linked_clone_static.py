"""GPU-0 static GUI proof for the 10163 linked presentation-clone mapping.

This never enables physics.  It preserves source instance proxies and puts a
normal, direct-bound display clone under each non-instance physics body.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import deque
from pathlib import Path

import carb
import omni.kit.app
import omni.timeline
import omni.usd
from omni.kit.viewport.utility import frame_viewport_prims, get_active_viewport
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade


RUN_DIR = Path(os.environ["PHYSX_GUI_RUN_DIR"])
INPUT_USD = Path(
    "/home/minsujo/Desktop/SH/PHYSx/staging/"
    "gt-only-isaac-control-20261002T072614Z-gt-only-control/"
    "10163/gt_10163/gt_10163.usda"
)
EXPECTED_SHA256 = "72cee88ff5ac563e89c34e4028a9a3fe3d8b839d40f88fed4ef048e3f4fab23b"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def marker(name: str, payload: dict) -> None:
    (RUN_DIR / f"marker_{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"PHYSX_GUI_MARKER_{name.upper()}={json.dumps(payload, ensure_ascii=False, sort_keys=True)}")


def matrix_rows(matrix) -> list[list[float]]:
    return [[float(matrix[row][column]) for column in range(4)] for row in range(4)]


def nearest_rigid_body(prim):
    current = prim.GetParent()
    while current.IsValid():
        if current.HasAPI(UsdPhysics.RigidBodyAPI):
            return current
        current = current.GetParent()
    raise RuntimeError(f"no rigid-body ancestor: {prim.GetPath()}")


def relation_target(joint, name: str):
    targets = joint.GetRelationship(name).GetTargets()
    if len(targets) != 1:
        raise RuntimeError(f"{joint.GetPath()} {name} targets={list(map(str, targets))}")
    return targets[0]


def fixed_path(graph: dict[str, list[str]], start: str, goal: str):
    queue = deque([(start, [start])])
    seen = {start}
    while queue:
        current, path = queue.popleft()
        if current == goal:
            return path
        for adjacent in graph.get(current, []):
            if adjacent not in seen:
                seen.add(adjacent)
                queue.append((adjacent, path + [adjacent]))
    return None


def xform_properties(prim) -> list[str]:
    return [
        name for name in prim.GetPropertyNames()
        if name == "xformOpOrder" or name.startswith("xformOp:")
    ]


settings = carb.settings.get_settings()
marker("app_startup", {"status": "PASS", "scope": "10163 GT-only linked-clone static GUI inspection"})
marker("omni_usd_import", {"status": "PASS", "module": getattr(omni.usd, "__file__", None)})
marker("gui_mode", {"status": "PASS", "headless_setting": settings.get("/app/window/hideUi"), "expected_headless": False})

actual_sha = digest(INPUT_USD)
if actual_sha != EXPECTED_SHA256:
    raise RuntimeError(f"10163 USD SHA256 mismatch: {actual_sha}")
marker("usd_verified", {"status": "PASS", "path": str(INPUT_USD), "bytes": INPUT_USD.stat().st_size, "sha256": actual_sha})

context = omni.usd.get_context()
context.open_stage(str(INPUT_USD))
stage = context.get_stage()
root = stage.GetDefaultPrim()
if not root.IsValid():
    raise RuntimeError("missing default prim")
marker("stage_open", {"status": "PASS", "default_prim": str(root.GetPath())})
variant = root.GetVariantSet("Physics")
variant.SetVariantSelection("physx")
if variant.GetVariantSelection() != "physx":
    raise RuntimeError("failed to select Physics=physx")
marker("physics_variant", {"status": "PASS", "selection": "physx"})

predicate = Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate)
prims = list(Usd.PrimRange(stage.GetPseudoRoot(), predicate))
meshes = [prim for prim in prims if prim.IsA(UsdGeom.Mesh)]
revolute = [prim for prim in prims if prim.IsA(UsdPhysics.RevoluteJoint)]
fixed = [prim for prim in prims if prim.IsA(UsdPhysics.FixedJoint)]
rigid = [prim for prim in prims if prim.HasAPI(UsdPhysics.RigidBodyAPI)]
colliders = [prim for prim in prims if prim.HasAPI(UsdPhysics.CollisionAPI)]
articulation = [prim for prim in prims if prim.HasAPI(UsdPhysics.ArticulationRootAPI)]
if len(meshes) != 2 or len(revolute) != 1 or revolute[0].GetName() != "gt_C_1":
    raise RuntimeError(f"unexpected composed structure: meshes={len(meshes)} revolute={[str(p.GetPath()) for p in revolute]}")

joint = revolute[0]
body0_path = relation_target(joint, "physics:body0")
body1_path = relation_target(joint, "physics:body1")
body0 = stage.GetPrimAtPath(body0_path)
body1 = stage.GetPrimAtPath(body1_path)
if not body0.IsValid() or not body1.IsValid() or body0.IsInstanceProxy() or body1.IsInstanceProxy():
    raise RuntimeError("gt_C_1 body0/body1 must be valid non-instance rigid bodies")

graph: dict[str, list[str]] = {}
for fixed_joint in fixed:
    first = str(relation_target(fixed_joint, "physics:body0"))
    second = str(relation_target(fixed_joint, "physics:body1"))
    graph.setdefault(first, []).append(second)
    graph.setdefault(second, []).append(first)

cache = UsdGeom.XformCache(Usd.TimeCode.Default())
original_target = stage.GetEditTarget()
stage.SetEditTarget(Usd.EditTarget(stage.GetSessionLayer()))
material = UsdShade.Material.Define(stage, "/__PhysXLinkedDiagnostic/Material")
shader = UsdShade.Shader.Define(stage, "/__PhysXLinkedDiagnostic/Material/PreviewSurface")
shader.CreateIdAttr("UsdPreviewSurface")
shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.12, 0.68, 0.92))
shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)
shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

clone_rows = []
clone_paths = []
for index, source in enumerate(meshes):
    nearest = nearest_rigid_body(source)
    nearest_path = str(nearest.GetPath())
    path_to_body0 = fixed_path(graph, nearest_path, str(body0_path))
    path_to_body1 = fixed_path(graph, nearest_path, str(body1_path))
    if path_to_body0 is not None and path_to_body1 is None:
        side, target_body, fixed_chain = "body0", body0, path_to_body0
    elif path_to_body1 is not None and path_to_body0 is None:
        side, target_body, fixed_chain = "body1", body1, path_to_body1
    elif nearest_path == str(body0_path):
        side, target_body, fixed_chain = "body0", body0, [nearest_path]
    elif nearest_path == str(body1_path):
        side, target_body, fixed_chain = "body1", body1, [nearest_path]
    else:
        raise RuntimeError(f"ambiguous link mapping for {source.GetPath()}: nearest={nearest_path}")
    if target_body.IsInstance() or target_body.IsInstanceProxy():
        raise RuntimeError(f"target body cannot own a clone: {target_body.GetPath()}")

    source_mesh = UsdGeom.Mesh(source)
    source_world = cache.GetLocalToWorldTransform(source)
    target_world = cache.GetLocalToWorldTransform(target_body)
    inverse_target_world = target_world.GetInverse()
    local_points = []
    max_world_error = 0.0
    for point in source_mesh.GetPointsAttr().Get() or []:
        source_point_world = source_world.Transform(Gf.Vec3d(float(point[0]), float(point[1]), float(point[2])))
        point_local = inverse_target_world.Transform(source_point_world)
        reconstructed_world = target_world.Transform(point_local)
        max_world_error = max(max_world_error, (reconstructed_world - source_point_world).GetLength())
        local_points.append(Gf.Vec3f(point_local))
    clone_path = target_body.GetPath().AppendChild(f"__GuiLinkedClone_{index}")
    clone = UsdGeom.Mesh.Define(stage, clone_path)
    clone.CreatePointsAttr(local_points)
    clone.CreateFaceVertexCountsAttr(list(source_mesh.GetFaceVertexCountsAttr().Get() or []))
    clone.CreateFaceVertexIndicesAttr(list(source_mesh.GetFaceVertexIndicesAttr().Get() or []))
    clone.CreateOrientationAttr(UsdGeom.Tokens.rightHanded)
    clone.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    clone.CreateDoubleSidedAttr(True)
    clone.CreateVisibilityAttr(UsdGeom.Tokens.inherited)
    clone.CreateDisplayColorPrimvar(UsdGeom.Tokens.constant).Set([Gf.Vec3f(0.12, 0.68, 0.92)])
    clone.CreateDisplayOpacityPrimvar(UsdGeom.Tokens.constant).Set([1.0])
    UsdShade.MaterialBindingAPI.Apply(clone.GetPrim()).Bind(material)
    targets = [str(target) for target in clone.GetPrim().GetRelationship("material:binding").GetTargets()]
    if targets != [str(material.GetPath())] or xform_properties(clone.GetPrim()) or max_world_error > 1.0e-6:
        raise RuntimeError(f"linked clone invariant failed: {clone_path}")
    clone_paths.append(str(clone_path))
    clone_rows.append({
        "source_mesh": str(source.GetPath()),
        "source_instance_proxy": bool(source.IsInstanceProxy()),
        "nearest_rigid_body": nearest_path,
        "fixed_joint_chain_to_target_body": fixed_chain,
        "joint_side": side,
        "target_rigid_body_parent": str(target_body.GetPath()),
        "clone_mesh": str(clone_path),
        "source_world_transform": matrix_rows(source_world),
        "target_body_world_transform": matrix_rows(target_world),
        "clone_local_xform_properties": xform_properties(clone.GetPrim()),
        "local_points_count": len(local_points),
        "initial_world_reconstruction_max_error_m": max_world_error,
        "direct_material_binding_targets": targets,
    })

cube = UsdGeom.Cube.Define(stage, "/__PhysXLinkedDiagnostic/ReferenceCube")
cube.CreateSizeAttr(0.35)
cube.AddTranslateOp().Set(Gf.Vec3d(1.8, 0.2, 0.15))
cube.CreateDisplayColorPrimvar(UsdGeom.Tokens.constant).Set([Gf.Vec3f(1.0, 0.3, 0.08)])
UsdLux.DistantLight.Define(stage, "/__PhysXLinkedDiagnostic/KeyLight").CreateIntensityAttr(3000.0)
fill = UsdLux.SphereLight.Define(stage, "/__PhysXLinkedDiagnostic/FillLight")
fill.CreateIntensityAttr(30000.0)
fill.CreateRadiusAttr(0.5)
UsdGeom.Xformable(fill).AddTranslateOp().Set(Gf.Vec3d(2.0, -2.0, 3.0))
stage.SetEditTarget(original_target)

marker("joint_structure", {
    "status": "PASS", "path": str(joint.GetPath()), "body0": str(body0_path), "body1": str(body1_path),
    "axis": str(UsdPhysics.RevoluteJoint(joint).GetAxisAttr().Get()),
    "lower_limit_degrees": float(UsdPhysics.RevoluteJoint(joint).GetLowerLimitAttr().Get()),
    "upper_limit_degrees": float(UsdPhysics.RevoluteJoint(joint).GetUpperLimitAttr().Get()),
})
marker("schema_counts", {"status": "PASS", "revolute_joint_count": len(revolute), "fixed_joint_count": len(fixed), "articulation_root_count": len(articulation), "rigid_body_count": len(rigid), "collider_count_including_instance_proxies": len(colliders)})
marker("mesh_composition_audit", {"status": "PASS", "source_mesh_count": len(meshes), "source_meshes_are_instance_proxies": [bool(mesh.IsInstanceProxy()) for mesh in meshes], "source_usd_modified": False, "source_instance_deinstanced": False})
marker("material_diagnostic", {"status": "PASS", "mode": "linked_clone", "session_layer_only": True, "source_usd_modified": False, "clone_mappings": clone_rows, "reference_cube": str(cube.GetPath())})
marker("viewport_mesh_visibility", {"status": "PASS", "setting_path": "/persistent/app/viewport/Viewport/Viewport0/scene/meshes/visible", "visible": settings.get("/persistent/app/viewport/Viewport/Viewport0/scene/meshes/visible")})
viewport = get_active_viewport()
if viewport is None or not frame_viewport_prims(viewport, prims=clone_paths + [str(cube.GetPath())]):
    raise RuntimeError("failed to frame linked clones")
context.get_selection().set_selected_prim_paths([str(joint.GetPath())], True)
marker("viewport_framing", {"status": "PASS", "mesh_paths": clone_paths, "joint_selected": str(joint.GetPath()), "asset_transforms_changed": False})
physics_exts = {name: False for name in ("omni.physx", "omni.physics.tensors", "isaacsim.core.simulation_manager")}
for name in physics_exts:
    physics_exts[name] = bool(omni.kit.app.get_app().get_extension_manager().is_extension_enabled(name))
if any(physics_exts.values()) or omni.timeline.get_timeline_interface().is_playing():
    raise RuntimeError(f"static physics guard failed: {physics_exts}")
marker("physics_steps", {"status": "PASS", "simulation_steps_requested": 0, "physics_scene_created": False, "simulation_manager_called": False, "tensor_control_called": False, "physics_extensions_enabled": physics_exts})
marker("summary", {"status": "AUTOMATION_MARKERS_PASS_HUMAN_LINKED_CLONE_GUI_CHECK_REQUIRED", "scope": "GPU 0 static linked clones under gt_C_1 body0/body1; not AI prediction", "human_verified": False, "physics_steps": 0, "clone_xform_authoring_during_run": False})
